"""Report subcommand: totals, top-N ranking, stale-case surfacing."""

import contextlib
import io
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from qacompanion.__main__ import main
from qacompanion import report as report_mod
from qacompanion import store

NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)


def make_case(case_id, signature, times_seen=1, last_seen="2026-08-26T00:00:00Z"):
    return {
        "id": case_id,
        "signature": signature,
        "error_excerpt": "e",
        "diagnosis": "d",
        "times_seen": times_seen,
        "last_seen": last_seen,
        "confirmed_by": "unknown",
    }


class TopCasesTests(unittest.TestCase):
    def test_ranks_by_times_seen_desc_then_id_asc(self):
        cases = [
            make_case(4, "d :: w", times_seen=2),
            make_case(2, "b :: y", times_seen=7),
            make_case(1, "a :: x", times_seen=7),
        ]
        ranked = report_mod.top_cases(cases)
        self.assertEqual([1, 2, 4], [case["id"] for case in ranked])

    def test_caps_at_five_entries(self):
        cases = [make_case(i, f"s{i} :: e") for i in range(1, 8)]
        self.assertEqual(5, len(report_mod.top_cases(cases)))


class StaleTests(unittest.TestCase):
    def test_exactly_30_days_old_is_not_stale(self):
        case = make_case(1, "s :: e", last_seen="2026-07-27T00:00:00Z")
        self.assertFalse(report_mod.is_stale(case, now=NOW))

    def test_31_days_old_is_stale(self):
        case = make_case(1, "s :: e", last_seen="2026-07-26T00:00:00Z")
        self.assertTrue(report_mod.is_stale(case, now=NOW))

    def test_naive_last_seen_is_treated_as_utc_not_crash(self):
        case = make_case(1, "s :: e", last_seen="2026-01-01T00:00:00")
        self.assertTrue(report_mod.is_stale(case, now=NOW))

    def test_stale_cases_keep_load_order(self):
        cases = [
            make_case(3, "c :: z", last_seen="2026-01-03T00:00:00Z"),
            make_case(1, "a :: x"),
            make_case(2, "b :: y", last_seen="2026-01-02T00:00:00Z"),
        ]
        stale = report_mod.stale_cases(cases, now=NOW)
        self.assertEqual([3, 2], [case["id"] for case in stale])


class FormatReportTests(unittest.TestCase):
    def test_golden_output_on_fixture_base(self):
        cases = [
            make_case(1, "a :: x", times_seen=7, last_seen="2026-08-20T00:00:00Z"),
            make_case(2, "b :: y", times_seen=7, last_seen="2026-07-01T00:00:00Z"),
            make_case(3, "c :: z", times_seen=3),
        ]
        expected = "\n".join(
            [
                "total cases: 3",
                "top 5 by times_seen:",
                "case #1 times_seen=7 sig: a :: x",
                "case #2 times_seen=7 sig: b :: y",
                "case #3 times_seen=3 sig: c :: z",
                "stale (>30d):",
                "case #2 last_seen=2026-07-01T00:00:00Z sig: b :: y",
            ]
        )
        self.assertEqual(expected, report_mod.format_report(cases, now=NOW))

    def test_empty_base_states_zero_and_none_honestly(self):
        expected = "\n".join(
            [
                "total cases: 0",
                "top 5 by times_seen:",
                "none",
                "stale (>30d):",
                "none",
            ]
        )
        self.assertEqual(expected, report_mod.format_report([], now=NOW))


class ReportCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store_path = Path(self._tmp.name) / "cases.jsonl"
        patcher = mock.patch.dict(
            os.environ, {store.ENV_OVERRIDE: str(self.store_path)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_report_on_missing_store_exits_zero_with_empty_summary(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["report"])
        self.assertEqual(0, code)
        self.assertIn("total cases: 0", buffer.getvalue())

    def test_report_reflects_recorded_cases(self):
        main(["record", "--sig", "sig :: one", "--err", "e", "--diag", "d"])
        main(["record", "--sig", "sig :: one", "--err", "e", "--diag", "d"])
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["report"])
        self.assertEqual(0, code)
        self.assertIn("total cases: 1", buffer.getvalue())
        self.assertIn("case #1 times_seen=2 sig: sig :: one", buffer.getvalue())

    def test_corrupt_store_exits_one(self):
        self.store_path.write_text("{bad}\n", encoding="utf-8")
        code = main(["report"])
        self.assertEqual(1, code)


if __name__ == "__main__":
    unittest.main()
