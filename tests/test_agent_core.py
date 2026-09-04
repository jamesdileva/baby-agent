"""S31 agent foundation tests: contracts, providers, session.

All tests are hermetic — Ollama bridge internals are mocked. The single
live test is opt-in via QA_OLLAMA_LIVE=1 (DECISIONS 2026-09-04: live
provider tests are never CI gates).
"""

import dataclasses
import json
import os
import re
import unittest
from unittest.mock import patch

from qacompanion import ollama_bridge as bridge
from qacompanion.agent import (
    TERMINAL_STATES,
    AgentConfig,
    AgentSession,
    AgentState,
    FakeModelProvider,
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    OllamaProvider,
    ProviderError,
    SessionError,
    ToolCall,
    ToolDefinition,
    ToolResult,
    knowledge_tool_definitions,
)
from qacompanion.agent.providers import _flatten_messages
from qacompanion.ollama_bridge import OllamaError


STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _msg(role="user", content="hello"):
    return ModelMessage(role=role, content=content)


def _tool_def(name="case_search"):
    return ToolDefinition(
        name=name, description=f"desc {name}", parameters_schema={"type": "object"}
    )


class TestModelMessage(unittest.TestCase):
    def test_valid_roles_accepted(self):
        for role in ("system", "user", "assistant", "tool"):
            self.assertEqual(ModelMessage(role=role, content="x").role, role)

    def test_invalid_role_rejected(self):
        with self.assertRaises(ValueError):
            ModelMessage(role="wizard", content="x")

    def test_non_string_content_rejected(self):
        with self.assertRaises(ValueError):
            ModelMessage(role="user", content=42)

    def test_dict_round_trip(self):
        m = ModelMessage(role="assistant", content="de compuestó ✅")
        self.assertEqual(ModelMessage.from_dict(m.to_dict()), m)

    def test_from_dict_malformed(self):
        with self.assertRaises(ValueError):
            ModelMessage.from_dict(["user", "x"])
        with self.assertRaises(ValueError):
            ModelMessage.from_dict({"role": "user"})


class TestModelRequest(unittest.TestCase):
    def test_defaults(self):
        r = ModelRequest(messages=[_msg()])
        self.assertEqual(r.tools, [])
        self.assertIsNone(r.model)
        self.assertIsNone(r.temperature)

    def test_rejects_non_message_items(self):
        with self.assertRaises(ValueError):
            ModelRequest(messages=["hello"])

    def test_rejects_non_tool_definition_items(self):
        with self.assertRaises(ValueError):
            ModelRequest(messages=[_msg()], tools=["case_search"])

    def test_round_trip(self):
        r = ModelRequest(
            messages=[_msg("system", "be honest"), _msg("user", "q?")],
            tools=[_tool_def()],
            model="m1",
            temperature=0.2,
        )
        self.assertEqual(ModelRequest.from_dict(r.to_dict()), r)


class TestModelResponse(unittest.TestCase):
    def test_defaults(self):
        r = ModelResponse(text="done")
        self.assertEqual(r.finish_reason, "stop")
        self.assertEqual(r.tool_calls, [])
        self.assertFalse(r.has_tool_calls())

    def test_has_tool_calls(self):
        r = ModelResponse(text="", tool_calls=[ToolCall(name="t", arguments={})],
                          finish_reason="tool_calls")
        self.assertTrue(r.has_tool_calls())

    def test_invalid_finish_reason_rejected(self):
        with self.assertRaises(ValueError):
            ModelResponse(text="x", finish_reason="vibes")

    def test_rejects_non_tool_call_items(self):
        with self.assertRaises(ValueError):
            ModelResponse(text="x", tool_calls=["case_search"])

    def test_round_trip(self):
        r = ModelResponse(
            text="a",
            tool_calls=[ToolCall(name="case_search", arguments={"query": "x"}, call_id="c1")],
            finish_reason="tool_calls",
            usage={"prompt_tokens": 3, "completion_tokens": 5},
            model="m1",
        )
        self.assertEqual(ModelResponse.from_dict(r.to_dict()), r)


