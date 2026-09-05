"""S47 experience memory: the case base becomes one source among many.

ExperienceStore adds episodic/agent memory (JSONL, atomic, strict) with
recurrence reinforcement — recording a repeated goal bumps times_seen
instead of duplicating, which is "better at recurring problems" made
mechanical. MemoryLayer is the unified READ over all four stores
(cases / digest / journal / experiences), merged, score-ranked, and
source-labeled — a missing store degrades to empty, never a crash.

Pins (fixtures-first discipline):
- strict validation on load (S1 culture): malformed lines raise
  ValueError; BOM/CRLF tolerated (S19 lessons);
- retrieval is deterministic keyword scoring with honest boosts
  (times_seen, confidence) — no embeddings; the semantic upgrade path is
  S56's;
- automatic context injection is S56; today retrieval is tool-driven
  (the S27 pattern the 1.5B model already uses).
"""

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .registry import READ_ONLY, SAFE_WRITE, RegisteredTool, ToolDefinition, ToolOperationError, ToolRegistry
from .workspace import Workspace

DEFAULT_EXPERIENCE_FILE = "experience.jsonl"
OUTCOMES = ("success", "failed", "recovered", "human_corrected", "partial")


class ExperienceError(ToolOperationError):
    """Structured experience-memory failure."""


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _normalize_goal(goal: str) -> str:
    """Normalization for recurrence detection: lowercase, collapse
    whitespace, strip punctuation."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", goal.lower())).strip()


@dataclass
class Experience:
    """One remembered agent episode (or taught procedure)."""

    goal: str
    outcome: str
    experience_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    session_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    actions: List[str] = field(default_factory=list)
    failure: Optional[str] = None
    diagnosis: Optional[str] = None
    resolution: Optional[str] = None
    verification: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    times_seen: int = 1
    tags: List[str] = field(default_factory=list)
    project_type: Optional[str] = None
    languages: List[str] = field(default_factory=list)
    recorded_at: str = field(default_factory=_utc_stamp)
    last_reinforced_at: str = field(default_factory=_utc_stamp)

    def __post_init__(self):
        _require(isinstance(self.goal, str) and self.goal.strip(),
                 "experience goal required")
        _require(self.outcome in OUTCOMES,
                 f"outcome must be one of {OUTCOMES}: {self.outcome!r}")
        _require(isinstance(self.confidence, (int, float))
                 and not isinstance(self.confidence, bool)
                 and 0.0 <= self.confidence <= 1.0,
                 "confidence must be within [0, 1]")
        _require(isinstance(self.times_seen, int) and self.times_seen >= 1,
                 "times_seen must be a positive integer")

    def to_dict(self):
        return {
            "experience_id": self.experience_id,
            "session_id": self.session_id,
            "goal": self.goal,
            "outcome": self.outcome,
            "context": self.context,
            "actions": list(self.actions),
            "failure": self.failure,
            "diagnosis": self.diagnosis,
            "resolution": self.resolution,
            "verification": self.verification,
            "confidence": self.confidence,
            "times_seen": self.times_seen,
            "tags": list(self.tags),
            "project_type": self.project_type,
            "languages": list(self.languages),
            "recorded_at": self.recorded_at,
            "last_reinforced_at": self.last_reinforced_at,
        }

    @classmethod
    def from_dict(cls, data):
        _require(isinstance(data, dict), "experience record must be an object")
        _require("goal" in data and "outcome" in data,
                 "experience record missing goal/outcome")
        return cls(
            goal=data["goal"],
            outcome=data["outcome"],
            experience_id=data.get("experience_id") or uuid.uuid4().hex,
            session_id=data.get("session_id"),
            context=dict(data.get("context", {})),
            actions=list(data.get("actions", [])),
            failure=data.get("failure"),
            diagnosis=data.get("diagnosis"),
            resolution=data.get("resolution"),
            verification=dict(data.get("verification", {})),
            confidence=data.get("confidence", 0.5),
            times_seen=data.get("times_seen", 1),
            tags=list(data.get("tags", [])),
            project_type=data.get("project_type"),
            languages=list(data.get("languages", [])),
            recorded_at=data.get("recorded_at", _utc_stamp()),
            last_reinforced_at=data.get("last_reinforced_at", _utc_stamp()),
        )

    def text(self) -> str:
        """The searchable text surface (goal + tags + narrative fields)."""
        return " ".join(filter(None, [
            self.goal, " ".join(self.tags), self.failure or "",
            self.diagnosis or "", self.resolution or "",
        ])).lower()


class ExperienceStore:
    """Strict JSONL persistence with recurrence reinforcement."""

    def __init__(self, path=None):
        self.path = Path(path or os.environ.get("QA_EXPERIENCE_FILE")
                         or DEFAULT_EXPERIENCE_FILE)

    def load(self) -> List[Experience]:
        if not self.path.exists():
            return []
        experiences = []
        text = self.path.read_text(encoding="utf-8-sig")
        for raw in text.splitlines():
            if not raw.strip():
                continue
            experiences.append(Experience.from_dict(json.loads(raw)))
        return experiences

    def save(self, experiences: List[Experience]) -> None:
        payload = "".join(
            json.dumps(e.to_dict(), ensure_ascii=False) + "\n"
            for e in experiences
        )
        tmp = self.path.with_name(self.path.name + ".tmp-exp")
        tmp.write_text(payload, encoding="utf-8", newline="")
        os.replace(tmp, self.path)

    def record(self, experience: Experience) -> Experience:
        """Reinforce an existing near-identical goal, else append."""
        existing = self.load()
        normalized = _normalize_goal(experience.goal)
        for candidate in existing:
            if _normalize_goal(candidate.goal) == normalized:
                candidate.times_seen += 1
                candidate.confidence = experience.confidence
                candidate.outcome = experience.outcome
                if experience.diagnosis:
                    candidate.diagnosis = experience.diagnosis
                if experience.resolution:
                    candidate.resolution = experience.resolution
                candidate.last_reinforced_at = _utc_stamp()
                self.save(existing)
                return candidate
        existing.append(experience)
        self.save(existing)
        return experience

    def find_similar(self, query: str, k: int = 5) -> List[Experience]:
        terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
        scored = []
        for experience in self.load():
            text = experience.text()
            overlap = sum(1 for term in terms if term in text)
            if not overlap and terms:
                continue
            score = (overlap * 2.0
                     + min(experience.times_seen, 5) * 0.5
                     + experience.confidence)
            scored.append((score, experience))
        scored.sort(key=lambda pair: (-pair[0], pair[1].recorded_at))
        return [experience for _, experience in scored[:k]]


class MemoryLayer:
    """Unified read over the four memory sources, source-labeled."""

    def __init__(self, experience_store: Optional[ExperienceStore] = None,
                 cases_path=None, digest_path=None, journal_path=None):
        self.experiences = experience_store or ExperienceStore()
        self.cases_path = cases_path
        self.digest_path = digest_path
        self.journal_path = journal_path

    def search(self, query: str, k_per_source: int = 3) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        results.extend(self._from_experiences(query, k_per_source))
        results.extend(self._from_cases(query, k_per_source))
        results.extend(self._from_docs(query, k_per_source))
        results.extend(self._from_journal(query, k_per_source))
        results.sort(key=lambda item: -item["score"])
        return results

    def _from_experiences(self, query, k):
        try:
            for experience in self.experiences.find_similar(query, k=k):
                yield {
                    "source": "experience",
                    "score": 3.0 + experience.confidence,
                    "goal": experience.goal,
                    "outcome": experience.outcome,
                    "diagnosis": experience.diagnosis,
                    "resolution": experience.resolution,
                    "times_seen": experience.times_seen,
                }
        except (OSError, ValueError):
            pass  # degraded source: honest empty

    def _from_cases(self, query, k):
        try:
            from .. import ollama_bridge as bridge
            cases_path = Path(self.cases_path) if self.cases_path \
                else Path(bridge.DEFAULT_CASES)
            if not cases_path.exists():
                return
            cases = bridge._load_cases(cases_path)
            matched = bridge._match_cases(cases, query)[:k]
            for case in matched:
                yield {
                    "source": "case",
                    "score": 2.5 + min(case.get("times_seen", 1), 5) * 0.2,
                    "signature": case.get("signature"),
                    "diagnosis": case.get("diagnosis"),
                    "times_seen": case.get("times_seen"),
                }
        except Exception:
            pass  # degraded source: honest empty

    def _from_docs(self, query, k):
        try:
            from ..skills import digest as digest_mod
            results = digest_mod.search(query, store_path=self.digest_path)
            for item in results[:k]:
                yield {
                    "source": "doc",
                    "score": 2.0,
                    "heading": item.get("heading"),
                    "snippet": (item.get("content") or "")[:200],
                }
        except Exception:
            pass  # degraded source: honest empty

    def _from_journal(self, query, k):
        try:
            from ..skills import journal as journal_mod
            entries = journal_mod.grep(query, ledger=self.journal_path)
            for entry in entries[:k]:
                yield {
                    "source": "journal",
                    "score": 1.5,
                    "text": str(entry.get("text", ""))[:200]
                    if isinstance(entry, dict) else str(entry)[:200],
                    "date": entry.get("date") if isinstance(entry, dict)
                    else None,
                }
        except Exception:
            pass  # degraded source: honest empty


class MemoryToolkit:
    """Binds the three memory tools (brain-level, no workspace needed)."""

    def __init__(self, experience_store: Optional[ExperienceStore] = None,
                 cases_path=None, digest_path=None, journal_path=None):
        self.store = experience_store or ExperienceStore()
        self.layer = MemoryLayer(
            experience_store=self.store, cases_path=cases_path,
            digest_path=digest_path, journal_path=journal_path,
        )

    def experience_record(self, goal: str, outcome: str,
                          session_id: Optional[str] = None,
                          diagnosis: Optional[str] = None,
                          resolution: Optional[str] = None,
                          actions: Optional[List[str]] = None,
                          tags: Optional[List[str]] = None,
                          project_type: Optional[str] = None,
                          confidence: float = 0.5) -> str:
        try:
            experience = Experience(
                goal=goal, outcome=outcome, session_id=session_id,
                diagnosis=diagnosis, resolution=resolution,
                actions=actions or [], tags=tags or [],
                project_type=project_type, confidence=confidence,
            )
            recorded = self.store.record(experience)
        except ValueError as exc:
            raise ExperienceError(f"invalid experience record: {exc}") from exc
        return json.dumps({
            "recorded": True,
            "experience_id": recorded.experience_id,
            "times_seen": recorded.times_seen,
            "reinforced": recorded.times_seen > 1,
        }, ensure_ascii=False)

    def experience_search(self, query: str, k: int = 5) -> str:
        matches = self.store.find_similar(query, k=k)
        return json.dumps({
            "query": query, "count": len(matches),
            "experiences": [e.to_dict() for e in matches],
        }, ensure_ascii=False)

    def memory_search(self, query: str, k_per_source: int = 3) -> str:
        results = self.layer.search(query, k_per_source=k_per_source)
        return json.dumps({
            "query": query, "count": len(results), "results": results,
        }, ensure_ascii=False)

    def tools(self) -> List[RegisteredTool]:
        return [
            RegisteredTool(
                definition=ToolDefinition(
                    name="experience_record",
                    description="Record a lesson/outcome so future similar "
                                "tasks retrieve it (repeated goals "
                                "reinforce, not duplicate).",
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "goal": {"type": "string"},
                            "outcome": {"type": "string"},
                            "session_id": {"type": "string"},
                            "diagnosis": {"type": "string"},
                            "resolution": {"type": "string"},
                            "actions": {"type": "array"},
                            "tags": {"type": "array"},
                            "project_type": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["goal", "outcome"],
                    },
                ),
                handler=self.experience_record,
                category="memory",
                side_effect_level=SAFE_WRITE,
            ),
            RegisteredTool(
                definition=ToolDefinition(
                    name="experience_search",
                    description="Search remembered agent experiences "
                                "(episodes and taught procedures).",
                    parameters_schema={
                        "type": "object",
                        "properties": {"query": {"type": "string"},
                                       "k": {"type": "integer"}},
                        "required": ["query"],
                    },
                ),
                handler=self.experience_search,
                category="memory",
                side_effect_level=READ_ONLY,
            ),
            RegisteredTool(
                definition=ToolDefinition(
                    name="memory_search",
                    description="Unified memory search across experiences, "
                                "failure cases, digested docs, and the "
                                "journal — results are source-labeled.",
                    parameters_schema={
                        "type": "object",
                        "properties": {"query": {"type": "string"},
                                       "k_per_source": {"type": "integer"}},
                        "required": ["query"],
                    },
                ),
                handler=self.memory_search,
                category="memory",
                side_effect_level=READ_ONLY,
            ),
        ]


def update_agent_registry(registry: ToolRegistry, workspace: Workspace,
                          experience_store: Optional[ExperienceStore] = None,
                          cases_path=None, digest_path=None,
                          journal_path=None) -> None:
    """Register the memory tools into an existing registry."""
    for tool in MemoryToolkit(
            experience_store, cases_path=cases_path, digest_path=digest_path,
            journal_path=journal_path).tools():
        registry.register(tool)
