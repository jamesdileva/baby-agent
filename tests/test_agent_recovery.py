"""S58 failure recovery tests: tracker, strategy ladder, loop wiring.

All hermetic — fake providers script every brain; Windows adapter not
exercised here (S54 owns it).
"""

import unittest

from qacompanion.agent.recovery import (
    FailureTracker,
    RecoveryError,
    RecoveryPolicy,
    RecoveryStateMachine,
    Strategy,
)


class TestFailureTracker(unittest.TestCase):
    def test_signature_stable_across_case_and_space(self):
        tracker = FailureTracker()
        a = tracker.signature("tool", "Error: File NOT found ")
        b = tracker.signature("tool", "error: file not found")
        self.assertEqual(a, b)

    def test_consecutive_same(self):
        tracker = FailureTracker(threshold=3)
        for _ in range(3):
            tracker.record("sig-a")
        self.assertTrue(tracker.no_progress())
        tracker.record("sig-b")
        self.assertFalse(tracker.no_progress())
        self.assertEqual(tracker.consecutive_same(), 1)

    def test_threshold_minimum(self):
        with self.assertRaises(RecoveryError):
            FailureTracker(threshold=1)


class TestStrategyLadder(unittest.TestCase):
    def setUp(self):
        self.policy = RecoveryPolicy(max_same_failure=3, max_alternates=2)

    def decide(self, kind="tool", error="boom", repeat=1, alternates=0,
               escalation=True, iterations_left=True):
        return self.policy.decide(kind, error, repeat, alternates,
                                  escalation, iterations_left)

    def test_first_failure_retries_with_advice(self):
        d = self.decide(repeat=1)
        self.assertEqual(d.strategy, Strategy.RETRY_WITH_ADVICE)

    def test_repeated_failure_alternates(self):
        d = self.decide(repeat=3)
        self.assertEqual(d.strategy, Strategy.ALTERNATE_APPROACH)

    def test_alternates_exhausted_escalates(self):
        d = self.decide(repeat=5, alternates=2, escalation=True)
        self.assertEqual(d.strategy, Strategy.ESCALATE_MODEL)

    def test_no_escalation_ask_user(self):
        d = self.decide(repeat=5, alternates=2, escalation=False)
        self.assertEqual(d.strategy, Strategy.ASK_USER)

    def test_environment_failure_checks_environment(self):
        d = self.decide(error="ImportError: no module named requests")
        self.assertEqual(d.strategy, Strategy.ENVIRONMENT_CHECK)

    def test_verification_failure_alternates(self):
        d = self.decide(kind="verification", error="unit-tests=FAIL",
                        repeat=1)
        self.assertEqual(d.strategy, Strategy.ALTERNATE_APPROACH)

    def test_no_iterations_terminates(self):
        d = self.decide(repeat=1, iterations_left=False)
        self.assertEqual(d.strategy, Strategy.TERMINATE)

    def test_ladder_is_one_directional(self):
        # desperation order: each later rung requires more evidence
        ladder = [Strategy.RETRY_WITH_ADVICE, Strategy.ALTERNATE_APPROACH,
                  Strategy.ESCALATE_MODEL, Strategy.ASK_USER]
        first = self.decide(repeat=1)
        self.assertEqual(first.strategy, ladder[0])


class TestStateMachine(unittest.TestCase):
    def test_alternate_count_increments(self):
        machine = RecoveryStateMachine()
        d1 = machine.on_failure("verification", "unit-tests=FAIL", 2, 25)
        d2 = machine.on_failure("verification", "unit-tests=FAIL", 3, 25)
        self.assertEqual(d1.strategy, Strategy.ALTERNATE_APPROACH)
        self.assertEqual(d2.strategy, Strategy.ALTERNATE_APPROACH)
        self.assertEqual(machine.alternate_count, 2)

    def test_escalation_is_one_way(self):
        machine = RecoveryStateMachine()
        machine.mark_escalated()
        d = machine.on_failure("tool", "boom", 5, 25,
                               escalation_available=True)
        self.assertNotEqual(d.strategy, Strategy.ESCALATE_MODEL)

    def test_environment_beats_repeat_count(self):
        machine = RecoveryStateMachine()
        for _ in range(5):
            machine.tracker.record("tool:same")
        d = machine.on_failure("tool", "ImportError: no module named x",
                               6, 25)
        self.assertEqual(d.strategy, Strategy.ENVIRONMENT_CHECK)

    def test_report(self):
        machine = RecoveryStateMachine()
        machine.on_failure("tool", "boom", 1, 25)
        report = machine.report()
        self.assertEqual(report["tracker"]["total"], 1)


