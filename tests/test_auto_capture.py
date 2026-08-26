"""S7 auto-capture tests: wrap, capture, record - with a real failing child.

Fixture-only coverage is insufficient for capture paths (AGENTS.md
verification culture): the e2e tests here drive actual subprocesses.
"""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from qacompanion import store
from qacompanion.__main__ import main
from qacompanion.skills import auto_capture
from tests import quiet_stdout


class AutoCaptureUnitTests(unittest.TestCase):
    def test_parse_failure_signature_uses_last_nonempty_line(self):
        signature, _ = auto_capture.parse_failure(
            "pytest -k boom", "collected 3 items\nE   AssertionError: nope\n"
        )
        self.assertIn("assertionerror: nope", signature)
        self.assertIn("pytest -k boom ::", signature)

    def test_parse_failure_empty_output_uses_placeholder(self):
        signature, excerpt = auto_capture.parse_failure("tool arg", "")
        self.assertIn(auto_capture.NO_OUTPUT_PLACEHOLDER, signature)
        self.assertEqual("", excerpt)

    def test_signature_stable_across_volatile_summary_counts(self):
        """Regression for the S8 hard-gate failure mode: the SAME failing
        cmd must yield an identical signature even when only the runner's
        summary counts differ between runs (FAIL-volatile @e1322f3)."""
        body = (
            "FAIL: test_a (__main__.T.test_a)\n"
            "Traceback (most recent call last):\n"
            "AssertionError: boom\n"
        )
        two = body + "\nRan 2 tests in 0.001s\nFAILED (failures=2)\n"
        three = body + "\nRan 3 tests in 0.001s\nFAILED (failures=3)\n"
        sig_two, _ = auto_capture.parse_failure("python -m unittest", two)
        sig_three, _ = auto_capture.parse_failure("python -m unittest", three)
        self.assertEqual(sig_two, sig_three)
        self.assertIn("fail: test_a", sig_two)

    def test_summary_only_output_never_keys_the_summary_line(self):
        """Strip-before-scan ordering keeps '^FAILED (failures=N)' from
        being misread as a FAIL marker."""
        one, _ = auto_capture.parse_failure("cmd", "FAILED (failures=1)\n")
        two, _ = auto_capture.parse_failure("cmd", "FAILED (failures=2)\n")
        self.assertEqual(one, two)
        self.assertIn(auto_capture.NO_OUTPUT_PLACEHOLDER, one)

    def test_first_error_marker_line_wins_over_later_noise(self):
        out = (
            "starting suite\n"
            "ERROR: test_z (__main__.T.test_z)\n"
            "FAIL: test_a (__main__.T.test_a)\n"
            "Ran 5 tests in 0.002s\nFAILED (failures=2)\n"
        )
        signature, _ = auto_capture.parse_failure("cmd", out)
        self.assertIn("error: test_z", signature)

    def test_markerless_generic_commands_keep_last_line_rule(self):
        out = "progress 40%\nE   AssertionError: nope\n"
        signature, _ = auto_capture.parse_failure("pytest -k boom", out)
        self.assertIn("assertionerror: nope", signature)

    def test_parse_failure_bounds_excerpt_and_flags_truncation(self):
        big = "x" * (auto_capture.MAX_EXCERPT_CHARS + 50)
        _, excerpt = auto_capture.parse_failure("cmd", big)
        self.assertTrue(excerpt.startswith("[truncated] "))
        self.assertLessEqual(
            len(excerpt), len("[truncated] ") + auto_capture.MAX_EXCERPT_CHARS
        )

    def test_diagnosis_is_honest_placeholder_not_fabrication(self):
        text = auto_capture.build_diagnosis("npm test", 1)
        self.assertIn("exit 1", text)
        self.assertIn("pending teacher review", text)

    def test_execute_passes_argv_list_without_shell(self):
        with mock.patch.object(
            auto_capture.subprocess, "run", return_value=CompletedProcess([], 0)
        ) as spawn:
            auto_capture.execute(["some-tool", "--flag; rm -rf"])
        spawn.assert_called_once()
        args, kwargs = spawn.call_args
        self.assertEqual(["some-tool", "--flag; rm -rf"], args[0])
        self.assertFalse(kwargs["shell"])
        self.assertEqual("1", kwargs["env"][auto_capture.GUARD_ENV])


