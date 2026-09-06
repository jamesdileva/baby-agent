# S58 — Failure Recovery & Escalation 2.0: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S58. Builds on S31–S57 (S49 brain advice, S55 router escalation, S56
context builder). One slice, stdlib only, no CLI changes.

## Overview

Failure becomes a controlled state machine. Today the loop feeds a
failed verification back and hopes — the "indefinite looping" the
roadmap calls out. S58 adds deliberate classification, no-progress
detection, and strategy selection: retry with advice → alternate
approach → environment check → escalate model → ask user → terminate,
in that order of desperation, each transition driven by counted
evidence rather than hope.

## Module layout

```text
qacompanion/agent/recovery.py    # tracker + policy state machine
qacompanion/agent/loop.py        # additive wiring (recovery + escalation swap)
tests/test_agent_recovery.py
```

## Failure tracking

`FailureTracker.record(iteration, kind, signature)` — signature is the
S2-derived first-error-line (qa_brain.derive_signature), so "same
failure" is deterministic, not vibes. `no_progress(threshold)` → True
when the SAME signature repeated `threshold` consecutive times
(default 3). `report()` for dashboards.

## RecoveryPolicy (the state machine)

```text
RecoveryPolicy(max_same_failure=3, max_alternates=2)
    .decide(context) -> Decision(strategy, reason)

context: {kind: tool|verification|provider, repeat_count,
          failure_count, iteration, max_iterations,
          escalation_available: bool}

Strategy ladder (desperation order):
    tool failure, repeats < 3      -> RETRY_WITH_ADVICE (S49 already
                                      injected the diagnosis)
    repeats >= 3                   -> ALTERNATE_APPROACH ("your previous
                                      approach failed N times — change
                                      strategy", injected as instruction)
    verification, repeats < 3      -> ALTERNATE_APPROACH
    alternates exhausted (>= 2)    -> ESCALATE_MODEL (S55 router's
                                      escalation tier) when available,
                                      else TERMINATE
    environment-class failure      -> ENVIRONMENT_CHECK (run the S40
                                      summary before another attempt)
    iterations exhausted           -> TERMINATE (existing reasons)
    ASK_USER                       -> terminate, reason "needs human
                                      decision" (the dashboard can
                                      restart with new instructions)
```

## Loop wiring (additive)

`AgentLoop(recovery=None, escalation_factory=None)`:

- tool failures: after S49 advice, `no_progress` triggers the policy —
  ALTERNATE_APPROACH/ENVIRONMENT_CHECK inject instructions;
  ESCALATE_MODEL swaps the loop's provider mid-run (factory from the
  S55 router's escalation tier) and emits `model_escalated`; ASK_USER
  and TERMINATE finish the session with honest reasons.
- verification failures: the RECOVERING path consults the same policy
  — alternate-approach instructions replace the bare "verification
  failed, try again" after repeats.
- `model_escalated` event (S39 vocabulary, additive).

## Testing strategy (tests/test_agent_recovery.py)

- Tracker: signature stability, consecutive no-progress threshold,
  report.
- Policy: full ladder mapping — each strategy reachable, desperation
  order respected, escalation-available vs unavailable branches.
- Loop: repeated identical tool failure → alternate-approach
  instruction injected at exactly the threshold turn; escalation swap
  fires with a second provider (fake) and the session completes on
  the escalated brain; ASK_USER terminates; environment-class injects
  the check.
- Existing loop tests unmodified (recovery=None default).

Expected suite growth: 1422 → ~1440 OK.

## Exit criteria (from ROADMAP-agentlite.md §S58)

Several failure classes → correct recovery strategy each time;
escalation fires on trigger; runaway looping terminates with honest
reasons. Full suite green; preflight clean.
