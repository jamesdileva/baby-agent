"""S22 school mode tests — interactive session walking unconfirmed diagnoses.

Pins: pending = confirmed_by 'unknown', confirm/correct atomic writes,
session summary format, CLI exit contract.
"""

import io
import os
import tempfile
import unittest
from pathlib import Path

from qacompanion import store
from qacompanion.skills import school


def _make_case(sig="sig-alpha", err="error text", diag="diagnosis text",
               cid=1, times=1, confirmed="unknown"):
    return {
        "id": cid,
        "signature": sig,
        "error_excerpt": err,
        "diagnosis": diag,
        "times_seen": times,
        "last_seen": "2026-01-01T00:00:00Z",
        "confirmed_by": confirmed,
    }


class SchoolPendingTests(unittest.TestCase):
    """Unit tests for get_pending_cases()."""

    def test_empty_cases(self):
        self.assertEqual(school.get_pending_cases([]), [])

    def test_no_pending(self):
        cases = [_make_case(confirmed="agent-a")]
        self.assertEqual(school.get_pending_cases(cases), [])

    def test_one_pending(self):
        pending = _make_case(confirmed="unknown")
        confirmed = _make_case(confirmed="agent-a", cid=2)
        result = school.get_pending_cases([pending, confirmed])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], 1)

    def test_multiple_pending(self):
        c1 = _make_case(cid=1, confirmed="unknown")
        c2 = _make_case(cid=2, confirmed="unknown")
        c3 = _make_case(cid=3, confirmed="human")
        result = school.get_pending_cases([c1, c2, c3])
        self.assertEqual(len(result), 2)


class SchoolConfirmTests(unittest.TestCase):
    """Unit tests for confirm_case()."""

    def test_confirm_sets_by(self):
        case = _make_case(confirmed="unknown")
        result = school.confirm_case(case, "human")
        self.assertEqual(result["confirmed_by"], "human")

    def test_confirm_returns_same_dict(self):
        case = _make_case(confirmed="unknown")
        result = school.confirm_case(case, "agent-b")
        self.assertIs(result, case)


class SchoolCorrectTests(unittest.TestCase):
    """Unit tests for correct_case()."""

    def test_correct_updates_diagnosis(self):
        case = _make_case(confirmed="unknown")
        result = school.correct_case(case, "human", "new diagnosis")
        self.assertEqual(result["diagnosis"], "new diagnosis")
        self.assertEqual(result["confirmed_by"], "human")

    def test_correct_returns_same_dict(self):
        case = _make_case(confirmed="unknown")
        result = school.correct_case(case, "human", "fixed")
        self.assertIs(result, case)


class SchoolFormatTests(unittest.TestCase):
    """Unit tests for format functions."""

    def test_format_case_shows_id(self):
        case = _make_case(cid=42)
        text = school.format_case(case, 1, 3)
        self.assertIn("Case #42", text)
        self.assertIn("1/3", text)

    def test_format_case_truncates_long_sig(self):
        case = _make_case(sig="x" * 200)
        text = school.format_case(case, 1, 1)
        self.assertIn("...", text)

    def test_format_session_summary_zero(self):
        text = school.format_session_summary(0, 0, 0, 0)
        self.assertIn("0 case(s) processed", text)

    def test_format_session_summary_full(self):
        text = school.format_session_summary(5, 3, 1, 1)
        self.assertIn("5 case(s) processed", text)
        self.assertIn("confirmed: 3", text)
        self.assertIn("corrected: 1", text)
        self.assertIn("new cases created: 1", text)


