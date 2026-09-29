# S105 — Rung 7 explore-qa: the eval task, built MEASUREMENT-FIRST

## Scope

Rung 7 of the capability ladder (observation-grounded exploration,
proposed S103): answer a question about a workspace from what it
READS, never from guessed paths. Per the anti-flaky protocol the
DEMOS stay gated (they would be ep19's variable); this slice ships
the deterministic EVAL TASK only and baselines the current champions
zero-shot — the same recipe S93 used for indirect.

Motivating evidence: the live docs-question sessions (S102.4) — the
model guessed `src/main.py` x3 while the root listing sat unread in
its context, and later anchored on the README's old Usage block while
the answer sat in the run section it had also read.

## The task

`explore-qa`, appended AFTER defect-fix-indirect in `default_tasks()`
so `--tasks 5` keeps the pinned ladder set byte-stable and
`--tasks 6` adds rung 7.

- **Fixture** (no tests — the fact gate replaces the unittest gate):
  - `docs/running.md` — the planted fact: the server starts with
    `python -m serverctl --port 8765`.
  - `docs/api.md` — a decoy doc (real content, no fact).
  - `README.md` — plausible project blurb, NO run instructions (the
    live finding: the model must go PAST the README into the listing
    and into docs/).
- **Goal**: "How do you start this project's server? I think there
  are docs in here somewhere — find the answer and tell me the exact
  command."
- **The fact gate** (deterministic, no LLM judge): the session's
  final answer must contain `python -m serverctl` AND `8765`
  (case-insensitive substring). Two facts make lucky containment
  implausible while keeping the check exact.

## Mechanics

- `EvalTask` gains `fact_gate: Optional[List[str]] = None`.
- `run_benchmark` gains `verifier=None` (additive): when a caller
  supplies a verifier callable it REPLACES the internal unittest plan
  (explore-qa has no tests; the default plan would make the task
  impossible). Existing callers unchanged.
- `run_evaluation` builds the fact-gate verifier for tasks that
  declare one: all facts contained in `session.final_result` -> pass;
  otherwise the loop's normal verification-failure path applies
  (recover, retry, honest termination).

## Baseline (the measurement this slice exists for)

Zero-shot, n=3, temp 0 / seed 42, ep17-q4 + ep11-q4 (6 runs): rates
recorded in the ladder ledger's rung-7 row. Prediction from the live
sessions: low (the trained chains are defect-fix shaped; nothing
teaches open-book workspace QA). The baseline is what ep19's demos
must move.

## Honest bounds

- Substring containment cannot judge answer QUALITY — it judges
  evidence-grounding (did the answer carry the planted fact). A model
  that guesses the fact string without reading passes only if it
  guesses an exact `--port 8765`-shaped fact; the port is arbitrary
  by construction, so guessing is effectively ruled out.
- The task is eval-only; no demos are authored in this slice and the
  corpus is untouched.

## Test plan

1. Fixture: explore-qa writes the docs tree; no test files; fact
   strings present in docs/running.md only.
2. Verifier wiring: hermetic scripted provider whose final contains
   both facts -> COMPLETED; final missing a fact -> verification
   failed (loop recovers/terminates honestly, never falsely
   COMPLETED).
3. `--tasks 5` set is byte-identical to the pinned ladder (the first
   five task names unchanged); explore-qa is sixth.
4. run_benchmark default behavior unchanged when verifier=None
   (existing suite stays green).
