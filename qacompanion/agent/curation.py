"""S62 trajectory curation: the gate between "something happened" and
"Baby-Agent should learn this" (docs/ROADMAP-agentlite.md §S62).

Deterministic core — no LLM: classify, score (measurable dimensions
only, None = honestly unknown), hard rejections, soft penalties,
ACCEPT / REVIEW / REJECT verdicts, dedupe + diversity, lesson
candidates, and atomic exports under QA_CURATED_DIR (default curated/).

Permanent dataset separation (roadmap rule):
  EXPERIENCE DATA = everything that happened
  CURATED DATA    = useful, verified experiences
  TRAINING DATA   = the explicitly accepted subset (S63's input)
Curation only PROPOSES lessons (failure cases, skill seeds) — writing
cases.jsonl stays deliberate and teacher-gated (case-#10 lore).

Pins (fixtures-first discipline):
- every run summary reports rejected / flagged items with reasons;
- credential-flagged text is REDACTED in exports — the flag names the
  pattern, never echoes the secret;
- mined != verified: PARTIAL provenance is never upgraded to success.
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .experience import Experience, ExperienceStore, _normalize_goal

DEFAULT_CURATED_DIR = "curated"

CLASS_SUCCESS = "SUCCESS"
CLASS_FAILED = "FAILED"
CLASS_RECOVERED = "RECOVERED"
CLASS_HUMAN_CORRECTED = "HUMAN_CORRECTED"
CLASS_PARTIAL = "PARTIAL"
CLASS_UNSAFE = "UNSAFE"
CLASS_INVALID = "INVALID"

VERDICT_ACCEPT = "ACCEPT"
VERDICT_REVIEW = "REVIEW"
VERDICT_REJECT = "REJECT"

# the roadmap's ten quality dimensions; a scorer fills each with 0..1
# or None when no deterministic signal exists (never guessed)
DIMENSIONS = ("verification", "recovery", "tool_use", "efficiency",
              "clarity", "completeness", "correctness", "robustness",
              "diversity", "relevance")

ACCEPT_THRESHOLD = 0.5
REVIEW_THRESHOLD = 0.3
REVIEW_CONFIDENCE = 0.5
PLACEHOLDER_GOAL_PREFIX = "continued prior work"

# (label, pattern) — the label is what reports show; matched text is
# always redacted, never echoed
_CREDENTIAL_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("credential_assignment", re.compile(
        r"(?i)\b(api[_-]?key|apikey|secret|password|passwd|auth[_-]?token"
        r"|access[_-]?token)\b\s*[:=]\s*\S+")),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

_DESTRUCTIVE_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("posix_rm_rf_root", re.compile(
        r"\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*\s+/(?![\w.-])")),
    ("disk_format", re.compile(r"(?i)\bmkfs\b|\bformat\s+c:")),
    ("windows_del_tree", re.compile(
        r"(?i)\bdel\s+/[sq]\b|\brd\s+/s\b"
        r"|\bRemove-Item\s+-Recurse\s+-Force\s+[A-Za-z]:\\")),
    ("forced_system_stop", re.compile(
        r"(?i)\b(shutdown|reboot)\s+(-f|--force|now)\b")),
)


def _failure_pairs(experience: Experience) -> list:
    pairs = experience.context.get("failure_pairs") or []
    return pairs if isinstance(pairs, list) else []


def redact(text: str) -> str:
    """Replace credential-shaped matches with a marker (never echo)."""
    if not text:
        return text
    for _label, pattern in _CREDENTIAL_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def redact_all(value: Any) -> Any:
    """Deep-walk a JSON-ish structure redacting every string."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_all(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_all(v) for v in value]
    return value


def _scan_text(experience: Experience) -> str:
    """Every string a trajectory carries, for pattern scanning."""
    parts: List[str] = [
        experience.goal,
        " ".join(experience.actions),
        experience.failure or "",
        experience.diagnosis or "",
        experience.resolution or "",
        json.dumps(experience.context, ensure_ascii=False, default=str),
    ]
    return "\n".join(p for p in parts if p)


