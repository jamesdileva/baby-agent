"""S9 environment skill tests: classification + capture-time integration.

Fixture suite covers every environment class plus honest unsure fallback
(ROADMAP S9 exit). Fixture-only coverage is insufficient for capture
paths (AGENTS.md verification culture): e2e tests drive real subprocesses
through `qa run` for both halves - a classified ENOENT child and an
unclassifiable child that must keep the legacy placeholder.
"""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qacompanion import store
from qacompanion.__main__ import main
from qacompanion.skills import auto_capture, environment


class ClassifyUnitTests(unittest.TestCase):
    def test_empty_repo_classifies(self):
        text = (
            "git log\n"
            "fatal: not a git repository (or any of the parent directories): .git\n"
        )
        env_class, evidence = environment.classify(text)
        self.assertEqual("empty repo", env_class)
        self.assertIn("not a git repository", evidence)

    def test_version_mismatch_variants(self):
        for text in (
            "Unsupported engine version: requires node >=18",
            "ERROR: requires python >=3.10",
            "pip: version mismatch between pkg and metadata",
        ):
            env_class, _ = environment.classify(text)
            self.assertEqual("version mismatch", env_class, text)

    def test_permission_denied_variants(self):
        for text in (
            "PermissionError: [Errno 13] Permission denied: 'lock'",
            "[WinError 5] Access is denied.",
            "npm ERR! code EPERM",
            "git: eacces writing pack",
        ):
            env_class, _ = environment.classify(text)
            self.assertEqual("permission denied", env_class, text)

    def test_tool_missing_variants(self):
        for text in (
            "'foo' is not recognized as an internal or external command, "
            "operable program or batch file.",
            "/bin/sh: 1: foo: command not found",
            "ModuleNotFoundError: No module named 'requests'",
        ):
            env_class, _ = environment.classify(text)
            self.assertEqual("tool missing", env_class, text)

    def test_wrong_cwd_enoent_variants(self):
        for text in (
            "FileNotFoundError: [Errno 2] No such file or directory: 'cfg.json'",
            "npm ERR! code ENOENT",
            "IOError: [Errno 2] No such file or directory: 'data.csv'",
        ):
            env_class, _ = environment.classify(text)
            self.assertEqual("wrong cwd", env_class, text)

    def test_unknown_output_stays_honestly_unsure(self):
        self.assertEqual(
            (environment.UNSURE, None),
            environment.classify("AssertionError: boom\n"),
        )
        self.assertEqual(
            (environment.UNSURE, None), environment.classify("")
        )
        self.assertIsNone(environment.diagnose("AssertionError: boom\n"))

    def test_matching_is_case_insensitive(self):
        env_class, _ = environment.classify("FATAL: NOT A GIT REPOSITORY")
        self.assertEqual("empty repo", env_class)

    def test_rule_order_is_deterministic_specific_before_generic(self):
        combined = (
            "ModuleNotFoundError: No module named 'tool'\n"
            "FileNotFoundError: [Errno 2] No such file or directory: 'x'\n"
        )
        env_class, _ = environment.classify(combined)
        self.assertEqual("tool missing", env_class)

    def test_full_output_scanned_not_just_tail(self):
        text = "npm ERR! code ENOENT\nnpm ERR! syscall spawn git\nA complete log...\n"
        env_class, _ = environment.classify(text)
        self.assertEqual("wrong cwd", env_class)

    def test_build_diagnosis_names_class_and_teacher_path(self):
        text = environment.build_diagnosis("wrong cwd")
        self.assertIn("Environment failure (wrong cwd)", text)
        self.assertIn("not found", text)


class EnvironmentCaptureCliTests(unittest.TestCase):
    """E2E through main(): classified vs unclassified captured failures."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store_path = Path(self._tmp.name) / "cases.jsonl"
        patcher = mock.patch.dict(os.environ, {store.ENV_OVERRIDE: str(self.store_path)})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(auto_capture.GUARD_ENV, None)

    def load_cases(self):
        return store.CaseStore(self.store_path).load()

    def qa_run(self, child):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(["run", "--", "python", "-c", child])
        return code, stderr.getvalue()

    def test_real_enoent_child_gets_environment_diagnosis(self):
        child = (
            "open('qa-probe-missing.tmp', encoding='utf-8').read()\n"
        )
        code, merged = self.qa_run(child)
        self.assertEqual(1, code)
        cases = self.load_cases()
        self.assertEqual(1, len(cases))
        case = cases[0]
        self.assertEqual(auto_capture.CONFIRMED_BY, case["confirmed_by"])
        self.assertTrue(
            case["diagnosis"].startswith(
                "Environment failure (wrong cwd)"
            ),
            case["diagnosis"],
        )
        self.assertIn("No such file or directory", case["error_excerpt"])

    def test_unclassifiable_child_keeps_legacy_placeholder(self):
        code, _ = self.qa_run("raise SystemExit(4)")
        self.assertEqual(4, code)
        cases = self.load_cases()
        self.assertEqual(1, len(cases))
        diagnosis = cases[0]["diagnosis"]
        self.assertIn("exit 4", diagnosis)
        self.assertIn("pending teacher review", diagnosis)

    def test_classification_never_changes_signature_or_exit_passthrough(self):
        child = (
            "import sys\n"
            "sys.stderr.write('fatal: not a git repository\\n')\n"
            "raise SystemExit(7)\n"
        )
        code, _ = self.qa_run(child)
        self.assertEqual(7, code)
        case = self.load_cases()[0]
        expected_sig, _ = auto_capture.parse_failure(
            "python -c " + child.replace("\n", " "),
            "fatal: not a git repository\n",
        )
        self.assertEqual(expected_sig, case["signature"])
        self.assertIn("(empty repo)", case["diagnosis"])


if __name__ == "__main__":
    unittest.main()
