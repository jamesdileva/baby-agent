"""Tests for S26 Ollama bridge: local model integration with retrieval context."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from qacompanion.ollama_bridge import (
    OllamaError,
    _build_prompt,
    _format_cases_context,
    _format_digest_context,
    _is_ollama_available,
    _ollama_generate,
    ask,
    build_retrieval_context,
)


def _cases_file(path, cases):
    """Write a cases.jsonl file."""
    with open(path, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")


def _digest_file(path, entries):
    """Write a digest.jsonl file."""
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


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


def _make_digest(id=1, source="doc.md", heading="Intro", content="Some content"):
    return {
        "id": id,
        "source": source,
        "heading": heading,
        "content": content,
        "content_hash": "abc123",
        "digested_at": "2026-08-26T00:00:00Z",
    }


# --- is_ollama_available ---

class TestIsOllamaAvailable(unittest.TestCase):
    @patch("qacompanion.ollama_bridge._ollama_generate")
    def test_available_returns_true(self, mock_gen):
        mock_gen.return_value = "test response"
        self.assertTrue(_is_ollama_available())

    @patch("qacompanion.ollama_bridge._ollama_generate")
    def test_unavailable_returns_false(self, mock_gen):
        mock_gen.side_effect = OllamaError("connection refused")
        self.assertFalse(_is_ollama_available())

    @patch("qacompanion.ollama_bridge._ollama_generate")
    def test_custom_url(self, mock_gen):
        mock_gen.return_value = "ok"
        self.assertTrue(_is_ollama_available(url="http://custom:9999"))
        mock_gen.assert_called_once()
        args, kwargs = mock_gen.call_args
        self.assertEqual(args[0], "ping")
        self.assertIsNone(kwargs.get("model"))
        self.assertEqual(kwargs.get("url"), "http://custom:9999")


# --- build_retrieval_context ---

class TestBuildRetrievalContext(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_stores(self):
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        cases_path.write_text("")
        digest_path.write_text("")
        ctx = build_retrieval_context("test query", cases_path, digest_path)
        self.assertEqual(ctx["cases"], [])
        self.assertEqual(ctx["digest"], [])
        self.assertEqual(ctx["total_items"], 0)

    def test_matching_cases(self):
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        digest_path.write_text("")
        c1 = _make_case(id=1, sig="test failure in foo", err="FooError", diag="fix foo")
        c2 = _make_case(id=2, sig="bar crash", err="BarError", diag="fix bar", seen=5)
        _cases_file(cases_path, [c1, c2])
        ctx = build_retrieval_context("foo", cases_path, digest_path)
        self.assertEqual(len(ctx["cases"]), 1)
        self.assertIn("foo", ctx["cases"][0]["signature"])

    def test_matching_digest(self):
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        cases_path.write_text("")
        d1 = _make_digest(id=1, content="How to deploy the app")
        d2 = _make_digest(id=2, content="Unrelated text about dogs")
        _digest_file(digest_path, [d1, d2])
        ctx = build_retrieval_context("deploy", cases_path, digest_path)
        self.assertEqual(len(ctx["digest"]), 1)
        self.assertIn("deploy", ctx["digest"][0]["content"].lower())

    def test_cases_sorted_by_times_seen(self):
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        digest_path.write_text("")
        c1 = _make_case(id=1, sig="err a", seen=1)
        c2 = _make_case(id=2, sig="err a similar", seen=10)
        _cases_file(cases_path, [c1, c2])
        ctx = build_retrieval_context("err", cases_path, digest_path)
        self.assertEqual(ctx["cases"][0]["id"], 2)

    def test_missing_files(self):
        ctx = build_retrieval_context("q", Path("/nonexistent"), Path("/also-nonexistent"))
        self.assertEqual(ctx["cases"], [])
        self.assertEqual(ctx["digest"], [])

    def test_total_items_count(self):
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        c = _make_case(id=1, sig="err x", seen=1)
        _cases_file(cases_path, [c])
        d = _make_digest(id=1, content="about x")
        _digest_file(digest_path, [d])
        ctx = build_retrieval_context("x", cases_path, digest_path)
        self.assertEqual(ctx["total_items"], 2)

    def test_max_cases_limit(self):
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        digest_path.write_text("")
        cases = [_make_case(id=i, sig=f"err {i}", seen=i) for i in range(1, 11)]
        _cases_file(cases_path, cases)
        ctx = build_retrieval_context("err", cases_path, digest_path, max_cases=3)
        self.assertEqual(len(ctx["cases"]), 3)

    def test_max_digest_limit(self):
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        cases_path.write_text("")
        entries = [_make_digest(id=i, content=f"topic {i}") for i in range(1, 11)]
        _digest_file(digest_path, entries)
        ctx = build_retrieval_context("topic", cases_path, digest_path, max_digest=2)
        self.assertEqual(len(ctx["digest"]), 2)


# --- _format_cases_context ---

class TestFormatCasesContext(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_format_cases_context([]), "")

    def test_single_case(self):
        cases = [_make_case(id=1, sig="fail foo", err="FooError", diag="fix foo", seen=3)]
        text = _format_cases_context(cases)
        self.assertIn("case #1", text)
        self.assertIn("times_seen=3", text)
        self.assertIn("fix foo", text)

    def test_multiple_cases(self):
        cases = [
            _make_case(id=1, sig="a", err="ea", diag="da", seen=1),
            _make_case(id=2, sig="b", err="eb", diag="db", seen=5),
        ]
        text = _format_cases_context(cases)
        self.assertIn("case #1", text)
        self.assertIn("case #2", text)


# --- _format_digest_context ---

class TestFormatDigestContext(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_format_digest_context([]), "")

    def test_single_entry(self):
        entries = [_make_digest(id=1, source="doc.md", heading="Intro", content="Some text")]
        text = _format_digest_context(entries)
        self.assertIn("doc.md", text)
        self.assertIn("Intro", text)
        self.assertIn("Some text", text)


# --- _build_prompt ---

class TestBuildPrompt(unittest.TestCase):
    def test_basic_prompt(self):
        ctx = {"cases": [], "digest": [], "total_items": 0}
        prompt = _build_prompt("What is deployment?", ctx)
        self.assertIn("What is deployment?", prompt)
        self.assertIn("No", prompt)

    def test_prompt_with_cases(self):
        cases = [_make_case(id=1, sig="fail", err="e", diag="fix it", seen=2)]
        ctx = {"cases": cases, "digest": [], "total_items": 1}
        prompt = _build_prompt("help", ctx)
        self.assertIn("fix it", prompt)
        self.assertIn("case #1", prompt)

    def test_prompt_with_digest(self):
        entries = [_make_digest(id=1, content="Deploy using make deploy")]
        ctx = {"cases": [], "digest": entries, "total_items": 1}
        prompt = _build_prompt("how to deploy", ctx)
        self.assertIn("make deploy", prompt)

    def test_prompt_with_both(self):
        cases = [_make_case(id=1, sig="x", err="e", diag="d", seen=1)]
        entries = [_make_digest(id=1, content="reference info")]
        ctx = {"cases": cases, "digest": entries, "total_items": 2}
        prompt = _build_prompt("question", ctx)
        self.assertIn("d", prompt)
        self.assertIn("reference info", prompt)

    def test_system_instruction_in_prompt(self):
        ctx = {"cases": [], "digest": [], "total_items": 0}
        prompt = _build_prompt("q", ctx)
        self.assertIn("cite", prompt.lower())


# --- _ollama_generate ---

class TestOllamaGenerate(unittest.TestCase):
    @patch("qacompanion.ollama_bridge._http_post")
    def test_successful_generate(self, mock_post):
        mock_post.return_value = {"response": "test answer"}
        result = _ollama_generate("prompt here", model="test-model")
        self.assertEqual(result, "test answer")

    @patch("qacompanion.ollama_bridge._http_post")
    def test_generate_with_url(self, mock_post):
        mock_post.return_value = {"response": "ok"}
        _ollama_generate("p", url="http://custom:9999")
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertIn("custom:9999", call_args[0][0])

    @patch("qacompanion.ollama_bridge._http_post")
    def test_generate_error(self, mock_post):
        mock_post.side_effect = OllamaError("timeout")
        with self.assertRaises(OllamaError):
            _ollama_generate("p")


# --- ask ---

class TestAsk(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("qacompanion.ollama_bridge._is_ollama_available")
    @patch("qacompanion.ollama_bridge._ollama_generate")
    def test_ask_with_ollama(self, mock_gen, mock_avail):
        mock_avail.return_value = True
        mock_gen.return_value = "grounded answer"
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        c = _make_case(id=1, sig="err x", diag="fix x")
        _cases_file(cases_path, [c])
        _digest_file(digest_path, [])
        result = ask("what is x", cases_path=cases_path, digest_path=digest_path)
        self.assertTrue(result["used_ollama"])
        self.assertEqual(result["answer"], "grounded answer")
        self.assertIn("fix x", result["context_used"])

    @patch("qacompanion.ollama_bridge._is_ollama_available")
    def test_ask_fallback_no_ollama(self, mock_avail):
        mock_avail.return_value = False
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        _cases_file(cases_path, [])
        _digest_file(digest_path, [])
        result = ask("question", cases_path=cases_path, digest_path=digest_path)
        self.assertFalse(result["used_ollama"])
        self.assertEqual(result["answer"], "no matching case")

    @patch("qacompanion.ollama_bridge._is_ollama_available")
    def test_ask_fallback_with_cases(self, mock_avail):
        mock_avail.return_value = False
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        c = _make_case(id=1, sig="err foo", diag="fix foo", seen=5)
        _cases_file(cases_path, [c])
        _digest_file(digest_path, [])
        result = ask("foo", cases_path=cases_path, digest_path=digest_path)
        self.assertFalse(result["used_ollama"])
        self.assertIn("fix foo", result["answer"])

    @patch("qacompanion.ollama_bridge._is_ollama_available")
    @patch("qacompanion.ollama_bridge._ollama_generate")
    def test_ask_ollama_fails_falls_back(self, mock_gen, mock_avail):
        mock_avail.return_value = True
        mock_gen.side_effect = OllamaError("model crashed")
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        _cases_file(cases_path, [])
        _digest_file(digest_path, [])
        result = ask("q", cases_path=cases_path, digest_path=digest_path)
        self.assertFalse(result["used_ollama"])
        self.assertEqual(result["answer"], "no matching case")

    @patch("qacompanion.ollama_bridge._is_ollama_available")
    @patch("qacompanion.ollama_bridge._ollama_generate")
    def test_ask_returns_citations(self, mock_gen, mock_avail):
        mock_avail.return_value = True
        mock_gen.return_value = "answer"
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        c = _make_case(id=1, sig="err y", diag="diagnosis y")
        _cases_file(cases_path, [c])
        d = _make_digest(id=1, source="docs.md", heading="Y", content="about y")
        _digest_file(digest_path, [d])
        result = ask("y", cases_path=cases_path, digest_path=digest_path)
        self.assertEqual(result["citations"]["cases"], 1)
        self.assertEqual(result["citations"]["digest"], 1)


# --- CLI formatting ---

class TestFormatAskOutput(unittest.TestCase):
    def test_ollama_answer(self):
        from qacompanion.ollama_bridge import format_ask_output
        result = {
            "answer": "Use make deploy",
            "used_ollama": True,
            "citations": {"cases": 1, "digest": 2},
            "model": "qwen2.5-coder:1.5b",
        }
        output = format_ask_output(result)
        self.assertIn("Use make deploy", output)
        self.assertIn("qwen2.5-coder:1.5b", output)
        self.assertIn("3 sources", output)

    def test_fallback_answer(self):
        from qacompanion.ollama_bridge import format_ask_output
        result = {
            "answer": "case #1 times_seen=3\ndiagnosis: fix it",
            "used_ollama": False,
            "citations": {"cases": 1, "digest": 0},
            "model": None,
        }
        output = format_ask_output(result)
        self.assertIn("fix it", output)
        self.assertIn("no ollama", output.lower())

    def test_no_match_fallback(self):
        from qacompanion.ollama_bridge import format_ask_output
        result = {
            "answer": "no matching case",
            "used_ollama": False,
            "citations": {"cases": 0, "digest": 0},
            "model": None,
        }
        output = format_ask_output(result)
        self.assertIn("no matching case", output)


# --- Edge cases ---

class TestEdgeCases(unittest.TestCase):
    def test_ollama_generate_empty_response(self):
        with patch("qacompanion.ollama_bridge._http_post") as mock_post:
            mock_post.return_value = {}
            result = _ollama_generate("prompt")
            self.assertEqual(result, "")

    def test_ollama_generate_none_response(self):
        with patch("qacompanion.ollama_bridge._http_post") as mock_post:
            mock_post.return_value = {"response": None}
            result = _ollama_generate("prompt")
            self.assertEqual(result, "")

    def test_build_prompt_max_context_length(self):
        cases = [_make_case(id=i, sig=f"sig {i}", diag=f"diag {i}", seen=i) for i in range(1, 50)]
        ctx = {"cases": cases, "digest": [], "total_items": 49}
        prompt = _build_prompt("q", ctx)
        self.assertLessEqual(len(prompt), 8000)


if __name__ == "__main__":
    unittest.main()