def hard_flags(experience: Experience) -> List[Dict[str, str]]:
    """Deterministic hard rejections: credentials, unsafe, invalid."""
    flags: List[Dict[str, str]] = []
    text = _scan_text(experience)
    for label, pattern in _CREDENTIAL_PATTERNS:
        if pattern.search(text):
            flags.append({"kind": "credential_exposure", "pattern": label})
    for label, pattern in _DESTRUCTIVE_PATTERNS:
        if pattern.search(text):
            flags.append({"kind": "unsafe_action", "pattern": label})
    if experience.outcome == "success" and not experience.actions:
        flags.append({"kind": "invalid",
                      "pattern": "success claimed with zero recorded actions"})
    return flags


def classify(experience: Experience,
             flags: List[Dict[str, str]]) -> str:
    kinds = {flag["kind"] for flag in flags}
    if "unsafe_action" in kinds:
        return CLASS_UNSAFE
    if "invalid" in kinds:
        return CLASS_INVALID
    return {
        "success": CLASS_SUCCESS,
        "failed": CLASS_FAILED,
        "recovered": CLASS_RECOVERED,
        "human_corrected": CLASS_HUMAN_CORRECTED,
        "partial": CLASS_PARTIAL,
    }.get(experience.outcome, CLASS_PARTIAL)


def soft_penalties(experience: Experience) -> List[Dict[str, str]]:
    """Docked dims with recorded reasons (never silent)."""
    penalties: List[Dict[str, str]] = []
    actions = experience.actions
    longest_run, run = 1, 1
    for prev, curr in zip(actions, actions[1:]):
        run = run + 1 if curr == prev else 1
        longest_run = max(longest_run, run)
    if longest_run > 3:
        penalties.append({
            "dimension": "efficiency",
            "reason": f"same action repeated {longest_run}x consecutively"})
    tool_count = experience.context.get("tool_count", len(actions))
    if isinstance(tool_count, int) and tool_count > 30:
        penalties.append({
            "dimension": "efficiency",
            "reason": f"tool_count {tool_count} exceeds 30"})
    pairs = _failure_pairs(experience)
    if (isinstance(tool_count, int) and tool_count > 15 and not pairs
            and not (experience.failure or experience.resolution)):
        penalties.append({
            "dimension": "efficiency",
            "reason": "large tool usage captured no failure/fix signal"})
    if experience.goal.startswith(PLACEHOLDER_GOAL_PREFIX):
        penalties.append({"dimension": "clarity",
                          "reason": "placeholder goal"})
    elif len([t for t in re.split(r"\W+", experience.goal) if t]) < 3:
        penalties.append({"dimension": "clarity",
                          "reason": "goal under 3 words"})
    return penalties


