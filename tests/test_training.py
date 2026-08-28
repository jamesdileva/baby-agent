"""Tests for S30 training-data pipeline."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from qacompanion import training
from qacompanion import store as store_mod
from qacompanion.skills import digest as digest_mod


class CasesToPairsTest(unittest.TestCase):
    def test_basic_conversion(self):
        cases = [
            {
                "id": 1,
                "signature": "test :: error",
                "error_excerpt": "something broke",
                "diagnosis": "fix the thing",
                "times_seen": 1,
                "last_seen": "2026-08-26T00:00:00Z",
                "confirmed_by": "human",
            }
        ]
        pairs = training.cases_to_pairs(cases)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["instruction"], "Diagnose this failure")
        self.assertIn("test :: error", pairs[0]["input"])
        self.assertIn("something broke", pairs[0]["input"])
        self.assertEqual(pairs[0]["output"], "fix the thing")

    def test_holdout_exclusion(self):
        cases = [
            {
                "id": 1,
                "signature": "sig-a :: err",
                "error_excerpt": "err a",
                "diagnosis": "diag a",
                "times_seen": 1,
                "last_seen": "2026-08-26T00:00:00Z",
                "confirmed_by": "human",
            },
            {
                "id": 2,
                "signature": "sig-b :: err",
                "error_excerpt": "err b",
                "diagnosis": "diag b",
                "times_seen": 1,
                "last_seen": "2026-08-26T00:00:00Z",
                "confirmed_by": "human",
            },
        ]
        holdout_sigs = {"sig-a :: err"}
        pairs = training.cases_to_pairs(cases, holdout_sigs)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["output"], "diag b")

    def test_empty_cases(self):
        pairs = training.cases_to_pairs([])
        self.assertEqual(pairs, [])

    def test_multiple_cases(self):
        cases = [
            {
                "id": i,
                "signature": f"sig-{i} :: err",
                "error_excerpt": f"err {i}",
                "diagnosis": f"diag {i}",
                "times_seen": 1,
                "last_seen": "2026-08-26T00:00:00Z",
                "confirmed_by": "human",
            }
            for i in range(1, 4)
        ]
        pairs = training.cases_to_pairs(cases)
        self.assertEqual(len(pairs), 3)


class DigestToPairsTest(unittest.TestCase):
    def test_basic_conversion(self):
        entries = [
            {
                "id": 1,
                "source": "deploy.md",
                "heading": "Deployment",
                "content": "Run docker compose up.",
                "content_hash": "abc",
                "digested_at": "2026-08-26T00:00:00Z",
            }
        ]
        pairs = training.digest_to_pairs(entries)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["instruction"], "Answer based on documentation")
        self.assertIn("deploy.md", pairs[0]["input"])
        self.assertIn("Deployment", pairs[0]["input"])
        self.assertEqual(pairs[0]["output"], "Run docker compose up.")

    def test_empty_content_skipped(self):
        entries = [
            {
                "id": 1,
                "source": "a.md",
                "heading": "A",
                "content": "",
                "content_hash": "abc",
                "digested_at": "2026-08-26T00:00:00Z",
            }
        ]
        pairs = training.digest_to_pairs(entries)
        self.assertEqual(pairs, [])

    def test_whitespace_content_skipped(self):
        entries = [
            {
                "id": 1,
                "source": "a.md",
                "heading": "A",
                "content": "   \n  ",
                "content_hash": "abc",
                "digested_at": "2026-08-26T00:00:00Z",
            }
        ]
        pairs = training.digest_to_pairs(entries)
        self.assertEqual(pairs, [])

    def test_empty_entries(self):
        pairs = training.digest_to_pairs([])
        self.assertEqual(pairs, [])


class JournalToPairsTest(unittest.TestCase):
    def test_basic_conversion(self):
        entries = [("2026-08-26T12:00:00", "BOM breaks JSONL config")]
        pairs = training.journal_to_pairs(entries)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["instruction"], "What lesson was learned?")
        self.assertIn("2026-08-26T12:00:00", pairs[0]["input"])
        self.assertEqual(pairs[0]["output"], "BOM breaks JSONL config")

    def test_empty_text_skipped(self):
        entries = [("2026-08-26T12:00:00", "")]
        pairs = training.journal_to_pairs(entries)
        self.assertEqual(pairs, [])

    def test_empty_entries(self):
        pairs = training.journal_to_pairs([])
        self.assertEqual(pairs, [])


class ExportTrainingTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cases_path = os.path.join(self.tmpdir, "cases.jsonl")
        self.out_path = os.path.join(self.tmpdir, "train.jsonl")
        self.holdout_path = os.path.join(self.tmpdir, "holdout.jsonl")
        self.digest_path = os.path.join(self.tmpdir, "digest.jsonl")
        self.journal_path = os.path.join(self.tmpdir, "JOURNAL.md")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_cases(self, cases):
        with open(self.cases_path, "w", encoding="utf-8") as f:
            for case in cases:
                f.write(json.dumps(case) + "\n")

    def test_export_with_cases_only(self):
        self._write_cases([
            {
                "id": 1,
                "signature": "test :: error",
                "error_excerpt": "err",
                "diagnosis": "fix",
                "times_seen": 1,
                "last_seen": "2026-08-26T00:00:00Z",
                "confirmed_by": "human",
            }
        ])
        result = training.export_training(
            self.out_path,
            cases_path=self.cases_path,
            holdout_path=self.holdout_path,
            digest_path=self.digest_path,
            journal_path=self.journal_path,
        )
        self.assertEqual(result["cases"], 1)
        self.assertEqual(result["pairs"], 1)
        self.assertTrue(os.path.exists(self.out_path))
        with open(self.out_path, encoding="utf-8") as f:
            line = f.readline()
        obj = json.loads(line)
        self.assertIn("instruction", obj)
        self.assertIn("input", obj)
        self.assertIn("output", obj)

    def test_holdout_excluded(self):
        self._write_cases([
            {
                "id": 1,
                "signature": "sig-a :: err",
                "error_excerpt": "err a",
                "diagnosis": "diag a",
                "times_seen": 1,
                "last_seen": "2026-08-26T00:00:00Z",
                "confirmed_by": "human",
            },
            {
                "id": 2,
                "signature": "sig-b :: err",
                "error_excerpt": "err b",
                "diagnosis": "diag b",
                "times_seen": 1,
                "last_seen": "2026-08-26T00:00:00Z",
                "confirmed_by": "human",
            },
        ])
        with open(self.holdout_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"signature": "sig-a :: err", "diagnosis": "diag a"}) + "\n")
        result = training.export_training(
            self.out_path,
            cases_path=self.cases_path,
            holdout_path=self.holdout_path,
            digest_path=self.digest_path,
            journal_path=self.journal_path,
        )
        self.assertEqual(result["cases"], 1)

    def test_empty_sources(self):
        self._write_cases([])
        result = training.export_training(
            self.out_path,
            cases_path=self.cases_path,
            holdout_path=self.holdout_path,
            digest_path=self.digest_path,
            journal_path=self.journal_path,
        )
        self.assertEqual(result["pairs"], 0)
        self.assertTrue(os.path.exists(self.out_path))

    def test_output_is_valid_jsonl(self):
        self._write_cases([
            {
                "id": 1,
                "signature": "a :: b",
                "error_excerpt": "err",
                "diagnosis": "diag",
                "times_seen": 1,
                "last_seen": "2026-08-26T00:00:00Z",
                "confirmed_by": "human",
            }
        ])
        training.export_training(
            self.out_path,
            cases_path=self.cases_path,
            holdout_path=self.holdout_path,
            digest_path=self.digest_path,
            journal_path=self.journal_path,
        )
        with open(self.out_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    obj = json.loads(line)
                    self.assertIsInstance(obj, dict)
                    self.assertIn("instruction", obj)
                    self.assertIn("input", obj)
                    self.assertIn("output", obj)

    def test_digest_included(self):
        self._write_cases([])
        with open(self.digest_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "id": 1,
                "source": "deploy.md",
                "heading": "Deploy",
                "content": "Run docker.",
                "content_hash": "abc",
                "digested_at": "2026-08-26T00:00:00Z",
            }) + "\n")
        result = training.export_training(
            self.out_path,
            cases_path=self.cases_path,
            holdout_path=self.holdout_path,
            digest_path=self.digest_path,
            journal_path=self.journal_path,
        )
        self.assertEqual(result["digest"], 1)
        self.assertEqual(result["pairs"], 1)

    def test_journal_included(self):
        self._write_cases([])
        with open(self.journal_path, "w", encoding="utf-8") as f:
            f.write("## 2026-08-26T12:00:00 BOM breaks config\n")
        result = training.export_training(
            self.out_path,
            cases_path=self.cases_path,
            holdout_path=self.holdout_path,
            digest_path=self.digest_path,
            journal_path=self.journal_path,
        )
        self.assertEqual(result["journal"], 1)
        self.assertEqual(result["pairs"], 1)

    def test_missing_holdout_handled(self):
        self._write_cases([
            {
                "id": 1,
                "signature": "a :: b",
                "error_excerpt": "err",
                "diagnosis": "diag",
                "times_seen": 1,
                "last_seen": "2026-08-26T00:00:00Z",
                "confirmed_by": "human",
            }
        ])
        result = training.export_training(
            self.out_path,
            cases_path=self.cases_path,
            holdout_path=os.path.join(self.tmpdir, "nonexistent.jsonl"),
            digest_path=self.digest_path,
            journal_path=self.journal_path,
        )
        self.assertEqual(result["cases"], 1)

    def test_missing_journal_handled(self):
        self._write_cases([
            {
                "id": 1,
                "signature": "a :: b",
                "error_excerpt": "err",
                "diagnosis": "diag",
                "times_seen": 1,
                "last_seen": "2026-08-26T00:00:00Z",
                "confirmed_by": "human",
            }
        ])
        result = training.export_training(
            self.out_path,
            cases_path=self.cases_path,
            holdout_path=self.holdout_path,
            digest_path=self.digest_path,
            journal_path=os.path.join(self.tmpdir, "nonexistent.md"),
        )
        self.assertEqual(result["pairs"], 1)

    def test_missing_digest_handled(self):
        self._write_cases([
            {
                "id": 1,
                "signature": "a :: b",
                "error_excerpt": "err",
                "diagnosis": "diag",
                "times_seen": 1,
                "last_seen": "2026-08-26T00:00:00Z",
                "confirmed_by": "human",
            }
        ])
        result = training.export_training(
            self.out_path,
            cases_path=self.cases_path,
            holdout_path=self.holdout_path,
            digest_path=os.path.join(self.tmpdir, "nonexistent.jsonl"),
            journal_path=self.journal_path,
        )
        self.assertEqual(result["pairs"], 1)


class LoadHoldoutSignaturesTest(unittest.TestCase):
    def test_loads_signatures(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"signature": "a :: b", "diagnosis": "d"}) + "\n")
            path = f.name
        try:
            sigs = training._load_holdout_signatures(path)
            self.assertEqual(sigs, {"a :: b"})
        finally:
            os.unlink(path)

    def test_missing_file_returns_empty(self):
        sigs = training._load_holdout_signatures("/nonexistent/path.jsonl")
        self.assertEqual(sigs, set())


class LoadJournalEntriesTest(unittest.TestCase):
    def test_parses_entries(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("## 2026-08-26T12:00:00 Lesson learned\n")
            f.write("## 2026-08-26T13:00:00 Another lesson\n")
            path = f.name
        try:
            entries = training._load_journal_entries(path)
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0], ("2026-08-26T12:00:00", "Lesson learned"))
            self.assertEqual(entries[1], ("2026-08-26T13:00:00", "Another lesson"))
        finally:
            os.unlink(path)

    def test_missing_file_returns_empty(self):
        entries = training._load_journal_entries("/nonexistent.md")
        self.assertEqual(entries, [])


if __name__ == "__main__":
    unittest.main()
