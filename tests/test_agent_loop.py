"""S37 agent loop tests: autonomous multi-step runs driven by fake models.

Hermetic: fake providers script everything; real workspace tools run via
sys.executable only.
"""

import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from qacompanion.agent import (
    TERMINATION_CANCELLED,
    TERMINATION_COMPLETED,
    TERMINATION_MAX_ITERATIONS,
    TERMINATION_MAX_RUNTIME,
    TERMINATION_PROVIDER_ERROR,
    TERMINATION_VERIFICATION_FAILED,
    AgentConfig,
    AgentLoop,
    AgentSession,
    AgentState,
    FakeModelProvider,
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    OllamaProvider,
    ProviderError,
    RegisteredTool,
    ToolCall,
    ToolDefinition,
    ToolRegistry,
    Workspace,
    build_system_prompt,
)
from qacompanion.agent.execution import ExecutionToolkit
from qacompanion.agent.fs_tools import FilesystemToolkit

EXE = f'"{sys.executable}"'


def _registry(tmp: Path, ws: Workspace) -> ToolRegistry:
    reg = ToolRegistry()
    for tool in FilesystemToolkit(ws).tools():
        reg.register(tool)
    for tool in ExecutionToolkit(ws).tools():
        reg.register(tool)
    return reg


def _final(text="Done. The build passes."):
    return ModelResponse(text=text)


class _RecordingProvider(ModelProvider):
    """Scripted provider that records every request for feedback proofs."""

    name = "recording"

    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        item = self.script.pop(0)
        if isinstance(item, ToolCall):
            return ModelResponse(text="", tool_calls=[item],
                                 finish_reason="tool_calls")
        return item


class LoopTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.reg = _registry(self.tmp, self.ws)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestRoadmapSequence(LoopTestBase):
    """The audit2 verification script: write (buggy) -> run (fail) ->
    read error -> edit (fix) -> run (pass) -> final — no task knowledge
    hard-coded in the runtime."""

    def _script(self):
        return [
            ToolCall(name="write_file", arguments={
                "path": "calc.py",
                "content": "result = 1 +\nprint(result)\n",
            }),
            ToolCall(name="run_command", arguments={
                "command": f"{EXE} calc.py",
            }),
            ToolCall(name="read_file", arguments={"path": "calc.py"}),
            ToolCall(name="edit_file", arguments={
                "path": "calc.py",
                "old_string": "result = 1 +\n",
                "new_string": "result = 1 + 1\n",
            }),
            ToolCall(name="run_command", arguments={
                "command": f"{EXE} calc.py",
            }),
            _final("Created calc.py, fixed the syntax error, output is 2."),
        ]

    def test_multi_step_autonomous_run(self):
        provider = FakeModelProvider(self._script())
        loop = AgentLoop(provider, self.reg, self.ws)
        session = loop.run("Make a script that prints 2, and prove it runs.")

        self.assertEqual(session.state, AgentState.COMPLETED)
        self.assertEqual(session.termination_reason, TERMINATION_COMPLETED)
        self.assertEqual(len(session.tool_calls), 5)
        self.assertEqual(len(session.observations), 5)
        self.assertIn("calc.py", session.files_changed)
        self.assertIn("fixed the syntax error", session.final_result)

        # the first run failed (syntax error), the second passed
        run_results = [o for o in session.observations
                       if o.call_name == "run_command"]
        self.assertIn('"exit_code": 1', run_results[0].output)
        self.assertIn('"exit_code": 0', run_results[1].output)

        # fix observed on disk
        self.assertIn("1 + 1", (self.tmp / "calc.py").read_text(encoding="utf-8"))


