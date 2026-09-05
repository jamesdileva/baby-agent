"""S49 QA brain tests: layered advice, loop injection, honest silence.

Hermetic: temp case stores and experience fixtures; commands run via
sys.executable.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import (
    FakeModelProvider,
    ModelResponse,
    ToolCall,
    ToolRegistry,
    ToolResult,
    Workspace,
)
from qacompanion.agent.execution import ExecutionToolkit
from qacompanion.agent.fs_tools import FilesystemToolkit
from qacompanion.agent.experience import Experience, ExperienceStore, MemoryLayer
from qacompanion.agent.loop import AgentLoop
from qacompanion.agent.qa_brain import QABrain, derive_signature
from qacompanion.agent.providers import ModelProvider
from qacompanion.agent.registry import ALLOW_ALL_POLICY
from qacompanion.store import CaseStore

PY = f'"{sys.executable}"'
FAILING_COMMAND = f'{PY} -c "x = 1 / 0"'


def _seed_case(cases_path: Path):
    signature = derive_signature(
        "run_command",
        "Traceback (most recent call last):\nZeroDivisionError: division by zero")
    CaseStore(cases_path).record(
        signature,
        "ZeroDivisionError: division by zero",
        "ZeroDivisionError means guard the denominator before dividing",
        by="test")
    return signature


class _RecordingProvider(ModelProvider):
    """Scripted provider that records every request for injection proofs."""

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


class TestDeriveSignature(unittest.TestCase):
    def test_stable_across_noise(self):
        a = derive_signature("run_command",
                             "Traceback...\nZeroDivisionError: division by zero")
        b = derive_signature("run_command",
                             "  Traceback...\nzerodivisionerror: DIVISION BY ZERO")
        self.assertEqual(a, b)

    def test_empty_output_is_honest(self):
        signature = derive_signature("run_command", "")
        self.assertIn("no output", signature)


class TestAdviseLayers(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cases_path = self.tmp / "cases.jsonl"
        self.store_path = self.tmp / "experience.jsonl"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _failed(self, output=None):
        text = output or ("Traceback (most recent call last):\n"
                          "ZeroDivisionError: division by zero")
        return ToolResult(call_name="run_command", ok=False,
                          output=text, error=text)

    def test_exact_case_match(self):
        _seed_case(self.cases_path)
        brain = QABrain(cases_path=self.cases_path)
        advice = brain.advise(self._failed())
        self.assertIsNotNone(advice)
        self.assertEqual(advice["source"], "case")
        self.assertIn("guard the denominator", advice["diagnosis"])

    def test_keyword_match_on_variant(self):
        _seed_case(self.cases_path)
        brain = QABrain(cases_path=self.cases_path)
        advice = brain.advise(self._failed(
            "some prefix noise\nZeroDivisionError: division by zero"))
        self.assertIsNotNone(advice)
        self.assertEqual(advice["source"], "case")

    def test_memory_fallback_when_no_case(self):
        store = ExperienceStore(self.store_path)
        store.record(Experience(
            goal="fix divide by zero crashes",
            outcome="recovered",
            resolution="always validate the denominator first",
            confidence=0.9))
        brain = QABrain(cases_path=self.cases_path,
                        memory_layer=MemoryLayer(
                            experience_store=store,
                            cases_path=self.cases_path))
        advice = brain.advise(self._failed())
        self.assertIsNotNone(advice)
        self.assertEqual(advice["source"], "experience")
        self.assertIn("denominator", advice["diagnosis"])

    def test_total_miss_is_honest_silence(self):
        store = ExperienceStore(self.store_path)
        store.record(Experience(goal="unrelated css styling",
                                outcome="success"))
        brain = QABrain(cases_path=self.cases_path,
                        memory_layer=MemoryLayer(
                            experience_store=store,
                            cases_path=self.cases_path))
        self.assertIsNone(brain.advise(self._failed()))

    def test_corrupt_store_degrades_to_memory(self):
        self.cases_path.write_text("garbage{", encoding="utf-8")
        store = ExperienceStore(self.store_path)
        store.record(Experience(goal="zero division fix",
                                outcome="recovered",
                                resolution="check denominators"))
        brain = QABrain(cases_path=self.cases_path,
                        memory_layer=MemoryLayer(
                            experience_store=store,
                            cases_path=self.cases_path))
        advice = brain.advise(self._failed())
        self.assertIsNotNone(advice)
        self.assertEqual(advice["source"], "experience")

    def test_successful_results_never_advised(self):
        _seed_case(self.cases_path)
        brain = QABrain(cases_path=self.cases_path)
        self.assertIsNone(brain.advise(
            ToolResult(call_name="run_command", ok=True, output="all good")))

    def test_embedded_command_failure_is_advised(self):
        # S35 convention: run_command is ok=True with the CommandResult
        # JSON carrying the nonzero exit code — the brain reads it
        _seed_case(self.cases_path)
        brain = QABrain(cases_path=self.cases_path)
        payload = json.dumps({
            "command": "python -c x = 1 / 0", "exit_code": 1,
            "stdout": "",
            "stderr": "Traceback (most recent call last):\n"
                      "ZeroDivisionError: division by zero",
        })
        advice = brain.advise(ToolResult(call_name="run_command", ok=True,
                                         output=payload))
        self.assertIsNotNone(advice)
        self.assertEqual(advice["source"], "case")
        self.assertIn("guard the denominator", advice["diagnosis"])

    def test_embedded_command_success_not_advised(self):
        _seed_case(self.cases_path)
        brain = QABrain(cases_path=self.cases_path)
        payload = json.dumps({"command": "x", "exit_code": 0, "stdout": "ok"})
        self.assertIsNone(brain.advise(ToolResult(
            call_name="run_command", ok=True, output=payload)))


class TestLoopInjection(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.cases_path = self.tmp / "cases.jsonl"
        self.reg = ToolRegistry()
        for tool in FilesystemToolkit(self.ws).tools():
            self.reg.register(tool)
        for tool in ExecutionToolkit(self.ws).tools():
            self.reg.register(tool)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _qa_messages(self, requests):
        found = []
        for request in requests:
            for message in request.messages:
                if message.role == "system" and "qa_memory" in message.content:
                    found.append(json.loads(message.content)["qa_memory"])
        return found

    def test_diagnosis_supplied_before_next_action(self):
        signature = _seed_case(self.cases_path)
        provider = _RecordingProvider([
            ToolCall(name="run_command", arguments={"command": FAILING_COMMAND}),
            ModelResponse(text="I used the memory advice and stopped the "
                               "bleeding.", finish_reason="stop"),
        ])
        loop = AgentLoop(provider, self.reg, self.ws,
                         policy=ALLOW_ALL_POLICY,
                         qa_brain=QABrain(cases_path=self.cases_path))
        session = loop.run("run the command and handle the failure")

        self.assertEqual(session.state.value, "COMPLETED")
        advice = self._qa_messages(provider.requests)
        self.assertEqual(len(advice), 1)
        self.assertEqual(advice[0]["source"], "case")
        self.assertEqual(advice[0]["signature"], signature)
        self.assertIn("guard the denominator", advice[0]["diagnosis"])
        # the advice arrived in the request AFTER the failing tool turn
        self.assertIn("qa_memory", provider.requests[1].messages[-1].content)

    def test_no_match_injects_nothing(self):
        provider = _RecordingProvider([
            ToolCall(name="run_command", arguments={"command": FAILING_COMMAND}),
            ModelResponse(text="handled it myself.", finish_reason="stop"),
        ])
        loop = AgentLoop(provider, self.reg, self.ws,
                         policy=ALLOW_ALL_POLICY,
                         qa_brain=QABrain(cases_path=self.cases_path))
        loop.run("run the command")
        self.assertEqual(self._qa_messages(provider.requests), [])

    def test_successful_commands_never_trigger_advice(self):
        _seed_case(self.cases_path)
        provider = _RecordingProvider([
            ToolCall(name="run_command",
                     arguments={"command": f'{PY} -c "print(1)"'}),
            ModelResponse(text="fine.", finish_reason="stop"),
        ])
        loop = AgentLoop(provider, self.reg, self.ws,
                         policy=ALLOW_ALL_POLICY,
                         qa_brain=QABrain(cases_path=self.cases_path))
        loop.run("run a passing command")
        self.assertEqual(self._qa_messages(provider.requests), [])


if __name__ == "__main__":
    unittest.main()
