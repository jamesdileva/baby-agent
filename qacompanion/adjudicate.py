"""S24 adjudication loop: walk proposed rules with parents, decide fate.

`qa review-rules` walks the queue produced by `qa detect`: approve → rule
installed to skills registry; correct → amended then installed; reject →
recorded so the same candidate shape is not re-proposed (the tool learns
what NOT to propose). Skipped candidates stay in the queue for next time.

Storage:
- rules_proposed.jsonl (S23 sidecar, read-only during adjudication)
- rules_rejected.jsonl (sidecar, append-only rejection memory)
- skills/taught.json (skill registry, appended on approve/correct)

Exit contract:
0 session completed, 1 operational error, 2 environment error.
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import detect
from .teach import teach_rule, render_teach, RegistryError, DEFAULT_PACK


REJECTED_SIDECAR = "rules_rejected.jsonl"

_REJECTED_FIELDS = {"type", "supporting_cases", "rejected_by", "rejected_at", "reason"}


class AdjudicateError(Exception):
    """Operational failure in the adjudication session."""


def default_rejected_path():
    """Rejected memory lives beside the case store."""
    from . import store
    return store.default_path().parent / REJECTED_SIDECAR


def _validate_rejected_entry(entry, line_number):
    if not isinstance(entry, dict):
        raise ValueError(f"line {line_number}: expected a JSON object")
    missing = sorted(f for f in _REJECTED_FIELDS if f not in entry)
    if missing:
        raise ValueError(
            f"line {line_number}: missing field(s): {', '.join(missing)}"
        )
    if not isinstance(entry["type"], str):
        raise ValueError(f"line {line_number}: 'type' must be a string")
    if not isinstance(entry["supporting_cases"], list):
        raise ValueError(f"line {line_number}: 'supporting_cases' must be a list")
    if not isinstance(entry["reason"], str):
        raise ValueError(f"line {line_number}: 'reason' must be a string")


def load_rejected(path=None):
    """Load rejection memory. Returns list of dicts."""
    path = path or default_rejected_path()
    if not path.exists():
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line:
                continue
            entry = json.loads(line)
            _validate_rejected_entry(entry, lineno)
            entries.append(entry)
    return entries


def save_rejected(entries, path=None):
    """Atomically save rejection memory."""
    path = path or default_rejected_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def _candidate_key(candidate):
    """Unique key for a candidate: (type, sorted supporting_cases)."""
    return (candidate["type"], tuple(sorted(candidate["supporting_cases"])))


def is_rejected(candidate, rejected_list):
    """Check if a candidate's shape has been rejected before."""
    key = _candidate_key(candidate)
    for entry in rejected_list:
        entry_key = (entry["type"], tuple(sorted(entry["supporting_cases"])))
        if entry_key == key:
            return True
    return False


def filter_unrejected(candidates, rejected_list):
    """Return only candidates not previously rejected."""
    return [c for c in candidates if not is_rejected(c, rejected_list)]


def format_candidate(candidate, index, total):
    """Render a proposed rule for interactive display."""
    lines = [
        f"--- Rule #{candidate['id']} ({index}/{total}) ---",
        f"  type: {candidate['type']}",
        f"  confidence: {candidate['confidence']:.1%}",
        f"  cases: {candidate['supporting_cases']}",
        f"  description: {candidate['description']}",
        f"  proposed rule: {candidate['proposed_rule'][:120]}",
    ]
    return "\n".join(lines)


def format_summary(approved, corrected, rejected, skipped, remaining):
    """Render the session summary."""
    parts = [f"adjudication session complete: {approved + corrected + rejected + skipped} candidate(s) processed"]
    if approved:
        parts.append(f"  approved (installed): {approved}")
    if corrected:
        parts.append(f"  corrected (installed): {corrected}")
    if rejected:
        parts.append(f"  rejected (suppressed): {rejected}")
    if skipped:
        parts.append(f"  skipped (kept in queue): {skipped}")
    if remaining:
        parts.append(f"  remaining in queue: {remaining}")
    return "\n".join(parts)


