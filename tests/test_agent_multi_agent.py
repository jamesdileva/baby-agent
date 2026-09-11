"""S61 multi-agent teacher session tests: session shapes, consensus
!= correctness, disagreement capture, diversity. All hermetic."""

import unittest

from qacompanion.agent.multi_agent import (
    MODES,
    MultiAgentError,
    MultiAgentLab,
    MultiAgentSessionRunner,
    Participant,
    ROLES,
)


class _FixedTeacher:
    """Teacher whose proposal is a fixed string (records calls)."""

    def __init__(self, name, role, proposal):
        self._name = name
        self._role = role
        self._proposal = proposal
        self.calls = 0

    @property
    def name(self):
        return self._name

    @property
    def role(self):
        return self._role

    def propose(self, task_text):
        self.calls += 1
        return self._proposal


class _DynamicTeacher(_FixedTeacher):
    """Returns per-call proposals in sequence, then sticks on the last."""

    def __init__(self, name, role, proposals):
        super().__init__(name, role, proposals[-1])
        self._proposals = list(proposals)

    def propose(self, task_text):
        if len(self._proposals) > 1:
            return self._proposals.pop(0)
        return self._proposals[0]


def _verified_when(ok_flag):
    def verifier(solution):
        return ok_flag, "verified" if ok_flag else "verification failed"
    return verifier


def _accept_anything(solution):
    return True, "verified"


class TestSessionShapes(unittest.TestCase):
    def test_independent_compared_and_verified(self):
        teachers = [
            Participant("alice", "coder", _FixedTeacher("alice", "coder",
                                                        "solution A")),
            Participant("bob", "reviewer", _FixedTeacher("bob", "reviewer",
                                                         "solution B")),
        ]
        runner = MultiAgentSessionRunner(verifier=_accept_anything)
        session = runner.run_independent("build a widget", teachers)

        self.assertEqual(session.mode, "independent")
        self.assertEqual(len(session.proposals), 2)
        self.assertFalse(session.consensus_reached)
        self.assertEqual(len(session.disagreements), 1)
        self.assertEqual(session.disagreements[0]["between"], ["alice",
                                                               "bob"])
        self.assertTrue(session.verified)
        self.assertTrue(session.final_solution)

    def test_consensus_detected_when_identical(self):
        teachers = [
            Participant("a", "coder", _FixedTeacher("a", "coder", "same")),
            Participant("b", "tester", _FixedTeacher("b", "tester", "same")),
        ]
        runner = MultiAgentSessionRunner(verifier=_accept_anything)
        session = runner.run_independent("task", teachers)
        self.assertTrue(session.consensus_reached)
        self.assertEqual(session.disagreements, [])

    def test_unanimous_wrong_consensus_still_fails_gate(self):
        # THE core principle: consensus != correctness. A unanimous panel
        # whose solution fails verification must NOT be marked verified.
        teachers = [
            Participant("a", "coder", _FixedTeacher("a", "coder", "wrong")),
            Participant("b", "reviewer", _FixedTeacher("b", "reviewer",
                                                       "wrong")),
        ]
        runner = MultiAgentSessionRunner(verifier=_verified_when(False))
        session = runner.run_independent("task", teachers)

        self.assertTrue(session.consensus_reached)  # they agreed...
        self.assertFalse(session.verified)          # ...and were wrong
        self.assertIsNone(session.final_solution)
        for vote in session.votes.values():
            self.assertIn("rejected", vote)

    def test_independent_needs_two(self):
        runner = MultiAgentSessionRunner(verifier=_accept_anything)
        with self.assertRaises(MultiAgentError):
            runner.run_independent("task", [
                Participant("solo", "coder",
                            _FixedTeacher("solo", "coder", "x"))])

    def test_debate_flow(self):
        # debate calls the proposer exactly twice: initial proposal,
        # then revision after the critique
        proposer = Participant("p", "coder", _DynamicTeacher(
            "p", "coder", ["draft one", "revised solution"]))
        critic = Participant("c", "reviewer", _FixedTeacher(
            "c", "reviewer", "the draft misses the edge case"))
        runner = MultiAgentSessionRunner(verifier=_accept_anything)
        session = runner.run_debate("build it", proposer, critic)

        self.assertEqual(session.mode, "debate")
        self.assertIn("p", session.proposals)
        self.assertIn("p (revised)", session.proposals)
        self.assertIn("c", session.critiques)
        self.assertTrue(session.verified)
        self.assertEqual(session.final_solution,
                         "revised solution")

    def test_critique_chain(self):
        reviewers = [
            Participant("r1", "architect", _DynamicTeacher(
                "r1", "architect", ["initial design"])),
            Participant("r2", "security_reviewer", _DynamicTeacher(
                "r2", "security_reviewer",
                ["initial design", "hardened design"])),
        ]
        runner = MultiAgentSessionRunner(verifier=_accept_anything)
        session = runner.run_critique_chain("design it", reviewers)
        self.assertEqual(session.mode, "critique_chain")
        self.assertEqual(session.final_solution, "hardened design")
        self.assertIn("r2", session.critiques)

    def test_specialist_flow(self):
        primary = Participant("lead", "coder", _DynamicTeacher(
            "lead", "coder", ["v1", "v2 (revised after review)"]))
        reviewers = [
            Participant("sec", "security_reviewer", _FixedTeacher(
                "sec", "security_reviewer", "watch for injection")),
            Participant("perf", "performance_reviewer", _FixedTeacher(
                "perf", "performance_reviewer", "watch allocations")),
        ]
        runner = MultiAgentSessionRunner(verifier=_accept_anything)
        session = runner.run_specialist("build it", primary, reviewers)
        self.assertTrue(session.verified)
        self.assertEqual(len(session.critiques), 2)

    def test_unknown_mode_rejected(self):
        runner = MultiAgentSessionRunner(verifier=_accept_anything)
        with self.assertRaises(MultiAgentError):
            runner.run_critique_chain("task", [])

    def test_unknown_role_rejected(self):
        with self.assertRaises(MultiAgentError):
            Participant("x", "wizard", _FixedTeacher("x", "wizard", "p"))


