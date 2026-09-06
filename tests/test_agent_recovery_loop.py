"""S58 loop integration: recovery strategies fire inside real runs.

All hermetic — scripted fake brains; the escalation swap proves the
session completes on a SECOND provider.
"""

import json
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import (
    AgentConfig,
    AgentLoop,
    AgentState,
    FakeModelProvider,
    ModelResponse,
    ToolCall,
    Workspace,
)
from qacompanion.agent.benchmark import coding_registry
from qacompanion.agent.recovery import (
    FailureTracker,
    RecoveryPolicy,
    RecoveryStateMachine,
    Strategy,
)


class RecoveryLoopBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.reg = coding_registry(self.ws)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestToolFailureRecovery(RecoveryLoopBase):
    def test_repeated_identical_failure_triggers_alternate(self):
        # a tool that always fails identically; model keeps retrying
        class AlwaysFails(FakeModelProvider):
            def __init__(self):
                super().__init__([])

            def generate(self, request):
                # ALWAYS emits the failing tool call — never a final
                # answer, so the loop spins until recovery/limits act
                return ModelResponse(
                    text="", tool_calls=[ToolCall(
                        name="computer_click",
                        arguments={"x": 1, "y": 2})],
                    finish_reason="tool_calls")

        from qacompanion.agent.computer import (
            ALLOWED_ACTIONS, ComputerUseConfig, ComputerUseToolkit,
            FakeComputerProvider,
        )
        reg = self.reg
        for tool in ComputerUseToolkit(
                self.ws, FakeComputerProvider(),
                ComputerUseConfig(
                    allowed_actions=frozenset(ALLOWED_ACTIONS),
                    max_actions=100, screen_width=1920,
                    screen_height=1080)).tools():
            reg.register(tool)

        recovery = RecoveryStateMachine(
            policy=RecoveryPolicy(max_same_failure=2, max_alternates=5),
            threshold=2)
        provider = AlwaysFails()
        loop = AgentLoop(provider, reg, self.ws,
                         config=AgentConfig(max_iterations=6),
                         recovery=recovery)
        session = loop.run("click the thing")
        # the alternate-approach instruction must have been injected
        approaches = [m for m in session.messages if m.role == "system"
                      and "Change your approach" in m.content]
        self.assertTrue(approaches)
        # with recovery present, the state machine terminates at the
        # failure (iterations exhausted) — same fact, recovery's phrasing
        self.assertEqual(session.termination_reason,
                         "no iterations left for another attempt")

    def test_escalation_swap_completes_on_second_brain(self):
        # the weak brain keeps writing OUTSIDE the workspace (identical
        # failures); after the ladder escalates, the strong brain writes
        # the file correctly and the session completes
        class WeakBrain:
            name = "weak"
            native_tools = True

            def generate(self, request):
                return ModelResponse(
                    text="", tool_calls=[ToolCall(
                        name="write_file",
                        arguments={"path": "../escape.txt",
                                   "content": "x"})],
                    finish_reason="tool_calls")

        class EscalatedBrain:
            name = "escalated"
            native_tools = True

            def __init__(self):
                self._wrote = False

            def generate(self, request):
                if self._wrote:
                    return ModelResponse(text="Escalated brain fixed it.",
                                         finish_reason="stop")
                self._wrote = True
                return ModelResponse(
                    text="", tool_calls=[ToolCall(
                        name="write_file",
                        arguments={"path": "blocked.txt",
                                   "content": "written by escalation"})],
                    finish_reason="tool_calls")

        weak = WeakBrain()
        escalated = EscalatedBrain()
        recovery = RecoveryStateMachine(
            policy=RecoveryPolicy(max_same_failure=2, max_alternates=1),
            threshold=2)
        loop = AgentLoop(weak, self.reg, self.ws,
                         config=AgentConfig(max_iterations=10),
                         recovery=recovery,
                         escalation_factory=lambda: escalated)
        session = loop.run("write blocked.txt")

        self.assertEqual(session.state, AgentState.COMPLETED)
        self.assertTrue(recovery.escalated)
        self.assertIn("written by escalation",
                      (self.tmp / "blocked.txt").read_text(
                          encoding="utf-8"))


class TestVerificationRecovery(RecoveryLoopBase):
    def test_ask_user_terminates_after_repeats(self):
        provider = FakeModelProvider([])
        # stateless final-answer-only brain that never satisfies verifier
        class FinalOnly(FakeModelProvider):
            def generate(self, request):
                return ModelResponse(text="trust me, it works",
                                     finish_reason="stop")

        def verifier(session):
            return False, "unit-tests=FAIL"

        recovery = RecoveryStateMachine(
            policy=RecoveryPolicy(max_same_failure=2, max_alternates=1),
            threshold=2)
        loop = AgentLoop(FinalOnly([]), self.reg, self.ws,
                         config=AgentConfig(max_iterations=10),
                         verifier=verifier, recovery=recovery)
        session = loop.run("impossible task")
        self.assertEqual(session.state, AgentState.FAILED)
        self.assertIn("needs human decision", session.termination_reason)


if __name__ == "__main__":
    unittest.main()
