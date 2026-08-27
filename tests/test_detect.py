"""Tests for S23 candidate detection."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from qacompanion import detect, store


class TestDetectModule(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cases_path = Path(self.tmpdir) / "cases.jsonl"
        self.proposed_path = Path(self.tmpdir) / "rules_proposed.jsonl"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_cases(self, cases):
        with open(self.cases_path, "w", encoding="utf-8") as f:
            for c in cases:
                f.write(json.dumps(c) + "\n")

    def test_empty_store_no_candidates(self):
        self._write_cases([])
        candidates = detect.detect_candidates(self.cases_path, self.proposed_path)
        self.assertEqual(candidates, [])

    def test_single_low_freq_no_candidate(self):
        self._write_cases([{
            "id": 1, "signature": "test :: error", "error_excerpt": "boom",
            "diagnosis": "fix", "times_seen": 1,
            "last_seen": "2026-08-26T00:00:00Z", "confirmed_by": "test",
        }])
        candidates = detect.detect_candidates(self.cases_path, self.proposed_path)
        self.assertEqual(candidates, [])

    def test_recurring_candidate(self):
        self._write_cases([{
            "id": 1, "signature": "test :: error", "error_excerpt": "boom",
            "diagnosis": "fix", "times_seen": 5,
            "last_seen": "2026-08-26T00:00:00Z", "confirmed_by": "test",
        }])
        candidates = detect.detect_candidates(self.cases_path, self.proposed_path)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["type"], "recurring")
        self.assertEqual(candidates[0]["supporting_cases"], [1])
        self.assertGreater(candidates[0]["confidence"], 0)

    def test_recurring_threshold_boundary(self):
        self._write_cases([{
            "id": 1, "signature": "test :: error", "error_excerpt": "boom",
            "diagnosis": "fix", "times_seen": 2,
            "last_seen": "2026-08-26T00:00:00Z", "confirmed_by": "test",
        }])
        candidates = detect.detect_candidates(self.cases_path, self.proposed_path)
        self.assertEqual(candidates, [])

    def test_cluster_candidate(self):
        self._write_cases([
            {"id": 1, "signature": "a :: err1", "error_excerpt": "same error here",
             "diagnosis": "fix1", "times_seen": 1,
             "last_seen": "2026-08-26T00:00:00Z", "confirmed_by": "test"},
            {"id": 2, "signature": "b :: err2", "error_excerpt": "same error here",
             "diagnosis": "fix2", "times_seen": 1,
             "last_seen": "2026-08-26T00:00:00Z", "confirmed_by": "test"},
        ])
        candidates = detect.detect_candidates(self.cases_path, self.proposed_path)
        clusters = [c for c in candidates if c["type"] == "cluster"]
        self.assertEqual(len(clusters), 1)
        self.assertEqual(sorted(clusters[0]["supporting_cases"]), [1, 2])

    def test_cluster_single_no_candidate(self):
        self._write_cases([{
            "id": 1, "signature": "a :: err", "error_excerpt": "unique error",
            "diagnosis": "fix", "times_seen": 1,
            "last_seen": "2026-08-26T00:00:00Z", "confirmed_by": "test",
        }])
        candidates = detect.detect_candidates(self.cases_path, self.proposed_path)
        clusters = [c for c in candidates if c["type"] == "cluster"]
        self.assertEqual(clusters, [])

    def test_both_patterns(self):
        self._write_cases([
            {"id": 1, "signature": "a :: err", "error_excerpt": "same error",
             "diagnosis": "fix1", "times_seen": 5,
             "last_seen": "2026-08-26T00:00:00Z", "confirmed_by": "test"},
            {"id": 2, "signature": "b :: err", "error_excerpt": "same error",
             "diagnosis": "fix2", "times_seen": 1,
             "last_seen": "2026-08-26T00:00:00Z", "confirmed_by": "test"},
        ])
        candidates = detect.detect_candidates(self.cases_path, self.proposed_path)
        types = {c["type"] for c in candidates}
        self.assertIn("recurring", types)
        self.assertIn("cluster", types)

    def test_save_and_load_roundtrip(self):
        entries = [{
            "id": 1, "type": "recurring", "description": "test",
            "confidence": 0.5, "supporting_cases": [1],
            "proposed_rule": "rule text", "created": "2026-08-26T00:00:00Z",
        }]
        detect.save_proposed(entries, self.proposed_path)
        loaded = detect.load_proposed(self.proposed_path)
        self.assertEqual(loaded, entries)

    def test_idempotent_detection(self):
        self._write_cases([{
            "id": 1, "signature": "test :: error", "error_excerpt": "boom",
            "diagnosis": "fix", "times_seen": 5,
            "last_seen": "2026-08-26T00:00:00Z", "confirmed_by": "test",
        }])
        new1 = detect.run_detection(self.cases_path, self.proposed_path)
        self.assertEqual(len(new1), 1)
        new2 = detect.run_detection(self.cases_path, self.proposed_path)
        self.assertEqual(new2, [])

    def test_format_proposed_empty(self):
        result = detect.format_proposed([])
        self.assertEqual(result, "no rule proposals")

    def test_format_proposed_entries(self):
        entries = [{
            "id": 1, "type": "recurring", "description": "test desc",
            "confidence": 0.75, "supporting_cases": [1, 2],
            "proposed_rule": "rule text here",
            "created": "2026-08-26T00:00:00Z",
        }]
        result = detect.format_proposed(entries)
        self.assertIn("proposed rules: 1", result)
        self.assertIn("recurring", result)
        self.assertIn("75.0%", result)

    def test_confidence_scaling(self):
        self._write_cases([{
            "id": 1, "signature": "test :: error", "error_excerpt": "boom",
            "diagnosis": "fix", "times_seen": 10,
            "last_seen": "2026-08-26T00:00:00Z", "confirmed_by": "test",
        }])
        candidates = detect.detect_candidates(self.cases_path, self.proposed_path)
        self.assertEqual(candidates[0]["confidence"], 0.5)

    def test_confidence_cap_at_1(self):
        self._write_cases([{
            "id": 1, "signature": "test :: error", "error_excerpt": "boom",
            "diagnosis": "fix", "times_seen": 50,
            "last_seen": "2026-08-26T00:00:00Z", "confirmed_by": "test",
        }])
        candidates = detect.detect_candidates(self.cases_path, self.proposed_path)
        self.assertEqual(candidates[0]["confidence"], 1.0)

    def test_corrupt_proposed_file(self):
        with open(self.proposed_path, "w") as f:
            f.write("not json\n")
        with self.assertRaises(ValueError):
            detect.load_proposed(self.proposed_path)

    def test_missing_proposed_file(self):
        entries = detect.load_proposed(Path(self.tmpdir) / "nonexistent.jsonl")
        self.assertEqual(entries, [])


if __name__ == "__main__":
    unittest.main()