def score(experience: Experience, classification: str,
          penalties: List[Dict[str, str]]
          ) -> Tuple[Dict[str, Optional[float]], float, List[str]]:
    """Per-dimension 0..1 or None; overall = mean over known dims."""
    dims: Dict[str, Optional[float]] = {}
    pairs = _failure_pairs(experience)

    if experience.outcome == "success":
        dims["verification"] = 1.0  # recorded success implies a passed gate
    elif experience.outcome == "failed":
        dims["verification"] = 0.0
    elif experience.verification:
        dims["verification"] = 1.0  # verification evidence exists
    else:
        dims["verification"] = None

    if experience.failure and (experience.resolution or experience.diagnosis):
        dims["recovery"] = 1.0
    elif experience.failure:
        dims["recovery"] = 0.25
    else:
        dims["recovery"] = None

    if experience.actions:
        dims["tool_use"] = min(1.0, len(set(experience.actions)) / 4.0)
    else:
        dims["tool_use"] = 0.0

    docked = sum(0.2 for p in penalties if p["dimension"] == "efficiency")
    dims["efficiency"] = max(0.0, 1.0 - docked)

    if experience.goal.startswith(PLACEHOLDER_GOAL_PREFIX):
        dims["clarity"] = 0.25
    else:
        docked = sum(0.3 for p in penalties if p["dimension"] == "clarity")
        dims["clarity"] = max(0.0, 1.0 - docked)

    complete = 0.0
    if experience.goal:
        complete += 0.2 if experience.goal.startswith(
            PLACEHOLDER_GOAL_PREFIX) else 0.4
    if experience.actions:
        complete += 0.3
    if any(k in experience.context
           for k in ("message_count", "part_count", "tool_count")):
        complete += 0.3
    dims["completeness"] = complete

    if classification == CLASS_SUCCESS:
        dims["correctness"] = 1.0
    elif classification in (CLASS_FAILED, CLASS_INVALID):
        dims["correctness"] = 0.0
    else:
        dims["correctness"] = None  # mined partials: cannot verify

    if pairs:
        dims["robustness"] = min(1.0, len(pairs) / 3.0)
    elif experience.failure:
        dims["robustness"] = 0.5
    else:
        dims["robustness"] = None

    dims["diversity"] = None  # filled by the curator's diversity pass

    if experience.goal.startswith(PLACEHOLDER_GOAL_PREFIX):
        dims["relevance"] = 0.25
    else:
        stopwords = {"the", "a", "an", "and", "or", "to", "for", "of", "in",
                     "on", "with", "my", "me", "i", "is", "it", "this",
                     "that", "please"}
        substance = [t for t in
                     (t for t in re.split(r"\W+", experience.goal.lower())
                      if t) if t not in stopwords]
        dims["relevance"] = min(1.0, len(substance) / 5.0)

    known = [v for v in dims.values() if v is not None]
    overall = round(sum(known) / len(known), 4) if known else 0.0
    unknown = [k for k in DIMENSIONS if dims.get(k) is None]
    return dims, overall, unknown


def verdict_for(experience: Experience, classification: str,
                flags: List[Dict[str, str]], overall: float,
                dims: Dict[str, Optional[float]]) -> Tuple[str, List[str]]:
    """ACCEPT / REVIEW / REJECT with recorded reasons."""
    reasons: List[str] = []
    if flags:
        for flag in flags:
            reasons.append(f"hard rejection: {flag['kind']} ({flag['pattern']})")
        return VERDICT_REJECT, reasons
    placeholder = experience.goal.startswith(PLACEHOLDER_GOAL_PREFIX)
    substance = bool(experience.failure or experience.resolution) \
        or len(experience.actions) >= 3
    if placeholder and not substance:
        reasons.append("placeholder goal with no failure data and <3 actions")
        return VERDICT_REJECT, reasons
    # human-review finding (DECISIONS 2026-09-11): a recovered pair under
    # a junk goal (greeting, closing template) is NOT high-value — goal
    # substance gates the high-value claim
    substantive_goal = (
        not placeholder
        and len([t for t in re.split(r"\W+", experience.goal) if t]) >= 3)
    if (experience.confidence < REVIEW_CONFIDENCE
            and dims.get("recovery") == 1.0 and substantive_goal):
        reasons.append("low-confidence high-value: recovered failure->fix "
                       "pair routed to human review")
        return VERDICT_REVIEW, reasons
    if overall >= ACCEPT_THRESHOLD:
        reasons.append(f"overall score {overall} >= {ACCEPT_THRESHOLD}")
        return VERDICT_ACCEPT, reasons
    if overall >= REVIEW_THRESHOLD:
        reasons.append(f"overall score {overall} between "
                       f"{REVIEW_THRESHOLD} and {ACCEPT_THRESHOLD}")
        return VERDICT_REVIEW, reasons
    reasons.append(f"overall score {overall} < {REVIEW_THRESHOLD}")
    return VERDICT_REJECT, reasons


