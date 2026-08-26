"""Accuracy subcommand: holdout loading, replay scoring, CLI exit policy."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qacompanion.__main__ import main
from qacompanion import accuracy as accuracy_mod
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


def write_holdout(path, entries):
    payload = "".join(json.dumps(entry) + "\n" for entry in entries)
    path.write_text(payload, encoding="utf-8", newline="\n")
    return path


class LoadHoldoutTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.holdout_path = Path(self._tmp.name) / "holdout.jsonl"

    def test_loads_valid_entries_in_order(self):
        write_holdout(
            self.holdout_path,
            [
                {"signature": "a :: x", "diagnosis": "d1"},
                {"signature": "b :: y", "diagnosis": "d2"},
            ],
        )
        entries = accuracy_mod.load_holdout(self.holdout_path)
        self.assertEqual(
            [
                {"signature": "a :: x", "diagnosis": "d1"},
                {"signature": "b :: y", "diagnosis": "d2"},
            ],
            entries,
        )

    def test_bom_prefix_is_stripped_not_fatal(self):
        self.holdout_path.write_text(
            "\ufeff"
            + json.dumps({"signature": "a :: x", "diagnosis": "d"}) + "\n",
            encoding="utf-8",
        )
        (entry,) = accuracy_mod.load_holdout(self.holdout_path)
        self.assertEqual("a :: x", entry["signature"])

    def test_crlf_and_missing_trailing_newline_are_fine(self):
        self.holdout_path.write_bytes(
            b'{"signature": "a :: x", "diagnosis": "d"}\r\n'
            b'{"signature": "b :: y", "diagnosis": "e"}'
        )
        self.assertEqual(2, len(accuracy_mod.load_holdout(self.holdout_path)))

    def test_blank_lines_are_skipped(self):
        self.holdout_path.write_text(
            '\n{"signature": "a :: x", "diagnosis": "d"}\n\n', encoding="utf-8"
        )
        self.assertEqual(1, len(accuracy_mod.load_holdout(self.holdout_path)))

    def test_invalid_json_names_the_line(self):
        self.holdout_path.write_text("{bad}\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            accuracy_mod.load_holdout(self.holdout_path)
        self.assertIn("line 1", str(ctx.exception))

    def test_non_object_line_rejected(self):
        self.holdout_path.write_text('["sig", "d"]\n', encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            accuracy_mod.load_holdout(self.holdout_path)
        self.assertIn("expected a JSON object", str(ctx.exception))

    def test_missing_field_rejected_with_line_number(self):
        self.holdout_path.write_text(
            '{"signature": "a :: x"}\n', encoding="utf-8"
        )
        with self.assertRaises(ValueError) as ctx:
            accuracy_mod.load_holdout(self.holdout_path)
        self.assertIn("missing field(s): diagnosis", str(ctx.exception))

    def test_non_string_field_rejected(self):
        self.holdout_path.write_text(
            '{"signature": 7, "diagnosis": "d"}\n', encoding="utf-8"
        )
        with self.assertRaises(ValueError) as ctx:
            accuracy_mod.load_holdout(self.holdout_path)
        self.assertIn("'signature' must be str", str(ctx.exception))

    def test_missing_file_is_operational_failure_not_empty_score(self):
        with self.assertRaises(ValueError) as ctx:
            accuracy_mod.load_holdout(self.holdout_path)
        self.assertIn("holdout file not found", str(ctx.exception))

    def test_empty_file_refuses_to_score(self):
        self.holdout_path.write_text("", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            accuracy_mod.load_holdout(self.holdout_path)
        self.assertIn("empty", str(ctx.exception))

    def test_empty_holdout_raises_dedicated_emptyholdout_valueerror(self):
        # report.py must be able to tell absence/emptiness (honest n/a per
        # D-0004) apart from malformed input (corruption -> exit 1).
        self.holdout_path.write_text("", encoding="utf-8")
        with self.assertRaises(accuracy_mod.EmptyHoldout):
            accuracy_mod.load_holdout(self.holdout_path)
        self.assertTrue(issubclass(accuracy_mod.EmptyHoldout, ValueError))


class ReplayTests(unittest.TestCase):
    def test_exact_diagnosis_hits(self):
        cases = [make_case(1, "a :: x", diagnosis="right")]
        hits, total = accuracy_mod.replay(
            cases, [{"signature": "a :: x", "diagnosis": "right"}]
        )
        self.assertEqual((1, 1), (hits, total))

    def test_wrong_diagnosis_is_a_miss(self):
        cases = [make_case(1, "a :: x", diagnosis="drifted")]
        hits, total = accuracy_mod.replay(
            cases, [{"signature": "a :: x", "diagnosis": "right"}]
        )
        self.assertEqual((0, 1), (hits, total))

    def test_unknown_signature_is_a_miss(self):
        hits, total = accuracy_mod.replay(
            [], [{"signature": "ghost :: z", "diagnosis": "d"}]
        )
        self.assertEqual((0, 1), (hits, total))

    def test_ambiguous_signature_never_counts_as_hit(self):
        cases = [
            make_case(1, "a :: x", diagnosis="right"),
            make_case(2, "a :: x", diagnosis="right"),
        ]
        hits, total = accuracy_mod.replay(
            cases, [{"signature": "a :: x", "diagnosis": "right"}]
        )
        self.assertEqual((0, 1), (hits, total))

    def test_entry_signature_passes_canonical_gate(self):
        # Frozen entry spelled with case/whitespace/path noise still finds
        # its canonical stored twin - same gate as record and lookup.
        cases = [make_case(1, "t :: err", diagnosis="d")]
        hits, total = accuracy_mod.replay(
            cases, [{"signature": r"C:\Repo\T  ::  ERR", "diagnosis": "d"}]
        )
        self.assertEqual((1, 1), (hits, total))


class FormatAccuracyTests(unittest.TestCase):
    def test_perfect_score_spells_out_denominator(self):
        self.assertEqual("accuracy: 100% (4/4)", accuracy_mod.format_accuracy(4, 4))

    def test_partial_score_rounded_but_fraction_kept_exact(self):
        self.assertEqual("accuracy: 50% (1/2)", accuracy_mod.format_accuracy(1, 2))
        self.assertEqual("accuracy: 12% (1/8)", accuracy_mod.format_accuracy(1, 8))

    def test_zero_score_is_printed_not_hidden(self):
        self.assertEqual("accuracy: 0% (0/3)", accuracy_mod.format_accuracy(0, 3))


class AccuracyCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store_path = Path(self._tmp.name) / "cases.jsonl"
        self.holdout_path = Path(self._tmp.name) / "holdout.jsonl"
        patcher = mock.patch.dict(
            os.environ,
            {
                store.ENV_OVERRIDE: str(self.store_path),
                accuracy_mod.ENV_OVERRIDE: str(self.holdout_path),
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _seed_one(self, signature="t :: err", diagnosis="d"):
        main(
            ["record", "--sig", signature, "--err", "e", "--diag", diagnosis]
        )
        (case,) = store.CaseStore(self.store_path).load()
        return case

    def test_full_recall_exits_zero_with_score_line(self):
        case = self._seed_one(diagnosis="the fix is on line one")
        write_holdout(
            self.holdout_path,
            [{"signature": case["signature"], "diagnosis": case["diagnosis"]}],
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["accuracy"])
        self.assertEqual(0, code)
        self.assertEqual("accuracy: 100% (1/1)", buffer.getvalue().strip())

    def test_empty_holdout_exits_one_not_silent_hundred_percent(self):
        self._seed_one()
        self.holdout_path.write_text("", encoding="utf-8")
        stderr = io.StringIO()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["accuracy"])
        self.assertEqual(1, code)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("empty", stderr.getvalue())

    def test_missing_holdout_exits_one(self):
        self._seed_one()
        code = main(["accuracy"])
        self.assertEqual(1, code)

    def test_corrupt_store_exits_one(self):
        self.store_path.write_text("{corrupt}\n", encoding="utf-8")
        write_holdout(
            self.holdout_path,
            [{"signature": "a :: x", "diagnosis": "d"}],
        )
        code = main(["accuracy"])
        self.assertEqual(1, code)

    def test_real_failure_output_round_trips_to_full_recall(self):
        proc = subprocess.run(
            [sys.executable, "-c", "raise ZeroDivisionError('division by zero')"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, proc.returncode)
        error_line = proc.stderr.splitlines()[-1].strip()
        diagnosis = "live traceback replayed into the case base unchanged"
        main(
            [
                "record",
                "--sig",
                f"test_real_failure :: {error_line}",
                "--err",
                error_line,
                "--diag",
                diagnosis,
            ]
        )
        (case,) = store.CaseStore(self.store_path).load()
        write_holdout(
            self.holdout_path,
            [{"signature": case["signature"], "diagnosis": case["diagnosis"]}],
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["accuracy"])
        self.assertEqual(0, code)
        self.assertEqual("accuracy: 100% (1/1)", buffer.getvalue().strip())


if __name__ == "__main__":
    unittest.main()