class TestConsensusPrinciple(unittest.TestCase):
    def test_consensus_recorded_not_equated(self):
        # the session contract carries consensus_reached as DATA next to
        # verified — consumers must join them, never conflate
        teachers = [
            Participant("a", "coder", _FixedTeacher("a", "coder", "same")),
            Participant("b", "tester", _FixedTeacher("b", "tester", "same")),
        ]
        runner = MultiAgentSessionRunner(verifier=_verified_when(False))
        session = runner.run_independent("task", teachers)
        data = session.to_dict()
        self.assertTrue(data["consensus_reached"])
        self.assertFalse(data["verified"])


class TestMultiAgentLab(unittest.TestCase):
    def test_report_aggregates_by_mode_and_diversity(self):
        lab = MultiAgentLab(verifier=_accept_anything)
        teachers_a = [
            Participant("a", "coder", _FixedTeacher("a", "coder", "s1")),
            Participant("b", "reviewer", _FixedTeacher("b", "reviewer",
                                                       "s2")),
        ]
        lab.run_independent("task", teachers_a)

        proposer = Participant("p", "coder", _FixedTeacher(
            "p", "coder", "draft"))
        critic = Participant("c", "debugger", _FixedTeacher(
            "c", "debugger", "rework it"))
        lab.run_debate("task", proposer, critic)

        report = lab.diversity_report()
        self.assertEqual(report["sessions"], 2)
        self.assertEqual(report["by_mode"]["independent"]["sessions"], 1)
        self.assertEqual(report["by_mode"]["debate"]["verified"], 1)
        self.assertIn("coder", report["distinct_roles"])
        self.assertIn("reviewer", report["distinct_roles"])
        self.assertIn("debugger", report["distinct_roles"])

    def test_disagreement_sessions_counted(self):
        lab = MultiAgentLab(verifier=_accept_anything)
        teachers = [
            Participant("a", "coder", _FixedTeacher("a", "coder", "A")),
            Participant("b", "tester", _FixedTeacher("b", "tester", "B")),
        ]
        lab.run_independent("task", teachers)
        self.assertEqual(lab.diversity_report()["disagreement_sessions"], 1)

    def test_roles_and_modes_constants(self):
        self.assertIn("independent", MODES)
        self.assertIn("architect", ROLES)
        self.assertIn("project_manager", ROLES)


if __name__ == "__main__":
    unittest.main()