@dataclass
class CuratedTrajectory:
    """One experience through the curation gate."""

    experience_id: str
    session_id: Optional[str]
    source: str
    goal: str
    outcome: str
    classification: str
    dims: Dict[str, Optional[float]]
    overall: float
    unknown_dims: List[str]
    hard_flags: List[Dict[str, str]]
    penalties: List[Dict[str, str]]
    verdict: str
    reasons: List[str]
    confidence: float
    times_seen: int
    project_tag: str = ""
    diversity_score: Optional[float] = None
    # S63: the substantive payload, so trajectory.jsonl is the full
    # structured export the training pipeline consumes (redacted at
    # export; training reads ONLY curated/, never raw experience)
    actions: List[str] = field(default_factory=list)
    failure: Optional[str] = None
    diagnosis: Optional[str] = None
    resolution: Optional[str] = None
    verification: Dict[str, Any] = field(default_factory=dict)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    final_answer: Optional[str] = None
    model: Optional[str] = None
    verification_failures: List[Dict[str, Any]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "session_id": self.session_id,
            "source": self.source,
            "goal": self.goal,
            "outcome": self.outcome,
            "classification": self.classification,
            "score": {"dimensions": self.dims, "overall": self.overall,
                      "unknown_dims": self.unknown_dims},
            "hard_flags": self.hard_flags,
            "penalties": self.penalties,
            "verdict": self.verdict,
            "reasons": self.reasons,
            "confidence": self.confidence,
            "times_seen": self.times_seen,
            "diversity_score": self.diversity_score,
            "actions": self.actions,
            "failure": self.failure,
            "diagnosis": self.diagnosis,
            "resolution": self.resolution,
            "verification": self.verification,
            "steps": self.steps,
            "final_answer": self.final_answer,
            "model": self.model,
            "verification_failures": self.verification_failures,
            "tags": self.tags,
        }


def _source_of(experience: Experience) -> str:
    return str(experience.context.get("source") or "unspecified")


def _project_tag_of(experience: Experience) -> str:
    tags = experience.tags or []
    if len(tags) > 1:
        return tags[1]
    return tags[0] if tags else "unknown"


def _steps_of(experience: Experience) -> List[Dict[str, Any]]:
    """S63 step capture (loop-recorded sessions): context["tool_calls"]."""
    steps = experience.context.get("tool_calls") or []
    return steps if isinstance(steps, list) else []


def _final_answer_of(experience: Experience) -> Optional[str]:
    answer = experience.context.get("final_answer")
    return answer if isinstance(answer, str) else None


def _failures_of(experience: Experience) -> List[Dict[str, Any]]:
    """S72: captured verification-failed recovery states."""
    failures = experience.context.get("verification_failures") or []
    return failures if isinstance(failures, list) else []


def _model_of(experience: Experience) -> Optional[str]:
    """The recorded model/provider tag (e.g. `scripted-demo`) — the
    provenance chain the training corpus must carry."""
    model = experience.context.get("model")
    return model if isinstance(model, str) else None


