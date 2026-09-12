# S68 — The Self-Improvement Loop (S65 realized as plumbing)

Status: scoped 2026-09-12. Roadmap: docs/ROADMAP-agentlite.md §S68.
The S67 verdict named the gen-3 levers with evidence; this sprint turns
them into standing commands so every future generation is one command
per stage, no manual surgery.

## Implement

### 1. Corpus hygiene (the S67 finding, automated)

- `mark_superseded_demos(store)`: scripted-demo records whose FIRST
  captured step is `read_file` carry the pre-S66 answer-reading policy
  — tagged `superseded-pattern` (precise identifier: every S66 script
  starts with list_directory or run_tests, never read_file).
- `training.py` excludes superseded-pattern records from the training
  export WITH A RECORDED REASON (they stay in the store for
  provenance; curation carries experience tags through to the
  trajectory export to make this possible).
- **Idempotent rebuild**: `build_corpus` marks superseded first, then
  skips any task whose normalized goal already has a successful
  non-superseded scripted-demo record — which means re-demoing EXACTLY
  the stale goals in the new style and nothing else. A second
  `qa build-corpus` run does zero new work; a run after new verdict-day
  failures re-demos only what hygiene demands.

### 2. The daily drip (real-data share grows over time)

`qa gemini-drip`: ONE real benchmark pass on the free-tier brain
(GEMINI_MODEL, default flash-lite), recorded into the store like any
run — ~7 requests of the 20/day budget. Quota/HTTP errors surface
honestly as exit 1. Run daily; curation picks it up on the next chain.

### 3. `qa verdict` (the one-command generation verdict)

- `qa verdict --models a,b,c [--tasks N] [--max-iterations K]
  [--ab-demos] [--store PATH]`: runs the N S57 evaluation tasks per
  model under the trained textual contract, records every run, prints
  per-task results and the `protocol_metrics` table (discovery-first,
  with-calls, guessed-path, success).
- `--ab-demos`: the ep0.5 dimension as a standard eval — the FIRST
  model's first task runs twice, with and without demonstration
  injection (S64 slice 2's context builder), results reported side by
  side.
- Backed by a testable `run_verdict(providers, ...)` (providers is a
  name → ModelProvider map, so tests inject fakes; the CLI maps model
  names to OllamaProviders).

### Verification

- Supersede marking, training exclusion, and idempotent rebuild are
  unit-tested (second rebuild = zero new runs; a stale goal gets
  re-demoed).
- The loop's end-to-end property: corpus rebuild → train (Colab, one
  human job) → import → `qa verdict` — no manual surgery anywhere.
- The gen-3 corpus rebuild lands as the live run: expect the 25 stale
  gen-1 records superseded and ~13-17 re-demos (the tasks whose goals
  they shared).

## Deliberately deferred

- Scheduling the daily drip (cron/automation) — a human choice, offered
  after the command exists.
- Full cross-product grinds including the slow models (recorded
  baselines stand; an overnight run can extend the table later).
