# S103 — Recovery ladder: counted evidence for interleaved thrash

## Problem (live evidence, 2026-09-28)

A dashboard session ("how do I start this app? it should be in /docs",
ep11-q4) failed 6 of 10 iterations and was cancelled by the user. The
S58 recovery ladder never visibly engaged. Three stacked defects:

- **D1 — tool-path recovery is silent.** The loop consults the state
  machine on every failed tool call (loop.py `_apply_recovery`), but
  only the verification-failure path emits `recovery_started`. Decisions
  on the tool path (advice/alternate/environment) happen invisibly.
- **D2 — environment decisions loop uncounted** (the S98 follow-up).
  "file not found" matches `ENVIRONMENT_MARKERS`, so every failure
  returned ENVIRONMENT_CHECK — which injects a message but advances
  nothing (`alternate_count` only moves on ALTERNATE_APPROACH). The
  ladder can sit on its first rung forever.
- **D3 — interleaved thrash never trips the streak.** `no_progress`
  requires the SAME signature 3x CONSECUTIVE. The observed model cycled
  three different failing paths (`src/main.py`, `app/__init__.py`,
  `list src`), so no signature ever hit 3 back-to-back. Session-level
  non-progress (6 failures / 10 iterations) was invisible to the
  tracker.

## Design

### D3 — cycling detection (FailureTracker)

The tracker gains success awareness. The loop reports successful tool
results via a new `record_success()`.

- New tracker state: `consec_fail_steps` — failing STEPS in a row (a
  successful tool result resets it; a recorded failure increments it).
- New query `cycling(window=5, min_distinct=2) -> bool`: True when the
  current failing streak is >= `window` steps AND the failures inside
  the streak carry >= `min_distinct` distinct signatures.
- Rationale for the constants: the observed session's thrash tail was 5
  consecutive failing steps with 3 distinct signatures — window 5 /
  distinct 2 fires there and at anything worse. Legitimate exploration
  (guessed reads punctuated by successful reads/lists) resets the
  streak constantly and does not fire. Identical-retry thrash remains
  covered by the existing consecutive_same rule, which fires earlier.
- `record_success()` is part of the tracker contract; recovery=None
  loops never call it (behavior unchanged).

### D2 — environment decisions become counted (RecoveryStateMachine)

- The state machine counts consecutive decisions that land on
  ENVIRONMENT_CHECK (`environment_repeat`).
- `RecoveryPolicy.decide` gains `environment_repeat: int = 0` and
  `cycling: bool = False` (keyword, defaulted — backward compatible).
  Routing order becomes:
  1. no iterations left → TERMINATE (unchanged)
  2. environment-matched AND environment_repeat < 2 → ENVIRONMENT_CHECK
     (unchanged for first occurrence)
  3. environment-matched AND environment_repeat >= 2 → falls through to
     the repeat/cycling ladder (the S40 summary was already requested;
     more of the same is not a strategy)
  4. repeat_count >= max_same_failure → alternate/escalate/ask-user
     (unchanged)
  5. cycling → ALTERNATE_APPROACH if alternates remain, else the
     escalate/ask-user rungs (the cycling form of "change strategy")
  6. verification → ALTERNATE_APPROACH (unchanged)
  7. default → RETRY_WITH_ADVICE (unchanged)

### D1 — make tool-path decisions visible (loop)

- Every tool-path decision that is NOT a no-op (RETRY_WITH_ADVICE with
  no advice is the only no-op) emits `recovery_started` with
  `strategy` and `reason` payloads. The feed already labels the type;
  S102.4's renderEvent gains the strategy/reason rendering.
- The verification path's existing event gains the same payloads
  (additive keys).

## Honest bounds

- The ladder still never de-escalates; cycling only makes the EXISTING
  ladder engage earlier. ASK_USER still terminates honestly.
- A session alternating failures with successes never reaches the
  window — by design: that is exploration, and punishing it would
  regress the guessed-path behavior the corpus deliberately teaches.
- Constants (window 5, distinct 2, environment_repeat 2) are policy
  fields, documented and test-pinned, tunable without re-design.

## Test plan

1. cycling fires on the exact observed pattern (5 straight failing
   steps, 3 distinct signatures) — regression test named after the
   failure mode (`interleaved_thrash`).
2. cycling does NOT fire when successes interleave (exploration shape).
3. cycling does not fire on < window streaks (near-miss).
4. environment decisions advance after 2 (D2): third decision for the
   same env-class failure is no longer ENVIRONMENT_CHECK.
5. first environment decision unchanged (existing behavior pinned).
6. loop emits `recovery_started` on an actionable tool-path decision
   with strategy/reason payloads; silent for no-op decisions.
7. `record_success()` resets the streak; recovery=None loop unchanged
   (existing suite remains green).
