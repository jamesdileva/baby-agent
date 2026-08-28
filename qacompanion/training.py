"""S30 training-data pipeline: export instruction-format pairs.

Converts cases, corrections, journal entries, and digested doc Q&A into
instruction-format pairs (question → grounded answer) suitable for LoRA
fine-tuning. Holdout signatures are excluded from the training set.

Output format (one JSON object per line):
  {"instruction": "...", "input": "...", "output": "..."}

Three categories:
  - Cases: instruction="Diagnose this failure", input=signature+error, output=diagnosis
  - Digest: instruction="Answer based on documentation", input=heading+source, output=content
  - Journal: instruction="What lesson was learned?", input=timestamp, output=text
"""

import json
import os
import tempfile
from pathlib import Path

from . import accuracy
from . import store as store_mod
from .skills import digest as digest_mod
from .skills import journal as journal_mod


def _atomic_write(path, payload):
    """Temp file inside the destination directory, then os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle_fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".train-", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _load_holdout_signatures(holdout_path=None):
    """Load holdout signatures as a set for exclusion from training."""
    try:
        entries = accuracy.load_holdout(holdout_path)
        return {entry["signature"] for entry in entries}
    except (ValueError, FileNotFoundError):
        return set()


def _load_journal_entries(journal_path=None):
    """Parse journal entries from JOURNAL.md into list of (timestamp, text)."""
    path = Path(journal_path) if journal_path else Path("JOURNAL.md")
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []
    entries = []
    for line in content.splitlines():
        if line.startswith("## "):
            rest = line[3:]
            space_idx = rest.find(" ")
            if space_idx > 0:
                ts = rest[:space_idx]
                text = rest[space_idx + 1:]
                entries.append((ts, text))
    return entries


def cases_to_pairs(cases, holdout_sigs=None):
    """Convert cases to instruction-format pairs.

    Excludes cases whose signature matches a holdout entry.
    Returns list of {"instruction", "input", "output"} dicts.
    """
    exclude = holdout_sigs or set()
    pairs = []
    for case in cases:
        if case["signature"] in exclude:
            continue
        pairs.append({
            "instruction": "Diagnose this failure",
            "input": f"Signature: {case['signature']}\nError: {case['error_excerpt']}",
            "output": case["diagnosis"],
        })
    return pairs


def digest_to_pairs(entries):
    """Convert digest entries to doc Q&A instruction pairs.

    Returns list of {"instruction", "input", "output"} dicts.
    """
    pairs = []
    for entry in entries:
        heading = entry.get("heading", "unknown")
        source = entry.get("source", "unknown")
        content = entry.get("content", "")
        if not content.strip():
            continue
        pairs.append({
            "instruction": "Answer based on documentation",
            "input": f"Source: {source}\nTopic: {heading}",
            "output": content,
        })
    return pairs


def journal_to_pairs(entries):
    """Convert journal entries to lesson instruction pairs.

    Returns list of {"instruction", "input", "output"} dicts.
    """
    pairs = []
    for ts, text in entries:
        if not text.strip():
            continue
        pairs.append({
            "instruction": "What lesson was learned?",
            "input": f"Timestamp: {ts}",
            "output": text,
        })
    return pairs


def export_training(
    out_path,
    cases_path=None,
    holdout_path=None,
    digest_path=None,
    journal_path=None,
):
    """Export training data as instruction-format JSONL.

    Returns {"pairs": int, "cases": int, "digest": int, "journal": int}.
    """
    store = store_mod.CaseStore(cases_path)
    cases = store.load()

    holdout_sigs = _load_holdout_signatures(holdout_path)

    digest_store = digest_mod.DigestStore(digest_path)
    digest_entries = digest_store.load()

    journal_entries = _load_journal_entries(journal_path)

    case_pairs = cases_to_pairs(cases, holdout_sigs)
    digest_pairs = digest_to_pairs(digest_entries)
    journal_pairs = journal_to_pairs(journal_entries)

    all_pairs = case_pairs + digest_pairs + journal_pairs

    lines = "".join(
        json.dumps(pair, ensure_ascii=False) + "\n" for pair in all_pairs
    )
    _atomic_write(Path(out_path), lines)

    return {
        "pairs": len(all_pairs),
        "cases": len(case_pairs),
        "digest": len(digest_pairs),
        "journal": len(journal_pairs),
    }
