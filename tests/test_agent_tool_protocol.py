"""Regression tests for super-audit S2 (B1/B2): the textual tool protocol.

Failure modes pinned here (all in providers._parse_textual_tool_calls):
- greedy line match merged two calls on one line / mis-split `)]` values;
- bare typed literals (count=2, force=true) the training renderer emits
  were unrepresentable, so every non-string arg failed validation;
- unknown escapes (\\r, \\u, ...) raised KeyError out of AgentLoop.run;
- shape-matched lines could vanish instead of becoming correctable calls.
Stdlib only.
"""

import unittest

from qacompanion.agent.providers import _parse_textual_tool_calls
from qacompanion.agent.training import format_tool_call


def _parsed_args(text):
    calls = _parse_textual_tool_calls(text)
    assert len(calls) == 1, text
    return calls[0].arguments


class TestTypedLiteralsB2(unittest.TestCase):
    def test_bare_int_bool_null_parse(self):
        args = _parsed_args('[TOOL: skill_find(query="x", k=3)]')
        self.assertEqual({"query": "x", "k": 3}, args)

    def test_negative_float_and_false(self):
        args = _parsed_args('[TOOL: thing(delta=-2, ratio=0.5, off=false)]')
        self.assertEqual({"delta": -2, "ratio": 0.5, "off": False}, args)

    def test_null_literal_is_none(self):
        args = _parsed_args('[TOOL: thing(limit=null)]')
        self.assertEqual({"limit": None}, args)

    def test_render_parse_round_trip_mixed(self):
        cases = [
            ("skill_find", {"query": "retry logic", "k": 3}),
            ("write_file", {"path": "a.py", "count": 2, "force": True}),
            ("thing", {"off": False, "limit": None, "ratio": -0.25}),
        ]
        for name, args in cases:
            with self.subTest(name=name):
                rendered = format_tool_call(name, args)
                self.assertNotIn("\n", rendered)
                self.assertEqual(args, _parsed_args(rendered))


class TestGreedyMatchB1(unittest.TestCase):
    def test_two_calls_on_one_line_stay_separate(self):
        calls = _parse_textual_tool_calls(
            '[TOOL: read_file(path="a.py")] [TOOL: read_file(path="b.py")]')
        self.assertEqual(2, len(calls))
        self.assertEqual("a.py", calls[0].arguments["path"])
        self.assertEqual("b.py", calls[1].arguments["path"])

    def test_close_bracket_paren_inside_string_value(self):
        args = _parsed_args('[TOOL: write_file(path="f.py", content="a)]b")]')
        self.assertEqual({"path": "f.py", "content": "a)]b"}, args)

    def test_parens_inside_string_value(self):
        args = _parsed_args('[TOOL: run_tests(command="pytest test_(x).py")]')
        self.assertEqual({"command": "pytest test_(x).py"}, args)

    def test_quote_bracket_inside_string_value(self):
        args = _parsed_args(r'[TOOL: write_file(content="say \"] done")]')
        self.assertEqual({"content": 'say "] done'}, args)

    def test_trailing_backslash_round_trip(self):
        args = {"path": "C:\\"}
        self.assertEqual(args, _parsed_args(format_tool_call("t", args)))

    def test_empty_string_value(self):
        self.assertEqual({"k": ""}, _parsed_args('[TOOL: t(k="")]'))


class TestUnknownEscapesB1(unittest.TestCase):
    def test_unknown_escape_never_crashes_and_keeps_backslash(self):
        args = _parsed_args(r'[TOOL: write_file(content="a\rb\qc")]')
        self.assertEqual({"content": "a\\rb\\qc"}, args)

    def test_known_escapes_still_unescape(self):
        args = _parsed_args(r'[TOOL: write_file(content="a\nb\tc\"d\\e")]')
        self.assertEqual({"content": 'a\nb\tc"d\\e'}, args)


class TestShapeMatchAlwaysYieldsACallB1(unittest.TestCase):
    def test_garbage_args_become_empty_args_call(self):
        calls = _parse_textual_tool_calls("[TOOL: read_file(path=)]")
        self.assertEqual(1, len(calls))
        self.assertEqual({}, calls[0].arguments)

    def test_empty_parens_become_empty_args_call(self):
        calls = _parse_textual_tool_calls("[TOOL: read_file()]")
        self.assertEqual(1, len(calls))
        self.assertEqual({}, calls[0].arguments)

    def test_unclosed_head_skipped_later_call_found(self):
        calls = _parse_textual_tool_calls(
            '[TOOL: broken(path="x"\n[TOOL: read_file(path="ok.py")]')
        self.assertEqual(1, len(calls))
        self.assertEqual({"path": "ok.py"}, calls[0].arguments)


class TestLegacyDialectsPreserved(unittest.TestCase):
    def test_bare_value_maps_to_query(self):
        calls = _parse_textual_tool_calls('[TOOL: case_search("flaky")]')
        self.assertEqual({"query": "flaky"}, calls[0].arguments)

    def test_bare_value_maps_to_pattern_for_journal(self):
        calls = _parse_textual_tool_calls("[TOOL: journal_read('oops')]")
        self.assertEqual({"pattern": "oops"}, calls[0].arguments)

    def test_single_quoted_windows_path_stays_raw(self):
        args = _parsed_args(r"[TOOL: read_file(path='C:\new\test')]")
        self.assertEqual({"path": "C:\\new\\test"}, args)


if __name__ == "__main__":
    unittest.main()
