"""Merge skill: teacher dedup tool for near-duplicate signatures.

merge --into A --from B re-points B's times_seen onto A and removes B
(with a merged-from note in A). Reduces false no-match results caused
by near-duplicate signatures.
"""

from datetime import timezone

from .. import store


class MergeError(Exception):
    """Raised when a merge operation is invalid."""


def _find_case(cases, case_id):
    for c in cases:
        if c["id"] == case_id:
            return c
    return None


def merge(case_store, into_id, from_id):
    """Merge case from_id into into_id.

    - Combines times_seen counts
    - Keeps the newer last_seen
    - Adds merged_from field to the target
    - Removes the source case

    Returns the updated target case dict.
    Raises MergeError on invalid operation.
    """
    if into_id == from_id:
        raise MergeError("cannot merge the same case into itself")

    cases = case_store.load()

    target = _find_case(cases, into_id)
    source = _find_case(cases, from_id)

    if target is None:
        raise MergeError(f"target case #{into_id} not found")
    if source is None:
        raise MergeError(f"source case #{from_id} not found")

    target["times_seen"] += source["times_seen"]

    from ..store import parse_timestamp

    target_stamp = parse_timestamp(target["last_seen"])
    source_stamp = parse_timestamp(source["last_seen"])
    if source_stamp > target_stamp:
        target["last_seen"] = source["last_seen"]

    target["merged_from"] = from_id

    remaining = [c for c in cases if c["id"] != from_id]
    case_store.save(remaining)

    return target


def format_merge(result):
    """Render the result of a merge operation."""
    return (
        f"merged case #{result['id']} "
        f"times_seen={result['times_seen']} "
        f"(absorbed case from merged_from={result['merged_from']})"
    )
