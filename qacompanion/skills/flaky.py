"""S8 flaky skill: count pass-after-fail, surface chronic flakes.

A zero-exit `qa run` counts one PASS for every existing case whose
signature was keyed by the same wrapped command (symmetric with S7's
failure capture). Flake-rate per case = passes / (passes + times_seen);
the denominator is sound because D-0007 Amendment 1 keys one stable
signature per failing test. Chronic flakes (>50% pass rate) are surfaced
separately from ordinary history - not every red is broken.

Storage: a skill-owned sidecar `flakes.jsonl` next to the case store
(NOT new fields in cases.jsonl - spec.md is frozen until v2). Entries:
{"signature", "times_passed", "last_pass"}, strict-validated, atomically
saved. Passes never create cases; orphaned entries (their case gone from
cases.jsonl) are retained on disk but never displayed.
"""

import json
import os
import tempfile
from pathlib import Path

from .. import signatures, store

SIDECAR_NAME = "flakes.jsonl"
CHRONIC_THRESHOLD = 0.5

_FIELD_TYPES = {
    "signature": str,
    "times_passed": int,
    "last_pass": str,
}


def default_path():
    """Sidecar lives beside the case store (QA_CASES_FILE routes both)."""
    return store.default_path().parent / SIDECAR_NAME


def _validate_entry(entry, line_number):
    if not isinstance(entry, dict):
        raise ValueError(f"line {line_number}: expected a JSON object")
    missing = sorted(field for field in _FIELD_TYPES if field not in entry)
    if missing:
        raise ValueError(
            f"line {line_number}: missing field(s): {', '.join(missing)}"
        )
    for field, expected in _FIELD_TYPES.items():
        value = entry[field]
        if isinstance(value, bool) or not isinstance(value, expected):
            raise ValueError(
                f"line {line_number}: field '{field}' must be {expected.__name__}"
            )
    if entry["times_passed"] < 1:
        raise ValueError(f"line {line_number}: times_passed must be >= 1")
    try:
        store.parse_timestamp(entry["last_pass"])
    except ValueError as exc:
        raise ValueError(
            f"line {line_number}: last_pass is not ISO-8601 ({exc})"
        ) from exc


def command_test_part(argv_text):
    """Normalized command prefix exactly as parse_failure keyed it."""
    probe = signatures.canonical(f"{argv_text} :: pass-probe")
    return probe.partition(signatures.SEPARATOR)[0]


def match_cases(cases, argv_text):
    """Existing cases whose signature came from this command."""
    cmd_part = command_test_part(argv_text)
    return [
        case
        for case in cases
        if case["signature"].partition(signatures.SEPARATOR)[0] == cmd_part
    ]


class FlakeStore:
    """Reader/writer for the flakes.jsonl sidecar."""

    def __init__(self, path=None):
        self.path = Path(default_path() if path is None else path)

    def load(self):
        """Return all entries; abort with ValueError naming the line."""
        if not self.path.exists():
            return []
        text = self.path.read_text(encoding="utf-8-sig")
        entries = []
        for line_number, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"line {line_number}: invalid JSON ({exc.msg})"
                ) from exc
            _validate_entry(entry, line_number)
            entries.append(entry)
        return entries

    def save(self, entries):
        """Atomically replace the sidecar (temp copy in the same directory)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(
            json.dumps(entry, ensure_ascii=False) + "\n"
            for entry in sorted(entries, key=lambda item: item["signature"])
        )
        handle_fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".flakes-", suffix=".tmp"
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(handle_fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
            os.replace(tmp_path, self.path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    def observe_command_pass(self, argv_text, now=None):
        """Count one pass against each existing case of this command.

        Returns updated {"id", "signature", "times_passed"} rows; empty
        when the command has no recorded failures (a pass never creates
        a case).
        """
        cases = store.CaseStore().load()
        matched = match_cases(cases, argv_text)
        if not matched:
            return []
        entries = self.load()
        by_signature = {entry["signature"]: entry for entry in entries}
        stamp = store.utc_now_stamp(now)
        updated = []
        for case in matched:
            entry = by_signature.get(case["signature"])
            if entry is None:
                entry = {
                    "signature": case["signature"],
                    "times_passed": 0,
                    "last_pass": stamp,
                }
                entries.append(entry)
                by_signature[entry["signature"]] = entry
            entry["times_passed"] += 1
            entry["last_pass"] = stamp
            updated.append(
                {
                    "id": case["id"],
                    "signature": case["signature"],
                    "times_passed": entry["times_passed"],
                }
            )
        self.save(entries)
        return updated


def pass_rate(case, times_passed):
    """passes / (passes + fails); times_seen >= 1 so denominator > 0."""
    return times_passed / (times_passed + case["times_seen"])


def is_chronic(case, times_passed):
    """Strictly above CHRONIC_THRESHOLD (ROADMAP: '>50% pass rate')."""
    return pass_rate(case, times_passed) > CHRONIC_THRESHOLD


def attach_stats(cases, entries):
    """Join sidecar entries onto live cases; orphans stay invisible.

    Returns [(case, times_passed)] ordered by case id.
    """
    by_signature = {entry["signature"]: entry for entry in entries}
    return [
        (case, by_signature[case["signature"]]["times_passed"])
        for case in sorted(cases, key=lambda item: item["id"])
        if case["signature"] in by_signature
    ]


def split_sections(joined):
    chronic = [
        (case, passes) for case, passes in joined if is_chronic(case, passes)
    ]
    history = [
        (case, passes) for case, passes in joined if not is_chronic(case, passes)
    ]
    return chronic, history


def format_flakes(cases, entries):
    """Deterministic two-section rendering; empty sections print `none`."""
    chronic, history = split_sections(attach_stats(cases, entries))

    def _render(title, rows):
        lines = [title]
        if rows:
            lines.extend(
                f"case #{case['id']} times_seen={case['times_seen']} "
                f"passes={passes} "
                f"rate={100 * pass_rate(case, passes):.1f}% "
                f"sig: {case['signature']}"
                for case, passes in rows
            )
        else:
            lines.append("none")
        return lines

    return "\n".join(
        _render("chronic (>50% pass rate):", chronic)
        + _render("flaky history (<=50% pass rate):", history)
    )


def has_entries(path=None):
    """True when any pass has ever been observed (gates the report flag)."""
    return bool(FlakeStore(path).load())
