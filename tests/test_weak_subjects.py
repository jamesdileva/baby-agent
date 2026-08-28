"""Tests for S25 weakest-subject requests."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from qacompanion import store
from qacompanion.skills import weak_subjects


def _make_case(id, sig, err, diag="fix", times_seen=1, confirmed="test"):
    return {
        "id": id,
        "signature": sig,
        "error_excerpt": err,
        "diagnosis": diag,
        "times_seen": times_seen,
        "last_seen": "2026-08-27T00:00:00Z",
        "confirmed_by": confirmed,
    }


class TestClassifyCase(unittest.TestCase):
    def test_enoent(self):
        c = _make_case(1, "open :: file", "FileNotFoundError: No such file")
        self.assertEqual(weak_subjects.classify_case(c), "environment-error")

    def test_not_a_git_repo(self):
        c = _make_case(1, "git :: scan", "fatal: not a git repository")
        self.assertEqual(weak_subjects.classify_case(c), "environment-error")

    def test_permission_denied(self):
        c = _make_case(1, "write :: err", "Permission denied: /tmp/x")
        self.assertEqual(weak_subjects.classify_case(c), "environment-error")

    def test_json_decode(self):
        c = _make_case(1, "load :: json", "json.decoder.JSONDecodeError")
        self.assertEqual(weak_subjects.classify_case(c), "configuration-error")

    def test_bom(self):
        c = _make_case(1, "read :: bom", "UTF-8 BOM prefix in file")
        self.assertEqual(weak_subjects.classify_case(c), "configuration-error")

    def test_syntax_error(self):
        c = _make_case(1, "compile :: err", "SyntaxError: invalid syntax")
        self.assertEqual(weak_subjects.classify_case(c), "build-failure")

    def test_import_error(self):
        c = _make_case(1, "import :: err", "ModuleNotFoundError: no module")
        self.assertEqual(weak_subjects.classify_case(c), "dependency-error")

    def test_version_mismatch(self):
        c = _make_case(1, "pip :: err", "Requires-Python >=3.10")
        self.assertEqual(weak_subjects.classify_case(c), "dependency-error")

    def test_assertion_error(self):
        c = _make_case(1, "test :: err", "AssertionError: 1 != 2")
        self.assertEqual(weak_subjects.classify_case(c), "test-failure")

    def test_type_error(self):
        c = _make_case(1, "test :: err", "TypeError: unsupported operand")
        self.assertEqual(weak_subjects.classify_case(c), "test-failure")

    def test_flaky(self):
        c = _make_case(1, "test :: err", "Intermittent failure in test_x")
        self.assertEqual(weak_subjects.classify_case(c), "flaky-test")

    def test_unknown_fallback(self):
        c = _make_case(1, "misc :: event", "something happened")
        self.assertEqual(weak_subjects.classify_case(c), "unknown")

    def test_empty_case(self):
        c = _make_case(1, "", "")
        self.assertEqual(weak_subjects.classify_case(c), "unknown")

    def test_signature_matches_first(self):
        c = _make_case(1, "test :: FileNotFoundError", "details here")
        self.assertEqual(weak_subjects.classify_case(c), "environment-error")


class TestAnalyzeGaps(unittest.TestCase):
    def test_empty_store_all_empty(self):
        gaps = weak_subjects.analyze_gaps([])
        self.assertEqual(len(gaps), len(weak_subjects.CATEGORIES))
        for g in gaps:
            self.assertEqual(g["count"], 0)
            self.assertEqual(g["status"], "empty")
            self.assertIn("no cases", g["request"])

    def test_covered_category(self):
        cases = [_make_case(i, f"test{i} :: fail", "AssertionError")
                 for i in range(1, 5)]
        gaps = weak_subjects.analyze_gaps(cases)
        by_cat = {g["category"]: g for g in gaps}
        self.assertEqual(by_cat["test-failure"]["count"], 4)
        self.assertEqual(by_cat["test-failure"]["status"], "covered")
        self.assertEqual(by_cat["test-failure"]["request"], "")

    def test_thin_category(self):
        cases = [_make_case(1, "test :: fail", "AssertionError")]
        gaps = weak_subjects.analyze_gaps(cases)
        by_cat = {g["category"]: g for g in gaps}
        self.assertEqual(by_cat["test-failure"]["count"], 1)
        self.assertEqual(by_cat["test-failure"]["status"], "thin")
        self.assertIn("1 case(s)", by_cat["test-failure"]["request"])

    def test_sorted_weakest_first(self):
        cases = [
            _make_case(1, "test :: fail", "AssertionError"),
            _make_case(2, "test :: fail2", "AssertionError"),
            _make_case(3, "test :: fail3", "AssertionError"),
            _make_case(4, "open :: file", "FileNotFoundError"),
        ]
        gaps = weak_subjects.analyze_gaps(cases)
        counts = [g["count"] for g in gaps]
        self.assertEqual(counts, sorted(counts))

    def test_mixed_statuses(self):
        cases = [
            _make_case(1, "test :: fail", "AssertionError"),
            _make_case(2, "test :: fail2", "AssertionError"),
            _make_case(3, "test :: fail3", "AssertionError"),
            _make_case(4, "open :: file", "FileNotFoundError"),
            _make_case(5, "open :: file2", "FileNotFoundError"),
        ]
        gaps = weak_subjects.analyze_gaps(cases)
        by_cat = {g["category"]: g for g in gaps}
        self.assertEqual(by_cat["test-failure"]["status"], "covered")
        self.assertEqual(by_cat["environment-error"]["status"], "thin")
        self.assertEqual(by_cat["build-failure"]["status"], "empty")


class TestFormatGapReport(unittest.TestCase):
    def test_empty_store(self):
        gaps = weak_subjects.analyze_gaps([])
        text = weak_subjects.format_gap_report(gaps)
        self.assertIn("Subject coverage report", text)
        self.assertIn("teaching requests", text.lower())
        self.assertIn("!!", text)

    def test_all_covered(self):
        cases = [
            _make_case(1, "test :: fail", "AssertionError"),
            _make_case(2, "test :: fail2", "AssertionError"),
            _make_case(3, "test :: fail3", "AssertionError"),
            _make_case(4, "open :: file", "FileNotFoundError"),
            _make_case(5, "open :: file2", "FileNotFoundError"),
            _make_case(6, "open :: file3", "FileNotFoundError"),
            _make_case(7, "compile :: err", "SyntaxError"),
            _make_case(8, "compile :: err2", "SyntaxError"),
            _make_case(9, "compile :: err3", "SyntaxError"),
            _make_case(10, "import :: err", "ModuleNotFoundError"),
            _make_case(11, "import :: err2", "ModuleNotFoundError"),
            _make_case(12, "import :: err3", "ModuleNotFoundError"),
            _make_case(13, "pip :: err", "pip install failed"),
            _make_case(14, "pip :: err2", "pip install failed"),
            _make_case(15, "pip :: err3", "pip install failed"),
            _make_case(16, "test :: flaky", "Intermittent timeout"),
            _make_case(17, "test :: flaky2", "Intermittent timeout"),
            _make_case(18, "test :: flaky3", "Intermittent timeout"),
            _make_case(19, "misc :: event", "something happened"),
            _make_case(20, "misc :: event2", "something happened"),
            _make_case(21, "misc :: event3", "something happened"),
            _make_case(22, "load :: json", "JSONDecodeError: Expecting property"),
            _make_case(23, "load :: json2", "JSONDecodeError: Expecting property"),
            _make_case(24, "load :: json3", "JSONDecodeError: Expecting property"),
        ]
        gaps = weak_subjects.analyze_gaps(cases)
        text = weak_subjects.format_gap_report(gaps)
        self.assertIn("All subjects adequately covered", text)

    def test_thin_marker(self):
        cases = [_make_case(1, "test :: fail", "AssertionError")]
        gaps = weak_subjects.analyze_gaps(cases)
        text = weak_subjects.format_gap_report(gaps)
        self.assertIn("! ", text)


class TestTrackGapFill(unittest.TestCase):
    def test_empty_to_thin(self):
        before = []
        after = [_make_case(1, "test :: fail", "AssertionError")]
        fills = weak_subjects.track_gap_fill(before, after)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0]["category"], "test-failure")
        self.assertEqual(fills[0]["filled"], "empty->thin")

    def test_thin_to_covered(self):
        before = [_make_case(1, "test :: fail", "AssertionError")]
        after = before + [
            _make_case(i, f"test{i} :: fail", "AssertionError")
            for i in range(2, 5)
        ]
        fills = weak_subjects.track_gap_fill(before, after)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0]["filled"], "thin->covered")

    def test_no_change(self):
        before = [_make_case(1, "test :: fail", "AssertionError")]
        after = [_make_case(1, "test :: fail", "AssertionError")]
        fills = weak_subjects.track_gap_fill(before, after)
        self.assertEqual(fills, [])

    def test_no_regression(self):
        before = [_make_case(i, f"test{i} :: fail", "AssertionError")
                  for i in range(1, 5)]
        after = before[:2]
        fills = weak_subjects.track_gap_fill(before, after)
        self.assertEqual(fills, [])

    def test_multiple_fills(self):
        before = []
        after = [
            _make_case(1, "test :: fail", "AssertionError"),
            _make_case(2, "open :: file", "FileNotFoundError"),
        ]
        fills = weak_subjects.track_gap_fill(before, after)
        cats = [f["category"] for f in fills]
        self.assertIn("test-failure", cats)
        self.assertIn("environment-error", cats)

    def test_preserves_order(self):
        fills = [
            {"category": "a", "before": 0, "after": 1, "filled": "empty->thin"},
            {"category": "z", "before": 0, "after": 1, "filled": "empty->thin"},
        ]
        result = weak_subjects.format_gap_fill(fills)
        lines = result.split("\n")
        self.assertIn("a", lines[1])
        self.assertIn("z", lines[2])


class TestFormatGapFill(unittest.TestCase):
    def test_empty_returns_empty(self):
        self.assertEqual(weak_subjects.format_gap_fill([]), "")

    def test_single_fill(self):
        fills = [{"category": "test-failure", "before": 0, "after": 1,
                  "filled": "empty->thin"}]
        text = weak_subjects.format_gap_fill(fills)
        self.assertIn("Gap fills:", text)
        self.assertIn("test-failure", text)
        self.assertIn("0 -> 1", text)
        self.assertIn("empty->thin", text)


class TestRunAnalysis(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cases_path = Path(self.tmpdir) / "cases.jsonl"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_cases(self, cases):
        with open(self.cases_path, "w", encoding="utf-8") as f:
            for c in cases:
                f.write(json.dumps(c) + "\n")

    def test_empty_store(self):
        self._write_cases([])
        gaps, cases = weak_subjects.run_analysis(self.cases_path)
        self.assertEqual(cases, [])
        self.assertEqual(len(gaps), len(weak_subjects.CATEGORIES))

    def test_mixed_cases(self):
        self._write_cases([
            _make_case(1, "test :: fail", "AssertionError"),
            _make_case(2, "open :: file", "FileNotFoundError"),
            _make_case(3, "pip :: err", "ModuleNotFoundError"),
        ])
        gaps, cases = weak_subjects.run_analysis(self.cases_path)
        self.assertEqual(len(cases), 3)
        by_cat = {g["category"]: g for g in gaps}
        self.assertEqual(by_cat["test-failure"]["count"], 1)
        self.assertEqual(by_cat["environment-error"]["count"], 1)
        self.assertEqual(by_cat["dependency-error"]["count"], 1)
        self.assertEqual(by_cat["build-failure"]["count"], 0)


class TestCliIntegration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cases_path = Path(self.tmpdir) / "cases.jsonl"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_cases(self, cases):
        with open(self.cases_path, "w", encoding="utf-8") as f:
            for c in cases:
                f.write(json.dumps(c) + "\n")

    def test_gaps_command_empty(self):
        from qacompanion.__main__ import main
        self._write_cases([])
        with mock_environ(self.cases_path):
            rc = main(["gaps"])
        self.assertEqual(rc, 0)

    def test_gaps_command_with_cases(self):
        from qacompanion.__main__ import main
        self._write_cases([
            _make_case(1, "test :: fail", "AssertionError"),
        ])
        with mock_environ(self.cases_path):
            rc = main(["gaps"])
        self.assertEqual(rc, 0)

    def test_gaps_exit_code_on_corrupt(self):
        from qacompanion.__main__ import main
        self.cases_path.write_text("NOT JSON", encoding="utf-8")
        with mock_environ(self.cases_path):
            rc = main(["gaps"])
        self.assertEqual(rc, 1)


class TestConstants(unittest.TestCase):
    def test_categories_are_strings(self):
        for cat in weak_subjects.CATEGORIES:
            self.assertIsInstance(cat, str)

    def test_thin_threshold_positive(self):
        self.assertGreater(weak_subjects.THIN_THRESHOLD, 0)

    def test_categories_unique(self):
        self.assertEqual(len(weak_subjects.CATEGORIES),
                         len(set(weak_subjects.CATEGORIES)))


class TestPatterns(unittest.TestCase):
    def test_all_categories_matchable(self):
        """Each non-unknown category has at least one pattern."""
        seen = set()
        for _, cat in weak_subjects._PATTERNS:
            seen.add(cat)
        for cat in weak_subjects.CATEGORIES:
            if cat == "unknown":
                continue
            self.assertIn(cat, seen, f"category {cat!r} has no patterns")


class TestCliWiring(unittest.TestCase):
    """Verify gaps is registered in the CLI."""

    def test_gaps_in_commands(self):
        from qacompanion import __main__
        self.assertIn("gaps", __main__._COMMANDS)

    def test_gaps_parser_exists(self):
        from qacompanion.__main__ import build_parser
        parser = build_parser()
        args = parser.parse_args(["gaps"])
        self.assertEqual(args.command, "gaps")

    def test_gaps_parser_with_cases(self):
        from qacompanion.__main__ import build_parser
        parser = build_parser()
        args = parser.parse_args(["gaps", "--cases", "/tmp/x.jsonl"])
        self.assertEqual(args.command, "gaps")
        self.assertEqual(args.cases, "/tmp/x.jsonl")


# --- helpers ---

class mock_environ:
    """Context manager that sets QA_CASES_FILE and restores on exit."""
    def __init__(self, path):
        self.path = str(path)
        self._old = None

    def __enter__(self):
        self._old = os.environ.get(store.ENV_OVERRIDE)
        os.environ[store.ENV_OVERRIDE] = self.path
        return self

    def __exit__(self, *exc):
        if self._old is None:
            os.environ.pop(store.ENV_OVERRIDE, None)
        else:
            os.environ[store.ENV_OVERRIDE] = self._old
        return False


if __name__ == "__main__":
    unittest.main()
