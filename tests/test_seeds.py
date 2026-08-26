"""Frozen seed artifacts pinned to docs/SEEDING.md digests (TASK #18 rider).

Mutating seed/holdout.jsonl invalidates every future accuracy comparison;
these tests fail loudly if either frozen file drifts from its recorded
SHA256 or stops being loadable through the shipped readers.
"""

import hashlib
import json
import re
import unittest
from pathlib import Path

from qacompanion import accuracy as accuracy_mod

REPO_ROOT = Path(__file__).resolve().parents[1]
FROZEN_SEEDS = ("seed/lore.jsonl", "seed/holdout.jsonl")

LORE_FIELDS = {
    "signature",
    "error_excerpt",
    "diagnosis",
    "times_seen",
    "last_seen",
    "confirmed_by",
}


def recorded_digests():
    text = (REPO_ROOT / "docs" / "SEEDING.md").read_text(encoding="utf-8-sig")
    return {
        path: digest.upper()
        for digest, path in re.findall(
            r"^([0-9A-Fa-f]{64})\s+(\S+)\s*$", text, re.MULTILINE
        )
    }


class SeedFreezeTests(unittest.TestCase):
    def test_seeding_md_records_both_frozen_seed_files(self):
        digests = recorded_digests()
        for relative in FROZEN_SEEDS:
            self.assertIn(relative, digests)

    def test_frozen_seed_files_match_their_recorded_sha256(self):
        digests = recorded_digests()
        for relative in FROZEN_SEEDS:
            data = (REPO_ROOT / relative).read_bytes()
            self.assertEqual(
                digests[relative],
                hashlib.sha256(data).hexdigest().upper(),
                f"{relative} drifted from its SEEDING.md digest",
            )

    def test_lore_is_record_input_shape_not_full_cases(self):
        # Frozen pre-record shape (no id): lore replays through the record
        # CLI, not through import - import validates the full frozen format.
        text = (REPO_ROOT / "seed" / "lore.jsonl").read_text(encoding="utf-8-sig")
        entries = [json.loads(line) for line in text.splitlines() if line.strip()]
        self.assertEqual(4, len(entries))
        for entry in entries:
            self.assertTrue(LORE_FIELDS <= set(entry))

    def test_holdout_loads_through_the_accuracy_reader(self):
        entries = accuracy_mod.load_holdout(REPO_ROOT / "seed" / "holdout.jsonl")
        self.assertEqual(4, len(entries))


if __name__ == "__main__":
    unittest.main()
