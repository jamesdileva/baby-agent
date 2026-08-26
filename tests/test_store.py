"""Tests for qacompanion.store — strict loading, robustness, record/bump."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from qacompanion import store

FIXTURE = Path(__file__).parent / "fixtures" / "sample_cases.jsonl"

VALID_CASE = {
    "id": 1,
    "signature": "test_login::assertion_error",
    "error_excerpt": "AssertionError: expected 200 got 500",
    "diagnosis": "session cookie expired mid-run",
    "times_seen": 2,
    "last_seen": "2026-08-21T12:00:00Z",
    "confirmed_by": "agent-a",
}


def write_store(tmp, text):
    path = Path(tmp) / "cases.jsonl"
    path.write_bytes(text.encode("utf-8"))
    return path


def case_json(**overrides):
    case = dict(VALID_CASE)
    case.update(overrides)
    return json.dumps(case)


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


class LoadTests(TempDirTest):
    def test_load_valid_fixture(self):
        cases = store.CaseStore(FIXTURE).load()
        self.assertEqual([1, 2], [case["id"] for case in cases])
        self.assertEqual("test_preflight::fail(0.0s)", cases[0]["signature"])

    def test_missing_file_loads_empty(self):
        self.assertEqual([], store.CaseStore(self.tmp / "absent.jsonl").load())

    def test_bom_prefix_is_stripped(self):
        path = write_store(self.tmp, "﻿" + case_json() + "\n")
        cases = store.CaseStore(path).load()
        self.assertEqual([1], [case["id"] for case in cases])

    def test_crlf_line_endings_tolerated(self):
        path = write_store(self.tmp, case_json() + "\r\n" + case_json(id=2) + "\r\n")
        cases = store.CaseStore(path).load()
        self.assertEqual([1, 2], [case["id"] for case in cases])

    def test_missing_trailing_newline_tolerated(self):
        path = write_store(self.tmp, case_json())
        cases = store.CaseStore(path).load()
        self.assertEqual([1], [case["id"] for case in cases])

    def test_blank_lines_skipped(self):
        path = write_store(self.tmp, "\n" + case_json() + "\n\n")
        self.assertEqual(1, len(store.CaseStore(path).load()))

    def test_malformed_json_names_line_number(self):
        path = write_store(self.tmp, case_json() + "\n{not json}\n")
        with self.assertRaises(ValueError) as ctx:
            store.CaseStore(path).load()
        self.assertIn("line 2", str(ctx.exception))

    def test_non_object_line_rejected(self):
        path = write_store(self.tmp, "[1, 2]\n")
        with self.assertRaises(ValueError) as ctx:
            store.CaseStore(path).load()
        self.assertIn("line 1", str(ctx.exception))

    def test_non_int_id_rejected(self):
        path = write_store(self.tmp, case_json(id="7") + "\n")
        with self.assertRaises(ValueError) as ctx:
            store.CaseStore(path).load()
        self.assertIn("'id'", str(ctx.exception))

    def test_boolean_id_rejected_even_though_bool_is_int(self):
        path = write_store(self.tmp, case_json(id=True) + "\n")
        with self.assertRaises(ValueError):
            store.CaseStore(path).load()

    def test_missing_diagnosis_rejected(self):
        broken = {key: value for key, value in VALID_CASE.items() if key != "diagnosis"}
        path = write_store(self.tmp, json.dumps(broken) + "\n")
        with self.assertRaises(ValueError) as ctx:
            store.CaseStore(path).load()
        self.assertIn("diagnosis", str(ctx.exception))

    def test_non_string_signature_rejected(self):
        path = write_store(self.tmp, case_json(signature=42) + "\n")
        with self.assertRaises(ValueError):
            store.CaseStore(path).load()

    def test_unparseable_last_seen_rejected(self):
        path = write_store(self.tmp, case_json(last_seen="yesterday") + "\n")
        with self.assertRaises(ValueError) as ctx:
            store.CaseStore(path).load()
        self.assertIn("line 1", str(ctx.exception))

    def test_ids_must_strictly_increase(self):
        path = write_store(self.tmp, case_json(id=2) + "\n" + case_json(id=2) + "\n")
        with self.assertRaises(ValueError) as ctx:
            store.CaseStore(path).load()
        self.assertIn("line 2", str(ctx.exception))


class RecordTests(TempDirTest):
    def test_record_inserts_new_case_with_increasing_id(self):
        path = self.tmp / "cases.jsonl"
        case, created = store.CaseStore(path).record(
            "sig-a", "err", "diag", by="agent-b"
        )
        self.assertTrue(created)
        self.assertEqual(1, case["id"])
        self.assertEqual(1, case["times_seen"])
        self.assertEqual("agent-b", case["confirmed_by"])

    def test_record_bumps_matching_signature(self):
        path = self.tmp / "cases.jsonl"
        first, _ = store.CaseStore(path).record("sig-a", "err-1", "diag-1")
        second, created = store.CaseStore(path).record(
            "sig-a", "err-2", "diag-2", by="tess"
        )
        self.assertFalse(created)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(2, second["times_seen"])
        self.assertEqual("diag-2", second["diagnosis"])
        self.assertEqual("tess", second["confirmed_by"])
        self.assertEqual(1, len(store.CaseStore(path).load()))

    def test_distinct_signatures_do_not_bump_each_other(self):
        path = self.tmp / "cases.jsonl"
        store.CaseStore(path).record("sig-a", "e", "d")
        case, created = store.CaseStore(path).record("sig-b", "e", "d")
        self.assertTrue(created)
        self.assertEqual(2, case["id"])

    def test_last_seen_stamp_is_iso_utc_z(self):
        path = self.tmp / "cases.jsonl"
        case, _ = store.CaseStore(path).record("sig-a", "e", "d")
        parsed = datetime.fromisoformat(case["last_seen"].replace("Z", "+00:00"))
        self.assertIsNotNone(parsed.tzinfo)

    def test_explicit_now_overrides_clock(self):
        path = self.tmp / "cases.jsonl"
        fixed = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        case, _ = store.CaseStore(path).record("sig-a", "e", "d", now=fixed)
        self.assertEqual("2026-01-02T03:04:05Z", case["last_seen"])

    def test_corrupt_store_record_aborts_without_partial_write(self):
        good_text = case_json() + "\n"
        path = write_store(self.tmp, good_text + "{corrupt}\n")
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            store.CaseStore(path).record("sig-new", "e", "d")
        self.assertEqual(before, path.read_bytes())


class EnvOverrideTests(TempDirTest):
    def test_default_path_prefers_env_override(self):
        override = self.tmp / "override.jsonl"
        with mock.patch.dict(
            os.environ, {store.ENV_OVERRIDE: str(override)}
        ):
            self.assertEqual(override, store.default_path())
            self.assertEqual(override, store.CaseStore().path)
        fallback = Path(store.DEFAULT_PATH)
        self.assertEqual(fallback, store.CaseStore().path)

    def test_explicit_path_beats_env_override(self):
        override = self.tmp / "override.jsonl"
        explicit = self.tmp / "explicit.jsonl"
        with mock.patch.dict(os.environ, {store.ENV_OVERRIDE: str(override)}):
            self.assertEqual(explicit, store.CaseStore(explicit).path)


if __name__ == "__main__":
    unittest.main()
