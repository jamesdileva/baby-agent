"""Case-base summary rendering for the report subcommand (pure logic).

Per docs/spec.md: total cases, top 5 by times_seen, stale cases (>30d
since last_seen), and - since D-0004 was ratified (human mail #15) -
an accuracy score line. Output is deterministic given (cases, now);
empty sections print `none` rather than vanishing silently. Stale cases
are reported, never deleted (retention is a human-approved act).
"""

from datetime import datetime, timedelta, timezone

from . import accuracy as accuracy_mod
from .store import parse_timestamp

TOP_LIMIT = 5
STALE_AFTER_DAYS = 30
ACCURACY_NA = "accuracy: n/a - holdout not yet created"


def _as_utc(moment):
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def top_cases(cases, limit=TOP_LIMIT):
    """Highest times_seen first; ties broken by lower id for determinism."""
    ranked = sorted(cases, key=lambda case: (-case["times_seen"], case["id"]))
    return ranked[:limit]


def is_stale(case, now=None):
    """Strictly older than STALE_AFTER_DAYS since last_seen.

    A naive last_seen stamp is interpreted as UTC so mixed-offset stores
    cannot crash the report.
    """
    moment = _as_utc(now or datetime.now(timezone.utc))
    cutoff = moment - timedelta(days=STALE_AFTER_DAYS)
    return _as_utc(parse_timestamp(case["last_seen"])) < cutoff


def stale_cases(cases, now=None):
    return [case for case in cases if is_stale(case, now)]


def format_report(cases, now=None):
    lines = [f"total cases: {len(cases)}"]

    lines.append(f"top {TOP_LIMIT} by times_seen:")
    top = top_cases(cases)
    if top:
        lines.extend(
            f"case #{case['id']} times_seen={case['times_seen']}"
            f" sig: {case['signature']}"
            for case in top
        )
    else:
        lines.append("none")

    lines.append(f"stale (>{STALE_AFTER_DAYS}d):")
    stale = stale_cases(cases, now)
    if stale:
        lines.extend(
            f"case #{case['id']} last_seen={case['last_seen']}"
            f" sig: {case['signature']}"
            for case in stale
        )
    else:
        lines.append("none")

    return "\n".join(lines)


def accuracy_line(cases):
    """Accuracy score for report output (D-0004, ratified with condition).

    Missing or unplayed (empty) holdout degrades honestly to ACCURACY_NA,
    never a fabricated percentage. A malformed holdout is corruption, not
    absence: its ValueError propagates so the uniform policy exits 1.
    """
    if not accuracy_mod.default_holdout_path().exists():
        return ACCURACY_NA
    try:
        entries = accuracy_mod.load_holdout()
    except accuracy_mod.EmptyHoldout:
        return ACCURACY_NA
    hits, total = accuracy_mod.replay(cases, entries)
    return accuracy_mod.format_accuracy(hits, total)
