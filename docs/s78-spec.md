# S78 — Gen-10: Direct Teaching at Volume + the Capability Ladder

Status: scoped 2026-09-25. Three pieces: a correction (SRFT lane
filter), a benchmark addition (the capability ladder grows), and gen-10's
one training variable (volume-teach the json synthesis directly).

## Base-model decision (recorded)

Staying at Qwen2.5-Coder-3B. Rationale: a bigger base without our
training is just another model; with our training it destroys the
measurement (a 27B may already pass the eval zero-shot — the ep0
lesson), and 27B-class weights cannot drive 12-iteration agent loops
on the available hardware at usable speeds. The program's contribution
is the data, gates, and harness — base-agnostic by design; every
generation re-runs on any base when hardware allows. Fine-tuning IS
making our own model: the weights are changed by our data. From-scratch
pretraining (teaching language itself) is 5-9 orders of magnitude
beyond free Colab and out of scope permanently.

## 1. SRFT lane filter (the gen-9 correction)

`_srft_prefix_steps` now keeps only `ok=True` steps within the prefix —
failed reads in the mined prefixes taught path-guessing (guessed_path
0.78 → 1.22 in gen-9). The productive chain is reads that SUCCEEDED.

## 2. The capability ladder: cascade eval task (benchmark, not training)

Calculator is solved (3/3). The ladder grows: **defect-fix-cascade** —
a module with TWO declared defects (`add` subtracts, `multiply` adds);
tests fail on both, and fixing one only reveals the other. Requires the
diagnosis chain to run TWICE with a rerun between — the persistence
step up from single-defect tasks. Deterministic fixture, S41 gate,
added to `default_tasks()` so every future verdict measures it.

## 3. Volume-teaching the synthesis (gen-10's training variable)

The json wall's evidence: run 3 in gen-9's verdict executed the whole
chain and still couldn't compose the chained-`.get` expression. More
demonstrations of the SAME shape is "teaching it directly": the
nested_lookup category grows from 4 hand-written variants to **24
deterministic pool-generated variants** (section names, key names,
depths 1-2, defaults — all from fixed pools, no randomness), each
verified through the real loop. corpus-v8 → idempotent rebuild.

## Verification

- Cascade task: fixture contains both defects (subprocess: tests fail
  pre-fix, one-fix-still-fails, both-fixes-pass); registered in
  default_tasks.
- SRFT filter test: prefixes contain no ok=False steps.
- Volume test: the pool generates 24 distinct variants; spot drills
  verify through the real loop; corpus-v8 rebuild all-green.
- The human's Colab job → ep10 → `qa verdict --models
  baby-agent:ep10,baby-agent:ep9` on the 4-task ladder: calculator
  1.0 is the regression guard, cascade is the new rung, json shows
  whether volume teaching moved the wall.
