# S63 — Training Dataset Pipeline 2.0

Status: scoped 2026-09-11. Roadmap: docs/ROADMAP-agentlite.md §S63.
Builds the training corpus from S62's CURATED dataset — never raw
experience — and proves the chain end-to-end with the roadmap's literal
verification: a completed coding session exports as a valid structured
training record.

## Objective

> Structured trajectory export: goal, context, plan, action, observation,
> …, verification, outcome — with enough metadata to reproduce the task.
> Trajectory classes: successful / failed / recovered / human-corrected /
> unsafe / inefficient. Source: S62's CURATED dataset — never raw
> experience. (ROADMAP §S63)

The S55 finding gave this sprint its true purpose: the training data
teaches the textual tool protocol that general small models lack — the
baby-agent:ep1 distill (S64) consumes it.

## Design

### 1. Capture upgrade (session_learning, additive)

`session_to_experience` records two new bounded context fields:

- `tool_calls`: ordered `{tool, args, ok, result_head}` — paired from
  `session.tool_calls` × `session.observations` (args are the structured
  `ToolCall.arguments`; result heads cap at 200 chars; 50 calls max).
  This is the "enough metadata to reproduce the task" requirement.
- `final_answer`: the last text-only assistant message, 500 chars.

ADDITIVE only: `actions` stays tool names (S50 compatibility), and mined
experiences are untouched — they have no step data and never will
fabricate any.

### 2. The curated export carries the payload (curation, additive)

`CuratedTrajectory` gains `actions` / `failure` / `diagnosis` /
`resolution` / `verification` / `steps` (from context tool_calls) /
`final_answer`, so `trajectory.jsonl` is the full structured export the
training pipeline consumes. Redaction at export already covers the new
fields. "Never raw experience" is preserved: training reads ONLY the
`curated/` directory.

### 3. `qacompanion/agent/training.py` — the pipeline

- `TrajectoryRecord` (strict schema): goal, trajectory_class, source,
  session_id, context (directory / languages / model / state),
  actions, steps, failure, diagnosis, resolution, verification,
  outcome, final_answer, provenance (experience_id, curation score),
  eligible + eligibility_reasons, chat (the SFT record, when built).
- Class mapping: SUCCESS→successful, FAILED→failed, RECOVERED→recovered,
  HUMAN_CORRECTED→human-corrected, UNSAFE→unsafe, PARTIAL→partial;
  INVALID excluded entirely. `inefficient` is an orthogonal flag from
  S62's efficiency penalties, not a replacement class.
- **The eligibility gate (the permanent dataset-separation rule,
  enforced here):** a trajectory enters `training.jsonl` iff
  verdict == ACCEPT **and** classification == SUCCESS **and**
  verification evidence exists. Everything else is excluded WITH A
  RECORDED REASON — mined partials can never masquerade as verified
  success.
- Chat record (SFT messages), built only for eligible AND
  step-trainable (steps carry args) trajectories: system =
  `build_system_prompt` (the EXACT protocol the runtime teaches),
  user = goal, assistant turns = `[TOOL: name(k="v", ...)]` from the
  captured args, user turns = observation result heads, final assistant
  turn = final answer. No fabricated observations — records without
  step data stay trajectory-level.

### 4. Export + CLI

`QA_TRAINING_DIR` (default `training/`, gitignored), atomic writes:
`training.jsonl` (eligible chat records), `trajectories.jsonl` (all
structured records), `report.json` (per-class counts, eligible /
excluded with reasons, step-trainable count). CLI: `qa build-training
[--curated-dir DIR] [--out-dir DIR] [--dry-run]` — deliberately distinct
from S30's case-base `qa export-training`.

### Deliberately deferred

- Preference-optimization formats (DPO pairs) — no paired chosen /
  rejected data exists yet; noted honestly in the report.
- Full observation replay beyond bounded heads.
- Any fine-tuning itself — that is S64 (baby-agent:ep1), which also
  owns the honest before/after benchmark comparison.

## Pins (fixtures-first discipline)

- Source is the CURATED dataset only; raw experience is never read.
- Eligible = verified-success only; exclusions carry reasons.
- No fabricated steps or observations, ever.
- Deterministic and hermetic; no LLM in the pipeline.

## Verification

1. Hermetic end-to-end test: scripted-provider S48 benchmark run →
   `record_session` → `TrajectoryCurator` → `build_training` → exactly
   one eligible, step-trainable, valid chat record.
2. Live run: a real benchmark pass (the S55-proven
   gemini-3.1-flash-lite brain) → record → curate → build-training →
   the training set's first REAL record. If the network / quota fails,
   the report says so honestly and the sprint still lands with the
   hermetic proof.
