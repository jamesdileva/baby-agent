"""S23 candidate detection: find patterns in the case base, propose rules.

Offline pass over cases.jsonl: recurring co-occurrences, error clusters,
timing anomalies → filed as RULE PROPOSED entries into a review queue
(never auto-installed). Includes confidence estimate + supporting cases.

Storage: a skill-owned sidecar `rules_proposed.jsonl` next to the case store.
Entries: {"id", "type", "description", "confidence", "supporting_cases",
"proposed_rule", "created"}, strict-validated, atomically saved.
"""

import json
import os
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import store

SIDECAR_NAME = "rules_proposed.jsonl"
RECURRING_THRESHOLD = 3
CLUSTER_MIN_SIZE = 2

_FIELD_TYPES = {
    "id": int,
    "type": str,
    "description": str,
    "confidence": float,
    "supporting_cases": list,
    "proposed_rule": str,
    "created": str,
}


def default_path():
    """Sidecar lives beside the case store."""
    return store.default_path().parent / SIDECAR_NAME


def _validate_entry(entry, line_number):
    if not isinstance(entry, dict):
        raise ValueError(f"line {line_number}: expected a JSON object")
    missing = sorted(f for f in _FIELD_TYPES if f not in entry)
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
    if entry["id"] < 1:
        raise ValueError(f"line {line_number}: id must be >= 1")
    if not (0.0 <= entry["confidence"] <= 1.0):
        raise ValueError(f"line {line_number}: confidence must be 0.0-1.0")
    if entry["type"] not in ("recurring", "cluster", "timing"):
        raise ValueError(f"line {line_number}: unknown type '{entry['type']}'")


def load_proposed(path=None):
    """Load proposed rules from sidecar. Returns list of dicts."""
    path = path or default_path()
    if not path.exists():
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line:
                continue
            entry = json.loads(line)
            _validate_entry(entry, lineno)
            entries.append(entry)
    return entries


def save_proposed(entries, path=None):
    """Atomically save proposed rules to sidecar."""
    path = path or default_path()
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


def _cluster_by_error_excerpt(cases):
    """Group cases by similar error excerpts (first 80 chars)."""
    clusters = defaultdict(list)
    for case in cases:
        key = case["error_excerpt"][:80].lower().strip()
        clusters[key].append(case)
    return clusters


def detect_candidates(cases_path=None, proposed_path=None):
    """Analyze case base, return list of proposed rule dicts."""
    cs = store.CaseStore(cases_path)
    cases = cs.load()
    existing = load_proposed(proposed_path)
    existing_ids = {e["id"] for e in existing}
    max_id = max(existing_ids, default=0)

    candidates = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    # Pattern 1: Recurring cases (times_seen >= threshold)
    for case in cases:
        if case["times_seen"] >= RECURRING_THRESHOLD:
            confidence = min(case["times_seen"] / 20.0, 1.0)
            max_id += 1
            candidates.append({
                "id": max_id,
                "type": "recurring",
                "description": f"Case #{case['id']} seen {case['times_seen']} times",
                "confidence": round(confidence, 3),
                "supporting_cases": [case["id"]],
                "proposed_rule": f"Recurring failure pattern: {case['signature'][:100]}",
                "created": now,
            })

    # Pattern 2: Error clusters (similar error excerpts)
    clusters = _cluster_by_error_excerpt(cases)
    for _key, group in clusters.items():
        if len(group) >= CLUSTER_MIN_SIZE:
            confidence = min(len(group) / 5.0, 1.0)
            max_id += 1
            candidates.append({
                "id": max_id,
                "type": "cluster",
                "description": f"Cluster of {len(group)} cases with similar errors",
                "confidence": round(confidence, 3),
                "supporting_cases": [c["id"] for c in group],
                "proposed_rule": f"Error cluster: {group[0]['error_excerpt'][:80]}",
                "created": now,
            })

    return candidates


def run_detection(cases_path=None, proposed_path=None):
    """Run detection and persist new candidates. Returns list of new entries."""
    candidates = detect_candidates(cases_path, proposed_path)
    existing = load_proposed(proposed_path)
    existing_sigs = {(e["type"], tuple(e["supporting_cases"])) for e in existing}

    new_entries = []
    for c in candidates:
        key = (c["type"], tuple(c["supporting_cases"]))
        if key not in existing_sigs:
            new_entries.append(c)
            existing_sigs.add(key)
    if new_entries:
        save_proposed(existing + new_entries, proposed_path)
    return new_entries


def format_proposed(entries):
    """Format proposed rules for display."""
    if not entries:
        return "no rule proposals"
    lines = [f"proposed rules: {len(entries)}"]
    for e in entries:
        lines.append(
            f"  #{e['id']} [{e['type']}] confidence={e['confidence']:.1%} "
            f"cases={e['supporting_cases']}"
        )
        lines.append(f"    {e['description']}")
        lines.append(f"    rule: {e['proposed_rule'][:120]}")
    return "\n".join(lines)
