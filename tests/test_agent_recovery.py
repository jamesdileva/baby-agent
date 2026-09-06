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


if __name__ == "__main__":
    unittest.main()
