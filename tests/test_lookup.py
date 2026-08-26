"""Lookup honesty states: known, unknown, ambiguous; plus CLI wiring."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qacompanion.__main__ import main
from qacompanion import lookup
from qacompanion import store


def make_case(case_id, signature, diagnosis, times_seen=1):
    return {
        "id": case_id,
        "signature": signature,
        "error_excerpt": "e",
        "diagnosis": diagnosis,
        "times_seen": times_seen,
        "last_seen": "2026-08-26T00:00:00Z",
        "confirmed_by": "unknown",
    }


class SelectTests(unittest.TestCase):
    def test_only_exact_signature_matches_selected(self):
        cases = [make_case(1, "a :: x", "A"), make_case(2, "b :: y", "B")]
        matches = lookup.select(cases, "b :: y")
        self.assertEqual([2], [case["id"] for case in matches])

    def test_no_match_returns_empty_list(self):
        self.assertEqual([], lookup.select([], "missing :: sig"))


class FormatMatchesTests(unittest.TestCase):
    def test_unknown_state_is_exact_sentinel(self):
        self.assertEqual("no matching case", lookup.format_matches([]))

    def test_known_state_prints_id_times_seen_diagnosis(self):
        text = lookup.format_matches([make_case(3, "s", "check the BOM")])
        self.assertIn("case #3", text)
        self.assertIn("times_seen=1", text)
        self.assertIn("diagnosis: check the BOM", text)

    def test_duplicate_signature_is_ambiguous_not_silent(self):
        matches = [
            make_case(5, "dup", "second choice", times_seen=9),
            make_case(2, "dup", "first choice", times_seen=4),
        ]
        text = lookup.format_matches(matches)
        self.assertIn("AMBIGUOUS - teacher review required", text)
        self.assertIn("#5", text)
        self.assertIn("#2", text)
        self.assertLess(text.index("#5"), text.index("#2"))


class LookupCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store_path = Path(self._tmp.name) / "cases.jsonl"
        patcher = mock.patch.dict(
            os.environ, {store.ENV_OVERRIDE: str(self.store_path)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_unknown_signature_exits_zero_with_sentinel(self):
        code = main(["record", "--sig", "known :: s", "--err", "e", "--diag", "d"])
        self.assertEqual(0, code)
        sentinel_hit = main(["lookup", "--sig", "unknown :: t"])
        self.assertEqual(0, sentinel_hit)

    def test_lookup_after_record_finds_the_case(self):
        main(["record", "--sig", "sig :: one", "--err", "e", "--diag", "blame BOM"])
        cases = store.CaseStore(self.store_path).load()
        formatted = lookup.format_matches(lookup.select(cases, "sig :: one"))
        self.assertIn("diagnosis: blame BOM", formatted)

    def test_corrupt_store_exits_one(self):
        self.store_path.write_text("{bad}\n", encoding="utf-8")
        self.assertEqual(1, main(["lookup", "--sig", "s"]))


class CrossPathE2eTests(unittest.TestCase):
    """Teacher-loop failure mode: record and lookup spellings must not
    have to agree; canonical() is the one gate both commands pass through."""

    WIN_SIG = "tests/test_config.py::test_load :: FileNotFoundError: C:\\Users\\j\\proj\\data\\config.json"
    POSIX_SIG = "tests/test_config.py::test_load :: filenotfounderror: /home/j/proj/data/config.json"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store_path = Path(self._tmp.name) / "cases.jsonl"
        patcher = mock.patch.dict(
            os.environ, {store.ENV_OVERRIDE: str(self.store_path)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_record_windows_spelling_lookup_posix_hits_same_case(self):
        code = main(["record", "--sig", self.WIN_SIG, "--err", "no file", "--diag", "check cwd"])
        self.assertEqual(0, code)
        hit = main(["lookup", "--sig", self.POSIX_SIG])
        self.assertEqual(0, hit)

    def test_stored_signature_is_canonical_and_bumps_across_spellings(self):
        main(["record", "--sig", self.WIN_SIG, "--err", "e", "--diag", "d"])
        main(["record", "--sig", self.POSIX_SIG, "--err", "e", "--diag", "d"])
        (case,) = store.CaseStore(self.store_path).load()
        self.assertEqual(
            "test_config.py::test_load :: filenotfounderror: config.json",
            case["signature"],
        )
        self.assertEqual(2, case["times_seen"])


if __name__ == "__main__":
    unittest.main()
