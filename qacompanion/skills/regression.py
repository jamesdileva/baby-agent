"""S10 regression skill: a signature that returns after clean passes.

Pinned rule (D-0012): a live case is a REGRESSION iff

1. its sidecar entry records >= MIN_CLEAN_PASSES (3) passes - it was
   demonstrably green, not merely unobserved;
2. its latest event is a failure: case last_seen strictly after the
   entry's last_pass. Ordering comes from comparing the two event stamps;
   an exact tie is conservatively NOT a regression. Detection uses only
   pass/fail counts plus this ordering - never wall-clock duration
   windows (determinism rule);
3. the case is NOT chronic (pass rate <= 50%). Interplay rule with S8:
   chronic flakes are flake-bounce, never regression - a signature that
   passes more often than it fails is statistically noise-dominated, and
   flooding the prominent block with known noise would destroy its
   signal value. Honest tradeoff, same entry: a freshly-fixed rarely-
   failing test may briefly read chronic until reds accumulate; it
   promotes to regression once its cumulative rate drops to <= 50%.

Zero-pass signatures (no sidecar entry) are NEVER regressions - absence
of evidence stays absent. Cases seen exactly once without any pass are
surfaced separately as first-time failures so the report distinguishes
new trouble from returning trouble. Each regression links its last-green
date from the S8 sidecar's last_pass (D-0008 linkage).

This module is a read-only view over cases.jsonl + flakes.jsonl: store
format, lookup semantics, capture paths, and exit codes are untouched
(scope fence, TASK mail #93).
"""

from datetime import timezone

from .. import store
from . import flaky

MIN_CLEAN_PASSES = 3


def _aware(stamp):
    """Parse an ISO stamp; naive values are interpreted as UTC."""
    moment = store.parse_timestamp(stamp)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def classify(cases, entries):
    """Split live cases into (regressions, first_time_failures).

    Regressions are [(case, entry)] ordered by case id; first-time
    failures are [case] ordered by case id. Pure and read-only.
    """
    by_signature = {entry["signature"]: entry for entry in entries}
    regressions = []
    first_time = []
    for case in sorted(cases, key=lambda item: item["id"]):
        entry = by_signature.get(case["signature"])
        if entry is None:
            if case["times_seen"] == 1:
                first_time.append(case)
            continue
        if (
            not flaky.is_chronic(case, entry["times_passed"])
            and entry["times_passed"] >= MIN_CLEAN_PASSES
            and _aware(case["last_seen"]) > _aware(entry["last_pass"])
        ):
            regressions.append((case, entry))
    return regressions, first_time


def format_regressions(cases, entries):
    """Deterministic two-block rendering; empty blocks print `none`."""
    regressions, first_time = classify(cases, entries)
    lines = [f"regressions (returned after >={MIN_CLEAN_PASSES} clean passes):"]
    if regressions:
        lines.extend(
            f"case #{case['id']} times_seen={case['times_seen']} "
            f"passes={entry['times_passed']} "
            f"last_green={entry['last_pass']} "
            f"sig: {case['signature']}"
            for case, entry in regressions
        )
    else:
        lines.append("none")
    lines.append("first-time failures (single sighting, never passed):")
    if first_time:
        lines.extend(
            f"case #{case['id']} times_seen=1 sig: {case['signature']}"
            for case in first_time
        )
    else:
        lines.append("none")
    return "\n".join(lines)
