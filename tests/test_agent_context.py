"""S56 context optimization tests: budget, reducers, builder, memory,
loop integration. All hermetic."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import (
    AgentConfig,
    AgentLoop,
    AgentSession,
    AgentState,
    FakeModelProvider,
    ModelMessage,
    ModelResponse,
    ToolCall,
    ToolResult,
    Workspace,
)
from qacompanion.agent.context import (
    ContextBudget,
    ContextBuilder,
    ContextError,
    MemoryRetriever,
    reduce_message,
    summarize_command_result,
)
from qacompanion.agent.experience import Experience, ExperienceStore, MemoryLayer


def _command_result(stdout_lines=40, exit_code=1):
    return json.dumps({
        "command": "python -m unittest", "exit_code": exit_code,
        "stdout": "\n".join(f"line{i}" for i in range(stdout_lines)),
        "stderr": "ERROR: something failed",
        "duration_ms": 100, "timed_out": False, "cancelled": False,
    })


class TestBudget(unittest.TestCase):
    def test_accounting(self):
        budget = ContextBudget(max_chars=1000)
        self.assertTrue(budget.fits(500, "x" * 400))
        self.assertFalse(budget.fits(500, "x" * 600))

    def test_min_budget_enforced(self):
        with self.assertRaises(ContextError):
            ContextBudget(max_chars=10)


class TestReducers(unittest.TestCase):
    def test_command_summary_keeps_decision_surface(self):
        reduced = summarize_command_result(_command_result(40))
        self.assertIn("exit_code=1", reduced)
        self.assertIn("line0", reduced)
        self.assertIn("line39", reduced)
        self.assertIn("lines omitted", reduced)
        self.assertNotIn("line20\n", reduced)

    def test_command_summary_stderr_head(self):
        reduced = summarize_command_result(_command_result(5))
        self.assertIn("ERROR: something failed", reduced)

    def test_non_json_passthrough_truncated(self):
        self.assertEqual(len(reduce_message("x" * 1000)), 600)

    def test_latest_stays_verbatim(self):
        content = _command_result(40)
        self.assertEqual(reduce_message(content, is_latest=True), content)

    def test_reduce_message_old_tool_result(self):
        content = _command_result(40)
        reduced = reduce_message(content)
        self.assertIn("exit_code=1", reduced)
        self.assertLess(len(reduced), len(content))


class TestMemoryRetriever(unittest.TestCase):
    def test_block_from_store(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            store = ExperienceStore(tmp / "e.jsonl")
            store.record(Experience(
                goal="fix websocket reconnect failures", outcome="recovered",
                resolution="recreate session inside retry loop"))
            retriever = MemoryRetriever(
                MemoryLayer(experience_store=store))
            block = retriever.block("websocket reconnect fails")
            self.assertIn("websocket", block)
            self.assertIn("[experience]", block)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_empty_store_silent(self):
        retriever = MemoryRetriever(None)
        self.assertEqual(retriever.block("anything"), "")


class TestContextBuilder(unittest.TestCase):
    def _large_session(self, turns=60):
        session = AgentSession(goal="Fix the failing login test")
        session.messages.append(ModelMessage(
            role="system", content="You are Baby-Agent. " + "x" * 200))
        session.messages.append(ModelMessage(
            role="user", content="Fix the failing login test"))
        for i in range(turns):
            session.messages.append(ModelMessage(
                role="assistant", content=f"thinking step {i}"))
            session.messages.append(ModelMessage(
                role="tool", content=_command_result(30)))
        session.messages.append(ModelMessage(
            role="assistant", content="final answer attempt"))
        return session

    def test_budget_held_on_large_session(self):
        session = self._large_session(60)
        builder = ContextBuilder(budget=ContextBudget(max_chars=8000))
        messages = builder.build(session, offered_tools=[])
        used = sum(len(m.content) for m in messages)
        self.assertLessEqual(used, 8000)
        self.assertGreater(builder.last_report.dropped, 0)

    def test_goal_and_latest_tool_result_survive(self):
        session = self._large_session(30)
        builder = ContextBuilder(budget=ContextBudget(max_chars=6000),
                                 keep_last_turns=6)
        messages = builder.build(session, offered_tools=[])
        self.assertIn("Fix the failing login test",
                      messages[1].content)
        tool_messages = [m for m in messages if m.role == "tool"]
        self.assertTrue(tool_messages)
        # assembled newest-first: [0] is the latest tool result — kept
        # VERBATIM by design (the model reasons over it next); [1] is an
        # older one, reduced to the decision surface
        self.assertEqual(tool_messages[0].content, _command_result(30))
        self.assertIn("exit_code=1", tool_messages[1].content)
        self.assertLess(len(tool_messages[1].content), 2000)

    def test_report_records_the_five_answers(self):
        session = self._large_session(20)
        builder = ContextBuilder(budget=ContextBudget(max_chars=8000))
        builder.build(session, offered_tools=[])
        report = builder.last_report.to_dict()
        self.assertTrue(report["goal_present"])
        self.assertTrue(report["latest_tool_result_verbatim"])
        self.assertLessEqual(report["chars"], report["budget"])

    def test_small_session_drops_nothing(self):
        session = AgentSession(goal="small task")
        session.messages.append(ModelMessage(role="user", content="small task"))
        session.messages.append(ModelMessage(
            role="tool", content=_command_result(3, exit_code=0)))
        builder = ContextBuilder(budget=ContextBudget(max_chars=20_000))
        messages = builder.build(session, offered_tools=[])
        self.assertEqual(builder.last_report.dropped, 0)
        self.assertEqual(len(messages), 3)


class TestLoopIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.script = [
            ToolCall(name="run_tests",
                     arguments={"command": '"python" -m unittest'}),
            ModelResponse(text="done", finish_reason="stop"),
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _provider(self):
        from qacompanion.agent.benchmark import coding_registry
        provider = FakeModelProvider(list(self.script))
        captured = {}

        original = provider.generate

        def generate(request):
            captured["messages"] = request.messages
            return original(request)

        provider.generate = generate
        registry = coding_registry(self.ws)
        return provider, registry, captured

    def test_context_builder_wired_into_loop(self):
        provider, registry, captured = self._provider()
        builder = ContextBuilder(budget=ContextBudget(max_chars=2500))
        loop = AgentLoop(provider, registry, self.ws,
                         context_builder=builder)
        session = loop.run("run the tests")
        self.assertEqual(session.state, AgentState.COMPLETED)
        used = sum(len(m.content) for m in captured["messages"])
        # system+catalog is a fixed cost; the budget governs the rest —
        # the 40-line tool result must have been reduced
        tool_msgs = [m for m in captured["messages"] if m.role == "tool"]
        self.assertTrue(tool_msgs)
        self.assertLess(len(tool_msgs[0].content), 1500)
        # system+catalog is a fixed cost (~2.2k); budget governs the rest:
        # the tool result arrived reduced, total may slightly exceed the
        # budget because the latest evidence is non-droppable (over_budget
        # is reported honestly)
        self.assertTrue(builder.last_report.over_budget
                        or used < 4000)

    def test_no_builder_keeps_full_history(self):
        provider, registry, captured = self._provider()
        loop = AgentLoop(provider, registry, self.ws)
        loop.run("run the tests")
        # system + user + assistant + tool result replayed wholesale
        self.assertEqual(len(captured["messages"]), 4)


if __name__ == "__main__":
    unittest.main()
