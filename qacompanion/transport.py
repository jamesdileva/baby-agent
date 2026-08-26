"""Export/import round-trips for the case base (ROADMAP S5).

Export is an atomic, no-locking copy of the live store; import validates
the whole incoming file first and then atomically replaces the live base,
so corrupt input never touches live data. Duplicate-signature policy is
D-0005 (ratified, human mail #15): reject by default naming every
offending line/signature pair; an explicit --merge folds counts instead.

Signatures pass through verbatim on both paths - canonical() stays a
record/lookup gate - so export -> import -> export is byte-stable.
"""

import json
import os
import tempfile
from pathlib import Path

from . import store


def _atomic_write(path, payload):
    """Temp file inside the destination directory, then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle_fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".qa-", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def export_cases(live_store, out_path):
    """Atomically copy the case base to out_path; returns the case count."""
    cases = live_store.load()
    _atomic_write(Path(out_path), store.serialize(cases))
    return len(cases)


def _signature_lines(in_path):
    """Map signature -> [line numbers]; call only after a strict load."""
    text = Path(in_path).read_text(encoding="utf-8-sig")
    lines = {}
    for line_number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        signature = json.loads(raw)["signature"]
        lines.setdefault(signature, []).append(line_number)
    return lines


def _split_offenders(live_cases, signature_lines):
    intra_file, vs_live = [], []
    for signature, numbers in signature_lines.items():
        if len(numbers) > 1:
            intra_file.extend((number, signature) for number in numbers)
        elif any(case["signature"] == signature for case in live_cases):
            vs_live.append((numbers[0], signature))
    return intra_file, vs_live


def _detail(offenders):
    return "; ".join(
        f"line {number}: {signature}" for number, signature in offenders
    )


def import_cases(live_store, in_path, merge=False):
    """Validate in_path, then atomically replace (or merge into) the base.

    Returns (added, merged, total). Per D-0005: duplicate signatures within
    the file, or against the live store, abort the import by default while
    naming every offending line/signature. With merge=True, duplicates fold
    their times_seen onto the live twin (no stored field is overwritten;
    corrections travel the teacher loop, not import), unseen signatures are
    appended with fresh ids in file order, and a signature matching several
    live cases (AMBIGUOUS state) refuses to pick a merge target.
    Intra-file duplicates abort in both modes.
    """
    in_path = Path(in_path)
    if not in_path.exists():
        raise ValueError(f"import file not found: {in_path}")
    incoming = store.CaseStore(in_path).load()
    live = live_store.load()
    sig_lines = _signature_lines(in_path)
    intra_file, vs_live = _split_offenders(live, sig_lines)
    if intra_file:
        raise ValueError(
            "duplicate signature(s) within import file, aborted: "
            + _detail(intra_file)
        )
    if not merge:
        if vs_live:
            raise ValueError(
                "duplicate signature(s) already in live store, aborted: "
                + _detail(vs_live)
            )
        live_store.save(incoming)
        return len(incoming), 0, len(incoming)

    by_signature = {}
    for case in live:
        by_signature.setdefault(case["signature"], []).append(case)
    ambiguous = [sig for _, sig in vs_live if len(by_signature[sig]) > 1]
    if ambiguous:
        raise ValueError(
            "ambiguous merge target(s) (AMBIGUOUS state), aborted: "
            + "; ".join(ambiguous)
        )

    result = list(live)
    next_id = max((case["id"] for case in live), default=0) + 1
    added = merged = 0
    for case in incoming:
        twins = by_signature.get(case["signature"])
        if twins:
            twins[0]["times_seen"] += case["times_seen"]
            merged += 1
        else:
            result.append(dict(case, id=next_id))
            next_id += 1
            added += 1
    live_store.save(result)
    return added, merged, len(result)
