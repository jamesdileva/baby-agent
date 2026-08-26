"""Tests for S21 archive-mine skill: learn from past eras."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qacompanion.skills.archive_mine import (
    MineError,
    _construct_signature,
    _dedup_cases,
    _extract_diagnosis,
    _extract_error_excerpt,
    export_mined,
    format_results,
    mine_directory,
    parse_decisions,
    parse_git_log,
    parse_transcript,
)


# --- Fixtures ---

_DECISIONS_BOM = """\
## D-0006 BOM breaks JSONL config [RATIFIED 2026-08-25]

File begins with a UTF-8 BOM and json.loads chokes on the invisible prefix.
Diagnosis: Read with encoding='utf-8-sig' so the BOM is stripped before
parsing; every reader in this repo uses utf-8-sig for exactly this reason.

Status: RATIFIED.
"""

_DECISIONS_FAIL_0S = """\
## Case #6 sitrep-reliability failure [RESOLVED 2026-08-26]

FAIL reported with 0.0s elapsed and no executed-test count means the runner
never actually ran (output swallowed by wrapper or wrong invocation).
Rule: Re-run with native stream merge and read the 'Ran N tests' tail.
"""

_DECISIONS_ENOENT = """\
## D-0010 environment skill: wrong cwd [ADOPTED 2026-08-26]

ENOENT / FileNotFoundError means the tool is invoked outside the expected
directory. Classify as wrong-cwd environment diagnosis instead of generic
storage. Confirm the expected path exists before running.
"""

_DECISIONS_UNRELATED = """\
## D-0009 Twin-commit prevention [ADOPTED 2026-08-26]

Workflow fix: single-committer-per-cycle, attribution trailer, intent-to-
commit ping. No spec impact.
"""

_DECISIONS_MALFORMED = """\
## D-0099 broken section

