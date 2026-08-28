"""Tests for S28 escalation handshake: brain drafts question for live agent."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qacompanion.__main__ import build_parser, main
from qacompanion.escalation import (
    CONFIDENCE_MARKERS,
    EscalationError,
    detect_confidence,
    format_escalation_output,
    format_escalation_question,
    record_escalated_answer,
)


def _cases_file(path, cases):
    with open(path, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")


def _make_case(id=1, sig="test failure", err="error line", diag="fix it", seen=1):
    return {
        "id": id,
        "signature": sig,
        "error_excerpt": err,
        "diagnosis": diag,
        "times_seen": seen,
        "last_seen": "2026-08-26T00:00:00Z",
        "confirmed_by": "agent-a",
    }


# --- detect_confidence ---

class TestDetectConfidence(unittest.TestCase):
    def test_confident_answer(self):
        answer = "Based on case #3, the fix is to update the config file."
        result = detect_confidence(answer)
        self.assertTrue(result["confident"])
        self.assertEqual(result["markers"], [])

    def test_low_confidence_not_sure(self):
        answer = "I'm not sure about this, but maybe try reinstalling."
        result = detect_confidence(answer)
        self.assertFalse(result["confident"])
        self.assertTrue(len(result["markers"]) > 0)

    def test_low_confidence_dont_know(self):
        answer = "I don't know the answer to this question."
        result = detect_confidence(answer)
        self.assertFalse(result["confident"])

    def test_low_confidence_uncertain(self):
        answer = "This is uncertain without more context."
        result = detect_confidence(answer)
        self.assertFalse(result["confident"])

    def test_low_confidence_no_relevant(self):
        answer = "No relevant cases found in the knowledge base."
        result = detect_confidence(answer)
        self.assertFalse(result["confident"])

    def test_low_confidence_cannot_determine(self):
        answer = "I cannot determine the cause from the available information."
        result = detect_confidence(answer)
        self.assertFalse(result["confident"])

    def test_low_confidence_unable_to(self):
        answer = "I was unable to find a matching diagnosis."
        result = detect_confidence(answer)
        self.assertFalse(result["confident"])

    def test_low_confidence_no_information(self):
        answer = "There is no information about this error in the case base."
        result = detect_confidence(answer)
        self.assertFalse(result["confident"])

    def test_low_confidence_no_match(self):
        answer = "I found no matching case for this signature."
        result = detect_confidence(answer)
        self.assertFalse(result["confident"])

    def test_multiple_markers(self):
        answer = "I'm not sure and I don't know — no relevant cases found."
        result = detect_confidence(answer)
        self.assertFalse(result["confident"])
        self.assertGreaterEqual(len(result["markers"]), 2)

    def test_empty_answer(self):
        result = detect_confidence("")
        self.assertTrue(result["confident"])
        self.assertEqual(result["markers"], [])

    def test_none_answer(self):
        result = detect_confidence(None)
        self.assertTrue(result["confident"])
        self.assertEqual(result["markers"], [])

    def test_case_insensitive(self):
        answer = "I AM NOT SURE about this."
        result = detect_confidence(answer)
        self.assertFalse(result["confident"])

    def test_markers_populated(self):
        answer = "I'm not sure and cannot determine the cause."
        result = detect_confidence(answer)
        self.assertGreater(len(result["markers"]), 0)
        for marker in result["markers"]:
            self.assertIsInstance(marker, str)

    def test_no_false_positive_on_normal_text(self):
        answer = (
            "The error occurs because the config file is missing. "
            "Fix: create config.yaml with the required fields. "
            "See case #5 for a similar issue."
        )
        result = detect_confidence(answer)
        self.assertTrue(result["confident"])


# --- format_escalation_question ---

class TestFormatEscalationQuestion(unittest.TestCase):
    def test_basic_question(self):
        text = format_escalation_question("What is deployment?", "")
        self.assertIn("What is deployment?", text)
        self.assertIn("ESCALATION", text.upper())

    def test_includes_context(self):
        context = "case #1: sig=foo, diag=bar"
        text = format_escalation_question("question?", context)
        self.assertIn("question?", text)
        self.assertIn("case #1", text)

    def test_includes_answer(self):
        text = format_escalation_question("q?", "ctx", answer="I'm not sure")
        self.assertIn("I'm not sure", text)

    def test_no_context(self):
        text = format_escalation_question("q?", "")
        self.assertIn("q?", text)

    def test_format_output(self):
        text = format_escalation_question("q?", "ctx")
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 0)


# --- record_escalated_answer ---

class TestRecordEscalatedAnswer(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_record_new_case(self):
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        _cases_file(cases_path, [_make_case(id=1)])
        case, created = record_escalated_answer(
            question="What causes error X?",
            answer="Error X is caused by missing config.",
            signature="error X missing config",
            error_excerpt="Error: config not found",
            diagnosis="Create the config file",
            by="agent-a",
            cases_path=cases_path,
        )
        self.assertTrue(created)
        self.assertEqual(case["id"], 2)
        self.assertIn("error X", case["signature"])

    def test_record_bumps_existing(self):
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        c = _make_case(id=1, sig="error X missing config", seen=2)
        _cases_file(cases_path, [c])
        case, created = record_escalated_answer(
            question="What causes error X?",
            answer="Error X is caused by missing config.",
            signature="error X missing config",
            error_excerpt="Error: config not found",
            diagnosis="Create the config file",
            by="agent-a",
            cases_path=cases_path,
        )
        self.assertFalse(created)
        self.assertEqual(case["id"], 1)
        self.assertEqual(case["times_seen"], 3)

    def test_record_empty_cases(self):
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        cases_path.write_text("")
        case, created = record_escalated_answer(
            question="q",
            answer="a",
            signature="sig",
            error_excerpt="err",
            diagnosis="diag",
            by="test",
            cases_path=cases_path,
        )
        self.assertTrue(created)
        self.assertEqual(case["id"], 1)

    def test_record_missing_file(self):
        cases_path = Path(self.tmpdir) / "nonexistent.jsonl"
        case, created = record_escalated_answer(
            question="q",
            answer="a",
            signature="sig",
            error_excerpt="err",
            diagnosis="diag",
            by="test",
            cases_path=cases_path,
        )
        self.assertTrue(created)

    def test_record_stores_answer(self):
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        _cases_file(cases_path, [_make_case(id=1)])
        case, _ = record_escalated_answer(
            question="What is X?",
            answer="X is a test case.",
            signature="X is test",
            error_excerpt="test error",
            diagnosis="test diagnosis",
            by="human",
            cases_path=cases_path,
        )
        self.assertEqual(case["confirmed_by"], "human")
        self.assertEqual(case["diagnosis"], "test diagnosis")

    def test_record_preserves_id_sequence(self):
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        _cases_file(cases_path, [_make_case(id=1), _make_case(id=2)])
        case, _ = record_escalated_answer(
            question="q",
            answer="a",
            signature="new sig",
            error_excerpt="err",
            diagnosis="diag",
            by="test",
            cases_path=cases_path,
        )
        self.assertEqual(case["id"], 3)

    def test_record_default_by(self):
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        cases_path.write_text("")
        case, _ = record_escalated_answer(
            question="q",
            answer="a",
            signature="sig",
            error_excerpt="err",
            diagnosis="diag",
            by=None,
            cases_path=cases_path,
        )
        self.assertEqual(case["confirmed_by"], "unknown")


# --- format_escalation_output ---

class TestFormatEscalationOutput(unittest.TestCase):
    def test_output_contains_question(self):
        question = format_escalation_question("What is deployment?", "ctx")
        text = format_escalation_output(question)
        self.assertIn("What is deployment?", text)

    def test_output_contains_header(self):
        question = format_escalation_question("q", "ctx")
        text = format_escalation_output(question)
        self.assertIn("ESCALATION", text.upper())

    def test_output_suggests_record(self):
        question = format_escalation_question("q", "ctx")
        text = format_escalation_output(question)
        self.assertIn("record", text.lower())


# --- CONFIDENCE_MARKERS constant ---

class TestConfidenceMarkers(unittest.TestCase):
    def test_markers_is_list(self):
        self.assertIsInstance(CONFIDENCE_MARKERS, list)

    def test_markers_not_empty(self):
        self.assertGreater(len(CONFIDENCE_MARKERS), 0)

    def test_markers_are_strings(self):
        for marker in CONFIDENCE_MARKERS:
            self.assertIsInstance(marker, str)


# --- CLI escalation subcommand ---

class TestCLIEscalate(unittest.TestCase):
    def test_escalate_basic(self):
        argv = ["escalate", "What causes error X?"]
        parser = build_parser()
        args = parser.parse_args(argv)
        result = main(argv)
        self.assertEqual(result, 0)

    def test_escalate_with_context(self):
        argv = ["escalate", "What causes error X?", "--context", "case #1: sig=foo"]
        parser = build_parser()
        args = parser.parse_args(argv)
        result = main(argv)
        self.assertEqual(result, 0)

    def test_escalate_with_answer(self):
        argv = ["escalate", "q", "--answer", "I'm not sure"]
        result = main(argv)
        self.assertEqual(result, 0)

    def test_escalate_parser_has_query(self):
        parser = build_parser()
        args = parser.parse_args(["escalate", "test query"])
        self.assertEqual(args.query, "test query")

    def test_escalate_parser_optional_args(self):
        parser = build_parser()
        args = parser.parse_args([
            "escalate", "q",
            "--context", "ctx",
            "--answer", "ans",
            "--cases", "/tmp/cases.jsonl",
            "--digest", "/tmp/digest.jsonl",
        ])
        self.assertEqual(args.query, "q")
        self.assertEqual(args.context, "ctx")
        self.assertEqual(args.answer, "ans")
        self.assertEqual(args.cases, "/tmp/cases.jsonl")
        self.assertEqual(args.digest, "/tmp/digest.jsonl")

    def test_escalate_output_contains_question(self):
        import io
        import sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            main(["escalate", "What is deployment?"])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("What is deployment?", output)
        self.assertIn("ESCALATION", output.upper())

    def test_escalate_output_suggests_record(self):
        import io
        import sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            main(["escalate", "q"])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        self.assertIn("record", output.lower())


if __name__ == "__main__":
    unittest.main()