class TestFeedback(LoopTestBase):
    def test_tool_output_fed_back_into_next_iteration(self):
        provider = _RecordingProvider([
            ToolCall(name="write_file", arguments={"path": "a.txt", "content": "data"}),
            _final("ok"),
        ])
        loop = AgentLoop(provider, self.reg, self.ws)
        session = loop.run("write a.txt")

        self.assertEqual(session.state, AgentState.COMPLETED)
        self.assertEqual(len(provider.requests), 2)
        second_messages = provider.requests[1].messages
        tool_msgs = [m for m in second_messages if m.role == "tool"]
        self.assertEqual(len(tool_msgs), 1)
        payload = json.loads(tool_msgs[0].content)
        self.assertEqual(payload["call_name"], "write_file")
        self.assertTrue(payload["ok"])
        self.assertIn('"path": "a.txt"', payload["output"])
        self.assertIn("sha256", payload["output"])

    def test_denial_is_observation_not_exception(self):
        class DenyAll:
            def check(self, tool_name, arguments, tool=None):
                return "DENY"

        provider = _RecordingProvider([
            ToolCall(name="write_file", arguments={"path": "a.txt", "content": "x"}),
            _final("I was denied; stopping."),
        ])
        loop = AgentLoop(provider, self.reg, self.ws, policy=DenyAll())
        session = loop.run("write a.txt")

        self.assertEqual(session.state, AgentState.COMPLETED)
        denial = session.observations[0]
        self.assertFalse(denial.ok)
        self.assertIn("permission denied", denial.error)
        tool_msgs = [m for m in provider.requests[1].messages if m.role == "tool"]
        self.assertIn("permission denied", tool_msgs[0].content)

    def test_unknown_tool_is_observation(self):
        provider = _RecordingProvider([
            ToolCall(name="ghost_tool", arguments={}),
            _final("The tool does not exist; stopping."),
        ])
        loop = AgentLoop(provider, self.reg, self.ws)
        session = loop.run("use a ghost tool")
        self.assertEqual(session.state, AgentState.COMPLETED)
        self.assertIn("unknown tool", session.observations[0].error)


class TestLimits(LoopTestBase):
    def test_iteration_limit(self):
        class AlwaysCalling(ModelProvider):
            name = "looping"

            def generate(self, request):
                return ModelResponse(
                    text="", tool_calls=[ToolCall(name="file_exists",
                                                  arguments={"path": "x"})],
                    finish_reason="tool_calls",
                )

        loop = AgentLoop(AlwaysCalling(), self.reg, self.ws,
                         config=AgentConfig(max_iterations=5))
        session = loop.run("loop forever")
        self.assertEqual(session.state, AgentState.FAILED)
        self.assertEqual(session.termination_reason,
                         TERMINATION_MAX_ITERATIONS.format(5))
        self.assertEqual(session.iterations, 5)

    def test_provider_script_exhaustion(self):
        provider = FakeModelProvider([ToolCall(name="file_exists",
                                               arguments={"path": "x"})])
        loop = AgentLoop(provider, self.reg, self.ws)
        session = loop.run("exhaust the script")
        self.assertEqual(session.state, AgentState.FAILED)
        self.assertIn("provider error", session.termination_reason)

    def test_runtime_deadline_unit(self):
        from qacompanion.agent.loop import _deadline_exceeded
        config = AgentConfig(max_runtime_minutes=30)
        now = time.monotonic()
        self.assertFalse(_deadline_exceeded(now - 60, config, now=now))
        self.assertTrue(_deadline_exceeded(now - 31 * 60, config, now=now))
        self.assertEqual(TERMINATION_MAX_RUNTIME, "max runtime exceeded")

    def test_empty_response_continues_then_completes(self):
        provider = _RecordingProvider([
            ModelResponse(text="   "),
            _final("recovered from empty response"),
        ])
        loop = AgentLoop(provider, self.reg, self.ws)
        session = loop.run("say something")
        self.assertEqual(session.state, AgentState.COMPLETED)
        self.assertEqual(session.iterations, 2)
        self.assertTrue(any("empty model response" in e for e in session.errors))


class TestVerification(LoopTestBase):
    def test_verifier_pass_path(self):
        seen_states = []

        def verifier(session):
            seen_states.append(session.state)
            return True, "output verified"

        provider = _RecordingProvider([_final("all done")])
        loop = AgentLoop(provider, self.reg, self.ws, verifier=verifier)
        session = loop.run("do the thing")

        self.assertEqual(session.state, AgentState.COMPLETED)
        self.assertEqual(seen_states, [AgentState.VERIFYING])
        self.assertEqual(session.verification_results[0]["ok"], True)

    def test_verifier_fail_then_recover(self):
        attempts = {"n": 0}

        def verifier(session):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return False, "flag file missing"
            return True, "flag file present"

        provider = _RecordingProvider([
            _final("I think I am done"),
            ToolCall(name="write_file", arguments={"path": "flag.txt",
                                                   "content": "ready"}),
            _final("now the flag exists"),
        ])
        loop = AgentLoop(provider, self.reg, self.ws, verifier=verifier)
        session = loop.run("create flag.txt")

        self.assertEqual(session.state, AgentState.COMPLETED)
        self.assertEqual([r["ok"] for r in session.verification_results],
                         [False, True])
        self.assertEqual(len(session.tool_calls), 1)
        # the verification failure was fed back as a user message
        user_msgs = [m for m in provider.requests[2].messages
                     if m.role == "user" and "Verification failed" in m.content]
        self.assertTrue(user_msgs)

    def test_verification_exhaustion(self):
        def verifier(session):
            return False, "still broken"

        provider = _RecordingProvider([_final("done?")] * 1)
        loop = AgentLoop(provider, self.reg, self.ws,
                         config=AgentConfig(max_iterations=1), verifier=verifier)
        session = loop.run("impossible task")
        self.assertEqual(session.state, AgentState.FAILED)
        self.assertEqual(session.termination_reason,
                         TERMINATION_VERIFICATION_FAILED.format(1))


