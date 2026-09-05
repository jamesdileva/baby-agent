# S50 — Learning From Agent Sessions: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S50 (including the human-directed curation backlog notes). Builds on
S31–S49. One slice, stdlib only, no CLI changes.

## Overview

Sessions become experience. Three pieces:

1. **Capture** — an `AgentSession` (S31) is converted into an `Experience`
   (S47) with a mechanically honest outcome classification, and recorded
   by the benchmark harness at run end (the loop itself stays pure —
   hermeticity first; recording is a harness concern).
2. **Curate** — the `Curator` cleans the mined corpus (S47.1) by rule:
   greeting pings out, the ×321 resume pattern promoted into a SKILL
   seed file and removed from the episodic store, everything else kept.
   Never silent: every run returns kept/removed counts by rule.
3. **Enrich** — the opencode miner learns to detect error→patch patterns
   inside marathon sessions, filling diagnosis/resolution on the
   experiences it records (conservative: only when an error-shaped tool
   output is followed by a later patch part in the same session).

## Module layout

```text
qacompanion/agent/session_learning.py   # capture + classification + curator
qacompanion/agent/opencode_mine.py      # + error->patch enrichment
qacompanion/agent/benchmark.py          # + session recording at run end
skills/agent/resume_interrupted_task.json  # skill SEED (S51 runtime consumes)
tests/test_agent_session_learning.py
```

## Classification (mechanical, from observable facts)

```text
COMPLETED + first verification attempt ok        -> success
COMPLETED + later verification attempt ok        -> recovered
FAILED                                           -> failed
CANCELLED                                        -> partial
```

`human_corrected` / `unsafe` stay undocumented-in-code until
intervention tracking exists (roadmap-honest: they need observability
that doesn't exist yet). The QA brain's injected advice (S49) is
harvested from session messages into diagnosis/resolution when present.

## Session -> Experience

goal = session goal; actions = ordered tool names (+counts in context);
context = {iterations, state, workspace_root, model}; failure = first
observation error; diagnosis/resolution = qa_memory advice extracted
from system messages; verification = session.verification_results;
outcome = classified; tags = ["autonomous-session", model];
project metadata from the workspace.

## Curator rules (this sprint's backlog delivery)

```text
greeting-ping      normalized goal in greeting vocabulary (hello/hi/hey/
                   helo/yo/...) or <= 2 tokens -> REMOVE
resume-pattern     goal matches the interrupted/continue pattern
                   -> REMOVE from episodic store; the canonical skill
                   seed file represents it (one skill beats 321 copies)
everything else    KEEP
```

The resume skill seed follows the S51 skill schema (name, goal,
description, required_tools, preconditions, procedure, verification,
failure_modes, examples, confidence) as DATA — the S51 runtime will
load it; nothing reads it yet, documented as such.

## Miner enrichment

`mine_session` gains error→patch correlation: collect tool outputs whose
text matches error shapes (`Traceback`, `Error`, `FAIL`, `error:`) and
later `patch` parts in the same session; when an error precedes a patch,
set failure (first error line) and resolution ("fix applied via patch;
<files>") on the experience. Re-import is reinforcement-safe: the store
updates diagnosis/resolution on goal matches without duplicating rows.

## Testing strategy (tests/test_agent_session_learning.py)

- Classification matrix (all four mechanical outcomes).
- session_to_experience: qa_memory harvest, actions, metadata;
  record_session persists.
- Curator: greeting removal; resume-pattern promotion (removed + counts);
  keep-rest; stats honesty; idempotent second run.
- Miner enrichment: fixture DB session with error output followed by a
  patch part → experience carries failure/resolution; error without
  patch → no resolution claim.
- Benchmark wiring: a run with an experience_store records exactly one
  experience whose outcome matches the run (success / recovered paths).

Expected suite growth: 1306 → ~1320 OK.

## Live operations (after the suite is green)

1. Curate the real experience.jsonl: expect the 99 to shrink (greetings,
   resume pattern out), with honest counts.
2. Re-run the opencode import: reinforcement enriches existing records
   with diagnosis/resolution where the new extractor found error→patch
   pairs.

## Exit criteria (from ROADMAP-agentlite.md §S50)

Run a task with an unknown failure, recover, verify a new
experience/case exists with signature, diagnosis, resolution,
verification, timestamp — the benchmark's recovered-path test proves the
mechanism; the live curation delivers the clean corpus. Full suite
green; preflight clean.