class TrajectoryCurator:
    """Run experiences through the gate; write exports; report honestly."""

    EXPORT_FILES = ("trajectory.jsonl", "curated.jsonl", "review.jsonl",
                    "rejected.jsonl", "lessons.jsonl", "skills.jsonl",
                    "failures.jsonl", "preferences.jsonl", "benchmarks.jsonl")

    def __init__(self, store: ExperienceStore):
        self.store = store

    def curate(self, out_dir=None, dry_run: bool = False) -> Dict[str, Any]:
        experiences = self.store.load()
        trajectories = [self._trajectory(exp) for exp in experiences]
        self._apply_diversity(trajectories)

        merged: Dict[str, CuratedTrajectory] = {}
        duplicates_merged = 0
        for traj in sorted(trajectories, key=lambda t: -t.overall):
            key = _normalize_goal(traj.goal)
            if key in merged:
                duplicates_merged += 1
                winner = merged[key]
                winner.times_seen += traj.times_seen
                winner.reasons.append(
                    f"absorbed duplicate trajectory (+{traj.times_seen} "
                    "times_seen)")
            else:
                merged[key] = traj
        unique = list(merged.values())

        curated = [t for t in unique if t.verdict == VERDICT_ACCEPT]
        review = [t for t in unique if t.verdict == VERDICT_REVIEW]
        rejected = [t for t in unique if t.verdict == VERDICT_REJECT]

        by_id = {exp.experience_id: exp for exp in experiences}
        failure_cases, skill_candidates = self._extract_lessons(
            unique, by_id)

        out_path = Path(out_dir or os.environ.get("QA_CURATED_DIR")
                        or DEFAULT_CURATED_DIR)
        exports = self._export(out_path, trajectories, curated, review,
                               rejected, failure_cases, skill_candidates,
                               dry_run=dry_run)

        report = {
            "experiences": len(experiences),
            "unique_after_dedupe": len(unique),
            "duplicates_merged": duplicates_merged,
            "verdicts": {VERDICT_ACCEPT: len(curated),
                         VERDICT_REVIEW: len(review),
                         VERDICT_REJECT: len(rejected)},
            "classifications": self._tally(t.classification for t in unique),
            "hard_flagged": sum(1 for t in unique if t.hard_flags),
            "penalized": sum(1 for t in unique if t.penalties),
            "lessons": {"failure_cases": len(failure_cases),
                        "skill_candidates": len(skill_candidates)},
            "exports": exports,
            "out_dir": str(out_path),
            "dry_run": dry_run,
            "notes": self._notes(experiences),
        }
        return report

    # -- pipeline pieces ------------------------------------------------

    def _trajectory(self, experience: Experience) -> CuratedTrajectory:
        flags = hard_flags(experience)
        classification = classify(experience, flags)
        penalties = soft_penalties(experience)
        dims, overall, unknown = score(experience, classification, penalties)
        verdict, reasons = verdict_for(experience, classification, flags,
                                       overall, dims)
        return CuratedTrajectory(
            experience_id=experience.experience_id,
            session_id=experience.session_id,
            source=_source_of(experience),
            goal=experience.goal,
            outcome=experience.outcome,
            classification=classification,
            dims=dims,
            overall=overall,
            unknown_dims=unknown,
            hard_flags=flags,
            penalties=penalties,
            verdict=verdict,
            reasons=reasons,
            confidence=experience.confidence,
            times_seen=experience.times_seen,
            project_tag=_project_tag_of(experience),
            actions=list(experience.actions),
            failure=experience.failure,
            diagnosis=experience.diagnosis,
            resolution=experience.resolution,
            verification=dict(experience.verification or {}),
            steps=_steps_of(experience),
            final_answer=_final_answer_of(experience),
            model=_model_of(experience),
            verification_failures=_failures_of(experience),
            tags=list(experience.tags or []),
        )

    def _apply_diversity(self, trajectories: List[CuratedTrajectory]) -> None:
        """Diversity = rarity of (source, project) within the corpus."""
        total = len(trajectories)
        groups: Dict[Tuple[str, str], int] = {}
        for traj in trajectories:
            key = (traj.source, traj.project_tag)
            groups[key] = groups.get(key, 0) + 1
        for traj in trajectories:
            key = (traj.source, traj.project_tag)
            fraction = groups[key] / total if total else 0.0
            traj.diversity_score = round(1.0 - fraction, 4)
            traj.dims["diversity"] = traj.diversity_score
        for traj in trajectories:
            known = [v for v in traj.dims.values() if v is not None]
            traj.overall = (round(sum(known) / len(known), 4)
                            if known else 0.0)
            traj.unknown_dims = [k for k in DIMENSIONS
                                 if traj.dims.get(k) is None]

    def _extract_lessons(self, trajectories: List[CuratedTrajectory],
                         by_id: Dict[str, Experience]) -> Tuple[List[dict],
                                                                List[dict]]:
        """Candidates only — flagged trajectories never yield lessons."""
        failure_cases: List[dict] = []
        skill_candidates: List[dict] = []
        for traj in trajectories:
            if traj.hard_flags or traj.verdict == VERDICT_REJECT:
                continue
            exp = by_id[traj.experience_id]
            if exp.failure:
                signature = _candidate_signature(exp.goal, exp.failure)
                failure_cases.append({
                    "goal": exp.goal,
                    "error": exp.failure,
                    "diagnosis": exp.diagnosis,
                    "resolution": exp.resolution,
                    "signature_candidate": signature,
                    "provenance": {"experience_id": exp.experience_id,
                                   "session_id": exp.session_id,
                                   "source": traj.source},
                    "trajectory_verdict": traj.verdict,
                })
            if traj.verdict == VERDICT_ACCEPT and len(exp.actions) >= 3:
                skill_candidates.append({
                    "name": _skill_name(exp.goal),
                    "goal": exp.goal,
                    "description": exp.goal,
                    "required_tools": sorted(
                        {a for a in exp.actions if isinstance(a, str)}),
                    "preconditions": [],
                    # S75.3: procedure steps are RENDERED calls (tool + the
                    # captured args), not bare tool names — and the whole
                    # candidate validates as a Skill (underscore name,
                    # list[str] procedure, string verification), so the
                    # curation->skills handoff loads instead of breaking.
                    "procedure": _skill_procedure(exp),
                    "verification": "",
                    "failure_modes": [],
                    "examples": [],
                    "confidence": traj.overall,
                    "provenance": {"experience_id": exp.experience_id,
                                   "session_id": exp.session_id,
                                   "source": traj.source},
                })
        return failure_cases, skill_candidates

    def _export(self, out_path: Path, trajectories, curated, review,
                rejected, failure_cases, skill_candidates,
                dry_run: bool) -> Dict[str, int]:
        """failure_cases / skill_candidates partition into lessons.jsonl,
        failures.jsonl and skills.jsonl; preferences / benchmarks are
        honestly empty until their source data exists."""
        rows = {
            "trajectory.jsonl": [t.to_dict() for t in trajectories],
            "curated.jsonl": [t.to_dict() for t in curated],
            "review.jsonl": [t.to_dict() for t in review],
            "rejected.jsonl": [t.to_dict() for t in rejected],
            "lessons.jsonl": failure_cases + skill_candidates,
            "skills.jsonl": skill_candidates,
            "failures.jsonl": failure_cases,
            "preferences.jsonl": [],   # no human_corrected outcomes yet
            "benchmarks.jsonl": [],    # no verified eval sessions yet
        }
        counts = {name: len(rows[name]) for name in self.EXPORT_FILES}
        if dry_run:
            return counts
        out_path.mkdir(parents=True, exist_ok=True)
        for name, records in rows.items():
            _write_jsonl_atomic(out_path / name,
                                [redact_all(r) for r in records])
        _write_json_atomic(out_path / "diversity.json",
                           self._diversity_section(trajectories))
        return counts

    def _diversity_section(self, trajectories) -> Dict[str, Any]:
        """The standalone diversity.json: measurable coverage, not raw
        count (per-source / per-project groups, distinct vocabularies)."""
        per_source: Dict[str, int] = {}
        per_group: Dict[str, int] = {}
        goal_heads: set = set()
        tags: set = set()
        tools: set = set()
        for traj in trajectories:
            per_source[traj.source] = per_source.get(traj.source, 0) + 1
            group = f"{traj.source}/{traj.project_tag}"
            per_group[group] = per_group.get(group, 0) + 1
            goal_heads.add(_normalize_goal(traj.goal)[:40])
        for exp in self.store.load():
            tags.update(exp.tags)
            tools.update(exp.actions)
        return {
            "trajectories": len(trajectories),
            "per_source": per_source,
            "per_source_project": per_group,
            "distinct_tags": sorted(tags),
            "distinct_goal_heads": len(goal_heads),
            "tool_vocabulary": sorted(tools),
        }

    @staticmethod
    def _tally(values) -> Dict[str, int]:
        tally: Dict[str, int] = {}
        for value in values:
            tally[value] = tally.get(value, 0) + 1
        return tally

    @staticmethod
    def _notes(experiences: List[Experience]) -> List[str]:
        notes = []
        if not any(e.outcome == "human_corrected" for e in experiences):
            notes.append("preferences.jsonl empty: no human_corrected "
                         "outcomes exist yet (S50 left intervention "
                         "tracking unimplemented)")
        verified = [e for e in experiences
                    if e.verification and e.outcome == "success"]
        if not verified:
            notes.append("benchmarks.jsonl empty: no verified eval "
                         "sessions recorded in the store yet")
        return notes