class AutoCaptureCliTests(unittest.TestCase):
    """E2E through main() against an isolated temp store."""

    def setUp(self):
        self.stdout_buf = quiet_stdout(self)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store_path = Path(self._tmp.name) / "cases.jsonl"
        patcher = mock.patch.dict(os.environ, {store.ENV_OVERRIDE: str(self.store_path)})
        patcher.start()
        self.addCleanup(patcher.stop)
        env_cleaner = mock.patch.dict(os.environ, {}, clear=False)
        env_cleaner.start()
        self.addCleanup(env_cleaner.stop)
        os.environ.pop(auto_capture.GUARD_ENV, None)

    def load_cases(self):
        return store.CaseStore(self.store_path).load()

    def test_success_exit_zero_records_nothing(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(["run", "--", "python", "-c", "pass"])
        self.assertEqual(0, code)
        self.assertFalse(self.store_path.exists())
        self.assertNotIn("case #", stderr.getvalue())

    def test_real_failing_command_recorded_with_passthrough(self):
        child = (
            "import sys; sys.stderr.write('BOOM-marker\\n'); "
            "sys.stdout.write('partial progress\\n'); raise SystemExit(3)"
        )
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(["run", "--", "python", "-c", child])
        merged = stderr.getvalue()
        self.assertEqual(3, code)  # exact exit-code passthrough
        self.assertIn("BOOM-marker", merged)  # real child stderr preserved
        self.assertIn("partial progress", merged)  # stdout stream also visible
        cases = self.load_cases()
        self.assertEqual(1, len(cases))  # exactly one append, no double-record
        case = cases[0]
        self.assertIn("partial progress", case["signature"])  # documented rule: last line
        self.assertIn("BOOM-marker", case["error_excerpt"])  # parsed real output
        self.assertEqual(auto_capture.CONFIRMED_BY, case["confirmed_by"])

    def test_repeat_failure_bumps_single_case(self):
        failing = ["run", "--", "python", "-c", "raise SystemExit(2)"]
        for _ in range(2):
            with contextlib.redirect_stderr(io.StringIO()):
                code = main(failing)
        self.assertEqual(2, code)
        cases = self.load_cases()
        self.assertEqual(1, len(cases))
        self.assertEqual(2, cases[0]["times_seen"])

    def test_nested_qa_run_refused_before_execution(self):
        self.store_path.write_text("", encoding="utf-8")
        before = self.store_path.read_bytes()
        os.environ[auto_capture.GUARD_ENV] = "1"
        try:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = main(["run", "--", "python", "-c", "pass"])
        finally:
            os.environ.pop(auto_capture.GUARD_ENV, None)
        self.assertEqual(1, code)
        self.assertIn("recursion guard", stderr.getvalue())
        self.assertEqual(before, self.store_path.read_bytes())

    def test_missing_command_rejected_nonzero(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(1, main(["run"]))
            self.assertEqual(1, main(["run", "--"]))

    def test_spawn_failure_maps_to_one(self):
        missing = str(Path(self._tmp.name) / "definitely-not-here.exe")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(["run", "--", missing])
        self.assertEqual(1, code)
        self.assertIn("error:", stderr.getvalue())

    def test_corrupt_store_keeps_child_exit_code_with_warning(self):
        self.store_path.write_text("{corrupt}\n", encoding="utf-8")
        before = self.store_path.read_bytes()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(["run", "--", "python", "-c", "raise SystemExit(5)"])
        self.assertEqual(5, code)  # child result never masked by store failure
        self.assertIn("auto-record failed", stderr.getvalue())
        self.assertEqual(before, self.store_path.read_bytes())


class StoreIsolationTests(unittest.TestCase):
    def setUp(self):
        self.stdout_buf = quiet_stdout(self)

    def test_env_override_routes_auto_record_to_isolated_store(self):
        """A QA_CASES_FILE-wrapped run lands ONLY in the override store.

        Verified as a byte-for-byte non-touch of the repo-root store
        rather than by counting confirmed_by=auto-capture rows there:
        since case #7 (TASK #11 discharge, D-0010) the live base
        legitimately HOLDS auto-capture cases, so the old zero-rows
        heuristic misfired. Byte comparison proves the same isolation
        property regardless of live-store history.
        """
        with tempfile.TemporaryDirectory() as tmp:
            isolated = Path(tmp) / "isolated.jsonl"
            live = Path(store.DEFAULT_PATH)
            live_before = live.read_bytes() if live.exists() else None
            with mock.patch.dict(os.environ, {store.ENV_OVERRIDE: str(isolated)}):
                os.environ.pop(auto_capture.GUARD_ENV, None)
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = main(
                        ["run", "--", "python", "-c", "raise SystemExit(1)"]
                    )
            self.assertEqual(1, code)
            self.assertTrue(isolated.exists())  # went to override, not repo base
            if live_before is None:
                self.assertFalse(live.exists())
            else:
                self.assertEqual(live_before, live.read_bytes())


if __name__ == "__main__":
    unittest.main()
