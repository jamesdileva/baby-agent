"""S63 training dataset pipeline 2.0: CURATED data -> training corpus.

Source discipline (permanent roadmap rule): the input is the S62 CURATED
export directory — NEVER raw experience. The eligibility gate enforces
the second half of the rule: a trajectory enters training.jsonl iff it
was ACCEPTED by the curation gate AND classified SUCCESS AND carries
verification evidence. Mined PARTIAL data stays a structured trajectory
record but can never masquerade as verified success.

The chat record teaches the EXACT textual tool protocol the runtime
teaches (loop.build_system_prompt) — the S55 finding: the protocol is
what general small models lack, so this corpus is baby-agent:ep1's (S64)
training data.

Pins (fixtures-first discipline):
- no fabricated steps or observations, ever — records without captured
  step data stay trajectory-level and are reported as not
  step-trainable;
- exclusions carry reasons; the report never inflates eligibility;
- deterministic and hermetic — no LLM in the pipeline.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .loop import TOOL_PROTOCOL_PROMPT, build_system_prompt

DEFAULT_TRAINING_DIR = "training"

CLASS_MAP = {
    "SUCCESS": "successful",
    "FAILED": "failed",
    "RECOVERED": "recovered",
    "HUMAN_CORRECTED": "human-corrected",
    "UNSAFE": "unsafe",
    "PARTIAL": "partial",
}

MAX_STEPS = 50
MAX_TEXT_CHARS = 500


class TrainingError(ValueError):
    """Structured training-pipeline failure (missing curated export)."""


@dataclass
class TrajectoryRecord:
    """One curated trajectory, structured for training consumption."""

    goal: str
    trajectory_class: str
    verdict: str
    source: str
    session_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    actions: List[str] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    failure: Optional[str] = None
    diagnosis: Optional[str] = None
    resolution: Optional[str] = None
    verification: Dict[str, Any] = field(default_factory=dict)
    outcome: str = ""
    final_answer: Optional[str] = None
    inefficient: bool = False
    provenance: Dict[str, Any] = field(default_factory=dict)
    eligible: bool = False
    eligibility_reasons: List[str] = field(default_factory=list)
    chat: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "trajectory_class": self.trajectory_class,
            "verdict": self.verdict,
            "source": self.source,
            "session_id": self.session_id,
            "context": self.context,
            "actions": self.actions,
            "steps": self.steps,
            "failure": self.failure,
            "diagnosis": self.diagnosis,
            "resolution": self.resolution,
            "verification": self.verification,
            "outcome": self.outcome,
            "final_answer": self.final_answer,
            "inefficient": self.inefficient,
            "provenance": self.provenance,
            "eligible": self.eligible,
            "eligibility_reasons": self.eligibility_reasons,
            "chat": self.chat,
        }


def _record_from_trajectory(traj: Dict[str, Any]) -> TrajectoryRecord:
    classification = traj.get("classification") or "PARTIAL"
    penalties = traj.get("penalties") or []
    record = TrajectoryRecord(
        goal=traj.get("goal") or "",
        trajectory_class=CLASS_MAP.get(classification, "partial"),
        verdict=traj.get("verdict") or "",
        source=traj.get("source") or "unspecified",
        session_id=traj.get("session_id"),
        context={
            "project_tag": _project_tag(traj),
            "model": traj.get("model") or (traj.get("verification")
                                           or {}).get("model"),
            "state": (traj.get("verification") or {}).get("state"),
        },
        actions=[str(a) for a in (traj.get("actions") or [])][:MAX_STEPS],
        steps=[s for s in (traj.get("steps") or [])[:MAX_STEPS]
               if isinstance(s, dict)],
        failure=traj.get("failure"),
        diagnosis=traj.get("diagnosis"),
        resolution=traj.get("resolution"),
        verification=traj.get("verification") or {},
        outcome=traj.get("outcome") or "",
        final_answer=traj.get("final_answer"),
        inefficient=any(p.get("dimension") == "efficiency"
                        for p in penalties if isinstance(p, dict)),
        provenance={
            "experience_id": traj.get("experience_id"),
            "overall_score": (traj.get("score") or {}).get("overall"),
        },
    )
    record.eligible, record.eligibility_reasons = _eligibility(record, traj)
    if record.eligible and _step_trainable(record):
        record.chat = _chat_record(record)
    return record


def _project_tag(traj: Dict[str, Any]) -> str:
    # the curated trajectory dict does not carry tags; the source and
    # session id are the reproducibility anchors we honestly have
    return str(traj.get("source") or "unspecified")


def _eligibility(record: TrajectoryRecord,
                 traj: Dict[str, Any]) -> "tuple[bool, List[str]]":
    """The dataset-separation gate: ACCEPT + SUCCESS + verification.
    S68: superseded-pattern demos (stale pre-S66 policy, kept in the
    store for provenance) are excluded with a reason."""
    reasons: List[str] = []
    if "superseded-pattern" in (traj.get("tags") or []):
        reasons.append("superseded-pattern: stale demo policy replaced "
                       "by the S66 explore-first corpus")
    if record.verdict != "ACCEPT":
        reasons.append(f"curation verdict {record.verdict}, not ACCEPT")
    if record.trajectory_class != "successful":
        reasons.append(f"class {record.trajectory_class}, not successful "
                       "(only verified success enters training data)")
    verification = record.verification or {}
    attempts = verification.get("attempts") or []
    has_evidence = bool(verification.get("ok")) or any(
        isinstance(a, dict) and a.get("ok") for a in attempts)
    if record.trajectory_class == "successful" and not has_evidence:
        reasons.append("no verification evidence recorded")
    return (not reasons, reasons)


def _step_trainable(record: TrajectoryRecord) -> bool:
    return bool(record.steps) and all(
        isinstance(step.get("args"), dict) for step in record.steps)


def format_tool_call(name: str, args: Dict[str, Any]) -> str:
    """The taught textual protocol: [TOOL: name(k="v", k2="v2")]."""
    parts = []
    for key, value in args.items():
        if isinstance(value, str):
            rendered = '"' + value.replace("\\", "\\\\").replace('"', '\\"') \
                + '"'
        elif isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = json.dumps(value, ensure_ascii=False)
        parts.append(f'{key}={rendered}')
    return f"[TOOL: {name}({', '.join(parts)})]"


def _chat_record(record: TrajectoryRecord) -> Dict[str, Any]:
    """SFT messages teaching the runtime's own tool protocol. The base
    prompt plus the [TOOL: ...] syntax section — the catalog is
    task-specific, the protocol is what the corpus teaches."""
    system = (build_system_prompt(tools=[], native_tools=False)
              + TOOL_PROTOCOL_PROMPT)
    messages: List[Dict[str, str]] = [{"role": "system", "content": system},
                                      {"role": "user",
                                       "content": record.goal}]
    for step in record.steps:
        messages.append({"role": "assistant",
                         "content": format_tool_call(step["tool"],
                                                     step["args"])})
        head = step.get("result_head") or ""
        observation = head if head else (
            "ok" if step.get("ok") else "no output captured")
        messages.append({"role": "user",
                         "content": observation[:MAX_TEXT_CHARS]})
    final = record.final_answer or (
        f"Completed: {record.goal[:MAX_TEXT_CHARS]}")
    messages.append({"role": "assistant", "content": final})
    return {"messages": messages,
            "metadata": {"session_id": record.session_id,
                         "source": record.source,
                         "model": record.context.get("model"),
                         "steps": len(record.steps)}}


def build_records(curated_dir=None) -> List[TrajectoryRecord]:
    """Parse the CURATED export into structured training records."""
    directory = Path(curated_dir or os.environ.get("QA_CURATED_DIR")
                     or "curated")
    path = directory / "trajectory.jsonl"
    if not path.exists():
        raise TrainingError(
            f"curated export not found: {path} — run 'qa curate' first")
    records: List[TrajectoryRecord] = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        if not raw.strip():
            continue
        traj = json.loads(raw)
        if traj.get("classification") == "INVALID":
            continue  # invalid data never becomes a training record
        records.append(_record_from_trajectory(traj))
    return records


def build_training(curated_dir=None, out_dir=None,
                   dry_run: bool = False) -> Dict[str, Any]:
    """Build the training corpus exports; report honestly."""
    records = build_records(curated_dir)
    eligible = [r for r in records if r.eligible]
    step_trainable = [r for r in eligible if r.chat is not None]
    report: Dict[str, Any] = {
        "trajectories": len(records),
        "classes": _tally(r.trajectory_class for r in records),
        "eligible": len(eligible),
        "step_trainable": len(step_trainable),
        "excluded": _tally(r.trajectory_class for r in records
                           if not r.eligible),
        "exclusion_reasons": _tally_reasons(records),
        "notes": _notes(records),
        "dry_run": dry_run,
    }
    if dry_run:
        return report
    out_path = Path(out_dir or os.environ.get("QA_TRAINING_DIR")
                    or DEFAULT_TRAINING_DIR)
    out_path.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_path / "trajectories.jsonl",
                 [r.to_dict() for r in records])
    _write_jsonl(out_path / "training.jsonl",
                 [r.chat for r in step_trainable])
    _write_json(out_path / "report.json", report)
    report["out_dir"] = str(out_path)
    return report


def _notes(records: List[TrajectoryRecord]) -> List[str]:
    notes = []
    if not any(r.eligible for r in records):
        notes.append("training.jsonl is empty: no verified-success "
                     "trajectories exist yet — populate via completed "
                     "benchmark/eval sessions (S48/S57 harnesses record "
                     "them automatically)")
    stepless = sum(1 for r in records if r.eligible and r.chat is None)
    if stepless:
        notes.append(f"{stepless} eligible record(s) carry no captured "
                     "step data (mined sessions have tool names only) — "
                     "structured but not step-trainable")
    notes.append("preference-optimization (DPO pair) export deferred: "
                 "no paired chosen/rejected data exists yet")
    return notes


def _tally(values) -> Dict[str, int]:
    tally: Dict[str, int] = {}
    for value in values:
        tally[value] = tally.get(value, 0) + 1
    return tally


def _tally_reasons(records: List[TrajectoryRecord]) -> Dict[str, int]:
    tally: Dict[str, int] = {}
    for record in records:
        if record.eligible:
            continue
        for reason in record.eligibility_reasons:
            tally[reason] = tally.get(reason, 0) + 1
    return tally


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    payload = "".join(
        json.dumps(row, ensure_ascii=False, default=str) + "\n"
        for row in rows)
    tmp = path.with_name(path.name + ".tmp-training")
    tmp.write_text(payload, encoding="utf-8", newline="")
    os.replace(tmp, path)


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp-training")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2),
                   encoding="utf-8", newline="")
    os.replace(tmp, path)


def format_report(report: Dict[str, Any]) -> str:
    lines = [
        "training dataset report:",
        f"  trajectories: {report['trajectories']} "
        f"(classes: {report['classes']})",
        f"  eligible (verified success): {report['eligible']}, "
        f"step-trainable: {report['step_trainable']}",
    ]
    if report.get("dry_run"):
        lines.append("  dry run: no exports written")
    else:
        lines.append(f"  exports: {report.get('out_dir', 'training/')}")
    for note in report["notes"]:
        lines.append(f"  note: {note}")
    return "\n".join(lines)
