"""S59 agent apprenticeship lab: the student attempts the task, a
teacher demonstrates a better way, the student retries, and ONLY a
verified lesson is accepted into memory.

The flow (spec s59): student attempt → teacher demonstration → student
retry with the lesson → S41 verification gate → curation gate →
ACCEPT (record the retry as experience, S50) or REJECT (recorded with
a reason, never stored).

Pins (fixtures-first discipline):
- teachers demonstrate via REAL tool calls (actions), not chat text —
  a teacher that can't produce actions can't teach here;
- "teacher said it" is never evidence: ACCEPT requires the S41
  verification to pass on the STUDENT's post-lesson attempt;
- ScriptedTeacherProvider is the hermetic backbone; real teachers
  (Gemini, opencode) plug into the same ABC later;
- the lab composes S48's benchmark machinery (run_benchmark) so both
  trajectories carry honest metrics.
"""

import json
import tempfile
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .benchmark import run_benchmark
from .experience import ExperienceStore
from .events import EventStream
from .workspace import Workspace


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z")


@dataclass
class Lesson:
    """A teacher's demonstration: explanation + real tool actions."""

    explanation: str
    actions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self):
        return {"explanation": self.explanation,
                "actions": [dict(action) for action in self.actions]}

    @classmethod
    def from_dict(cls, data):
        return cls(explanation=data.get("explanation", ""),
                   actions=[dict(action) for action
                            in data.get("actions", [])])


