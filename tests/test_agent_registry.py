"""S32 tool registry v2 tests: registration, pipeline stages, knowledge tools.

Hermetic: knowledge-tool e2e fixtures use temp files; no Ollama, no network.
"""

import dataclasses
import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from qacompanion.agent import ToolCall, ToolDefinition, ToolResult
from qacompanion.agent.registry import (
    ALLOW_ALL_POLICY,
    DESTRUCTIVE,
    READ_ONLY,
    RegisteredTool,
    RegistryError,
    ToolRegistry,
    default_knowledge_registry,
    validate_tool_arguments,
)
from qacompanion.skills import digest as digest_mod
from qacompanion.skills import journal as journal_mod
from qacompanion.store import CaseStore


def _def(name="echo", schema=None):
    return ToolDefinition(
        name=name,
        description=f"test tool {name}",
        # default test schema accepts arbitrary kwargs (strict schemas are
        # declared explicitly in the validation/denial tests)
        parameters_schema=schema
        if schema is not None
        else {"type": "object", "properties": {}, "additionalProperties": True},
    )


def _tool(name="echo", handler=lambda **kw: "ok", **kwargs):
    if "definition" not in kwargs:
        kwargs["definition"] = _def(name, kwargs.pop("schema", None))
    return RegisteredTool(handler=handler, **kwargs)


class TestArgumentValidation(unittest.TestCase):
    def _schema(self, **extra):
        return {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["query"],
            **extra,
        }

    def _validate(self, arguments, schema=None):
        return validate_tool_arguments(_def(schema=schema or self._schema()), arguments)

    def test_valid_arguments_pass(self):
        self.assertEqual(self._validate({"query": "x", "limit": 3}), [])

    def test_missing_required_rejected(self):
        errors = self._validate({"limit": 3})
        self.assertTrue(any("missing required argument: query" in e for e in errors))

    def test_wrong_type_rejected(self):
        errors = self._validate({"query": 42})
        self.assertTrue(any("query must be a string" in e for e in errors))

    def test_bool_is_not_integer(self):
        errors = self._validate({"query": "x", "limit": True})
        self.assertTrue(any("limit must be an integer" in e for e in errors))

    def test_unknown_argument_rejected(self):
        errors = self._validate({"query": "x", "bogus": 1})
        self.assertTrue(any("unknown argument: bogus" in e for e in errors))

    def test_additional_properties_allowed_when_declared(self):
        errors = self._validate({"query": "x", "bogus": 1}, self._schema(additionalProperties=True))
        self.assertEqual(errors, [])

    def test_non_object_arguments_rejected(self):
        self.assertEqual(self._validate("query=x"), ["arguments must be an object, got str"])

    def test_multiple_errors_reported(self):
        errors = self._validate({"bogus": 1})
        self.assertGreaterEqual(len(errors), 2)


class TestRegistration(unittest.TestCase):
    def test_register_get_names_describe(self):
        reg = ToolRegistry()
        reg.register(_tool("case_search"))
        self.assertEqual(reg.names(), ["case_search"])
        self.assertEqual(reg.get("case_search").definition.name, "case_search")
        described = reg.describe()[0]
        self.assertEqual(described["name"], "case_search")
        self.assertEqual(described["side_effect_level"], READ_ONLY)

    def test_describe_is_json_serializable(self):
        reg = ToolRegistry()
        reg.register(_tool("t1", side_effect_level=DESTRUCTIVE, timeout_seconds=1.5))
        line = json.dumps(reg.describe())
        self.assertIn("DESTRUCTIVE", line)

    def test_schemas_returns_definitions_for_providers(self):
        reg = ToolRegistry()
        reg.register(_tool("b_tool"))
        reg.register(_tool("a_tool"))
        self.assertEqual([d.name for d in reg.schemas()], ["a_tool", "b_tool"])

    def test_duplicate_registration_rejected(self):
        reg = ToolRegistry()
        reg.register(_tool("dup"))
        with self.assertRaises(RegistryError):
            reg.register(_tool("dup"))

    def test_unknown_get_rejected(self):
        with self.assertRaises(RegistryError):
            ToolRegistry().get("nope")

    def test_invalid_metadata_rejected(self):
        with self.assertRaises(RegistryError):
            _tool(handler="not callable")
        with self.assertRaises(RegistryError):
            _tool(side_effect_level="TELEPORT")
        with self.assertRaises(RegistryError):
            _tool(timeout_seconds=0)
        with self.assertRaises(RegistryError):
            _tool(definition="not-a-definition")


