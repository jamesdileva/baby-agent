"""S64 slices 2+3 tests: ep0.5 demonstration injection (worked examples
in context assembly) and dashboard brain selection."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qacompanion.agent import ModelResponse, ToolCall
from qacompanion.agent.benchmark import run_benchmark
from qacompanion.agent.context import ContextBuilder, MemoryRetriever
from qacompanion.agent.ep1 import format_demonstration
from qacompanion.agent.experience import ExperienceStore, MemoryLayer
from qacompanion.agent.providers import FakeModelProvider, \
    GeminiModelProvider, OllamaProvider
from qacompanion.agent.server import default_provider_factory

STEPS = [
    {"tool": "read_file", "args": {"path": "calculator.py"},
     "ok": True, "result_head": "def add(a, b):\n    return a - b"},
    {"tool": "edit_file",
     "args": {"path": "calculator.py", "old_string": "return a - b",
              "new_string": "return a + b"},
     "ok": True, "result_head": "edit applied"},
    {"tool": "run_tests", "args": {"command": "python -m unittest"},
     "ok": True, "result_head": "Ran 2 tests ... OK"},
]


def _demo_experience(store: ExperienceStore, outcome="success"):
    from qacompanion.agent.session_learning import session_to_experience
    from qacompanion.agent.session import AgentSession, AgentState

    session = AgentSession(goal="The tests in this project are failing. "
                                "Find the bug, fix it, and run the tests "
                                "to verify they pass.")
    session.tool_calls = [
        ToolCall(name=s["tool"], arguments=dict(s["args"])) for s in STEPS]
    from qacompanion.agent.contracts import ToolResult
    session.observations = [
        ToolResult(call_name=s["tool"], ok=True,
                   output=s["result_head"]) for s in STEPS]
    session.messages = []
    session.verification_results = [{"ok": True}]
    session.final_result = "The add() function subtracted; fixed to add."
    session.state = AgentState.COMPLETED
    experience = session_to_experience(session, model="scripted-demo")
    if outcome != "success":
        experience.outcome = outcome
    store.record(experience)
    return experience


class FormatDemonstrationTests(unittest.TestCase):
    def test_renders_protocol_shaped_worked_example(self):
        demo = format_demonstration("Fix the calculator", STEPS,
                                    "The add() function subtracted; "
                                    "fixed.", "scripted-demo")
        self.assertIn("Worked example", demo)
        self.assertIn("provenance: scripted-demo", demo)
        self.assertIn('[TOOL: read_file(path="calculator.py")]', demo)
        self.assertIn("-> def add(a, b):", demo)
        self.assertIn("Final answer:", demo)

    def test_no_steps_returns_none(self):
        self.assertIsNone(format_demonstration("g", [], "done", "m"))

    def test_steps_capped_at_six(self):
        steps = [{"tool": "read_file", "args": {"path": "x"},
                  "ok": True, "result_head": "ok"}] * 9
        demo = format_demonstration("g", steps, None, "m")
        numbered = [line for line in demo.splitlines()
                    if line[:2].rstrip(".").isdigit()]
        self.assertEqual(6, len(numbered))


class RetrieverDemonstrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = ExperienceStore(Path(self._tmp.name) / "e.jsonl")
        _demo_experience(self.store)
        # S49 hermeticity lesson: never let MemoryLayer default to the
        # repo's real cases.jsonl inside tests
        self.layer = MemoryLayer(
            experience_store=self.store,
            cases_path=Path(self._tmp.name) / "no-cases.jsonl")

    def test_memory_layer_carries_step_data(self):
        results = self.layer.search("failing tests fix bug")
        experience_results = [r for r in results
                              if r["source"] == "experience"]
        self.assertTrue(experience_results)
        self.assertEqual(3, len(experience_results[0]["steps"]))
        self.assertEqual("scripted-demo",
                         experience_results[0]["model"])

    def test_verified_steps_render_as_worked_example(self):
        retriever = MemoryRetriever(memory_layer=self.layer)
        block = retriever.block("The tests in this project are failing")
        self.assertIn("## Worked example", block)
        self.assertIn('[TOOL: read_file(path="calculator.py")]', block)

    def test_failed_outcome_with_steps_never_teaches(self):
        store = ExperienceStore(Path(self._tmp.name) / "failed.jsonl")
        _demo_experience(store, outcome="failed")
        block = MemoryRetriever(memory_layer=MemoryLayer(
            experience_store=store,
            cases_path=Path(self._tmp.name) / "no-cases.jsonl")).block(
            "The tests in this project are failing")
        self.assertIn("- [experience]", block)
        self.assertNotIn("Worked example", block)

    def test_builder_injects_demo_into_assembly(self):
        session = _session_with_goal(
            "The tests in this project are failing. Find the bug.")
        builder = ContextBuilder(memory_retriever=MemoryRetriever(
            memory_layer=self.layer))
        messages = builder.build(session, offered_tools=[])
        self.assertTrue(any("Worked example" in m.content
                            for m in messages))


def _session_with_goal(goal):
    from qacompanion.agent.contracts import ModelMessage
    from qacompanion.agent.session import AgentSession
    session = AgentSession(goal=goal)
    session.messages.append(ModelMessage(role="system", content="sys"))
    session.messages.append(ModelMessage(role="user", content=goal))
    return session


class BenchmarkPassthroughTests(unittest.TestCase):
    def test_benchmark_loop_receives_the_demonstration(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ExperienceStore(Path(tmp) / "e.jsonl")
            _demo_experience(store)
            seen = {}

            class ProbeProvider(FakeModelProvider):
                def generate(self, request):
                    seen["has_demo"] = any(
                        "Worked example" in m.content
                        for m in request.messages)
                    return ModelResponse(
                        text="The defect is fixed in calculator.py.",
                        finish_reason="stop")

            builder = ContextBuilder(
                memory_retriever=MemoryRetriever(
                    memory_layer=MemoryLayer(
                        experience_store=store,
                        cases_path=Path(tmp) / "no-cases.jsonl")))
            run_benchmark(ProbeProvider([]),
                                   context_builder=builder)
            # the provider fakes a final answer; verification fails and
            # that is fine — we only assert the demo reached the model
            self.assertIn("has_demo", seen)
            self.assertTrue(seen["has_demo"])


class DashboardBrainTests(unittest.TestCase):
    def test_default_is_ollama(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QA_AGENT_PROVIDER", None)
            provider = default_provider_factory()
        self.assertIsInstance(provider, OllamaProvider)

    def test_gemini_selected_by_env(self):
        with mock.patch.dict(os.environ,
                             {"QA_AGENT_PROVIDER": "gemini"}):
            provider = default_provider_factory()
        self.assertIsInstance(provider, GeminiModelProvider)

    def test_unknown_provider_is_structured_error(self):
        with mock.patch.dict(os.environ,
                             {"QA_AGENT_PROVIDER": "gpt-5"}):
            with self.assertRaises(ValueError):
                default_provider_factory()


if __name__ == "__main__":
    unittest.main()