class TestToolDefinition(unittest.TestCase):
    def test_frozen(self):
        d = _tool_def()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            d.name = "other"

    def test_invalid_name_rejected(self):
        with self.assertRaises(ValueError):
            ToolDefinition(name="  ", description="d", parameters_schema={})

    def test_non_dict_schema_rejected(self):
        with self.assertRaises(ValueError):
            ToolDefinition(name="t", description="d", parameters_schema="object")

    def test_round_trip(self):
        d = _tool_def()
        self.assertEqual(ToolDefinition.from_dict(d.to_dict()), d)

    def test_from_dict_missing_fields(self):
        with self.assertRaises(ValueError):
            ToolDefinition.from_dict({"name": "t"})


class TestToolCall(unittest.TestCase):
    def test_frozen(self):
        c = ToolCall(name="case_search", arguments={"query": "x"})
        with self.assertRaises(dataclasses.FrozenInstanceError):
            c.name = "doc_grep"

    def test_non_dict_arguments_rejected(self):
        with self.assertRaises(ValueError):
            ToolCall(name="case_search", arguments="disk full")

    def test_round_trip_with_call_id(self):
        c = ToolCall(name="doc_grep", arguments={"query": "bom"}, call_id="abc")
        self.assertEqual(ToolCall.from_dict(c.to_dict()), c)


class TestToolResult(unittest.TestCase):
    def test_defaults(self):
        r = ToolResult(call_name="case_search", ok=True, output="hi")
        self.assertIsNone(r.error)
        self.assertIsNone(r.duration_ms)
        self.assertIsNone(r.call_id)

    def test_failure_record(self):
        r = ToolResult(call_name="case_search", ok=False, output="",
                       error="boom", duration_ms=12)
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "boom")

    def test_round_trip(self):
        r = ToolResult(call_name="t", ok=True, output="o", call_id="c",
                       error=None, duration_ms=7)
        self.assertEqual(ToolResult.from_dict(r.to_dict()), r)


class TestKnowledgeToolDefinitions(unittest.TestCase):
    def test_three_tools_with_canonical_names(self):
        defs = knowledge_tool_definitions()
        self.assertEqual(
            [d.name for d in defs], ["case_search", "doc_grep", "journal_read"]
        )

    def test_schemas_match_dispatch_argument_names(self):
        defs = {d.name: d for d in knowledge_tool_definitions()}
        self.assertEqual(defs["case_search"].parameters_schema["required"], ["query"])
        self.assertEqual(defs["doc_grep"].parameters_schema["required"], ["query"])
        self.assertEqual(defs["journal_read"].parameters_schema["required"], ["pattern"])
        for d in defs.values():
            self.assertTrue(d.description)


class TestFakeProvider(unittest.TestCase):
    def test_implements_interface(self):
        p = FakeModelProvider([])
        self.assertIsInstance(p, ModelProvider)
        self.assertEqual(p.name, "fake")

    def test_script_pops_in_order(self):
        p = FakeModelProvider([ModelResponse(text="first"), ModelResponse(text="second")])
        req = ModelRequest(messages=[_msg()])
        self.assertEqual(p.generate(req).text, "first")
        self.assertEqual(p.generate(req).text, "second")

    def test_tool_call_shortcut_wraps_response(self):
        call = ToolCall(name="case_search", arguments={"query": "x"})
        p = FakeModelProvider([call])
        resp = p.generate(ModelRequest(messages=[_msg()]))
        self.assertTrue(resp.has_tool_calls())
        self.assertEqual(resp.finish_reason, "tool_calls")
        self.assertEqual(resp.tool_calls[0], call)

    def test_exhaustion_raises(self):
        p = FakeModelProvider([ModelResponse(text="only")])
        req = ModelRequest(messages=[_msg()])
        p.generate(req)
        with self.assertRaises(ProviderError):
            p.generate(req)

    def test_empty_script_raises(self):
        with self.assertRaises(ProviderError):
            FakeModelProvider([]).generate(ModelRequest(messages=[_msg()]))


