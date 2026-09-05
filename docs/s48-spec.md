# S48 — First Autonomous Coding Task: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S48. Builds on S31–S47. One slice, stdlib only, no CLI changes.

## Overview

The capstone of the foundation: a repeatable benchmark where the agent —
not the human — inspects a project, finds an intentional defect, fixes
it, and PROVES the fix by running the tests. The deliverable is the
**harness and honest metrics**; the live model's success is the smoke,
not the bar (a 1.5B model may fail — that is capability, recorded
honestly, and exactly what S55 routing will improve).

## Module layout

```text
qacompanion/agent/benchmark.py     # fixture task + harness + report
tests/test_agent_benchmark.py      # hermetic (FakeModelProvider)
```

## The benchmark task (fixture)

A tiny deterministic project written into a temp workspace:

```text
calculator.py        two functions; add() carries THE defect (a - b)
test_calculator.py   unittest suite: one failing test (add), one passing
README.md            describes the intent
```

Goal (natural language, no file names): "The tests in this project are
failing. Find the bug, fix it, and run the tests to verify they pass."

## Harness

```text
run_benchmark(provider, config=None, registry=None, events=None)
    -> BenchmarkReport
```

- Workspace: temp dir with the fixture; agent_registry's coding-relevant
  families (filesystem, execution, verification, code-intelligence,
  memory) — web/vision are deliberately absent (not needed; keeps the
  benchmark hermetic).
- Verification: an S41 VerificationPlan (single TEST step:
  `python -m unittest`, expect_exit 0) adapted via `plan_verifier` —
  the loop may only reach COMPLETED when the tests genuinely pass.
- Everything runs through the S32 pipeline with the S38 engine policy.

## BenchmarkReport (honest metrics, all recorded)

```text
task, goal, model, success, termination_reason,
iterations, duration_seconds,
files_changed, tool_calls, commands_run, tool_failures,
recovery_count (RECOVERING transitions), verification_results,
intervention_count   # 0 by construction — autonomous means no human
to_dict()
```

Metrics derive from the session + the S39 event stream (tool_failed /
recovery_started / tool_completed counts) — the harness observes what
the runtime already narrates.

## Testing strategy (tests/test_agent_benchmark.py)

All hermetic via FakeModelProvider + sys.executable:

- **Success path**: scripted inspect → run_tests (fail) → edit_file
  (correct fix) → run_tests (pass) → final answer. Assert
  report.success is True, the fixture file on disk is actually fixed,
  and the metrics count what happened (1 tool failure, ≥2 commands,
  files_changed, verification ok).
- **Failure path**: a model that never fixes anything → success False,
  honest termination_reason, metrics still complete.
- **Recovery accounting**: a run that fails verification once then
  recovers counts recovery_count = 1.
- Report serialization; fixture determinism (the defect is present
  before the run; the passing test passes).

## Live attempt (manual, after the suite is green)

qwen2.5-coder:1.5b via OllamaProvider on the same fixture. Whatever
happens is reported honestly — success or a documented capability gap
for S55's routing discussion.

Expected suite growth: 1288 → ~1295 OK.

## Exit criteria (from ROADMAP-agentlite.md §S48)

The benchmark records files changed, commands executed, failures,
recovery, verification, final result, and intervention count — no
manual command execution anywhere. Full suite green; preflight clean.
