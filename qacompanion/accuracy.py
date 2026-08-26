"""Holdout replay scoring for the accuracy subcommand (pure logic).

Per docs/spec.md: replay `seed/holdout.jsonl` and report the percentage of
entries where lookup returns the recorded diagnosis. The holdout file is
created once and frozen; it is the fixed yardstick that keeps accuracy
re-runnable forever (docs/SEEDING.md preserves the creation provenance).

Honesty rules inherited from lookup: a hit requires exactly one stored
case whose diagnosis equals the recorded one. No match, several matches
(AMBIGUOUS), or a differing diagnosis all count as misses - never silent
passes.
"""

import json
import os
from pathlib import Path

from . import lookup
from . import signatures

DEFAULT_HOLDOUT_PATH = Path("seed") / "holdout.jsonl"
ENV_OVERRIDE = "QA_HOLDOUT_FILE"

_FIELD_TYPES = {"signature": str, "diagnosis": str}


def default_holdout_path():
    """Explicit arg > env override > repo-root default."""
    return Path(os.environ.get(ENV_OVERRIDE) or DEFAULT_HOLDOUT_PATH)


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


def load_holdout(path=None):
    """Load frozen holdout entries ({"signature", "diagnosis"} per line).

    Same robustness contract as the case store: BOM prefix stripped, CRLF
    treated like LF, trailing newline optional. Raises ValueError naming
    the offending line on malformed input. A missing or empty holdout is
    an operational failure (exit 1), never silently a 100%.
    """
    holdout_path = Path(path) if path is not None else default_holdout_path()
    if not holdout_path.exists():
        raise ValueError(f"holdout file not found: {holdout_path}")
    text = holdout_path.read_text(encoding="utf-8-sig")
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
    if not entries:
        raise ValueError("holdout file is empty: refusing to score")
    return entries


def replay(cases, entries):
    """Score holdout entries against the case base; returns (hits, total).

    Every entry signature passes the same canonical() gate as record and
    lookup, so a frozen entry and its live twin can never drift apart.
    """
    hits = 0
    for entry in entries:
        query = signatures.canonical(entry["signature"])
        matches = lookup.select(cases, query)
        if len(matches) == 1 and matches[0]["diagnosis"] == entry["diagnosis"]:
            hits += 1
    return hits, len(entries)


def format_accuracy(hits, total):
    """Deterministic score line with the denominator spelled out."""
    pct = round(100 * hits / total)
    return f"accuracy: {pct}% ({hits}/{total})"