class TestOllamaProvider(unittest.TestCase):
    def setUp(self):
        self.p = OllamaProvider()
        self.req = ModelRequest(messages=[_msg("user", "what broke?")])

    def test_implements_interface(self):
        self.assertIsInstance(self.p, ModelProvider)
        self.assertEqual(self.p.name, "ollama")

    @patch("qacompanion.ollama_bridge._ollama_generate")
    @patch("qacompanion.ollama_bridge._is_ollama_available")
    def test_generate_happy_path(self, mock_avail, mock_gen):
        mock_avail.return_value = True
        mock_gen.return_value = "here is the answer"
        resp = self.p.generate(self.req)
        self.assertEqual(resp.text, "here is the answer")
        self.assertEqual(resp.finish_reason, "stop")
        self.assertFalse(resp.has_tool_calls())

    @patch("qacompanion.ollama_bridge._ollama_generate")
    @patch("qacompanion.ollama_bridge._is_ollama_available")
    def test_textual_tool_call_normalized(self, mock_avail, mock_gen):
        mock_avail.return_value = True
        mock_gen.return_value = '[TOOL: case_search(query="disk full")]'
        resp = self.p.generate(self.req)
        self.assertEqual(resp.finish_reason, "tool_calls")
        self.assertEqual(len(resp.tool_calls), 1)
        call = resp.tool_calls[0]
        self.assertEqual(call.name, "case_search")
        self.assertEqual(call.arguments, {"query": "disk full"})

    @patch("qacompanion.ollama_bridge._ollama_generate")
    @patch("qacompanion.ollama_bridge._is_ollama_available")
    def test_journal_read_uses_pattern_keyword(self, mock_avail, mock_gen):
        mock_avail.return_value = True
        mock_gen.return_value = '[TOOL: journal_read(pattern="BOM")]'
        resp = self.p.generate(self.req)
        self.assertEqual(resp.tool_calls[0].arguments, {"pattern": "BOM"})

    @patch("qacompanion.ollama_bridge._ollama_generate")
    @patch("qacompanion.ollama_bridge._is_ollama_available")
    def test_plain_text_finish_reason_stop(self, mock_avail, mock_gen):
        mock_avail.return_value = True
        mock_gen.return_value = "no tools needed"
        self.assertEqual(self.p.generate(self.req).finish_reason, "stop")

    @patch("qacompanion.ollama_bridge._ollama_generate")
    @patch("qacompanion.ollama_bridge._is_ollama_available")
    def test_bridge_error_wrapped_as_provider_error(self, mock_avail, mock_gen):
        mock_avail.return_value = True
        mock_gen.side_effect = OllamaError("model crashed")
        with self.assertRaises(ProviderError):
            self.p.generate(self.req)

    @patch("qacompanion.ollama_bridge._is_ollama_available")
    def test_unavailable_raises_provider_error(self, mock_avail):
        mock_avail.return_value = False
        with self.assertRaises(ProviderError):
            self.p.generate(self.req)

    @patch("qacompanion.ollama_bridge._ollama_generate")
    @patch("qacompanion.ollama_bridge._is_ollama_available")
    def test_request_model_forwarded(self, mock_avail, mock_gen):
        mock_avail.return_value = True
        mock_gen.return_value = "ok"
        self.p.generate(ModelRequest(messages=[_msg()], model="m2"))
        self.assertEqual(mock_gen.call_args.kwargs.get("model"), "m2")

    @patch("qacompanion.ollama_bridge._ollama_generate")
    @patch("qacompanion.ollama_bridge._is_ollama_available")
    def test_provider_model_wins_over_request_model(self, mock_avail, mock_gen):
        mock_avail.return_value = True
        mock_gen.return_value = "ok"
        resp = OllamaProvider(model="m1").generate(
            ModelRequest(messages=[_msg()], model="m2")
        )
        self.assertEqual(resp.model, "m1")

    @patch("qacompanion.ollama_bridge._ollama_generate")
    @patch("qacompanion.ollama_bridge._is_ollama_available")
    def test_default_model_fallback(self, mock_avail, mock_gen):
        mock_avail.return_value = True
        mock_gen.return_value = "ok"
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OLLAMA_MODEL", None)
            resp = self.p.generate(self.req)
        self.assertEqual(resp.model, bridge.DEFAULT_MODEL)

    @patch("qacompanion.ollama_bridge._ollama_generate")
    @patch("qacompanion.ollama_bridge._is_ollama_available")
    def test_textual_multi_arg_tool_call(self, mock_avail, mock_gen):
        # found by the live smoke: the S27 single-argument parser could not
        # express write_file(path=..., content=...)
        mock_avail.return_value = True
        mock_gen.return_value = (
            'Working on it.\n'
            '[TOOL: write_file(path="hello.txt", content="Hello from Baby-Agent")]'
        )
        resp = self.p.generate(self.req)
        self.assertEqual(resp.finish_reason, "tool_calls")
        call = resp.tool_calls[0]
        self.assertEqual(call.name, "write_file")
        self.assertEqual(call.arguments,
                         {"path": "hello.txt", "content": "Hello from Baby-Agent"})

    @patch("qacompanion.ollama_bridge._ollama_generate")
    @patch("qacompanion.ollama_bridge._is_ollama_available")
    def test_textual_bare_value_backward_compatible(self, mock_avail, mock_gen):
        mock_avail.return_value = True
        mock_gen.return_value = "[TOOL: case_search(\"disk full\")]"
        resp = self.p.generate(self.req)
        self.assertEqual(resp.tool_calls[0].arguments, {"query": "disk full"})


