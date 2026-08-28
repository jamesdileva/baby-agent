"""Tests for S27 research tools: callable tools for the brain layer."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qacompanion.ollama_bridge import ask
from qacompanion.tools import (
    MAX_TOOL_CALLS,
    TOOLS,
    case_search,
    dispatch_tool,
    doc_grep,
    journal_read,
    parse_tool_calls,
)


def _cases_file(path, cases):
    with open(path, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")


def _digest_file(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _journal_file(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


# --- parse_tool_calls ---

class TestParseToolCalls(unittest.TestCase):
    def test_single_tool_call(self):
        text = 'I need to look that up. [TOOL: case_search(query="ENOENT")]'
        result = parse_tool_calls(text)
        self.assertEqual(result, [("case_search", "ENOENT")])

    def test_single_tool_call_single_quotes(self):
        text = "[TOOL: doc_grep(query='deployment')]"
        result = parse_tool_calls(text)
        self.assertEqual(result, [("doc_grep", "deployment")])

    def test_multiple_tool_calls(self):
        text = (
            '[TOOL: case_search(query="error")]'
            '[TOOL: doc_grep(query="config")]'
        )
        result = parse_tool_calls(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("case_search", "error"))
        self.assertEqual(result[1], ("doc_grep", "config"))

    def test_no_tool_calls(self):
        text = "This is a plain answer with no tools."
        result = parse_tool_calls(text)
        self.assertEqual(result, [])

    def test_journal_read_tool(self):
        text = '[TOOL: journal_read(pattern="BOM")]'
        result = parse_tool_calls(text)
        self.assertEqual(result, [("journal_read", "BOM")])

    def test_extra_spaces(self):
        text = '[  TOOL:  case_search( query = "test" )  ]'
        result = parse_tool_calls(text)
        self.assertEqual(result, [("case_search", "test")])

    def test_case_insensitive(self):
        text = '[tool: Case_Search(query="test")]'
        result = parse_tool_calls(text)
        self.assertEqual(result, [("Case_Search", "test")])

    def test_tool_call_in_middle_of_text(self):
        text = (
            "Let me search for that.\n"
            '[TOOL: case_search(query="timeout")]\n'
            "Based on the results..."
        )
        result = parse_tool_calls(text)
        self.assertEqual(result, [("case_search", "timeout")])

    def test_unknown_tool_format_not_matched(self):
        text = "[TOOL: unknown_format]"
        result = parse_tool_calls(text)
        self.assertEqual(result, [])


# --- dispatch_tool ---

class TestDispatchTool(unittest.TestCase):
    def test_unknown_tool_returns_error(self):
        result = dispatch_tool("nonexistent", "query")
        self.assertIn("error", result)
        self.assertIn("nonexistent", result)

    @patch("qacompanion.tools.TOOLS", {"case_search": lambda q, **kw: "found it"})
    def test_dispatch_calls_correct_function(self):
        result = dispatch_tool("case_search", "error text")
        self.assertEqual(result, "found it")

    @patch("qacompanion.tools.TOOLS", {"doc_grep": lambda q, **kw: "docs found"})
    def test_dispatch_with_kwargs(self):
        result = dispatch_tool("doc_grep", "deploy", digest_path="/tmp/d.jsonl")
        self.assertEqual(result, "docs found")

    @patch("qacompanion.tools.TOOLS", {"boom": lambda q: 1 / 0})
    def test_dispatch_catches_exceptions(self):
        result = dispatch_tool("boom", "query")
        self.assertIn("error", result)
        self.assertIn("boom failed", result)


# --- case_search ---

class TestCaseSearch(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_matching_case(self):
        path = Path(self.tmpdir) / "cases.jsonl"
        _cases_file(path, [_make_case(sig="ENOENT file", diag="missing file")])
        result = case_search("ENOENT", cases_path=str(path))
        self.assertIn("missing file", result)
        self.assertIn("case #1", result)

    def test_no_match(self):
        path = Path(self.tmpdir) / "cases.jsonl"
        _cases_file(path, [_make_case(sig="timeout error")])
        result = case_search("ENOENT", cases_path=str(path))
        self.assertEqual(result, "no matching case")

    def test_empty_cases_file(self):
        path = Path(self.tmpdir) / "cases.jsonl"
        _cases_file(path, [])
        result = case_search("anything", cases_path=str(path))
        self.assertEqual(result, "no matching case")

    def test_missing_file(self):
        path = Path(self.tmpdir) / "nonexistent.jsonl"
        result = case_search("test", cases_path=str(path))
        self.assertEqual(result, "no matching case")


# --- doc_grep ---

class TestDocGrep(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_matching_doc(self):
        path = Path(self.tmpdir) / "digest.jsonl"
        _digest_file(path, [_make_digest(heading="Deploy", content="deploy to prod")])
        result = doc_grep("deploy", digest_path=str(path))
        self.assertIn("Deploy", result)
        self.assertIn("deploy to prod", result)

    def test_no_match(self):
        path = Path(self.tmpdir) / "digest.jsonl"
        _digest_file(path, [_make_digest(heading="Testing", content="run tests")])
        result = doc_grep("deploy", digest_path=str(path))
        self.assertIn("no matching", result)

    def test_empty_digest(self):
        path = Path(self.tmpdir) / "digest.jsonl"
        _digest_file(path, [])
        result = doc_grep("anything", digest_path=str(path))
        self.assertIn("no matching", result)

    def test_missing_file(self):
        path = Path(self.tmpdir) / "nonexistent.jsonl"
        result = doc_grep("test", digest_path=str(path))
        self.assertIn("no matching", result)


# --- journal_read ---

class TestJournalRead(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_matching_entry(self):
        path = Path(self.tmpdir) / "JOURNAL.md"
        _journal_file(path, [
            "## 2026-08-26T00:00:00 fixed BOM in config",
            "## 2026-08-26T01:00:00 deployed to prod",
        ])
        result = journal_read("BOM", ledger=str(path))
        self.assertIn("BOM", result)
        self.assertIn("fixed BOM", result)

    def test_no_match(self):
        path = Path(self.tmpdir) / "JOURNAL.md"
        _journal_file(path, ["## 2026-08-26T00:00:00 fixed BOM"])
        result = journal_read("zzz", ledger=str(path))
        self.assertIn("no entries matching", result)

    def test_missing_ledger(self):
        path = Path(self.tmpdir) / "nonexistent.md"
        result = journal_read("test", ledger=str(path))
        self.assertIn("error", result)


# --- ask() tool loop integration ---

class TestAskToolLoop(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    @patch("qacompanion.ollama_bridge._is_ollama_available")
    @patch("qacompanion.ollama_bridge._ollama_generate")
    def test_ask_no_tool_calls(self, mock_gen, mock_avail):
        mock_avail.return_value = True
        mock_gen.return_value = "The answer is in case #1."
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        _cases_file(cases_path, [_make_case()])
        result = ask("what is this?", cases_path=str(cases_path))
        self.assertTrue(result["used_ollama"])
        self.assertEqual(result["answer"], "The answer is in case #1.")
        self.assertEqual(mock_gen.call_count, 1)

    @patch("qacompanion.ollama_bridge._is_ollama_available")
    @patch("qacompanion.ollama_bridge._ollama_generate")
    def test_ask_single_tool_call(self, mock_gen, mock_avail):
        mock_avail.return_value = True
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        _cases_file(cases_path, [_make_case(sig="ENOENT file", diag="missing file")])
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        _digest_file(digest_path, [])

        # First call: model asks for a tool; second call: final answer
        mock_gen.side_effect = [
            '[TOOL: case_search(query="ENOENT")]',
            'The answer is: missing file (case #1).',
        ]
        result = ask("what is ENOENT?", cases_path=str(cases_path), digest_path=str(digest_path))
        self.assertTrue(result["used_ollama"])
        self.assertEqual(mock_gen.call_count, 2)
        self.assertIn("missing file", result["answer"])

    @patch("qacompanion.ollama_bridge._is_ollama_available")
    @patch("qacompanion.ollama_bridge._ollama_generate")
    def test_ask_loop_guard_stops_at_max(self, mock_gen, mock_avail):
        mock_avail.return_value = True
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        _cases_file(cases_path, [_make_case()])
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        _digest_file(digest_path, [])

        # Model keeps asking for tools every time
        mock_gen.return_value = '[TOOL: case_search(query="test")]'
        result = ask("test?", cases_path=str(cases_path), digest_path=str(digest_path))
        self.assertTrue(result["used_ollama"])
        # MAX_TOOL_CALLS + 1 calls total (initial + guard iterations)
        self.assertEqual(mock_gen.call_count, MAX_TOOL_CALLS + 1)

    @patch("qacompanion.ollama_bridge._is_ollama_available")
    @patch("qacompanion.ollama_bridge._ollama_generate")
    def test_ask_tool_error_handled(self, mock_gen, mock_avail):
        mock_avail.return_value = True
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        _cases_file(cases_path, [])
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        _digest_file(digest_path, [])

        mock_gen.side_effect = [
            '[TOOL: journal_read(pattern="test")]',
            "Based on the tool result, I cannot find information.",
        ]
        # journal_read with missing ledger returns error string, doesn't raise
        result = ask("test?", cases_path=str(cases_path), digest_path=str(digest_path))
        self.assertTrue(result["used_ollama"])
        self.assertEqual(mock_gen.call_count, 2)

    @patch("qacompanion.ollama_bridge._is_ollama_available")
    def test_ask_fallback_no_ollama(self, mock_avail):
        mock_avail.return_value = False
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        _cases_file(cases_path, [_make_case(sig="test error", diag="fix")])
        result = ask("test", cases_path=str(cases_path))
        self.assertFalse(result["used_ollama"])
        self.assertIn("fix", result["answer"])

    @patch("qacompanion.ollama_bridge._is_ollama_available")
    @patch("qacompanion.ollama_bridge._ollama_generate")
    def test_ask_multiple_tool_calls_one_turn(self, mock_gen, mock_avail):
        mock_avail.return_value = True
        cases_path = Path(self.tmpdir) / "cases.jsonl"
        _cases_file(cases_path, [_make_case(sig="BOM error", diag="strip BOM")])
        digest_path = Path(self.tmpdir) / "digest.jsonl"
        _digest_file(digest_path, [_make_digest(content="BOM in JSONL config")])

        mock_gen.side_effect = [
            '[TOOL: case_search(query="BOM")][TOOL: doc_grep(query="BOM")]',
            "BOM errors are caused by UTF-8 BOM markers (case #1, doc).",
        ]
        result = ask("BOM?", cases_path=str(cases_path), digest_path=str(digest_path))
        self.assertTrue(result["used_ollama"])
        self.assertEqual(mock_gen.call_count, 2)
        self.assertIn("BOM", result["answer"])


# --- tools registry ---

class TestToolsRegistry(unittest.TestCase):
    def test_three_tools_registered(self):
        self.assertEqual(set(TOOLS.keys()), {"case_search", "doc_grep", "journal_read"})

    def test_all_tools_are_callable(self):
        for name, fn in TOOLS.items():
            self.assertTrue(callable(fn), f"{name} is not callable")

    def test_max_tool_calls_constant(self):
        self.assertEqual(MAX_TOOL_CALLS, 3)
        self.assertIsInstance(MAX_TOOL_CALLS, int)


# --- tool_instructions constant ---

class TestToolInstructions(unittest.TestCase):
    def test_prompt_includes_tools_when_enabled(self):
        from qacompanion.ollama_bridge import _build_prompt, TOOL_INSTRUCTIONS
        context = {"cases": [], "digest": []}
        prompt = _build_prompt("test", context, use_tools=True)
        self.assertIn("Research Tools", prompt)
        self.assertIn("case_search", prompt)
        self.assertIn("doc_grep", prompt)
        self.assertIn("journal_read", prompt)

    def test_prompt_excludes_tools_when_disabled(self):
        from qacompanion.ollama_bridge import _build_prompt
        context = {"cases": [], "digest": []}
        prompt = _build_prompt("test", context, use_tools=False)
        self.assertNotIn("Research Tools", prompt)

    def test_tool_results_injected_into_prompt(self):
        from qacompanion.ollama_bridge import _build_prompt
        context = {
            "cases": [],
            "digest": [],
            "tool_results": ["[case_search(BOM)] => found case #1"],
        }
        prompt = _build_prompt("test", context, use_tools=True)
        self.assertIn("Tool Results", prompt)
        self.assertIn("found case #1", prompt)


if __name__ == "__main__":
    unittest.main()