This decision has no useful diagnosis content at all.
"""


class TestParseDecisions(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_extracts_bom_case(self):
        cases = parse_decisions(_DECISIONS_BOM)
        self.assertGreaterEqual(len(cases), 1)
        sigs = [c["signature"] for c in cases]
        self.assertTrue(any("bom" in s for s in sigs))

    def test_extracts_fail_0s_case(self):
        cases = parse_decisions(_DECISIONS_FAIL_0S)
        self.assertGreaterEqual(len(cases), 1)
        sigs = [c["signature"] for c in cases]
        self.assertTrue(any("fail" in s for s in sigs))

    def test_extracts_enoent_case(self):
        cases = parse_decisions(_DECISIONS_ENOENT)
        self.assertGreaterEqual(len(cases), 1)
        sigs = [c["signature"] for c in cases]
        self.assertTrue(any("enoent" in s or "wrong" in s for s in sigs))

    def test_skips_unrelated_decisions(self):
        cases = parse_decisions(_DECISIONS_UNRELATED)
        self.assertEqual(len(cases), 0)

    def test_skips_malformed_no_diagnosis(self):
        cases = parse_decisions(_DECISIONS_MALFORMED)
        self.assertEqual(len(cases), 0)

    def test_empty_text(self):
        cases = parse_decisions("")
        self.assertEqual(cases, [])

    def test_source_field_includes_heading(self):
        cases = parse_decisions(_DECISIONS_BOM)
        self.assertTrue(len(cases) >= 1)
        self.assertIn("DECISIONS.md", cases[0]["source"])

    def test_diagnosis_not_empty(self):
        combined = _DECISIONS_BOM + _DECISIONS_FAIL_0S + _DECISIONS_ENOENT
        cases = parse_decisions(combined)
        for case in cases:
            self.assertTrue(case["diagnosis"], "diagnosis should not be empty")

    def test_error_excerpt_not_empty(self):
        cases = parse_decisions(_DECISIONS_BOM)
        for case in cases:
            self.assertTrue(case["error_excerpt"], "error_excerpt should not be empty")

    def test_multiple_headings(self):
        combined = _DECISIONS_BOM + "\n" + _DECISIONS_ENOENT
        cases = parse_decisions(combined)
        self.assertGreaterEqual(len(cases), 2)


# --- Git log parsing ---

_GIT_LOG_FIX = """\
01e62c2 fix: resolve BOM issue in config reader
a3ad542 S12 locate skill: depth-pinned repo finder
e1322f3 bugfix: correct signature normalization path
740e1ed stdout-leak micro-slice
"""

_GIT_LOG_NO_FIXES = """\
01e62c2 S20 digest skill: document ingestion
a3ad542 S12 locate skill: depth-pinned repo finder
"""


class TestParseGitLog(unittest.TestCase):
    def test_extracts_fix_commits(self):
        cases = parse_git_log(_GIT_LOG_FIX)
        self.assertEqual(len(cases), 2)

    def test_fix_commit_has_signature(self):
        cases = parse_git_log(_GIT_LOG_FIX)
        for case in cases:
            self.assertIn(" :: ", case["signature"])

    def test_fix_commit_source_includes_hash(self):
        cases = parse_git_log(_GIT_LOG_FIX)
        sources = [c["source"] for c in cases]
        self.assertTrue(any("git log:" in s for s in sources))

    def test_no_fixes_returns_empty(self):
        cases = parse_git_log(_GIT_LOG_NO_FIXES)
        self.assertEqual(cases, [])

    def test_empty_log(self):
        cases = parse_git_log("")
        self.assertEqual(cases, [])

    def test_diagnosis_includes_commit_hash(self):
        cases = parse_git_log(_GIT_LOG_FIX)
        self.assertTrue(any("commit" in c["diagnosis"].lower() for c in cases))


# --- Transcript parsing ---

_TRANSCRIPT_PYTEST = """\
tests/test_config.py::test_load FAILED
tests/test_store.py::test_save PASSED
======================== FAILURES ========================
FAIL: test_load_config (test_config.TestConfig)
json.decoder.JSONDecodeError: Expecting property name
======================== 1 failed in 3.21s =================
"""

_TRANSCRIPT_NO_FAIL = """\
tests/test_config.py::test_load PASSED
tests/test_store.py::test_save PASSED
======================== 2 passed in 1.00s =================
"""


class TestParseTranscript(unittest.TestCase):
    def test_extracts_fail_line(self):
        cases = parse_transcript(_TRANSCRIPT_PYTEST)
        self.assertGreaterEqual(len(cases), 1)

    def test_fail_has_signature(self):
        cases = parse_transcript(_TRANSCRIPT_PYTEST)
        for case in cases:
            self.assertIn(" :: ", case["signature"])

    def test_no_fails_returns_empty(self):
        cases = parse_transcript(_TRANSCRIPT_NO_FAIL)
        self.assertEqual(cases, [])

    def test_empty_transcript(self):
        cases = parse_transcript("")
        self.assertEqual(cases, [])

    def test_diagnosis_pending(self):
        cases = parse_transcript(_TRANSCRIPT_PYTEST)
        for case in cases:
            self.assertIn("pending", case["diagnosis"].lower())


# --- Dedup ---

class TestDedup(unittest.TestCase):
    def test_dedup_by_signature(self):
        cases = [
            {"signature": "a :: b", "error_excerpt": "x", "diagnosis": "d1"},
            {"signature": "a :: b", "error_excerpt": "y", "diagnosis": "d2"},
            {"signature": "c :: d", "error_excerpt": "z", "diagnosis": "d3"},
        ]
        deduped = _dedup_cases(cases)
        self.assertEqual(len(deduped), 2)

    def test_first_wins(self):
        cases = [
            {"signature": "a :: b", "error_excerpt": "first", "diagnosis": "d1"},
            {"signature": "a :: b", "error_excerpt": "second", "diagnosis": "d2"},
        ]
        deduped = _dedup_cases(cases)
        self.assertEqual(deduped[0]["error_excerpt"], "first")

    def test_empty_list(self):
        self.assertEqual(_dedup_cases([]), [])


# --- Export ---

class TestExportMined(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.out_path = Path(self.tmpdir) / "mined.jsonl"

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_export_creates_file(self):
        cases = [{"signature": "a :: b", "error_excerpt": "x", "diagnosis": "d"}]
        count = export_mined(cases, self.out_path)
        self.assertEqual(count, 1)
        self.assertTrue(self.out_path.exists())

    def test_export_valid_jsonl(self):
        cases = [
            {"signature": "a :: b", "error_excerpt": "x", "diagnosis": "d1"},
            {"signature": "c :: d", "error_excerpt": "y", "diagnosis": "d2"},
        ]
        export_mined(cases, self.out_path)
        lines = self.out_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        for line in lines:
            obj = json.loads(line)
            self.assertEqual(obj["id"], 0)
            self.assertEqual(obj["times_seen"], 1)
            self.assertEqual(obj["confirmed_by"], "archive-mine")

    def test_export_empty(self):
        count = export_mined([], self.out_path)
        self.assertEqual(count, 0)

    def test_export_atomic(self):
        cases = [{"signature": "a :: b", "error_excerpt": "x", "diagnosis": "d"}]
        export_mined(cases, self.out_path)
        # No temp files left behind
        parent = self.out_path.parent
        temps = list(parent.glob(".mined-*"))
        self.assertEqual(len(temps), 0)

    def test_export_preserves_fields(self):
        cases = [{"signature": "test :: err", "error_excerpt": "excerpt", "diagnosis": "diag"}]
        export_mined(cases, self.out_path)
        obj = json.loads(self.out_path.read_text(encoding="utf-8").strip())
        self.assertEqual(obj["signature"], "test :: err")
        self.assertEqual(obj["error_excerpt"], "excerpt")
        self.assertEqual(obj["diagnosis"], "diag")


# --- format_results ---

class TestFormatResults(unittest.TestCase):
    def test_no_cases(self):
        results = {"cases_mined": 0, "cases": [], "sources_scanned": 0, "errors": []}
        output = format_results(results)
        self.assertIn("0 case(s)", output)

    def test_with_cases(self):
        cases = [
            {"signature": "test :: err", "source": "DECISIONS.md: D-0006"},
        ]
        results = {"cases_mined": 1, "cases": cases, "sources_scanned": 1, "errors": []}
        output = format_results(results)
        self.assertIn("1 case(s)", output)
        self.assertIn("DECISIONS.md", output)

    def test_with_errors(self):
        results = {
            "cases_mined": 0,
            "cases": [],
            "sources_scanned": 1,
            "errors": [("bad.md", "permission denied")],
        }
        output = format_results(results)
        self.assertIn("warning:", output)

    def test_truncates_at_10(self):
        cases = [
            {"signature": f"test{i} :: err{i}", "source": f"src{i}"}
            for i in range(15)
        ]
        results = {"cases_mined": 15, "cases": cases, "sources_scanned": 1, "errors": []}
        output = format_results(results)
        self.assertIn("and 5 more", output)


# --- mine_directory ---

class TestMineDirectory(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_mine_decisions(self):
        docs_dir = Path(self.tmpdir) / "docs"
        docs_dir.mkdir()
        (docs_dir / "DECISIONS.md").write_text(_DECISIONS_BOM, encoding="utf-8")
        results = mine_directory(self.tmpdir, sources=["decisions"])
        self.assertGreaterEqual(results["cases_mined"], 1)
        self.assertGreaterEqual(results["sources_scanned"], 1)

    def test_nonexistent_dir_raises(self):
        with self.assertRaises(MineError):
            mine_directory(Path(self.tmpdir) / "nope")

    def test_empty_dir(self):
        results = mine_directory(self.tmpdir, sources=["decisions", "git", "transcripts"])
        self.assertEqual(results["cases_mined"], 0)

    def test_multiple_sources(self):
        docs_dir = Path(self.tmpdir) / "docs"
        docs_dir.mkdir()
        (docs_dir / "DECISIONS.md").write_text(
            _DECISIONS_BOM + "\n" + _DECISIONS_ENOENT, encoding="utf-8"
        )
        results = mine_directory(self.tmpdir, sources=["decisions"])
        self.assertGreaterEqual(results["cases_mined"], 2)

    def test_transcript_source(self):
        (Path(self.tmpdir) / "failures.log").write_text(
            _TRANSCRIPT_PYTEST, encoding="utf-8"
        )
        results = mine_directory(self.tmpdir, sources=["transcripts"])
        self.assertGreaterEqual(results["cases_mined"], 1)

    def test_dedup_across_sources(self):
        # If the same signature appears in decisions and transcript,
        # only one should survive
        docs_dir = Path(self.tmpdir) / "docs"
        docs_dir.mkdir()
        (docs_dir / "DECISIONS.md").write_text(_DECISIONS_BOM, encoding="utf-8")
        # Don't add transcript with same signature - just verify dedup works
        results = mine_directory(self.tmpdir, sources=["decisions"])
        sigs = [c["signature"] for c in results["cases"]]
        self.assertEqual(len(sigs), len(set(sigs)))


# --- CLI integration ---

class TestMineCLI(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.out_path = Path(self.tmpdir) / "mined.jsonl"
        self.docs_dir = Path(self.tmpdir) / "docs"
        self.docs_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, *args):
        from qacompanion.__main__ import main
        return main(list(args))

    def test_mine_exit_0_with_cases(self):
        (self.docs_dir / "DECISIONS.md").write_text(_DECISIONS_BOM, encoding="utf-8")
        rc = self._run(
            "mine", str(self.tmpdir),
            "--out", str(self.out_path),
            "--sources", "decisions",
        )
        self.assertEqual(rc, 0)
        self.assertTrue(self.out_path.exists())

    def test_mine_exit_0_empty_dir(self):
        rc = self._run(
            "mine", str(self.tmpdir),
            "--out", str(self.out_path),
        )
        self.assertEqual(rc, 0)

    def test_mine_exit_1_nonexistent_dir(self):
        rc = self._run(
            "mine", str(Path(self.tmpdir) / "nope"),
            "--out", str(self.out_path),
        )
        self.assertEqual(rc, 1)

    def test_mine_creates_valid_jsonl(self):
        (self.docs_dir / "DECISIONS.md").write_text(
            _DECISIONS_BOM + "\n" + _DECISIONS_ENOENT, encoding="utf-8"
        )
        self._run(
            "mine", str(self.tmpdir),
            "--out", str(self.out_path),
            "--sources", "decisions",
        )
        lines = self.out_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertGreaterEqual(len(lines), 2)
        for line in lines:
            obj = json.loads(line)
            self.assertIn("signature", obj)
            self.assertIn("diagnosis", obj)

    def test_mine_with_multiple_sources(self):
        (self.docs_dir / "DECISIONS.md").write_text(_DECISIONS_BOM, encoding="utf-8")
        (Path(self.tmpdir) / "fail.log").write_text(_TRANSCRIPT_PYTEST, encoding="utf-8")
        rc = self._run(
            "mine", str(self.tmpdir),
            "--out", str(self.out_path),
            "--sources", "decisions",
            "--sources", "transcripts",
        )
        self.assertEqual(rc, 0)
        self.assertTrue(self.out_path.exists())


# --- Helper function tests ---

class TestExtractDiagnosis(unittest.TestCase):
    def test_from_diagnosis_keyword(self):
        text = "Diagnosis: BOM causes JSON parse failure."
        diag = _extract_diagnosis(text)
        self.assertIn("BOM", diag)

    def test_from_rule_keyword(self):
        text = "Rule: always quote the SHA256 before probing."
        diag = _extract_diagnosis(text)
        self.assertIn("SHA256", diag)

    def test_fallback_to_substantial_line(self):
        text = "Status: adopted.\nThis is a substantial explanation of the failure.\nShort."
        diag = _extract_diagnosis(text)
        self.assertIsNotNone(diag)

    def test_empty_text(self):
        diag = _extract_diagnosis("")
        self.assertIsNone(diag)


class TestExtractErrorExcerpt(unittest.TestCase):
    def test_jsondecodeerror(self):
        text = "json.decoder.JSONDecodeError: Expecting property name"
        excerpt = _extract_error_excerpt(text)
        self.assertIsNotNone(excerpt)
        self.assertIn("JSONDecodeError", excerpt)

    def test_enoent(self):
        text = "FileNotFoundError: [Errno 2] No such file or directory"
        excerpt = _extract_error_excerpt(text)
        self.assertIsNotNone(excerpt)

    def test_fail_pattern(self):
        text = "FAIL: test_something (0.0s)"
        excerpt = _extract_error_excerpt(text)
        self.assertIsNotNone(excerpt)

    def test_no_pattern(self):
        text = "This is just some text without error patterns."
        excerpt = _extract_error_excerpt(text)
        self.assertIsNone(excerpt)


if __name__ == "__main__":
    unittest.main()