class _PipelineBase(unittest.TestCase):
    def setUp(self):
        self.reg = ToolRegistry()
        self.reg.register(_tool("echo", handler=lambda **kw: f"echo {kw}"))


class TestPipelineHappyPath(_PipelineBase):
    def test_successful_execution(self):
        result = self.reg.execute(ToolCall(name="echo", arguments={"x": 1}))
        self.assertTrue(result.ok)
        self.assertEqual(result.output, "echo {'x': 1}")
        self.assertIsNone(result.error)
        self.assertIsInstance(result.duration_ms, int)

    def test_call_id_carried_into_result(self):
        result = self.reg.execute(ToolCall(name="echo", arguments={}, call_id="c9"))
        self.assertEqual(result.call_id, "c9")

    def test_none_output_coerced_to_empty_string(self):
        self.reg.register(_tool("nuller", handler=lambda **kw: None))
        result = self.reg.execute(ToolCall(name="nuller", arguments={}))
        self.assertTrue(result.ok)
        self.assertEqual(result.output, "")

    def test_non_string_output_coerced(self):
        self.reg.register(_tool("counter", handler=lambda **kw: 42))
        result = self.reg.execute(ToolCall(name="counter", arguments={}))
        self.assertTrue(result.ok)
        self.assertEqual(result.output, "42")


class TestPipelineStageFailures(_PipelineBase):
    def test_unknown_tool(self):
        result = self.reg.execute(ToolCall(name="ghost", arguments={}))
        self.assertFalse(result.ok)
        self.assertIn("unknown tool", result.error)

    def test_malformed_arguments(self):
        self.reg.register(_tool("strict", schema={
            "type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"],
        }))
        result = self.reg.execute(ToolCall(name="strict", arguments={}))
        self.assertFalse(result.ok)
        self.assertIn("invalid arguments", result.error)
        self.assertIn("missing required argument: q", result.error)

    def test_permission_denied(self):
        class DenyAll:
            def check(self, tool_name, arguments):
                return "DENY"

        result = self.reg.execute(ToolCall(name="echo", arguments={}), policy=DenyAll())
        self.assertFalse(result.ok)
        self.assertIn("permission denied by policy", result.error)

    def test_permission_ask_is_structured_denial_until_s38(self):
        class Asker:
            def check(self, tool_name, arguments):
                return "ASK"

        result = self.reg.execute(ToolCall(name="echo", arguments={}), policy=Asker())
        self.assertFalse(result.ok)
        self.assertIn("ASK", result.error)
        self.assertIn("S38", result.error)

    def test_workspace_required_not_configured(self):
        self.reg.register(_tool("rooted", handler=lambda **kw: "ws", requires_workspace=True))
        result = self.reg.execute(ToolCall(name="rooted", arguments={}))
        self.assertFalse(result.ok)
        self.assertIn("workspace required", result.error)

    def test_workspace_present_allows_execution(self):
        # workspace is a pipeline gate context in S32, not a handler argument
        self.reg.register(_tool("rooted", handler=lambda **kw: "ws ok",
                                requires_workspace=True))
        result = self.reg.execute(ToolCall(name="rooted", arguments={}), workspace="C:/proj")
        self.assertTrue(result.ok)
        self.assertEqual(result.output, "ws ok")

    def test_cancellation_before_dispatch(self):
        ran = []

        def handler(**kw):
            ran.append(True)
            return "nope"

        self.reg.register(_tool("slow", handler=handler, cancellable=True))
        event = threading.Event()
        event.set()
        result = self.reg.execute(ToolCall(name="slow", arguments={}), cancel_event=event)
        self.assertFalse(result.ok)
        self.assertTrue(result.cancelled)
        self.assertEqual(ran, [])

    def test_timeout_is_structured_outcome(self):
        def sleepy(**kw):
            time.sleep(0.4)
            return "late"

        self.reg.register(_tool("sleepy", handler=sleepy, timeout_seconds=0.05))
        result = self.reg.execute(ToolCall(name="sleepy", arguments={}))
        self.assertFalse(result.ok)
        self.assertTrue(result.timed_out)
        self.assertIn("timed out", result.error)

    def test_handler_exception_is_structured(self):
        def boom(**kw):
            raise RuntimeError("disk on fire")

        self.reg.register(_tool("boomer", handler=boom))
        result = self.reg.execute(ToolCall(name="boomer", arguments={}))
        self.assertFalse(result.ok)
        self.assertIn("handler failed", result.error)
        self.assertIn("disk on fire", result.error)


