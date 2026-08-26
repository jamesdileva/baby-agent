"""S8 flaky skill tests: pass-after-fail tracking, chronic separation.

Fixture-only coverage is insufficient for capture paths (AGENTS.md
verification culture): the e2e tests drive real subprocesses through
`qa run` for BOTH halves of the sequence - the recorded failure and
the later zero-exit rerun of the SAME command that updates flake stats
(stateful children flip from red to green between runs).
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
from qacompanion.skills import auto_capture, flaky
from tests import quiet_stdout


class FlakyUnitTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cases_path = Path(self._tmp.name) / "cases.jsonl"
        patcher = mock.patch.dict(os.environ, {store.ENV_OVERRIDE: str(self.cases_path)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def seed_failure(self, suffix="boom"):
        store.CaseStore().record(
            signature=f"cmd :: err: {suffix}",
            error_excerpt="err: boom",
            diagnosis="d",
        )

    def test_pass_bumps_existing_case_never_creates_one(self):
        self.seed_failure()
        rows = flaky.FlakeStore().observe_command_pass("cmd")
        self.assertEqual(1, len(rows))
        self.assertEqual(1, rows[0]["times_passed"])
        again = flaky.FlakeStore().observe_command_pass("cmd")
        self.assertEqual(2, again[0]["times_passed"])
        self.assertEqual(1, len(store.CaseStore().load()))

    def test_pass_with_no_recorded_failures_writes_nothing(self):
        self.assertEqual([], flaky.FlakeStore().observe_command_pass("never-seen"))
        self.assertFalse(self.cases_path.exists())
        self.assertFalse(flaky.default_path().exists())

    def test_command_prefix_isolates_cases(self):
        self.seed_failure()
        self.assertEqual([], flaky.FlakeStore().observe_command_pass("other --flag"))

    def test_rate_boundaries_chronic_is_strictly_over_half(self):
        case = {"times_seen": 1}
        self.assertEqual(0.5, flaky.pass_rate(case, 1))
        self.assertFalse(flaky.is_chronic(case, 1))
        self.assertTrue(flaky.is_chronic(case, 2))
        self.assertTrue(flaky.is_chronic({"times_seen": 2}, 3))

    def test_corrupt_sidecar_load_names_the_line(self):
        path = Path(self._tmp.name) / "flakes.jsonl"
        path.write_text('{"signature": "x"}\n', encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            flaky.FlakeStore(path).load()
        self.assertIn("line 1", str(ctx.exception))

    def test_attach_stats_hides_orphans_and_orders_by_id(self):
        self.seed_failure()  # id 1
        store.CaseStore().record(
            signature="cmd-b :: err: b", error_excerpt="e", diagnosis="d"
        )  # id 2
        entries = [
            {
                "signature": "orphan :: gone",
                "times_passed": 9,
                "last_pass": "2026-01-01T00:00:00Z",
            },
            {
                "signature": "cmd :: err: boom",
                "times_passed": 1,
                "last_pass": "2026-01-01T00:00:00Z",
            },
        ]
        joined = flaky.attach_stats(store.CaseStore().load(), entries)
        self.assertEqual([1], [case["id"] for case, _ in joined])
        self.assertEqual(1, joined[0][1])

    def test_format_flakes_sections_and_determinism(self):
        self.seed_failure()  # id 1, times_seen=1 -> 2 passes => chronic
        flaky.FlakeStore().observe_command_pass("cmd")
        flaky.FlakeStore().observe_command_pass("cmd")
        cases = store.CaseStore().load()
        entries = flaky.FlakeStore().load()
        one = flaky.format_flakes(cases, entries)
        self.assertEqual(one, flaky.format_flakes(cases, entries))
        self.assertIn("chronic (>50% pass rate):", one)
        self.assertIn("case #1 times_seen=1 passes=2 rate=66.7%", one)
        self.assertIn("flaky history (<=50% pass rate):\nnone", one)


class FlakyCliTests(unittest.TestCase):
    """E2E through main(): fail via `qa run`, pass later via same cmd."""

    def setUp(self):
        self.stdout_buf = quiet_stdout(self)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store_path = Path(self._tmp.name) / "cases.jsonl"
        patcher = mock.patch.dict(os.environ, {store.ENV_OVERRIDE: str(self.store_path)})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(auto_capture.GUARD_ENV, None)

    def flaky_child(self, name):
        """Red on first run (writes marker), green on later runs."""
        marker = str(Path(self._tmp.name) / f"{name}.marker")
        return (
            "import sys, pathlib\n"
            f"p = pathlib.Path({marker!r})\n"
            "if p.exists():\n"
            "    sys.exit(0)\n"
            "p.write_text('x')\n"
            f"sys.stderr.write('FAIL: test_{name}\\n')\n"
            "sys.exit(1)\n"
        )

    def qa_run(self, child):
        stderr = io.StringIO()
        stdout = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            code = main(["run", "--", "python", "-c", child])
        return code, stdout.getvalue(), stderr.getvalue()

    def flakes_output(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(0, main(["flakes"]))
        return stdout.getvalue()

    def test_fail_then_pass_updates_flake_stats_end_to_end(self):
        code, _, _ = self.qa_run(self.flaky_child("alpha"))
        self.assertEqual(1, code)
        code, out, err = self.qa_run(self.flaky_child("alpha"))
        self.assertEqual(0, code)
        self.assertEqual("", err)
        self.assertIn("pass counted case #1 times_passed=1", out)
        text = self.flakes_output()
        self.assertIn("chronic (>50% pass rate):\nnone", text)
        self.assertIn("flaky history (<=50% pass rate):", text)
        self.assertIn("case #1 times_seen=1 passes=1 rate=50.0%", text)

    def test_chronic_surfaces_separately_from_ordinary_failures(self):
        alpha = self.flaky_child("alpha")
        self.qa_run(alpha)  # case #1 recorded
        self.qa_run(self.flaky_child("beta"))  # case #2, never passes again
        self.qa_run(alpha)  # pass 1 -> 50%
        self.qa_run(alpha)  # pass 2 -> 66.7% => chronic
        lines = self.flakes_output().splitlines()
        chronic_idx = lines.index("chronic (>50% pass rate):")
        history_idx = lines.index("flaky history (<=50% pass rate):")
        self.assertIn("case #1 times_seen=1 passes=2 rate=66.7%", lines[chronic_idx + 1])
        self.assertEqual("none", lines[history_idx + 1])
        self.assertNotIn("case #2", "\n".join(lines))

    def test_report_flags_flakes_only_once_evidence_exists(self):
        before = io.StringIO()
        with contextlib.redirect_stdout(before):
            main(["report"])
        self.assertNotIn("pass rate", before.getvalue())
        alpha = self.flaky_child("alpha")
        self.qa_run(alpha)
        self.qa_run(alpha)
        after = io.StringIO()
        with contextlib.redirect_stdout(after):
            self.assertEqual(0, main(["report"]))
        self.assertIn("chronic (>50% pass rate)", after.getvalue())

    def test_stats_failure_on_passing_run_never_masks_exit_zero(self):
        alpha = self.flaky_child("alpha")
        self.qa_run(alpha)  # legit case first
        self.store_path.write_text("{corrupt}\n", encoding="utf-8")
        code, out, err = self.qa_run(alpha)
        self.assertEqual(0, code)
        self.assertNotIn("pass counted", out)
        self.assertIn("pass counting failed", err)

    def test_corrupt_sidecar_exits_one_via_flakes_cli(self):
        (self.store_path.parent / flaky.SIDECAR_NAME).write_text(
            "{bad json}\n", encoding="utf-8"
        )
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(["flakes"])
        self.assertEqual(1, code)
        self.assertIn("error:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
