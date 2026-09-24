"""S61 multi-agent teacher sessions: structured multi-teacher
collaboration that generates higher-quality learning examples.

Session shapes: independent (N teachers solve, verifier adjudicates),
debate (propose -> critique -> revise), critique_chain (sequential
role reviews), specialist (primary + role reviewers -> revision).

THE core principle, pinned: **consensus != correctness.** A unanimous
panel can be wrong — every final solution passes the S41 verification
gate, and DISAGREEMENTS are recorded as first-class data (the most
valuable training examples per the S62 curation principles).

Diversity is measured, not assumed: each session records the
models/roles/approaches that participated, and the report aggregates
distinct counts — the measurable form of "avoid 1 teacher, 1 style,
1 architecture repeated thousands of times".
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

MODES = ("independent", "debate", "critique_chain", "specialist")
ROLES = ("architect", "coder", "debugger", "reviewer", "security_reviewer",
         "performance_reviewer", "ui_designer", "researcher", "tester",
         "verifier", "project_manager")


class MultiAgentError(ValueError):
    """Invalid multi-agent session configuration."""


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z")


@dataclass
class Participant:
    """One teacher in a session: wraps a provider with a role."""

    name: str
    role: str
    provider: Any  # any object exposing generate(request) — TeacherProvider-like

    def __post_init__(self):
        if self.role not in ROLES:
            raise MultiAgentError(f"unknown role: {self.role!r}")

    def propose(self, task_text: str) -> str:
        """Ask this participant for a solution/proposal. Delegation
        order: provider.propose (duck-typed teacher) -> provider.teach
        (S59 TeacherProvider ABC) -> provider.generate (plain loop
        backend)."""
        from .contracts import ModelMessage, ModelRequest

        proposer = getattr(self.provider, "propose", None)
        if callable(proposer):
            return proposer(task_text)
        teach = getattr(self.provider, "teach", None)
        if callable(teach):
            return teach({"goal": task_text}).explanation
        request = ModelRequest(messages=[
            ModelMessage(role="system",
                         content=f"You are the {self.role} in a "
                                 f"software team."),
            ModelMessage(role="user", content=task_text),
        ])
        response = self.provider.generate(request)
        return response.text


@dataclass
class MultiAgentSession:
    """The full session contract (spec s61)."""

    session_id: str
    task_text: str
    mode: str
    participants: List[Participant]
    proposals: Dict[str, str] = field(default_factory=dict)
    critiques: Dict[str, str] = field(default_factory=dict)
    votes: Dict[str, str] = field(default_factory=dict)
    disagreements: List[Dict[str, Any]] = field(default_factory=list)
    consensus_reached: bool = False
    verified: bool = False
    final_solution: Optional[str] = None
    started_at: str = field(default_factory=_utc_stamp)
    diversity: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "task_text": self.task_text,
            "mode": self.mode,
            "participants": [{"name": p.name, "role": p.role}
                             for p in self.participants],
            "proposals": dict(self.proposals),
            "critiques": dict(self.critiques),
            "votes": dict(self.votes),
            "disagreements": list(self.disagreements),
            "consensus_reached": self.consensus_reached,
            "verified": self.verified,
            "final_solution": self.final_solution,
            "started_at": self.started_at,
            "diversity": dict(self.diversity),
        }


class MultiAgentSessionRunner:
    """Orchestrates teachers through the session shapes."""

    def __init__(self, verifier: Callable[[str], Tuple[bool, str]],
                 judge: Optional[Callable[[str, List[str]], str]] = None):
        """verifier(solution_text) -> (ok, detail) — the S41 gate.
        judge(task_text, proposals) -> chosen proposal text — used in
        independent mode to pick among verified solutions (defaults to
        majority text match, else first)."""
        self.verifier = verifier
        self.judge = judge

    def run_independent(self, task_text: str,
                        participants: List[Participant]) -> MultiAgentSession:
        """Every teacher solves independently; solutions are compared,
        verified, and disagreements recorded."""
        if len(participants) < 2:
            raise MultiAgentError(
                "independent mode needs at least 2 participants")
        session = MultiAgentSession(
            session_id=uuid.uuid4().hex[:12], task_text=task_text,
            mode="independent", participants=list(participants),
            started_at=_utc_stamp())
        for participant in participants:
            session.proposals[participant.name] = participant.propose(
                task_text)
        distinct = set(session.proposals.values())
        session.consensus_reached = len(distinct) == 1
        # disagreements recorded as first-class data
        names = sorted(session.proposals)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                if session.proposals[a] != session.proposals[b]:
                    session.disagreements.append({
                        "between": [a, b],
                        "positions": [session.proposals[a][:200],
                                      session.proposals[b][:200]],
                    })
        # diversity: distinct providers/roles
        session.diversity = {
            "participants": len(participants),
            "distinct_roles": len({p.role for p in participants}),
        }
        # verification gate per proposal — consensus never substitutes
        verified_proposals = []
        for name, text in session.proposals.items():
            ok, detail = self.verifier(text)
            session.votes[name] = "verified" if ok else f"rejected ({detail})"
            if ok:
                verified_proposals.append(text)
        session.verified = bool(verified_proposals)
        if verified_proposals:
            if self.judge is not None:
                session.final_solution = self.judge(task_text,
                                                    verified_proposals)
            else:
                session.final_solution = verified_proposals[0]
        return session

    def run_debate(self, task_text: str, proposer: Participant,
                   critic: Participant,
                   revision_rounds: int = 1) -> MultiAgentSession:
        """Propose -> critique -> revise; the revised solution is
        verified."""
        if len({proposer.name, critic.name}) < 2:
            raise MultiAgentError("debate needs two distinct participants")
        session = MultiAgentSession(
            session_id=uuid.uuid4().hex[:12], task_text=task_text,
            mode="debate", participants=[proposer, critic],
            started_at=_utc_stamp())
        proposal = proposer.propose(task_text)
        session.proposals[proposer.name] = proposal
        critique = critic.propose(f"Critique this solution to the task:\n"
                                  f"{task_text}\n\nSolution:\n{proposal}")
        session.critiques[critic.name] = critique
        revision = proposer.propose(
            f"{task_text}\n\nYour earlier solution:\n{proposal}\n\n"
            f"Critique received:\n{critique}\n\n"
            f"Produce a revised solution.")
        session.proposals[proposer.name + " (revised)"] = revision
        session.final_solution = revision
        ok, detail = self.verifier(revision)
        session.verified = ok
        session.diversity = {"participants": 2,
                             "distinct_roles": len({proposer.role,
                                                    critic.role})}
        if not ok:
            session.disagreements.append({
                "between": [proposer.name, "verifier"],
                "positions": [revision[:200],
                              f"verification failed: {detail}"],
            })
        return session

    def run_critique_chain(self, task_text: str,
                           reviewers: List[Participant]
                           ) -> MultiAgentSession:
        """Sequential role reviews: each reviewer critiques the running
        solution; the last revision is verified."""
        if len(reviewers) < 2:
            raise MultiAgentError("critique chain needs >= 2 reviewers")
        session = MultiAgentSession(
            session_id=uuid.uuid4().hex[:12], task_text=task_text,
            mode="critique_chain", participants=list(reviewers),
            started_at=_utc_stamp())
        solution = reviewers[0].propose(task_text)
        session.proposals[reviewers[0].name] = solution
        for reviewer in reviewers[1:]:
            critique = reviewer.propose(
                f"{task_text}\n\nCurrent solution:\n{solution}\n\n"
                f"Review it from your role's perspective.")
            session.critiques[reviewer.name] = critique
            revised = reviewer.propose(
                f"{task_text}\n\nSolution under review:\n{solution}\n\n"
                f"Your critique:\n{critique}\n\n"
                f"Produce the revised solution.")
            if revised != solution:
                session.proposals[reviewer.name + " (revised)"] = revised
                solution = revised
        session.final_solution = solution
        ok, detail = self.verifier(solution)
        session.verified = ok
        session.diversity = {"participants": len(reviewers),
                             "distinct_roles": len({p.role
                                                    for p in reviewers})}
        return session

    def run_specialist(self, task_text: str, primary: Participant,
                       reviewers: List[Participant]
                       ) -> MultiAgentSession:
        """Primary proposes; role reviewers critique; primary revises;
        the revision is verified."""
        session = MultiAgentSession(
            session_id=uuid.uuid4().hex[:12], task_text=task_text,
            mode="specialist",
            participants=[primary] + list(reviewers),
            started_at=_utc_stamp())
        proposal = primary.propose(task_text)
        session.proposals[primary.name] = proposal
        for reviewer in reviewers:
            critique = reviewer.propose(
                f"{task_text}\n\nProposal:\n{proposal}\n\nReview from "
                f"your specialist perspective.")
            session.critiques[reviewer.name] = critique
        revision = primary.propose(
            f"{task_text}\n\nYour proposal:\n{proposal}\n\n"
            f"Reviewer critiques:\n" +
            "\n".join(f"- {v}" for v in session.critiques.values()) +
            "\n\nProduce the final revised solution.")
        session.proposals[primary.name + " (final)"] = revision
        session.final_solution = revision
        ok, detail = self.verifier(revision)
        session.verified = ok
        session.diversity = {"participants": 1 + len(reviewers),
                             "distinct_roles": len(
                                 {p.role for p in
                                  [primary] + list(reviewers)})}
        if not ok:
            session.disagreements.append({
                "between": [primary.name, "verifier"],
                "positions": [revision[:200],
                              f"verification failed: {detail}"],
            })
        return session


class MultiAgentLab:
    """Session runner + report aggregation (diversity measurable)."""

    def __init__(self, verifier: Callable[[str], Tuple[bool, str]],
                 judge: Optional[Callable[[str, List[str]], str]] = None):
        self.runner = MultiAgentSessionRunner(verifier, judge)
        self.report: Dict[str, Any] = {
            "sessions": 0, "by_mode": {}, "consensus_sessions": 0,
            "verified_sessions": 0, "disagreement_sessions": 0,
            "distinct_roles": set(),
        }

    def record(self, session: MultiAgentSession) -> None:
        self.report["sessions"] += 1
        for participant in session.participants:
            self.report["distinct_roles"].add(participant.role)
        per = self.report["by_mode"].setdefault(session.mode, {
            "sessions": 0, "verified": 0, "consensus": 0})
        per["sessions"] += 1
        if session.verified:
            per["verified"] += 1
            self.report["verified_sessions"] += 1
        if session.consensus_reached:
            per["consensus"] += 1
            self.report["consensus_sessions"] += 1
        if session.disagreements:
            self.report["disagreement_sessions"] += 1

    def run_independent(self, task_text: str,
                        participants: List[Participant]) -> MultiAgentSession:
        session = self.runner.run_independent(task_text, participants)
        self.record(session)
        return session

    def run_debate(self, task_text: str, proposer: Participant,
                   critic: Participant) -> MultiAgentSession:
        session = self.runner.run_debate(task_text, proposer, critic)
        self.record(session)
        return session

    def run_critique_chain(self, task_text: str,
                           reviewers: List[Participant]
                           ) -> MultiAgentSession:
        session = self.runner.run_critique_chain(task_text, reviewers)
        self.record(session)
        return session

    def run_specialist(self, task_text: str, primary: Participant,
                       reviewers: List[Participant]) -> MultiAgentSession:
        session = self.runner.run_specialist(task_text, primary, reviewers)
        self.record(session)
        return session

    def diversity_report(self) -> Dict[str, Any]:
        report = dict(self.report)
        report["distinct_roles"] = sorted(self.report["distinct_roles"])
        return report