def _candidate_signature(goal: str, failure: str) -> str:
    """S2-style candidate signature (provenance-carrying proposal)."""
    from ..signatures import canonical, normalize
    return canonical(normalize(goal[:60], failure[:200]))


def _skill_name(goal: str) -> str:
    # S75.3: underscore-joined so the candidate satisfies the Skill name
    # rule ([a-z][a-z0-9_]*); hyphenated names failed skill_teach
    # validation, breaking the curation->skills handoff by construction.
    words = re.findall(r"[a-z0-9]+", goal.lower())[:5]
    name = "_".join(words) or "unnamed_skill"
    if not name[0].isascii() or not name[0].isalpha():
        name = "skill_" + name
    return name


def _skill_procedure(experience) -> List[str]:
    """Render one candidate's procedure as followable call strings.

    Captured step args (session_learning's bounded tool_calls) are paired
    by position with the action names; mined records without step capture
    fall back to bare tool names. Values are already capture-bounded, so
    the rendering stays compact.
    """
    captured = experience.context.get("tool_calls")
    if not isinstance(captured, list):
        captured = []
    steps: List[str] = []
    for index, action in enumerate(experience.actions):
        if not isinstance(action, str):
            continue
        args: Dict[str, Any] = {}
        if index < len(captured) and isinstance(captured[index], dict):
            step = captured[index]
            if step.get("tool") == action and isinstance(
                    step.get("args"), dict):
                args = step["args"]
        steps.append(_render_step_call(action, args))
    return steps