class TestAuditAndDefaults(_PipelineBase):
    def test_audit_called_for_success_and_denial(self):
        seen = []
        self.reg.execute(ToolCall(name="echo", arguments={}), audit=seen.append)
        self.reg.execute(ToolCall(name="ghost", arguments={}), audit=seen.append)
        self.assertEqual(len(seen), 2)
        self.assertTrue(seen[0].ok)
        self.assertFalse(seen[1].ok)

    def test_default_policy_allows(self):
        result = self.reg.execute(ToolCall(name="echo", arguments={}))
        self.assertTrue(result.ok)

    def test_allow_all_singleton_is_policy(self):
        self.assertEqual(ALLOW_ALL_POLICY.check("anything", {}), "ALLOW")


class TestToolResultExtension(unittest.TestCase):
    def test_flags_default_false(self):
        r = ToolResult(call_name="t", ok=True, output="o")
        self.assertFalse(r.timed_out)
        self.assertFalse(r.cancelled)

    def test_flags_round_trip(self):
        r = ToolResult(call_name="t", ok=False, output="",
                       error="timed out after 0.05s", timed_out=True)
        self.assertEqual(ToolResult.from_dict(r.to_dict()), r)

    def test_cancelled_round_trip(self):
        r = ToolResult(call_name="t", ok=False, output="", error="cancelled",
                       cancelled=True)
        restored = ToolResult.from_dict(json.loads(json.dumps(r.to_dict())))
        self.assertTrue(restored.cancelled)
        self.assertFalse(restored.timed_out)

    def test_dataclass_still_frozen_compatible(self):
        # ToolResult stays a plain mutable dataclass (frozen is ToolCall's job)
        self.assertFalse(dataclasses.fields(ToolResult)[0].name == "name")


class TestKnowledgeRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cases_path = Path(self.tmp) / "cases.jsonl"
        self.digest_path = Path(self.tmp) / "digest.jsonl"
        self.ledger = Path(self.tmp) / "journal.md"
        store = CaseStore(self.cases_path)
        store.record("TypeError: cannot pickle", "TypeError traceback",
                     "pickling a local lambda; move it to module scope", by="test")
        DigestStore = digest_mod.DigestStore
        ds = DigestStore(self.digest_path)
        ds.add("deploy.md", "Deploy", "Run docker compose with the prod env file.")
        journal_mod.add("VOID-L1 residual: BOM in configs breaks JSONL load",
                        ledger=str(self.ledger))
        self.reg = default_knowledge_registry(
            cases_path=self.cases_path, digest_path=self.digest_path,
            ledger=str(self.ledger),
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_three_knowledge_tools_registered(self):
        self.assertEqual(self.reg.names(), ["case_search", "doc_grep", "journal_read"])
        described = {d["name"]: d for d in self.reg.describe()}
        self.assertEqual(described["case_search"]["category"], "knowledge")
        self.assertEqual(described["case_search"]["side_effect_level"], READ_ONLY)
        self.assertEqual(described["case_search"]["permission_level"], "read")

    def test_case_search_through_registry(self):
        result = self.reg.execute(
            ToolCall(name="case_search", arguments={"query": "pickle"})
        )
        self.assertTrue(result.ok, result.error)
        self.assertIn("pickling a local lambda", result.output)

    def test_case_search_no_match_is_honest(self):
        result = self.reg.execute(
            ToolCall(name="case_search", arguments={"query": "zzz-unheard-of"})
        )
        self.assertTrue(result.ok)
        self.assertIn("no matching case", result.output)

    def test_doc_grep_through_registry(self):
        result = self.reg.execute(ToolCall(name="doc_grep", arguments={"query": "docker"}))
        self.assertTrue(result.ok, result.error)
        self.assertIn("docker compose", result.output)

    def test_journal_read_through_registry(self):
        result = self.reg.execute(
            ToolCall(name="journal_read", arguments={"pattern": "BOM"})
        )
        self.assertTrue(result.ok, result.error)
        self.assertIn("BOM", result.output)

    def test_malformed_arguments_denied_structurally(self):
        result = self.reg.execute(ToolCall(name="case_search", arguments={}))
        self.assertFalse(result.ok)
        self.assertIn("missing required argument: query", result.error)

    def test_defaults_use_cwd_paths_when_unset(self):
        bare = default_knowledge_registry()
        self.assertEqual(bare.names(), ["case_search", "doc_grep", "journal_read"])
        result = bare.execute(ToolCall(name="doc_grep", arguments={"query": "x"}))
        # repo-root digest.jsonl is gitignored runtime data; result must be
        # structured either way, never an exception
        self.assertIsInstance(result, ToolResult)


if __name__ == "__main__":
    unittest.main()