class SchoolRunSessionTests(unittest.TestCase):
    """Unit tests for run_session() with mocked stdin."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cases_path = os.path.join(self.tmpdir, "cases.jsonl")

    def _write_cases(self, cases):
        cs = store.CaseStore(self.cases_path)
        cs.save(cases)

    def test_empty_pending(self):
        self._write_cases([])
        cs = store.CaseStore(self.cases_path)
        result = school.run_session(cs, by="human")
        self.assertEqual(result["processed"], 0)

    def test_all_confirmed(self):
        self._write_cases([
            _make_case(cid=1, confirmed="unknown"),
            _make_case(cid=2, confirmed="unknown"),
        ])
        cs = store.CaseStore(self.cases_path)
        stdin = io.StringIO("c\nc\n")
        result = school.run_session(cs, by="human", stdin=stdin)
        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["confirmed"], 2)
        # Verify persistence
        cases = cs.load()
        self.assertEqual(cases[0]["confirmed_by"], "human")
        self.assertEqual(cases[1]["confirmed_by"], "human")

    def test_quit_stops_early(self):
        self._write_cases([
            _make_case(cid=1, confirmed="unknown"),
            _make_case(cid=2, confirmed="unknown"),
        ])
        cs = store.CaseStore(self.cases_path)
        stdin = io.StringIO("c\nq\n")
        result = school.run_session(cs, by="human", stdin=stdin)
        self.assertEqual(result["processed"], 1)
        # Second case still unconfirmed
        cases = cs.load()
        self.assertEqual(cases[1]["confirmed_by"], "unknown")

    def test_correct_updates_diagnosis(self):
        self._write_cases([_make_case(cid=1, confirmed="unknown")])
        cs = store.CaseStore(self.cases_path)
        stdin = io.StringIO("e\nfixed diagnosis\n")
        result = school.run_session(cs, by="human", stdin=stdin)
        self.assertEqual(result["corrected"], 1)
        cases = cs.load()
        self.assertEqual(cases[0]["diagnosis"], "fixed diagnosis")
        self.assertEqual(cases[0]["confirmed_by"], "human")

    def test_skip_leaves_case_unconfirmed(self):
        self._write_cases([_make_case(cid=1, confirmed="unknown")])
        cs = store.CaseStore(self.cases_path)
        stdin = io.StringIO("s\n")
        result = school.run_session(cs, by="human", stdin=stdin)
        self.assertEqual(result["processed"], 0)
        cases = cs.load()
        self.assertEqual(cases[0]["confirmed_by"], "unknown")

    def test_new_case_creation(self):
        self._write_cases([_make_case(cid=1, confirmed="unknown")])
        cs = store.CaseStore(self.cases_path)
        stdin = io.StringIO("n\nnew-sig\nnew-err\nnew-diag\n")
        result = school.run_session(cs, by="human", stdin=stdin)
        self.assertEqual(result["created"], 1)
        cases = cs.load()
        self.assertEqual(len(cases), 2)
        # signature is canonicalized
        self.assertIn("new-sig", cases[1]["signature"])

    def test_limit_restricts_cases(self):
        self._write_cases([
            _make_case(cid=1, confirmed="unknown"),
            _make_case(cid=2, confirmed="unknown"),
            _make_case(cid=3, confirmed="unknown"),
        ])
        cs = store.CaseStore(self.cases_path)
        stdin = io.StringIO("c\n")
        result = school.run_session(cs, by="human", limit=1, stdin=stdin)
        self.assertEqual(result["processed"], 1)
        cases = cs.load()
        self.assertEqual(cases[1]["confirmed_by"], "unknown")

    def test_empty_new_case_fields_skipped(self):
        self._write_cases([_make_case(cid=1, confirmed="unknown")])
        cs = store.CaseStore(self.cases_path)
        # n with empty sig -> skipped
        stdin = io.StringIO("n\n\n\n\n")
        result = school.run_session(cs, by="human", stdin=stdin)
        self.assertEqual(result["created"], 0)

    def test_empty_correct_diagnosis_skipped(self):
        self._write_cases([_make_case(cid=1, confirmed="unknown")])
        cs = store.CaseStore(self.cases_path)
        stdin = io.StringIO("e\n\n")
        result = school.run_session(cs, by="human", stdin=stdin)
        self.assertEqual(result["corrected"], 0)

    def test_unknown_choice_skipped(self):
        self._write_cases([_make_case(cid=1, confirmed="unknown")])
        cs = store.CaseStore(self.cases_path)
        stdin = io.StringIO("x\n")
        result = school.run_session(cs, by="human", stdin=stdin)
        self.assertEqual(result["processed"], 0)


class SchoolCLITests(unittest.TestCase):
    """CLI exit contract tests through main()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cases_path = os.path.join(self.tmpdir, "cases.jsonl")

    def _write_cases(self, cases):
        cs = store.CaseStore(self.cases_path)
        cs.save(cases)

    def test_exit_0_no_pending(self):
        from qacompanion.__main__ import main
        self._write_cases([])
        ret = main(["school", "--by", "human", "--cases", self.cases_path])
        self.assertEqual(ret, 0)

    def test_exit_0_with_confirm(self):
        from qacompanion.__main__ import main
        self._write_cases([_make_case(cid=1, confirmed="unknown")])
        # Simulate stdin with confirm
        import sys
        old_stdin = sys.stdin
        sys.stdin = io.StringIO("c\n")
        try:
            ret = main(["school", "--by", "human", "--cases", self.cases_path])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(ret, 0)

    def test_requires_by(self):
        from qacompanion.__main__ import main
        with self.assertRaises(SystemExit):
            main(["school", "--cases", self.cases_path])


class SchoolSessionSummaryTests(unittest.TestCase):
    """Verify summary format consistency."""

    def test_summary_lines(self):
        text = school.format_session_summary(10, 7, 2, 1)
        lines = text.split("\n")
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("school session complete:"))
        self.assertIn("confirmed: 7", lines[1])
        self.assertIn("corrected: 2", lines[2])
        self.assertIn("new cases created: 1", lines[3])

    def test_summary_minimal(self):
        text = school.format_session_summary(1, 1, 0, 0)
        lines = text.split("\n")
        self.assertEqual(len(lines), 2)


if __name__ == "__main__":
    unittest.main()