def _render_step_call(tool: str, args: Dict[str, Any]) -> str:
    """One procedure step: tool plus its demonstrated arguments.

    Same value dialect as training.format_tool_call (quoted strings with
    backslash/quote escaping, bare true/false/null/numbers) so a step
    reads exactly like the calls the runtime parses.
    """
    parts = []
    for key, value in (args or {}).items():
        if isinstance(value, str):
            rendered = '"' + (value[:200].replace("\\", "\\\\")
                              .replace('"', '\\"')) + '"'
        elif isinstance(value, bool):
            rendered = "true" if value else "false"
        elif value is None:
            rendered = "null"
        elif isinstance(value, (int, float)):
            rendered = str(value)
        else:
            rendered = json.dumps(value, ensure_ascii=False,
                                  default=str)[:200]
        parts.append(f"{key}={rendered}")
    return f"{tool}({', '.join(parts)})" if parts else tool


def _write_jsonl_atomic(path: Path, records: List[Dict[str, Any]]) -> None:
    payload = "".join(
        json.dumps(record, ensure_ascii=False, default=str) + "\n"
        for record in records)
    tmp = path.with_name(path.name + ".tmp-curation")
    tmp.write_text(payload, encoding="utf-8", newline="")
    os.replace(tmp, path)


def _write_json_atomic(path: Path, obj: Dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp-curation")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2),
                   encoding="utf-8", newline="")
    os.replace(tmp, path)


def format_report(report: Dict[str, Any]) -> str:
    """Human summary for the CLI (honest counts, notes included)."""
    lines = [
        "curation report:",
        f"  experiences: {report['experiences']} "
        f"(unique after dedupe: {report['unique_after_dedupe']}, "
        f"duplicates merged: {report['duplicates_merged']})",
        f"  verdicts: ACCEPT={report['verdicts']['ACCEPT']} "
        f"REVIEW={report['verdicts']['REVIEW']} "
        f"REJECT={report['verdicts']['REJECT']}",
        f"  classifications: {report['classifications']}",
        f"  hard-flagged: {report['hard_flagged']}, "
        f"penalized: {report['penalized']}",
        f"  lessons: failure_cases={report['lessons']['failure_cases']} "
        f"skill_candidates={report['lessons']['skill_candidates']}",
    ]
    if report["dry_run"]:
        lines.append("  dry run: no exports written")
    else:
        lines.append(f"  exports: {report['out_dir']} "
                     f"({sum(report['exports'].values())} records)")
    for note in report["notes"]:
        lines.append(f"  note: {note}")
    return "\n".join(lines)