def run_session(proposed_path=None, rejected_path=None, pack_path=None,
                by=None, limit=None, stdin=None):
    """Run an interactive adjudication session.

    Args:
        proposed_path: path to rules_proposed.jsonl (default: detect sidecar).
        rejected_path: path to rules_rejected.jsonl (default: beside store).
        pack_path: path to skill pack for install (default: skills/taught.json).
        by: name of the adjudicator.
        limit: max candidates to process (None = all pending).
        stdin: file-like for input (defaults to sys.stdin).

    Returns:
        dict with counts: approved, corrected, rejected, skipped, remaining.
    """
    if stdin is None:
        stdin = sys.stdin

    proposed_path = proposed_path or detect.default_path()
    rejected_path = rejected_path or default_rejected_path()
    pack_path = pack_path or DEFAULT_PACK

    candidates = detect.load_proposed(proposed_path)
    rejected = load_rejected(rejected_path)
    pending = filter_unrejected(candidates, rejected)

    if limit is not None:
        pending = pending[:limit]

    if not pending:
        return {
            "approved": 0, "corrected": 0, "rejected": 0,
            "skipped": 0, "remaining": 0,
        }

    approved = 0
    corrected = 0
    rejected_count = 0
    skipped = 0
    total = len(pending)
    adjudicated_ids = set()
    new_rejections = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    for i, candidate in enumerate(pending, 1):
        print(format_candidate(candidate, i, total))
        print()
        print("Options: [a]pprove, [c]orrect, [r]eject, [s]kip, [q]uit")
        print("> ", end="", flush=True)

        choice = stdin.readline().strip().lower()

        if choice == "a":
            # Approve: install proposed rule as-is
            # User must provide pattern, classification, diagnosis_hint
            print("  Pattern (regex on error text): ", end="", flush=True)
            pattern = stdin.readline().strip()
            print("  Classification: ", end="", flush=True)
            classification = stdin.readline().strip()
            print("  Diagnosis hint: ", end="", flush=True)
            diag_hint = stdin.readline().strip()
            if pattern and classification and diag_hint:
                rule_dict = {
                    "pattern": pattern,
                    "classification": classification,
                    "diagnosis_hint": diag_hint,
                }
                try:
                    pack = teach_rule(rule_dict, pack_path)
                    approved += 1
                    adjudicated_ids.add(candidate["id"])
                    print(f"  -> approved and installed rule #{candidate['id']}\n")
                except (RegistryError, OSError) as exc:
                    print(f"  -> install failed: {exc}\n")
            else:
                print("  -> skipped (incomplete fields)\n")

        elif choice == "c":
            # Correct: user provides all fields
            print("  Pattern (regex on error text): ", end="", flush=True)
            pattern = stdin.readline().strip()
            print("  Classification: ", end="", flush=True)
            classification = stdin.readline().strip()
            print("  Diagnosis hint: ", end="", flush=True)
            diag_hint = stdin.readline().strip()
            if pattern and classification and diag_hint:
                rule_dict = {
                    "pattern": pattern,
                    "classification": classification,
                    "diagnosis_hint": diag_hint,
                }
                try:
                    pack = teach_rule(rule_dict, pack_path)
                    corrected += 1
                    adjudicated_ids.add(candidate["id"])
                    print(f"  -> corrected and installed rule #{candidate['id']}\n")
                except (RegistryError, OSError) as exc:
                    print(f"  -> install failed: {exc}\n")
            else:
                print("  -> skipped (incomplete fields)\n")

        elif choice == "r":
            # Reject: record in rejection memory
            print("  Reason: ", end="", flush=True)
            reason = stdin.readline().strip()
            if not reason:
                reason = "rejected during adjudication"
            rejection = {
                "type": candidate["type"],
                "supporting_cases": candidate["supporting_cases"],
                "rejected_by": by,
                "rejected_at": now,
                "reason": reason,
            }
            new_rejections.append(rejection)
            rejected_count += 1
            adjudicated_ids.add(candidate["id"])
            print(f"  -> rejected rule #{candidate['id']} (suppressed)\n")

        elif choice == "s":
            skipped += 1
            print(f"  -> skipped (kept in queue)\n")

        elif choice == "q":
            print("  -> quitting session\n")
            break

        else:
            print(f"  -> skipped (unrecognized: '{choice}')\n")

    # Persist new rejections
    if new_rejections:
        existing = load_rejected(rejected_path)
        save_rejected(existing + new_rejections, rejected_path)

    # Remove adjudicated candidates from proposed queue
    if adjudicated_ids:
        remaining = [c for c in candidates if c["id"] not in adjudicated_ids]
        if remaining:
            detect.save_proposed(remaining, proposed_path)
        else:
            # Remove file if queue is empty
            if proposed_path.exists():
                proposed_path.unlink()

    remaining_queue = len(detect.load_proposed(proposed_path))

    return {
        "approved": approved,
        "corrected": corrected,
        "rejected": rejected_count,
        "skipped": skipped,
        "remaining": remaining_queue,
    }
