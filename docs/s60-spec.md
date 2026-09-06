# S60 — Synthetic Curriculum: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S60. Builds on S31–S59. One slice, stdlib only, no CLI changes.

## Overview

Systematically GENERATED learning tasks instead of random ones —
answering "what should Baby-Agent learn?" before "how do we train it?"
Tasks are DATA: deterministic templates × category × difficulty level
× seeded variation, with failure injection built into the fixtures.

**Composition over duplication:** curriculum tasks bridge directly to
the S57 harness (`as_eval_task()`), so the same run_evaluation that
compared models in S55 runs curricula unchanged.

## Module layout

```text
qacompanion/agent/curriculum.py    # CurriculumTask + generator + mastery
tests/test_agent_curriculum.py
```

## CurriculumTask (strict schema)

```text
task_id (C-NNNN), category (bug_fix | feature_add | testing | refactor |
build_repair | dependency | regression | docs), level (1..8),
difficulty {reasoning: 1..5, steps: n, tools_required: n},
goal (natural language, names no files), files {name: content},
verify_command, skills [names], known_failure_modes [strings],
seed (int — regeneration is byte-identical)
```

## Templates (failure injection by construction)

Eight category templates, each producing a small Python module +
unittest file where the WORK is the fix/feature/test:

```text
bug_fix       module contains a deliberate defect (variant: off-by-one,
              wrong operator, wrong key, missing return) — tests fail
              until fixed
feature_add   tests written for a function that doesn't exist yet —
              task is to implement it
testing       module is correct; the task is to WRITE the tests
              (verify: the new test file exists and passes)
refactor      behavior-preserving rename with tests pinning behavior
build_repair  module with a syntax error — fix until the suite imports
dependency    module imports a missing local helper — create it
regression    a fixed bug with a test that must be added to pin it
docs          module missing docstrings — add them (verified by
              __doc__ checks in the verify step)
```

Difficulty scales with level: subtler defects (wrong algorithm vs
wrong operator), more functions, larger modules. Known failure modes
are DECLARED per task (the roadmap's failure-injection requirement —
the curriculum states what the agent will hit).

## SyntheticCurriculum (generator)

- Deterministic: `random.Random(seed)` — same seed, same curriculum,
  byte-identical regeneration.
- `generate(count, level=None, categories=None)`: round-robins
  categories, scales level, unique task ids, **dedupe by normalized
  goal** (repeats detected and regenerated/skipped, per the roadmap's
  repeated-task reduction).
- `coverage()` → {skill: count} — the coverage matrix preventing
  dataset bias.

## MasteryTracker (adaptive)

- `record(skill, outcome)` per attempt; per-skill success streaks and
  failure counts.
- `working_level(skill)`: success streak ≥ 3 → level+1 (cap 8);
  2 consecutive failures → level−1 (floor 1).
- `recommend(skills, level_range)` → the least-covered skill in range —
  the adaptive loop the roadmap requires.

## S57 bridge

`CurriculumTask.as_eval_task()` → S57 `EvalTask`, so
`run_evaluation(models, tasks=[t.as_eval_task() ...])` runs curricula
through the identical harness/verifier machinery. The curriculum
never re-implements verification.

## Testing strategy (tests/test_agent_curriculum.py)

- Task schema validation; deterministic regeneration (same seed →
  identical tasks); unique ids; dedupe of repeated goals.
- Templates: every category generates a runnable fixture; bug_fix
  fixtures CONTAIN the declared defect (tests fail pre-fix — asserted
  by running unittest via subprocess once); difficulty scales with
  level (bigger modules at higher levels).
- Coverage matrix counts; mastery adaptation (streak → level up,
  failures → level down); recommend picks least-covered.
- S57 bridge: as_eval_task runs through run_evaluation with the
  AutoFix fake (1 task, fake provider) → success True.
- Registry count unchanged (curriculum is harness-level).

Expected suite growth: 1445 → ~1460 OK.

## Exit criteria (from ROADMAP-agentlite.md §S60)

Generated tasks are valid, seeded, deduped, difficulty-scaled,
coverage-tracked, mastery-adaptive, and runnable through the S57
harness. Full suite green; preflight clean.
