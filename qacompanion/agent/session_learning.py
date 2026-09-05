"""S50 learning from agent sessions: sessions become experience.

Capture: an AgentSession converts into an Experience with a mechanically
honest outcome (verified-first-attempt = success, later = recovered,
failed = failed, cancelled/unverified = partial) and the S49 QA brain's
advice harvested into diagnosis fields. Recording is a HARNESS concern —
the loop itself stays pure (hermeticity), so run_benchmark records at
run end, the loop does not.

Curate: rule-based cleanup of the mined corpus, never silent — every
run returns kept/removed counts by rule. The ×321 resume pattern is
PROMOTED into a skill seed file (S51 schema, DATA only — nothing loads
it until S51) and removed from the episodic store: one skill beats 321
copies.

Pins (fixtures-first discipline):
- human_corrected / unsafe classifications stay unimplemented until
  intervention tracking exists (roadmap-honest);
- the curator never fabricates: it only removes by explicit rule and
  reports what it did;
- greeting pings ("hello" and friends) are noise, not experience.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .experience import Experience, ExperienceStore, _normalize_goal
from .loop import AgentLoop  # noqa: F401  (typing only)
from .qa_brain import failure_text
from .session import AgentSession, AgentState

GREETING_WORDS = {"hello", "hi", "hey", "helo", "yo", "hiya", "greetings",
                  "sup"}
RESUME_PATTERN_RE = re.compile(
    r"previous response was interrupted|continue where you left off|"
    r"continue from where you left off",
    re.IGNORECASE)
RESUME_SKILL_NAME = "resume_interrupted_task"
DEFAULT_SKILL_DIR = Path("skills") / "agent"


def classify_outcome(session: AgentSession) -> str:
    """Mechanical outcome from observable facts only."""
    if session.state == AgentState.COMPLETED:
        attempts = session.verification_results
        if attempts and attempts[0].get("ok"):
            return "success"
        if attempts:
            return "recovered"
        return "partial"  # unverified completion: no proof either way
    if session.state == AgentState.FAILED:
        return "failed"
    if session.state == AgentState.CANCELLED:
        return "partial"
    return "partial"


def _harvest_qa_advice(session: AgentSession) -> List[Dict[str, Any]]:
    """QA brain advice (S49) from the session's system messages."""
    advice = []
    for message in session.messages:
        if message.role != "system":
            continue
        try:
            payload = json.loads(message.content)
        except (ValueError, TypeError):
            continue
        if isinstance(payload, dict) and "qa_memory" in payload:
            advice.append(payload["qa_memory"])
    return advice


def session_to_experience(session: AgentSession,
                          model: Optional[str] = None) -> Experience:
    """Convert a finished session into an Experience record."""
    advice = _harvest_qa_advice(session)
    failure = None
    for observation in session.observations:
        text = failure_text(observation)
        if text:
            failure = text.strip().splitlines()[0][:300] \
                if text.strip() else None
            break
    tags = ["autonomous-session", model or "unknown-model"]
    if classify_outcome(session) == "partial" \
            and session.state == AgentState.COMPLETED:
        tags.append("unverified")
    return Experience(
        goal=session.goal,
        outcome=classify_outcome(session),
        session_id=session.session_id,
        actions=[call.name for call in session.tool_calls],
        context={
            "iterations": session.iterations,
            "state": session.state.value,
            "workspace_root": session.workspace_root,
            "model": model,
        },
        failure=failure,
        diagnosis=(advice[0].get("diagnosis") if advice else None),
        verification={"attempts": list(session.verification_results)},
        tags=tags,
    )


def record_session(session: AgentSession, store: ExperienceStore,
                   model: Optional[str] = None) -> Experience:
    """Record a finished session into the experience store."""
    return store.record(session_to_experience(session, model=model))


# --- curation ----------------------------------------------------------------

def _is_greeting(goal: str) -> bool:
    tokens = _normalize_goal(goal).split()
    if not tokens:
        return True
    if all(token in GREETING_WORDS for token in tokens):
        return True
    return len(tokens) <= 2 and any(token in GREETING_WORDS
                                    for token in tokens)


def _is_resume_pattern(goal: str) -> bool:
    return bool(RESUME_PATTERN_RE.search(goal))


RESUME_SKILL_SEED = {
    "name": RESUME_SKILL_NAME,
    "goal": "Resume an interrupted task from partial state without "
            "redoing completed work",
    "description": "A previous session worked in this workspace and was "
                   "interrupted mid-task. Recover the state, finish the "
                   "job, and prove it.",
    "required_tools": ["list_directory", "read_file", "search_code",
                       "run_tests", "run_command", "edit_file"],
    "preconditions": [
        "a prior session worked here and was interrupted",
        "the workspace may contain partially completed work",
    ],
    "procedure": [
        "Inspect the workspace for partially completed work "
        "(new/modified files vs git status)",
        "Read any leftover test or verification output",
        "Determine the last completed step from evidence",
        "Continue from the next step — never from scratch",
        "Re-run the verification plan to prove completion",
    ],
    "verification": "The project's verification plan passes (tests/build "
                    "green); COMPLETED only on proof",
    "failure_modes": [
        "assuming prior work is complete",
        "redoing finished steps",
        "missing leftover broken state",
    ],
    "examples": [{
        "goal": "Your previous response was interrupted. Continue where "
                "you left off",
        "source": "opencode corpus, 321 reinforced occurrences (S47.1)",
    }],
    "confidence": 0.6,
}


def write_resume_skill(skill_dir: Optional[Path] = None) -> Path:
    """Write the resume skill seed (S51 schema). DATA only — the S51
    runtime will load it; nothing reads it yet."""
    target = Path(skill_dir or DEFAULT_SKILL_DIR) / f"{RESUME_SKILL_NAME}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(json.dumps(RESUME_SKILL_SEED, indent=2,
                                     ensure_ascii=False),
                          encoding="utf-8")
    return target


def curate(store: ExperienceStore,
           skill_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Rule-based curation of the experience store. Never silent."""
    experiences = store.load()
    stats: Dict[str, Any] = {
        "before": len(experiences),
        "kept": 0,
        "removed_greeting": 0,
        "removed_resume_pattern": 0,
        "skill_path": None,
    }
    kept: List[Experience] = []
    skill_written = False
    for experience in experiences:
        if _is_greeting(experience.goal):
            stats["removed_greeting"] += 1
            continue
        if _is_resume_pattern(experience.goal):
            stats["removed_resume_pattern"] += 1
            if not skill_written:
                path = write_resume_skill(skill_dir)
                stats["skill_path"] = str(path)
                skill_written = True
            continue
        kept.append(experience)
    store.save(kept)
    stats["kept"] = len(kept)
    if stats["removed_resume_pattern"] and not skill_written:
        # pattern matched but the seed already existed: still report it
        stats["skill_path"] = str(Path(skill_dir or DEFAULT_SKILL_DIR)
                                  / f"{RESUME_SKILL_NAME}.json")
    return stats
