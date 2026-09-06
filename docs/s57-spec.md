# S57 — Agent Evaluation Harness: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S57. Builds on S31–S56. One slice, stdlib only, no CLI changes.

## Overview

Improvement becomes measurable, not anecdotal. S57 wraps the S48
single-task benchmark in a multi-task, multi-model evaluation suite:
deterministic fixtures, aggregated metrics, persisted run records, and
a compare() that flags regressions between two runs — the tool the
S55 bake-off needed hand-rolled.

## Module layout

```text
qacompanion/agent/evaluation.py    # tasks, runner, report, compare
tests/test_agent_evaluation.py
```

## The task suite (three deterministic defect fixtures)

```text
defect-fix-calculator     add() subtracts (S48 fixture)
defect-fix-strings        reverse() returns the input unchanged
defect-fix-json           parse_config() ignores the nested key
```

Each: fixture files + natural-language goal (no file names) + S41
verification plan (unittest must pass). Deterministic, hermetic,
idempotent.

## The runner

```text
run_evaluation(models: {name: provider_factory}, tasks=[...],
               store=None, events=None) -> EvalReport
```

- Runs the full cross product: every model × every task via the S48
  `run_benchmark` (lean catalog, experience recording — everything
  from S50/S55 applies).
- **EvalReport**: per-(model, task) `BenchmarkReport`s plus aggregates
  per model: success_rate, avg_iterations, avg_duration_seconds,
  total_tool_calls, total_tool_failures, recovery counts.
- `to_dict()` / `save(path)` (JSON, atomic) / `load(path)` — run
  records persist under `eval-runs/` (env: `QA_EVAL_DIR`), gitignored
  runtime artifacts.
- **compare(a, b) -> dict**: per-model deltas (success rate change,
  avg iteration change) plus a `regressions` list — any (model, task)
  whose success flipped True→False between runs. Honest both ways:
  improvements are listed too.

Follow-up (not this slice): token usage metrics (the bridge currently
discards Ollama's eval counts — noted).

## Testing strategy (tests/test_agent_evaluation.py)

- Fixtures: all three deterministic; defect present pre-run; goals
  name no files.
- Runner: fake providers scripted per task — all-pass run produces a
  1.0 success rate; a failing task flips the aggregate; per-model
  separation; experience recorded per run (S50).
- Aggregation math: success_rate, averages — exact assertions.
- Persistence: save/load round trip; corrupt file structured error.
- compare: improvement + regression detection (True→False flagged).
- Registry count unchanged (65 — the harness composes existing tools).

Expected suite growth: 1411 → ~1425 OK.

## Exit criteria (from ROADMAP-agentlite.md §S57)

Identical benchmark suites against two versions produce comparable
reports with regression flags — provable hermetically with fake
providers. Full suite green; preflight clean.