class TestFlattenMessages(unittest.TestCase):
    def test_system_blocks_come_first(self):
        prompt = _flatten_messages([
            _msg("user", "question"),
            _msg("system", "be honest"),
            _msg("assistant", "sure"),
        ])
        self.assertTrue(prompt.startswith("be honest"))
        self.assertIn("user: question", prompt)
        self.assertIn("assistant: sure", prompt)

    def test_empty_messages_flatten_to_empty_prompt(self):
        self.assertEqual(_flatten_messages([]), "")


class TestAgentState(unittest.TestCase):
    def test_all_ten_states_exist(self):
        self.assertEqual(
            {s.value for s in AgentState},
            {"CREATED", "PLANNING", "RUNNING", "WAITING_FOR_PERMISSION",
             "VERIFYING", "RECOVERING", "PAUSED", "CANCELLED", "COMPLETED", "FAILED"},
        )

    def test_terminal_states(self):
        self.assertEqual(
            TERMINAL_STATES,
            {AgentState.CANCELLED, AgentState.COMPLETED, AgentState.FAILED},
        )


class TestAgentConfig(unittest.TestCase):
    def test_defaults(self):
        c = AgentConfig()
        self.assertEqual(c.max_iterations, 25)
        self.assertEqual(c.command_timeout_seconds, 120)
        self.assertEqual(c.max_runtime_minutes, 30)

    def test_custom_values(self):
        self.assertEqual(AgentConfig(max_iterations=5).max_iterations, 5)

    def test_non_positive_rejected(self):
        with self.assertRaises(ValueError):
            AgentConfig(max_iterations=0)
        with self.assertRaises(ValueError):
            AgentConfig(command_timeout_seconds=-1)

    def test_bool_is_not_a_valid_int(self):
        with self.assertRaises(ValueError):
            AgentConfig(max_iterations=True)

    def test_round_trip(self):
        c = AgentConfig(max_iterations=7, command_timeout_seconds=60, max_runtime_minutes=5)
        self.assertEqual(AgentConfig.from_dict(c.to_dict()), c)


