"""Export/import: byte-stable round-trip, atomic rejection, D-0005 dup policy."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qacompanion.__main__ import main
from qacompanion import store


def make_case(case_id, signature, diagnosis="d", times_seen=1):
    return {
        "id": case_id,
        "signature": signature,
        "error_excerpt": "e",
        "diagnosis": diagnosis,
        "times_seen": times_seen,
        "last_seen": "2026-08-26T00:00:00Z",
        "confirmed_by": "unknown",
    }


def write_jsonl(path, cases):
    payload = "".join(json.dumps(case) + "\n" for case in cases)
    path.write_text(payload, encoding="utf-8", newline="\n")
    return path


class TransportCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store_path = Path(self._tmp.name) / "cases.jsonl"
        patcher = mock.patch.dict(
            os.environ, {store.ENV_OVERRIDE: str(self.store_path)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _seed(self):
        cases = [
            make_case(1, "a :: x", diagnosis="fix a", times_seen=2),
            make_case(2, "b :: y", diagnosis="fix b"),
        ]
        store.CaseStore(self.store_path).save(cases)
        return cases

    def _run(self, *argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(list(argv))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_export_is_byte_identical_to_the_live_file(self):
        self._seed()
        out = Path(self._tmp.name) / "copy.jsonl"
        code, out_text, _ = self._run("export", "--out", str(out))
        self.assertEqual(0, code)
        self.assertEqual(self.store_path.read_bytes(), out.read_bytes())
        self.assertIn("exported 2 case(s)", out_text)

    def test_export_of_missing_store_writes_an_empty_valid_base(self):
        out = Path(self._tmp.name) / "empty.jsonl"
        code, _, _ = self._run("export", "--out", str(out))
        self.assertEqual(0, code)
        self.assertEqual(b"", out.read_bytes())

    def test_corrupt_live_store_exits_one_and_writes_nothing(self):
        self.store_path.write_text("{bad}\n", encoding="utf-8")
        out = Path(self._tmp.name) / "never.jsonl"
        code, _, err = self._run("export", "--out", str(out))
        self.assertEqual(1, code)
        self.assertFalse(out.exists())
        self.assertIn("error:", err)

    def test_unwritable_out_path_exits_one(self):
        self._seed()
        blocked = Path(self._tmp.name) / "blocked"
        blocked.write_text("", encoding="utf-8")
        code, _, err = self._run("export", "--out", str(blocked / "out.jsonl"))
        self.assertEqual(1, code)
        self.assertIn("error:", err)

    def test_round_trip_preserves_ids_and_bytes(self):
        self._seed()
        copy = Path(self._tmp.name) / "rt.jsonl"
        self._run("export", "--out", str(copy))
        self.store_path.unlink()
        code, out_text, _ = self._run("import", "--in", str(copy))
        self.assertEqual(0, code)
        self.assertEqual(copy.read_bytes(), self.store_path.read_bytes())
        loaded = store.CaseStore(self.store_path).load()
        self.assertEqual([1, 2], [case["id"] for case in loaded])
        self.assertIn("imported 2 new case(s), merged 0; store holds 2", out_text)

    def test_replace_drops_live_only_cases(self):
        self._seed()
        incoming = write_jsonl(
            Path(self._tmp.name) / "incoming.jsonl", [make_case(9, "c :: z")]
        )
        code, _, _ = self._run("import", "--in", str(incoming))
        self.assertEqual(0, code)
        (only,) = store.CaseStore(self.store_path).load()
        self.assertEqual(("c :: z", 9), (only["signature"], only["id"]))

    def test_corrupt_import_leaves_live_untouched(self):
        self._seed()
        before = self.store_path.read_bytes()
        incoming = Path(self._tmp.name) / "corrupt.jsonl"
        incoming.write_text(
            json.dumps(make_case(3, "c :: z")) + "\n{oops}\n", encoding="utf-8"
        )
        code, _, err = self._run("import", "--in", str(incoming))
        self.assertEqual(1, code)
        self.assertEqual(before, self.store_path.read_bytes())
        self.assertIn("line 2", err)

    def test_vs_live_duplicate_rejected_naming_line_and_signature(self):
        self._seed()
        before = self.store_path.read_bytes()
        incoming = write_jsonl(
            Path(self._tmp.name) / "dup.jsonl",
            [make_case(7, "fresh :: one"), make_case(8, "a :: x")],
        )
        code, _, err = self._run("import", "--in", str(incoming))
        self.assertEqual(1, code)
        self.assertEqual(before, self.store_path.read_bytes())
        self.assertIn("line 2: a :: x", err)

    def test_intra_file_duplicates_rejected_naming_both_lines(self):
        incoming = write_jsonl(
            Path(self._tmp.name) / "twins.jsonl",
            [make_case(7, "twin :: sig"), make_case(8, "twin :: sig")],
        )
        code, _, err = self._run("import", "--in", str(incoming))
        self.assertEqual(1, code)
        self.assertIn("line 1: twin :: sig", err)
        self.assertIn("line 2: twin :: sig", err)

    def test_missing_import_file_exits_one_not_silent_replace(self):
        ghost = Path(self._tmp.name) / "ghost.jsonl"
        code, _, err = self._run("import", "--in", str(ghost))
        self.assertEqual(1, code)
        self.assertFalse(self.store_path.exists())
        self.assertIn("not found", err)

    def test_merge_folds_counts_without_touching_stored_fields(self):
        live_case = make_case(
            1, "a :: x", diagnosis="teacher corrected", times_seen=2
        )
        live_case["confirmed_by"] = "human"
        live_case["error_excerpt"] = "live excerpt"
        live_case["last_seen"] = "2026-01-01T00:00:00Z"
        store.CaseStore(self.store_path).save([live_case])
        incoming_case = make_case(
            5, "a :: x", diagnosis="older wrong note", times_seen=3
        )
        incoming_case["confirmed_by"] = "seeded-lore"
        incoming = write_jsonl(
            Path(self._tmp.name) / "m.jsonl", [incoming_case]
        )
        code, out_text, _ = self._run("import", "--in", str(incoming), "--merge")
        self.assertEqual(0, code)
        (case,) = store.CaseStore(self.store_path).load()
        self.assertEqual(5, case["times_seen"])
        self.assertEqual("teacher corrected", case["diagnosis"])
        self.assertEqual("human", case["confirmed_by"])
        self.assertEqual("live excerpt", case["error_excerpt"])
        self.assertEqual("2026-01-01T00:00:00Z", case["last_seen"])
        self.assertIn("imported 0 new case(s), merged 1; store holds 1", out_text)

    def test_merge_appends_unseen_signatures_with_fresh_ids_in_file_order(self):
        store.CaseStore(self.store_path).save([make_case(4, "live :: one")])
        incoming = write_jsonl(
            Path(self._tmp.name) / "mix.jsonl",
            [
                make_case(10, "new :: b"),
                make_case(11, "new :: a"),
                make_case(12, "live :: one"),
            ],
        )
        code, out_text, _ = self._run("import", "--in", str(incoming), "--merge")
        self.assertEqual(0, code)
        cases = store.CaseStore(self.store_path).load()
        self.assertEqual([4, 5, 6], [case["id"] for case in cases])
        self.assertEqual(
            ["live :: one", "new :: b", "new :: a"],
            [case["signature"] for case in cases],
        )
        self.assertEqual([2, 1, 1], [case["times_seen"] for case in cases])
        self.assertIn("imported 2 new case(s), merged 1; store holds 3", out_text)

    def test_merge_still_rejects_intra_file_duplicates(self):
        self._seed()
        before = self.store_path.read_bytes()
        incoming = write_jsonl(
            Path(self._tmp.name) / "twins.jsonl",
            [make_case(7, "twin :: sig"), make_case(8, "twin :: sig")],
        )
        code, _, err = self._run("import", "--in", str(incoming), "--merge")
        self.assertEqual(1, code)
        self.assertIn("duplicate signature(s) within import file", err)
        self.assertEqual(before, self.store_path.read_bytes())

    def test_merge_refuses_ambiguous_target_instead_of_guessing(self):
        store.CaseStore(self.store_path).save(
            [
                make_case(1, "amb :: sig", times_seen=1),
                make_case(2, "amb :: sig", times_seen=3),
            ]
        )
        before = store.CaseStore(self.store_path).load()
        incoming = write_jsonl(
            Path(self._tmp.name) / "amb.jsonl", [make_case(9, "amb :: sig")]
        )
        code, _, err = self._run("import", "--in", str(incoming), "--merge")
        self.assertEqual(1, code)
        self.assertIn("ambiguous merge target", err)
        self.assertEqual(before, store.CaseStore(self.store_path).load())


if __name__ == "__main__":
    unittest.main()
