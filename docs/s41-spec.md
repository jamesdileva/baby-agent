# S41 — Verification Engine: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S41. Builds on S31–S40. One slice, stdlib only, no CLI changes.

## Overview

Verification becomes a first-class subsystem: named plans of sequential
steps, each executed through the S35 command machinery inside the
workspace, aggregated into a report the model can read and act on.
"I changed the code" ≠ "I proved the requested behavior works."

**Category scoping, documented:** BUILD / TEST / LINT / TYPECHECK / RUNTIME
/ HEALTHCHECK ship as command-step categories. GOAL stays the S37 verifier
seam (custom predicates — the engine does not replace it, it feeds it:
`plan_verifier(plan)` adapts a plan into the loop's verifier). REGRESSION
is semantically a TEST plan rerun (no separate machinery). VISUAL waits
for S44 vision.

## Module layout

```text
qacompanion/agent/verification.py    # plan model + runner + plan_verifier
qacompanion/agent/fs_tools.py        # agent_registry wiring (22 → 23)
tests/test_agent_verification.py
```

## Plan model (data-driven)

```text
VerificationStep (dataclass)
    name              str, required
    category          BUILD|TEST|LINT|TYPECHECK|RUNTIME|HEALTHCHECK
    command           shell line, run at the WORKSPACE ROOT only (no per-
                      step cwd — the root is the S33-resolved boundary;
                      per-step cwd can come later with a policy resolve)
    expect_exit       int, default 0
    must_contain      substring required in stdout, optional
    must_not_contain  substring forbidden in stdout+stderr, optional
    optional          bool, default False (failure doesn't fail the plan)

VerificationPlan
    name, steps, stop_on_first_failure=True
    from_dict(data)   strict validation (unknown category, missing
                      name/command, empty steps -> ValueError)
    run(workspace, timeout_seconds=120) -> VerificationReport
```

Execution: sequential; each step runs via `execution.execute_command`
(so timeout, tree-kill, output caps, and Z-stamps all apply); on failure
of a non-optional step with `stop_on_first_failure`, remaining steps are
recorded as skipped (ok=None) and not executed.

```text
VerificationResult   name, category, ok (True/False/None=skipped),
                     exit_code, stdout, stderr, duration_ms
VerificationReport   plan_name, ok, steps[], to_dict() JSON-ready
```

## The tool

`run_verification` (category "verification", EXECUTION side effect,
requires_workspace=True) — the roadmap's inventory entry: the MODEL can
request verification of its own work. Argument: `plan` (object, the same
shape as `VerificationPlan.from_dict`). Returns the report JSON. Commands
inside the plan run through the same S38-gated pipeline as every other
tool (no new escalation — the model could already run these commands via
run_command).

`plan_verifier(plan, workspace) -> callable(session) -> (ok, detail)`
adapts a plan into the S37 loop verifier: runs the plan, returns the
report summary as detail. `agent_registry()` grows to 23 tools.

## Testing strategy (tests/test_agent_verification.py)

- Plan model: from_dict round trip; validation rejections (unknown
  category, missing name/command, no steps, bad types).
- Runner (hermetic, sys.executable commands): all-pass plan; failing step
  (exit code) → report not ok + subsequent steps skipped with ok=None;
  must_contain satisfied/violated; must_not_contain violation; optional
  step failure → plan still ok; expect_exit nonzero (a command EXPECTED
  to fail passes the step).
- Report: to_dict JSON-serializable, ok semantics.
- Tool: registration (EXECUTION, workspace-gated); through-registry run
  of a plan that checks a file written beforehand.
- Loop integration: plan_verifier passing → COMPLETED; failing plan →
  FAILED "verification failed after N attempts" (max_iterations=1);
  recovery path (failing plan, then model fixes the file, then plan
  passes → COMPLETED via RECOVERING).

Expected suite growth: 1143 → ~1165 OK.

## Exit criteria (from ROADMAP-agentlite.md §S41)

Benchmark projects where build passes but tests fail, tests pass but
runtime fails — the engine distinguishes the states via per-step results.
The model can request verification through the registry; the loop can be
driven by a plan-based verifier. Full suite green; preflight clean.
