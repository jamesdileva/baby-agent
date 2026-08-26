"""CLI dispatch tests for the record subcommand (exit-code policy)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qacompanion.__main__ import main
from qacompanion import store


class RecordCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store_path = Path(self._tmp.name) / "cases.jsonl"
        patcher = mock.patch.dict(os.environ, {store.ENV_OVERRIDE: str(self.store_path)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_record_exit_zero_and_case_persisted(self):
        code = main(["record", "--sig", "s", "--err", "e", "--diag", "d"])
        self.assertEqual(0, code)
        cases = store.CaseStore(self.store_path).load()
        # canonical() gate: bare "s" has no separator, so it normalizes to
        # test-part "s" with an empty error part.
        self.assertEqual("s :: ", cases[0]["signature"])

    def test_record_attribution_lands_in_store(self):
        main(["record", "--sig", "s", "--err", "e", "--diag", "d", "--by", "tess"])
        (case,) = store.CaseStore(self.store_path).load()
        self.assertEqual("tess", case["confirmed_by"])

    def test_second_record_bumps_times_seen(self):
        argv = ["record", "--sig", "s", "--err", "e", "--diag", "d"]
        main(argv)
        code = main(argv)
        self.assertEqual(0, code)
        (case,) = store.CaseStore(self.store_path).load()
        self.assertEqual(2, case["times_seen"])

    def test_missing_required_flag_exits_nonzero(self):
        with self.assertRaises(SystemExit) as ctx:
            main(["record", "--sig", "s"])
        self.assertNotEqual(0, ctx.exception.code)

    def test_corrupt_store_exits_one_without_touching_file(self):
        self.store_path.write_text("{corrupt}\n", encoding="utf-8")
        before = self.store_path.read_bytes()
        code = main(["record", "--sig", "s", "--err", "e", "--diag", "d"])
        self.assertEqual(1, code)
        self.assertEqual(before, self.store_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