class TestCyclingDetection(unittest.TestCase):
    """S103: interleaved thrash — the live docs-question session cycled
    three different failing paths for 5 straight steps with the ladder
    silent, because no single signature repeated 3x back-to-back."""

    def _sig(self, kind, text):
        return FailureTracker().signature(kind, text)

    def test_interleaved_thrash_fires(self):
        # the exact observed pattern: 5 consecutive failing steps,
        # 3 distinct signatures, no success between them
        tracker = FailureTracker()
        for text in ("file not found: src/main.py",
                     "file not found: app/__init__.py",
                     "not a directory: src",
                     "file not found: src/main.py",
                     "file not found: app/__init__.py"):
            tracker.record(self._sig("tool", text))
        self.assertTrue(tracker.cycling())
        # the old rule stays silent on this pattern — the gap is real
        self.assertFalse(tracker.no_progress())

    def test_success_resets_the_streak(self):
        tracker = FailureTracker()
        for text in ("file not found: a", "file not found: b",
                     "file not found: c", "file not found: d"):
            tracker.record(self._sig("tool", text))
        tracker.record_success()
        tracker.record(self._sig("tool", "file not found: e"))
        self.assertFalse(tracker.cycling())

    def test_short_streak_does_not_fire(self):
        tracker = FailureTracker()
        for text in ("file not found: a", "file not found: b",
                     "file not found: c", "file not found: d"):
            tracker.record(self._sig("tool", text))
        self.assertFalse(tracker.cycling())

    def test_single_signature_streak_is_not_cycling(self):
        # identical retries are consecutive_same's job, not cycling's
        tracker = FailureTracker()
        for _ in range(5):
            tracker.record(self._sig("tool", "same error"))
        self.assertFalse(tracker.cycling())

    def test_cycling_ladder_alternates_then_ask_user(self):
        machine = RecoveryStateMachine()
        for text in ("file not found: src/main.py",
                     "file not found: app/__init__.py",
                     "not a directory: src",
                     "file not found: src/main.py"):
            machine.on_failure("tool", text, 6, 25)
        d = machine.on_failure("tool", "file not found: app/__init__.py",
                               7, 25)
        self.assertEqual(d.strategy, Strategy.ALTERNATE_APPROACH)
        machine2 = RecoveryStateMachine()
        for i in range(20):
            d = machine2.on_failure(
                "tool", f"file not found: path{i % 3}", i + 1, 50)
        self.assertEqual(d.strategy, Strategy.ASK_USER)

    def test_environment_repeats_then_falls_through(self):
        # S98 follow-up: environment decisions used to loop uncounted;
        # after 2 the ladder must advance instead of repeating
        machine = RecoveryStateMachine()
        d1 = machine.on_failure("tool", "file not found: x", 1, 25)
        self.assertEqual(d1.strategy, Strategy.ENVIRONMENT_CHECK)
        machine.on_success()
        d2 = machine.on_failure("tool", "file not found: y", 2, 25)
        self.assertEqual(d2.strategy, Strategy.ENVIRONMENT_CHECK)
        machine.on_success()
        # distinct cycling failures past the counted environment window
        machine.on_failure("tool", "file not found: a", 3, 25)
        machine.on_failure("tool", "file not found: b", 4, 25)
        d = machine.on_failure("tool", "file not found: c", 5, 25)
        self.assertNotEqual(d.strategy, Strategy.ENVIRONMENT_CHECK)

    def test_exploration_shape_never_fires(self):
        # guessed reads punctuated by successes = legitimate exploration;
        # punishing this shape would regress the guessed-path behavior
        # the corpus deliberately teaches
        machine = RecoveryStateMachine()
        d = None
        for i in range(12):
            d = machine.on_failure("tool", f"file not found: guess{i}",
                                   i + 1, 50)
            machine.on_success()  # each guess is followed by a real read
        self.assertEqual(d.strategy, Strategy.ENVIRONMENT_CHECK)


class TestLoopEmitsToolRecovery(unittest.TestCase):
    """S103/D1: tool-path recovery decisions were invisible — only the
    verification path emitted recovery_started."""

    def test_tool_failure_path_emits_recovery_event(self):
        import tempfile
        from pathlib import Path
        from qacompanion.agent.loop import AgentLoop
        from qacompanion.agent.providers import FakeModelProvider
        from qacompanion.agent.contracts import ToolCall
        from qacompanion.agent.workspace import Workspace
        from qacompanion.agent.registry import ToolRegistry
        from qacompanion.agent.fs_tools import FilesystemToolkit
        from qacompanion.agent.events import EventStream
        from qacompanion.agent.session import AgentConfig

        with tempfile.TemporaryDirectory() as tmp:
            reg = ToolRegistry()
            for tool in FilesystemToolkit(Workspace(Path(tmp))).tools():
                reg.register(tool)
            stream = EventStream()
            script = [
                ToolCall(name="read_file",
                         arguments={"path": "missing.py"}),
                ToolCall(name="read_file",
                         arguments={"path": "also-missing.py"}),
                ToolCall(name="read_file",
                         arguments={"path": "third-missing.py"}),
                ToolCall(name="read_file",
                         arguments={"path": "fourth-missing.py"}),
                ToolCall(name="read_file",
                         arguments={"path": "fifth-missing.py"}),
            ]
            loop = AgentLoop(
                FakeModelProvider(script), reg, Workspace(Path(tmp)),
                config=AgentConfig(max_iterations=12), events=stream,
                recovery=RecoveryStateMachine(),
            )
            loop.run("probe goal")
            strategies = [e.payload.get("strategy")
                          for e in stream.events
                          if e.event_type == "recovery_started"
                          and "strategy" in e.payload]
            self.assertTrue(strategies, "tool-path recovery stayed silent")
            self.assertNotIn("retry_with_advice", strategies)


if __name__ == "__main__":
    unittest.main()
