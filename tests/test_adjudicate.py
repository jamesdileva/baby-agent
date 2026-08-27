"""Tests for S24 adjudicate module."""

import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from qacompanion import adjudicate, detect, store


def _make_candidate(cid, ctype="recurring", cases=None, desc="test candidate"):
    """Helper to create a candidate dict."""
    if cases is None:
        cases = [cid]
    return {
        "id": cid,
        "type": ctype,
        "description": desc,
        "confidence": 0.5,
        "supporting_cases": cases,
        "proposed_rule": f"rule for {desc}",
        "created": "2026-08-27T00:00:00Z",
    }


def _make_rejected(ctype="recurring", cases=None, reason="no"):
    """Helper to create a rejection entry."""
    if cases is None:
        cases = [1]
    return {
        "type": ctype,
        "supporting_cases": cases,
        "rejected_by": "test",
        "rejected_at": "2026-08-27T00:00:00Z",
        "reason": reason,
    }


class TestRejectedIO(unittest.TestCase):
    def test_load_empty(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "nonexistent.jsonl"
            self.assertEqual(adjudicate.load_rejected(path), [])

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "rejected.jsonl"
            entries = [_make_rejected()]
            adjudicate.save_rejected(entries, path)
            loaded = adjudicate.load_rejected(path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["type"], "recurring")
            self.assertEqual(loaded[0]["reason"], "no")

    def test_validate_missing_fields(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "rejected.jsonl"
            path.write_text(json.dumps({"type": "recurring"}) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                adjudicate.load_rejected(path)

    def test_validate_bad_type(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "rejected.jsonl"
            entry = _make_rejected()
            entry["type"] = 123
            path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                adjudicate.load_rejected(path)

    def test_validate_bad_supporting_cases(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "rejected.jsonl"
            entry = _make_rejected()
            entry["supporting_cases"] = "not a list"
            path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                adjudicate.load_rejected(path)


class TestCandidateKey(unittest.TestCase):
    def test_same_key(self):
        c1 = _make_candidate(1, cases=[1, 2, 3])
        c2 = _make_candidate(2, cases=[3, 1, 2])
        self.assertEqual(
            adjudicate._candidate_key(c1),
            adjudicate._candidate_key(c2),
        )

    def test_different_key(self):
        c1 = _make_candidate(1, cases=[1, 2])
        c2 = _make_candidate(2, cases=[1, 3])
        self.assertNotEqual(
            adjudicate._candidate_key(c1),
            adjudicate._candidate_key(c2),
        )


class TestIsRejected(unittest.TestCase):
    def test_not_rejected(self):
        c = _make_candidate(1, cases=[1])
        rejected = [_make_rejected(cases=[2])]
        self.assertFalse(adjudicate.is_rejected(c, rejected))

    def test_rejected_same_shape(self):
        c = _make_candidate(1, cases=[1, 2])
        rejected = [_make_rejected(cases=[2, 1])]
        self.assertTrue(adjudicate.is_rejected(c, rejected))

    def test_rejected_different_type(self):
        c = _make_candidate(1, ctype="cluster", cases=[1])
        rejected = [_make_rejected(ctype="recurring", cases=[1])]
        self.assertFalse(adjudicate.is_rejected(c, rejected))

    def test_empty_rejected_list(self):
        c = _make_candidate(1, cases=[1])
        self.assertFalse(adjudicate.is_rejected(c, []))


class TestFilterUnrejected(unittest.TestCase):
    def test_filters_rejected(self):
        c1 = _make_candidate(1, cases=[1])
        c2 = _make_candidate(2, cases=[2])
        c3 = _make_candidate(3, cases=[3])
        rejected = [_make_rejected(cases=[2])]
        result = adjudicate.filter_unrejected([c1, c2, c3], rejected)
        self.assertEqual([c["id"] for c in result], [1, 3])

    def test_all_rejected(self):
        c1 = _make_candidate(1, cases=[1])
        rejected = [_make_rejected(cases=[1])]
        result = adjudicate.filter_unrejected([c1], rejected)
        self.assertEqual(result, [])

    def test_none_rejected(self):
        c1 = _make_candidate(1, cases=[1])
        result = adjudicate.filter_unrejected([c1], [])
        self.assertEqual(len(result), 1)


class TestFormatCandidate(unittest.TestCase):
    def test_basic(self):
        c = _make_candidate(5, ctype="cluster", cases=[1, 2], desc="test desc")
        text = adjudicate.format_candidate(c, 1, 3)
        self.assertIn("Rule #5", text)
        self.assertIn("cluster", text)
        self.assertIn("test desc", text)
        self.assertIn("1/3", text)


class TestFormatSummary(unittest.TestCase):
    def test_basic(self):
        text = adjudicate.format_summary(2, 1, 1, 3, 5)
        self.assertIn("approved", text)
        self.assertIn("corrected", text)
        self.assertIn("rejected", text)
        self.assertIn("skipped", text)
        self.assertIn("remaining", text)

    def test_zero_counts(self):
        text = adjudicate.format_summary(0, 0, 0, 0, 0)
        self.assertIn("0 candidate(s) processed", text)


class TestRunSession(unittest.TestCase):
    def _make_case_base(self, td):
        cases_path = Path(td) / "cases.jsonl"
        case = {
            "id": 1,
            "signature": "sig-alpha",
            "error_excerpt": "error text",
            "diagnosis": "diagnosis text",
            "times_seen": 5,
            "last_seen": "2026-08-27T00:00:00Z",
            "confirmed_by": "unknown",
        }
        cases_path.write_text(json.dumps(case) + "\n", encoding="utf-8")
        return cases_path

    def test_approve(self):
        with tempfile.TemporaryDirectory() as td:
            cases_path = self._make_case_base(td)
            proposed_path = Path(td) / "rules_proposed.jsonl"
            rejected_path = Path(td) / "rules_rejected.jsonl"
            pack_path = Path(td) / "taught.json"

            c = _make_candidate(1, cases=[1])
            detect.save_proposed([c], proposed_path)

            stdin = StringIO("a\n^Error: .*test\nenvironment-error\nKnown test error\n")
            result = adjudicate.run_session(
                proposed_path=proposed_path,
                rejected_path=rejected_path,
                pack_path=pack_path,
                by="test",
                stdin=stdin,
            )
            self.assertEqual(result["approved"], 1)
            self.assertEqual(result["corrected"], 0)
            self.assertEqual(result["rejected"], 0)
            self.assertTrue(pack_path.exists())

    def test_reject(self):
        with tempfile.TemporaryDirectory() as td:
            proposed_path = Path(td) / "rules_proposed.jsonl"
            rejected_path = Path(td) / "rules_rejected.jsonl"
            pack_path = Path(td) / "taught.json"

            c = _make_candidate(1, cases=[1])
            detect.save_proposed([c], proposed_path)

            stdin = StringIO("r\nNot useful\n")
            result = adjudicate.run_session(
                proposed_path=proposed_path,
                rejected_path=rejected_path,
                pack_path=pack_path,
                by="test",
                stdin=stdin,
            )
            self.assertEqual(result["rejected"], 1)
            rejected = adjudicate.load_rejected(rejected_path)
            self.assertEqual(len(rejected), 1)
            self.assertEqual(rejected[0]["reason"], "Not useful")

    def test_skip(self):
        with tempfile.TemporaryDirectory() as td:
            proposed_path = Path(td) / "rules_proposed.jsonl"
            rejected_path = Path(td) / "rules_rejected.jsonl"
            pack_path = Path(td) / "taught.json"

            c = _make_candidate(1, cases=[1])
            detect.save_proposed([c], proposed_path)

            stdin = StringIO("s\n")
            result = adjudicate.run_session(
                proposed_path=proposed_path,
                rejected_path=rejected_path,
                pack_path=pack_path,
                by="test",
                stdin=stdin,
            )
            self.assertEqual(result["skipped"], 1)

    def test_quit(self):
        with tempfile.TemporaryDirectory() as td:
            proposed_path = Path(td) / "rules_proposed.jsonl"
            rejected_path = Path(td) / "rules_rejected.jsonl"
            pack_path = Path(td) / "taught.json"

            c1 = _make_candidate(1, cases=[1])
            c2 = _make_candidate(2, cases=[2])
            detect.save_proposed([c1, c2], proposed_path)

            stdin = StringIO("q\n")
            result = adjudicate.run_session(
                proposed_path=proposed_path,
                rejected_path=rejected_path,
                pack_path=pack_path,
                by="test",
                stdin=stdin,
            )
            self.assertEqual(result["skipped"], 0)

    def test_empty_queue(self):
        with tempfile.TemporaryDirectory() as td:
            proposed_path = Path(td) / "rules_proposed.jsonl"
            rejected_path = Path(td) / "rules_rejected.jsonl"
            pack_path = Path(td) / "taught.json"

            result = adjudicate.run_session(
                proposed_path=proposed_path,
                rejected_path=rejected_path,
                pack_path=pack_path,
                by="test",
                stdin=StringIO(""),
            )
            self.assertEqual(result["approved"], 0)
            self.assertEqual(result["remaining"], 0)

    def test_limit(self):
        with tempfile.TemporaryDirectory() as td:
            proposed_path = Path(td) / "rules_proposed.jsonl"
            rejected_path = Path(td) / "rules_rejected.jsonl"
            pack_path = Path(td) / "taught.json"

            c1 = _make_candidate(1, cases=[1])
            c2 = _make_candidate(2, cases=[2])
            detect.save_proposed([c1, c2], proposed_path)

            stdin = StringIO("s\n")
            result = adjudicate.run_session(
                proposed_path=proposed_path,
                rejected_path=rejected_path,
                pack_path=pack_path,
                by="test",
                limit=1,
                stdin=stdin,
            )
            self.assertEqual(result["skipped"], 1)
            remaining = detect.load_proposed(proposed_path)
            self.assertEqual(len(remaining), 2)

    def test_rejection_suppresses_repeat(self):
        with tempfile.TemporaryDirectory() as td:
            proposed_path = Path(td) / "rules_proposed.jsonl"
            rejected_path = Path(td) / "rules_rejected.jsonl"
            pack_path = Path(td) / "taught.json"

            c = _make_candidate(1, cases=[1])
            detect.save_proposed([c], proposed_path)

            # Reject first
            stdin = StringIO("r\nnope\n")
            adjudicate.run_session(
                proposed_path=proposed_path,
                rejected_path=rejected_path,
                pack_path=pack_path,
                by="test",
                stdin=stdin,
            )

            # Re-detect same candidate
            detect.save_proposed([c], proposed_path)

            # Should be filtered out
            stdin2 = StringIO("")
            result = adjudicate.run_session(
                proposed_path=proposed_path,
                rejected_path=rejected_path,
                pack_path=pack_path,
                by="test",
                stdin=stdin2,
            )
            self.assertEqual(result["remaining"], 0)

    def test_adjudicated_removed_from_queue(self):
        with tempfile.TemporaryDirectory() as td:
            proposed_path = Path(td) / "rules_proposed.jsonl"
            rejected_path = Path(td) / "rules_rejected.jsonl"
            pack_path = Path(td) / "taught.json"

            c1 = _make_candidate(1, cases=[1])
            c2 = _make_candidate(2, cases=[2])
            detect.save_proposed([c1, c2], proposed_path)

            stdin = StringIO("a\n^Error: .*test\nenvironment-error\nKnown test error\n")
            result = adjudicate.run_session(
                proposed_path=proposed_path,
                rejected_path=rejected_path,
                pack_path=pack_path,
                by="test",
                stdin=stdin,
            )
            self.assertEqual(result["approved"], 1)
            remaining = detect.load_proposed(proposed_path)
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0]["id"], 2)

    def test_unrecognized_choice(self):
        with tempfile.TemporaryDirectory() as td:
            proposed_path = Path(td) / "rules_proposed.jsonl"
            rejected_path = Path(td) / "rules_rejected.jsonl"
            pack_path = Path(td) / "taught.json"

            c = _make_candidate(1, cases=[1])
            detect.save_proposed([c], proposed_path)

            stdin = StringIO("x\nq\n")
            result = adjudicate.run_session(
                proposed_path=proposed_path,
                rejected_path=rejected_path,
                pack_path=pack_path,
                by="test",
                stdin=stdin,
            )
            self.assertEqual(result["skipped"], 0)

    def test_reject_default_reason(self):
        with tempfile.TemporaryDirectory() as td:
            proposed_path = Path(td) / "rules_proposed.jsonl"
            rejected_path = Path(td) / "rules_rejected.jsonl"
            pack_path = Path(td) / "taught.json"

            c = _make_candidate(1, cases=[1])
            detect.save_proposed([c], proposed_path)

            stdin = StringIO("r\n\n")
            adjudicate.run_session(
                proposed_path=proposed_path,
                rejected_path=rejected_path,
                pack_path=pack_path,
                by="test",
                stdin=stdin,
            )
            rejected = adjudicate.load_rejected(rejected_path)
            self.assertEqual(rejected[0]["reason"], "rejected during adjudication")

    def test_approve_incomplete_fields(self):
        with tempfile.TemporaryDirectory() as td:
            proposed_path = Path(td) / "rules_proposed.jsonl"
            rejected_path = Path(td) / "rules_rejected.jsonl"
            pack_path = Path(td) / "taught.json"

            c = _make_candidate(1, cases=[1])
            detect.save_proposed([c], proposed_path)

            stdin = StringIO("a\n^Error\n\n\n")
            result = adjudicate.run_session(
                proposed_path=proposed_path,
                rejected_path=rejected_path,
                pack_path=pack_path,
                by="test",
                stdin=stdin,
            )
            self.assertEqual(result["approved"], 0)
            remaining = detect.load_proposed(proposed_path)
            self.assertEqual(len(remaining), 1)

    def test_correct_install(self):
        with tempfile.TemporaryDirectory() as td:
            proposed_path = Path(td) / "rules_proposed.jsonl"
            rejected_path = Path(td) / "rules_rejected.jsonl"
            pack_path = Path(td) / "taught.json"

            c = _make_candidate(1, cases=[1])
            detect.save_proposed([c], proposed_path)

            stdin = StringIO("c\n^Custom.*pattern\ntest-failure\nCustom diagnosis\n")
            result = adjudicate.run_session(
                proposed_path=proposed_path,
                rejected_path=rejected_path,
                pack_path=pack_path,
                by="test",
                stdin=stdin,
            )
            self.assertEqual(result["corrected"], 1)
            self.assertTrue(pack_path.exists())


if __name__ == "__main__":
    unittest.main()
