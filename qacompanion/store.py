"""Case store: strict-loading JSONL persistence for qacompanion.

Storage format (frozen, docs/spec.md): one JSON object per line in
`cases.jsonl`. Load aborts with ValueError naming the offending line number
on any malformed input; saves are atomic (temp copy + os.replace).
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = "cases.jsonl"
ENV_OVERRIDE = "QA_CASES_FILE"

_FIELD_TYPES = {
    "id": int,
    "signature": str,
    "error_excerpt": str,
    "diagnosis": str,
    "times_seen": int,
    "last_seen": str,
    "confirmed_by": str,
}


def default_path():
    """Env override (QA_CASES_FILE) > repo-root default."""
    return Path(os.environ.get(ENV_OVERRIDE) or DEFAULT_PATH)


def parse_timestamp(value):
    """Parse an ISO-8601 stamp from the store ('Z' suffix included)."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _validate_case(case, line_number):
    if not isinstance(case, dict):
        raise ValueError(f"line {line_number}: expected a JSON object")
    missing = sorted(field for field in _FIELD_TYPES if field not in case)
    if missing:
        raise ValueError(
            f"line {line_number}: missing field(s): {', '.join(missing)}"
        )
    for field, expected in _FIELD_TYPES.items():
        value = case[field]
        if isinstance(value, bool) or not isinstance(value, expected):
            raise ValueError(
                f"line {line_number}: field '{field}' must be {expected.__name__}"
            )
    if case["id"] < 1:
        raise ValueError(f"line {line_number}: id must be >= 1")
    if case["times_seen"] < 1:
        raise ValueError(f"line {line_number}: times_seen must be >= 1")
    try:
        parse_timestamp(case["last_seen"])
    except ValueError as exc:
        raise ValueError(
            f"line {line_number}: last_seen is not ISO-8601 ({exc})"
        ) from exc


def utc_now_stamp(now=None):
    moment = now or datetime.now(timezone.utc)
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


class CaseStore:
    """Reader/writer for the frozen cases.jsonl format."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_path()

    def load(self):
        """Return all cases ordered by strictly increasing id.

        Raises ValueError naming the first malformed line; nothing partial
        ever escapes a failed load.
        """
        if not self.path.exists():
            return []
        # utf-8-sig strips a BOM prefix (the BOM-breaks-config lesson);
        # splitlines treats CRLF identically to LF.
        text = self.path.read_text(encoding="utf-8-sig")
        cases = []
        previous_id = 0
        for line_number, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                case = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"line {line_number}: invalid JSON ({exc.msg})"
                ) from exc
            _validate_case(case, line_number)
            if case["id"] <= previous_id:
                raise ValueError(
                    f"line {line_number}: id {case['id']} does not increase "
                    f"(previous id {previous_id})"
                )
            previous_id = case["id"]
            cases.append(case)
        return cases

    def save(self, cases):
        """Atomically replace the store (temp copy in the same directory)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(
            json.dumps(case, ensure_ascii=False) + "\n"
            for case in sorted(cases, key=lambda item: item["id"])
        )
        handle_fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".cases-", suffix=".tmp"
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(handle_fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
            os.replace(tmp_path, self.path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    def record(self, signature, error_excerpt, diagnosis, by=None, now=None):
        """Insert a case or bump the one whose signature matches exactly.

        Returns (case, created).
        """
        cases = self.load()
        stamp = utc_now_stamp(now)
        for case in cases:
            if case["signature"] == signature:
                case["times_seen"] += 1
                case["last_seen"] = stamp
                case["error_excerpt"] = error_excerpt
                case["diagnosis"] = diagnosis
                if by:
                    case["confirmed_by"] = by
                created = False
                break
        else:
            next_id = cases[-1]["id"] + 1 if cases else 1
            case = {
                "id": next_id,
                "signature": signature,
                "error_excerpt": error_excerpt,
                "diagnosis": diagnosis,
                "times_seen": 1,
                "last_seen": stamp,
                "confirmed_by": by or "unknown",
            }
            cases.append(case)
            created = True
        self.save(cases)
        return case, created