class TestCancellation(LoopTestBase):
    def test_tripwire_tool_cancels_mid_run(self):
        event = threading.Event()

        def tripwire(**kwargs):
            event.set()
            return "tripped"

        self.reg.register(RegisteredTool(
            definition=ToolDefinition(
                name="tripwire", description="sets the cancel event",
                parameters_schema={"type": "object", "properties": {}}),
            handler=tripwire,
        ))
        provider = _RecordingProvider([
            ToolCall(name="tripwire", arguments={}),
            _final("never reached"),
        ])
        loop = AgentLoop(provider, self.reg, self.ws, cancel_event=event)
        session = loop.run("trip the wire")
        self.assertEqual(session.state, AgentState.CANCELLED)
        self.assertEqual(session.termination_reason, TERMINATION_CANCELLED)
        self.assertEqual(len(session.tool_calls), 1)


class TestPromptAndSession(unittest.TestCase):
    def test_system_prompt_renders_tool_catalog(self):
        reg = ToolRegistry()
        reg.register(RegisteredTool(
            definition=ToolDefinition(
                name="sample", description="does sample things",
                parameters_schema={"type": "object", "properties": {}}),
            handler=lambda **kw: "ok",
        ))
        prompt = build_system_prompt(reg.schemas())
        self.assertIn("- sample: does sample things", prompt)
        self.assertIn("Baby-Agent", prompt)

    def test_system_prompt_teaches_textual_protocol(self):
        # found by the live smoke: text-protocol models never called tools
        # because the exact syntax was never taught
        reg = ToolRegistry()
        reg.register(RegisteredTool(
            definition=ToolDefinition(
                name="sample", description="d",
                parameters_schema={"type": "object", "properties": {}}),
            handler=lambda **kw: "ok",
        ))
        prompt = build_system_prompt(reg.schemas())
        self.assertIn('[TOOL: tool_name(argument="value"', prompt)
        # few-shot example (live smoke: without it the 1.5B model invented
        # its own call syntax)
        self.assertIn('[TOOL: write_file(path="notes.txt"', prompt)

    def test_textual_ollama_path_end_to_end(self):
        """Hermetic proof of the exact live wire format: scripted bridge
        output parsed by the real OllamaProvider, driven by the real loop."""
        from unittest.mock import patch
        import shutil as _shutil

        tmp = Path(tempfile.mkdtemp())
        try:
            ws = Workspace(tmp)
            reg = _registry(tmp, ws)
            responses = [
                # NOTE: _is_ollama_available is fully mocked, so no ping is
                # made and every scripted entry is a real model turn
                'I will create the file.\n'
                '[TOOL: write_file(path="hello.txt", content="Hello from Baby-Agent")]',
                "The file is created with the exact text.",
            ]

            def scripted_generate(prompt, model=None, url=None):
                return responses.pop(0)

            with patch("qacompanion.ollama_bridge._is_ollama_available",
                       return_value=True), \
                 patch("qacompanion.ollama_bridge._ollama_generate",
                       side_effect=scripted_generate):
                provider = OllamaProvider()
                loop = AgentLoop(provider, reg, ws)
                session = loop.run(
                    "Create hello.txt containing: Hello from Baby-Agent")

            self.assertEqual(session.state, AgentState.COMPLETED)
            self.assertEqual(len(session.tool_calls), 1)
            self.assertEqual(session.tool_calls[0].name, "write_file")
            self.assertIn("Hello from Baby-Agent",
                          (tmp / "hello.txt").read_text(encoding="utf-8"))
        finally:
            _shutil.rmtree(tmp, ignore_errors=True)

    def test_verification_results_round_trip(self):
        session = AgentSession(goal="g")
        session.verification_results.append(
            {"ok": True, "detail": "d", "at": "2026-09-04T00:00:00Z"})
        restored = AgentSession.from_dict(session.to_dict())
        self.assertEqual(restored.verification_results,
                         session.verification_results)


if __name__ == "__main__":
    unittest.main()