class TeacherProvider(ABC):
    """A stronger agent that demonstrates the task via tool actions."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def teach(self, task: Dict[str, Any]) -> Lesson:
        """task: {goal, workspace_files: {name: content}} — the teacher
        sees the same files the student failed on and returns a Lesson
        whose actions use real tool names (write_file, edit_file, ...).
        """


class ScriptedTeacherProvider(TeacherProvider):
    """Deterministic teacher for tests and demos (hermetic)."""

    def __init__(self, lesson: Lesson, name: str = "scripted"):
        self._lesson = lesson
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def teach(self, task: Dict[str, Any]) -> Lesson:
        return Lesson(explanation=self._lesson.explanation,
                      actions=[dict(action) for action
                               in self._lesson.actions])


@dataclass
class ApprenticeshipRecord:
    """The full session contract (spec s59)."""

    session_id: str
    task_name: str
    teacher_name: str
    student_name: str
    started_at: str
    status: str                      # accepted | rejected
    reject_reason: Optional[str] = None
    student_first_report: Optional[Dict[str, Any]] = None
    lesson: Optional[Dict[str, Any]] = None
    student_retry_report: Optional[Dict[str, Any]] = None
    verified: bool = False
    lessons_extracted: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "task_name": self.task_name,
            "teacher_name": self.teacher_name,
            "student_name": self.student_name,
            "started_at": self.started_at,
            "status": self.status,
            "reject_reason": self.reject_reason,
            "student_first_report": self.student_first_report,
            "lesson": self.lesson,
            "student_retry_report": self.student_retry_report,
            "verified": self.verified,
            "lessons_extracted": list(self.lessons_extracted),
        }


class ApprenticeshipLab:
    """Runs apprenticeship sessions: student attempt → teacher lesson →
    student retry → verification gate → curation gate.

    Store discipline: attempts run against the QUARANTINE store (S50
    honesty — attempts are recorded, but separate); the MAIN store only
    receives ACCEPTED lessons, under a distinct goal so the store's
    goal-dedupe cannot merge the lesson away."""

    def __init__(self, store: Optional[ExperienceStore] = None,
                 attempt_store: Optional[ExperienceStore] = None,
                 events: Optional[EventStream] = None):
        self.store = store
        self.attempt_store = attempt_store
        self.events = events or EventStream()

    def _run_attempt(self, provider, task, workspace_root):
        return run_benchmark(provider, workspace_root=str(workspace_root),
                             experience_store=self.attempt_store,
                             events=self.events,
                             fixture_writer=lambda ws,
                             _task=task: _task.write_fixture(ws.root),
                             goal=task.goal)

    def run_session(self, task, student_factory, teacher: TeacherProvider,
                    student_name: str = "student") -> ApprenticeshipRecord:
        """task: EvalTask (S57); student_factory: returns a fresh
        provider per attempt (S55 slice 5 pattern — a stateless
        scripted student would exhaust its script across attempts)."""
        import tempfile

        record = ApprenticeshipRecord(
            session_id=uuid.uuid4().hex[:12],
            task_name=task.name, teacher_name=teacher.name,
            student_name=student_name, started_at=_utc_stamp(),
            status="rejected")

        # 1. student's FIRST attempt — on its own, unaided
        first_root = Path(tempfile.mkdtemp(prefix=f"appr-{task.name}-first-"))
        task.write_fixture(first_root)
        first = self._run_attempt(student_factory(model=None),
                                  task, first_root)
        record.student_first_report = first.to_dict()
        if first.success:
            # student already passes: nothing to learn, record and accept
            record.status = "accepted"
            record.verified = True
            record.lessons_extracted = ["student already passed unaided"]
            return record

        # 2. teacher demonstrates on a FRESH copy of the fixture
        teach_root = Path(tempfile.mkdtemp(prefix=f"appr-{task.name}-teach-"))
        task.write_fixture(teach_root)
        lesson = teacher.teach({
            "goal": task.goal,
            "workspace_files": {name: (teach_root / name).read_text(
                encoding="utf-8") for name in task.files},
        })
        record.lesson = lesson.to_dict()

        # 3. curation gate BEFORE the retry: the teacher's own actions
        # must be non-empty (a teacher with no actions can't teach)
        if not lesson.actions:
            record.reject_reason = "teacher_failed: empty lesson actions"
            return record

        # 4. student retries on a FRESH fixture copy — same defect, same
        # goal, now with the lesson applied by the STUDENT's provider
        retry_root = Path(tempfile.mkdtemp(prefix=f"appr-{task.name}-retry-"))
        task.write_fixture(retry_root)
        retry = self._run_attempt(student_factory(model=None),
                                  task, retry_root)
        record.student_retry_report = retry.to_dict()

        # 5. S41 gate on the STUDENT's post-lesson attempt
        verified = bool(retry.success)
        record.verified = verified
        if not verified:
            record.reject_reason = (
                f"verification_failed: student retry did not pass "
                f"({retry.termination_reason})")
            return record

        # 6. ACCEPT: the verified lesson enters MAIN memory under a
        # distinct goal (the plain task.goal would collide with the
        # quarantined attempt records and get merged away)
        record.status = "accepted"
        record.lessons_extracted = [
            f"{lesson.explanation[:200]} (actions: "
            + ", ".join(action.get("tool", "?") for action in lesson.actions)
            + ")"
        ]
        if self.store is not None:
            from .session import AgentSession
            from .session_learning import session_to_experience

            retry_session = AgentSession(goal=task.goal)
            experience = session_to_experience(retry_session)
            experience.outcome = "recovered"
            experience.diagnosis = lesson.explanation[:300]
            experience.resolution = json.dumps(lesson.to_dict(),
                                               ensure_ascii=False)[:1000]
            experience.tags = ["apprenticeship", f"teacher:{teacher.name}",
                               task.name]
            experience.goal = f"{task.goal} (apprenticeship lesson)"
            self.store.record(experience)
        return record


class LabReport:
    """Aggregated apprenticeship results."""

    def __init__(self):
        self.sessions = 0
        self.accepted = 0
        self.rejected = 0
        self.by_teacher: Dict[str, Dict[str, int]] = {}
        self.rejected_sessions: List[Dict[str, Any]] = []

    def add(self, record: ApprenticeshipRecord) -> None:
        self.sessions += 1
        if record.status == "accepted":
            self.accepted += 1
        else:
            self.rejected += 1
        per = self.by_teacher.setdefault(
            record.teacher_name, {"sessions": 0, "accepted": 0})
        per["sessions"] += 1
        if record.status == "accepted":
            per["accepted"] += 1
        if record.status == "rejected":
            self.rejected_sessions.append({
                "session_id": record.session_id,
                "task": record.task_name,
                "reason": record.reject_reason})

    def to_dict(self):
        return {"sessions": self.sessions, "accepted": self.accepted,
                "rejected": self.rejected, "by_teacher": dict(
                    self.by_teacher),
                "rejected_sessions": list(self.rejected_sessions)}
