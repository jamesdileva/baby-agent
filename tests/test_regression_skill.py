"""S10 regression skill tests: seeded histories, boundary rules, golden.

Per reviewer TASK mail #93: every detection test is driven by SEEDED
histories built through the store + sidecar APIs in-process (record with
fixed stamps, observe_command_pass with fixed stamps); exactly ONE test
exercises the real `qa run` hook end-to-end, with stamps normalized
afterwards so the assertion stays deterministic despite wall-clock ties.
"""

import contextlib
import io
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from qacompanion import report as report_mod
from qacompanion import store
from qacompanion.__main__ import main
from qacompanion.skills import auto_capture, flaky, regression

BASE = datetime(2026, 8, 25, 10, 0, 0, tzinfo=timezone.utc)


def t(seconds):
    return BASE + timedelta(seconds=seconds)


class RegressionSeedingTests(unittest.TestCase):
    """Detection rules over in-process seeded histories."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cases_path = Path(self._tmp.name) / "cases.jsonl"
        patcher = mock.patch.dict(os.environ, {store.ENV_OVERRIDE: str(self.cases_path)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def record_fail(self, sig, moment):
        store.CaseStore().record(
            signature=sig, error_excerpt="e", diagnosis="d", now=moment
        )

    def passes(self, argv_text, moments):
        for moment in moments:
            flaky.FlakeStore().observe_command_pass(argv_text, now=moment)

    def state(self):
        return store.CaseStore().load(), flaky.FlakeStore().load()

    def seed_regression(self):
        """Red red | green green green | red -> 3/6 = exactly 50%."""
        self.record_fail("cmd-r :: err: boom", t(1))
        self.record_fail("cmd-r :: err: boom", t(2))
        self.passes("cmd-r", [t(3), t(4), t(5)])
        self.record_fail("cmd-r :: err: boom", t(6))

    def seed_chronic_return(self):
        """red | green green green | red -> 3/5 = 60%, chronic."""
        self.record_fail("cmd-c :: err: fizz", t(1))
        self.passes("cmd-c", [t(2), t(3), t(4)])
        self.record_fail("cmd-c :: err: fizz", t(5))

    def seed_ordinary(self):
        """Many reds, two greens, return: below N, never a regression."""
        for second in (1, 2, 3, 4, 5):
            self.record_fail("cmd-o :: err: wobble", t(second))
        self.passes("cmd-o", [t(6), t(7)])
        self.record_fail("cmd-o :: err: wobble", t(8))

    def test_regression_detected_on_seeded_history(self):
        self.seed_regression()
        regressions, first_time = regression.classify(*self.state())
        self.assertEqual([1], [case["id"] for case, _ in regressions])
        self.assertEqual([], first_time)

    def test_chronic_return_is_flake_bounce_never_regression(self):
        self.seed_chronic_return()
        regressions, first_time = regression.classify(*self.state())
        self.assertEqual([], regressions)
        self.assertEqual([], first_time)

    def test_below_min_clean_passes_is_not_regression(self):
        self.seed_ordinary()
        regressions, first_time = regression.classify(*self.state())
        self.assertEqual([], regressions)
        self.assertEqual([], first_time)

    def test_zero_pass_signatures_never_regressions(self):
        self.record_fail("cmd-z :: err: once", t(1))  # first-time failure
        self.record_fail("cmd-y :: err: repeat", t(1))
        self.record_fail("cmd-y :: err: repeat", t(2))
        self.record_fail("cmd-y :: err: repeat", t(3))  # repeats, still zero passes
        regressions, first_time = regression.classify(*self.state())
        self.assertEqual([], regressions)
        self.assertEqual([1], [case["id"] for case in first_time])

    def test_returning_while_currently_green_not_regression(self):
        self.record_fail("cmd-g :: err: old", t(1))
        self.passes("cmd-g", [t(2), t(3), t(4)])  # last event is green
        regressions, _ = regression.classify(*self.state())
        self.assertEqual([], regressions)

    def test_stamp_tie_conservatively_not_regression(self):
        # last failure lands in the same second as the last green pass.
        self.record_fail("cmd-t :: err: tie", t(1))
        self.record_fail("cmd-t :: err: tie", t(2))
        self.passes("cmd-t", [t(3), t(3), t(3)])
        self.record_fail("cmd-t :: err: tie", t(3))
        regressions, _ = regression.classify(*self.state())
        self.assertEqual([], regressions)

    def test_detection_is_read_only_over_store_and_sidecar(self):
        self.seed_regression()
        cases_before = self.cases_path.read_bytes()
        sidecar_before = flaky.default_path().read_bytes()
        regression.classify(*self.state())
        regression.format_regressions(*self.state())
        self.assertEqual(cases_before, self.cases_path.read_bytes())
        self.assertEqual(sidecar_before, flaky.default_path().read_bytes())

    def test_format_blocks_deterministic_with_none_fallback(self):
        self.assertEqual(
            "regressions (returned after >=3 clean passes):\nnone\n"
            "first-time failures (single sighting, never passed):\nnone",
            regression.format_regressions([], []),
        )
        self.seed_regression()
        text = regression.format_regressions(*self.state())
        self.assertEqual(text, regression.format_regressions(*self.state()))
        self.assertIn(
            "case #1 times_seen=3 passes=3 "
            "last_green=2026-08-25T10:00:05Z sig: cmd-r :: err: boom",
            text,
        )


class RegressionCliTests(unittest.TestCase):
    """Golden report output + the single real-hook e2e (mail #93)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store_path = Path(self._tmp.name) / "cases.jsonl"
        patcher = mock.patch.dict(os.environ, {store.ENV_OVERRIDE: str(self.store_path)})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(auto_capture.GUARD_ENV, None)

    def record_fail(self, sig, moment):
        store.CaseStore().record(
            signature=sig, error_excerpt="e", diagnosis="d", now=moment
        )

    def passes(self, argv_text, moments):
        for moment in moments:
            flaky.FlakeStore().observe_command_pass(argv_text, now=moment)

    def report_output(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(0, main(["report"]))
        return stdout.getvalue()

    def test_golden_report_separates_regressions_prominently(self):
        self.record_fail("cmd-r :: err: boom", t(1))
        self.record_fail("cmd-r :: err: boom", t(2))
        self.passes("cmd-r", [t(3), t(4), t(5)])
        self.record_fail("cmd-r :: err: boom", t(6))  # #1 regression, exactly 50%
        self.record_fail("cmd-c :: err: fizz", t(1))
        self.passes("cmd-c", [t(2), t(3), t(4)])
        self.record_fail("cmd-c :: err: fizz", t(5))  # #2 chronic bounce, 60%
        self.record_fail("cmd-f :: err: new", t(7))  # #3 first-time failure
        expected = "\n".join(
            [
                "total cases: 3",
                "top 5 by times_seen:",
                "case #1 times_seen=3 sig: cmd-r :: err: boom",
                "case #2 times_seen=2 sig: cmd-c :: err: fizz",
                "case #3 times_seen=1 sig: cmd-f :: err: new",
                "stale (>30d):",
                "none",
                "accuracy: n/a - golden fixture",
                "chronic (>50% pass rate):",
                "case #2 times_seen=2 passes=3 rate=60.0% sig: cmd-c :: err: fizz",
                "flaky history (<=50% pass rate):",
                "case #1 times_seen=3 passes=3 rate=50.0% sig: cmd-r :: err: boom",
                "regressions (returned after >=3 clean passes):",
                "case #1 times_seen=3 passes=3 "
                "last_green=2026-08-25T10:00:05Z sig: cmd-r :: err: boom",
                "first-time failures (single sighting, never passed):",
                "case #3 times_seen=1 sig: cmd-f :: err: new",
            ]
        )
        with mock.patch.object(
            report_mod, "accuracy_line", return_value="accuracy: n/a - golden fixture"
        ):
            self.assertEqual(expected + "\n", self.report_output())

    def test_e2e_red_green_red_through_qa_run_surfaces_regression(self):
        counter = str(Path(self._tmp.name) / "count")
        child = (
            "import sys, pathlib\n"
            f"c = pathlib.Path({counter!r})\n"
            "n = (int(c.read_text()) + 1) if c.exists() else 1\n"
            "c.write_text(str(n))\n"
            "if n <= 2 or n >= 6:\n"
            "    sys.stderr.write('FAIL: test_loop\\n')\n"
            "    sys.exit(1)\n"
            "sys.exit(0)\n"
        )
        codes = []
        for _ in range(6):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
                codes.append(main(["run", "--", "python", "-c", child]))
        self.assertEqual([1, 1, 0, 0, 0, 1], codes)
        # Normalize stamps so the assertion ignores wall-clock ties; the
        # capture wiring itself was exercised by the six live runs above.
        cases = store.CaseStore().load()
        entries = flaky.FlakeStore().load()
        cases[0]["last_seen"] = "2026-08-25T12:00:06Z"
        entries[0]["last_pass"] = "2026-08-25T12:00:05Z"
        store.CaseStore().save(cases)
        flaky.FlakeStore().save(entries)
        text = self.report_output()
        self.assertIn("regressions (returned after >=3 clean passes):", text)
        self.assertIn(
            "case #1 times_seen=3 passes=3 "
            "last_green=2026-08-25T12:00:05Z sig:",
            text,
        )


if __name__ == "__main__":
    unittest.main()