class TestAgentSession(unittest.TestCase):
    def test_created_defaults(self):
        s = AgentSession(goal="fix the flaky test")
        self.assertEqual(s.state, AgentState.CREATED)
        self.assertEqual(s.iterations, 0)
        self.assertEqual(s.messages, [])
        self.assertRegex(s.session_id, r"^[0-9a-f]{32}$")
        self.assertRegex(s.created_at, STAMP_RE)

    def test_unique_session_ids(self):
        self.assertNotEqual(
            AgentSession(goal="a").session_id, AgentSession(goal="b").session_id
        )

    def test_empty_goal_rejected(self):
        with self.assertRaises(ValueError):
            AgentSession(goal="   ")

    def test_happy_path_transitions(self):
        s = AgentSession(goal="g")
        s.transition(AgentState.PLANNING)
        s.transition(AgentState.RUNNING)
        s.transition(AgentState.VERIFYING)
        s.transition(AgentState.COMPLETED)
        self.assertEqual(s.state, AgentState.COMPLETED)

    def test_transition_from_terminal_rejected(self):
        for terminal in (AgentState.CANCELLED, AgentState.COMPLETED, AgentState.FAILED):
            s = AgentSession(goal="g")
            s.state = terminal
            with self.assertRaises(SessionError):
                s.transition(AgentState.RUNNING)

    def test_transition_requires_state_enum(self):
        s = AgentSession(goal="g")
        with self.assertRaises(SessionError):
            s.transition("RUNNING")

    def test_updated_at_advances_on_transition(self):
        s = AgentSession(goal="g")
        first = s.updated_at
        s.transition(AgentState.PLANNING)
        self.assertGreaterEqual(s.updated_at, first)

    def test_full_round_trip(self):
        s = AgentSession(goal="fix import error", workspace_root="C:/proj")
        s.transition(AgentState.RUNNING)
        s.messages.append(_msg("user", "why import error?"))
        call = ToolCall(name="case_search", arguments={"query": "import"}, call_id="c1")
        s.tool_calls.append(call)
        s.observations.append(ToolResult(call_name="case_search", ok=True,
                                         output="case #3", call_id="c1"))
        s.files_changed.append("src/app.py")
        s.errors.append("ModuleNotFoundError")
        s.iterations = 4
        s.transition(AgentState.COMPLETED)
        s.final_result = "fixed"
        s.termination_reason = "goal verified"
        restored = AgentSession.from_dict(s.to_dict())
        self.assertEqual(restored, s)
        self.assertEqual(restored.state, AgentState.COMPLETED)

    def test_jsonl_round_trip(self):
        s = AgentSession(goal="g ✅")
        s.transition(AgentState.RUNNING)
        line = json.dumps(s.to_dict())
        self.assertEqual(AgentSession.from_dict(json.loads(line)), s)

    def test_from_dict_malformed(self):
        with self.assertRaises(ValueError):
            AgentSession.from_dict(["not", "an", "object"])
        with self.assertRaises(ValueError):
            AgentSession.from_dict({"workspace_root": "/x"})
        with self.assertRaises(ValueError):
            AgentSession.from_dict({"goal": "g", "state": "DREAMING"})
        with self.assertRaises(ValueError):
            AgentSession.from_dict({"goal": "g", "messages": [{"role": "wizard", "content": "x"}]})

    def test_from_dict_bad_tool_call_rejected(self):
        with self.assertRaises(ValueError):
            AgentSession.from_dict(
                {"goal": "g", "tool_calls": [{"name": "case_search"}]}
            )


@unittest.skipUnless(
    os.environ.get("QA_OLLAMA_LIVE"), "live Ollama test is opt-in (QA_OLLAMA_LIVE=1)"
)
class TestLiveOllama(unittest.TestCase):
    def test_live_generate(self):
        provider = OllamaProvider()
        resp = provider.generate(ModelRequest(messages=[_msg("user", "ping")]))
        self.assertIsInstance(resp.text, str)
        self.assertIn(resp.finish_reason, ("stop", "tool_calls"))


if __name__ == "__main__":
    unittest.main()
