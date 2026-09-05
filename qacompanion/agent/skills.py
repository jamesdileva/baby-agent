"""S51 skills 2.0: reusable procedures as DATA the model retrieves and
follows.

A Skill is a strict JSON record (name, goal, description, required_tools,
preconditions, procedure, verification, failure_modes, examples,
confidence) — the exact schema of the S50 resume seed. The SkillLibrary
loads a directory of skill files TOLERANTLY (one malformed file is
recorded and skipped — a library must not die on one bad entry, unlike
the strict single-file stores). Procedures are surfaced to the model via
skill_find; the model executes them with its ordinary tools. Nothing
here runs procedures programmatically — that is curation/S62-scale
machinery.

Pins (fixtures-first discipline):
- skill_teach validates and writes atomically — teaching is SAFE_WRITE;
- retrieval is deterministic keyword scoring over name/goal/description/
  tags (the S47 pattern); no embeddings;
- the first real consumer: skills/agent/resume_interrupted_task.json
  (S50's seed) loads and is findable.
"""

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .registry import READ_ONLY, SAFE_WRITE, RegisteredTool, ToolDefinition, ToolOperationError, ToolRegistry

DEFAULT_SKILL_DIR = Path("skills") / "agent"


class SkillError(ToolOperationError):
    """Structured skill failure (validation, teaching, missing)."""


def _require(condition, message):
    if not condition:
        raise ValueError(message)


@dataclass
class Skill:
    """One reusable procedure, taught once and retrieved forever."""

    name: str
    goal: str
    procedure: List[str]
    description: str = ""
    required_tools: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    verification: str = ""
    failure_modes: List[str] = field(default_factory=list)
    examples: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.5
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        _require(isinstance(self.name, str)
                 and re.fullmatch(r"[a-z][a-z0-9_]*", self.name),
                 "skill name must be lowercase identifier-like")
        _require(isinstance(self.goal, str) and self.goal.strip(),
                 "skill goal required")
        _require(isinstance(self.procedure, list) and self.procedure
                 and all(isinstance(step, str) and step.strip()
                         for step in self.procedure),
                 "skill procedure must be a non-empty list of steps")
        _require(isinstance(self.confidence, (int, float))
                 and not isinstance(self.confidence, bool)
                 and 0.0 <= self.confidence <= 1.0,
                 "confidence must be within [0, 1]")

    def to_dict(self):
        return {
            "name": self.name,
            "goal": self.goal,
            "description": self.description,
            "required_tools": list(self.required_tools),
            "preconditions": list(self.preconditions),
            "procedure": list(self.procedure),
            "verification": self.verification,
            "failure_modes": list(self.failure_modes),
            "examples": list(self.examples),
            "confidence": self.confidence,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data):
        _require(isinstance(data, dict), "skill record must be an object")
        _require("name" in data and "goal" in data and "procedure" in data,
                 "skill record missing name/goal/procedure")
        return cls(
            name=data["name"],
            goal=data["goal"],
            description=data.get("description", ""),
            required_tools=list(data.get("required_tools", [])),
            preconditions=list(data.get("preconditions", [])),
            procedure=[str(step) for step in data["procedure"]],
            verification=data.get("verification", ""),
            failure_modes=list(data.get("failure_modes", [])),
            examples=list(data.get("examples", [])),
            confidence=data.get("confidence", 0.5),
            tags=list(data.get("tags", [])),
        )

    def text(self) -> str:
        return " ".join(filter(None, [
            self.name, self.goal, self.description, " ".join(self.tags),
        ])).lower()


class SkillLibrary:
    """A directory of skill files, loaded tolerantly."""

    def __init__(self, directory: Optional[Path] = None):
        self.directory = Path(directory or DEFAULT_SKILL_DIR)
        self.errors: List[str] = []

    def load(self) -> List[Skill]:
        skills: List[Skill] = []
        self.errors = []
        if not self.directory.exists():
            return skills
        for path in sorted(self.directory.glob("*.json")):
            try:
                data = json.loads(
                    path.read_text(encoding="utf-8-sig"))
                skills.append(Skill.from_dict(data))
            except (json.JSONDecodeError, ValueError, OSError) as exc:
                self.errors.append(f"{path.name}: {exc}")
        return skills

    def list_skills(self) -> List[Skill]:
        return sorted(self.load(), key=lambda skill: skill.name)

    def get(self, name: str) -> Optional[Skill]:
        for skill in self.load():
            if skill.name == name:
                return skill
        return None

    def find(self, query: str, k: int = 3) -> List[Skill]:
        terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
        scored = []
        for skill in self.load():
            text = skill.text()
            overlap = sum(1 for term in terms if term in text)
            if not overlap and terms:
                continue
            scored.append((overlap + skill.confidence, skill))
        scored.sort(key=lambda pair: (-pair[0], pair[1].name))
        return [skill for _, skill in scored[:k]]

    def teach(self, skill: Skill) -> Path:
        """Persist a skill atomically (one file per skill)."""
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / f"{skill.name}.json"
        tmp = target.with_name(target.name + ".tmp-skill")
        tmp.write_text(json.dumps(skill.to_dict(), indent=2,
                                  ensure_ascii=False),
                       encoding="utf-8")
        import os
        os.replace(tmp, target)
        return target


class SkillToolkit:
    """Binds skill_find / skill_teach (brain-level, no workspace)."""

    def __init__(self, library: Optional[SkillLibrary] = None):
        self.library = library or SkillLibrary()

    def skill_find(self, query: str, k: int = 3) -> str:
        matches = self.library.find(query, k=k)
        return json.dumps({
            "query": query, "count": len(matches),
            "skills": [skill.to_dict() for skill in matches],
        }, ensure_ascii=False)

    def skill_teach(self, skill: Dict[str, Any]) -> str:
        try:
            parsed = Skill.from_dict(skill)
        except ValueError as exc:
            raise SkillError(f"invalid skill record: {exc}") from exc
        target = self.library.teach(parsed)
        return json.dumps({
            "taught": True,
            "name": parsed.name,
            "path": str(target),
        }, ensure_ascii=False)

    def tools(self) -> List[RegisteredTool]:
        return [
            RegisteredTool(
                definition=ToolDefinition(
                    name="skill_find",
                    description="Find a taught skill (goal, preconditions, "
                                "step-by-step procedure, verification) and "
                                "follow it with your other tools.",
                    parameters_schema={
                        "type": "object",
                        "properties": {"query": {"type": "string"},
                                       "k": {"type": "integer"}},
                        "required": ["query"],
                    },
                ),
                handler=self.skill_find,
                category="skills",
                side_effect_level=READ_ONLY,
            ),
            RegisteredTool(
                definition=ToolDefinition(
                    name="skill_teach",
                    description="Teach a new skill so future similar tasks "
                                "retrieve it: {name, goal, procedure: [...], "
                                "verification, ...}.",
                    parameters_schema={
                        "type": "object",
                        "properties": {"skill": {"type": "object"}},
                        "required": ["skill"],
                    },
                ),
                handler=self.skill_teach,
                category="skills",
                side_effect_level=SAFE_WRITE,
            ),
        ]


def update_agent_registry(registry: ToolRegistry, workspace: Workspace,
                          skill_dir: Optional[Path] = None) -> None:
    """Register the skill tools into an existing registry."""
    for tool in SkillToolkit(SkillLibrary(skill_dir)).tools():
        registry.register(tool)
