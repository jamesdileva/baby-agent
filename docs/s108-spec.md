# S108 — Rung 7 demonstrations: exploration-from-observations
# (ep21's single training variable)

## Scope

The rung-7 task (explore-qa, S105) is built and its zero-shot wall is
measured: ep17 0/3 (two CPU-timeout DNFs after 19-25 iters of
thrash), ep11 0/3 — neither trained model can answer a docs-lookup
question even at a 25-iteration budget with the planted fact and the
root listing in context. This slice authors the DEMOS (ep21's single
variable) in the untrusted lane, same discipline as S107: the beats
are demonstrated more than once per run so they persist.

Ladder note (honesty): rung-3 graduation sits at 2 consecutive
pinned in-band readings (gen-20 seeds 42+43); the third is pending.
Rung-7 authoring proceeds now under the parallel-authoring proposal
recorded in the ladder (the QA axis is orthogonal to the repair
rungs — zero edits) and by explicit user direction.

## The lane fact-gate (mechanics)

The authoring lane runs demos through run_benchmark's DEFAULT
unittest verifier — explore-qa demos have no tests and could never
complete. build_agent_corpus gains: a demo may declare
`"fact_gate": [facts...]`, and the lane builds the same
containment verifier run_evaluation uses (all facts present in the
pending answer, case-insensitive; the loop only COMPLETEDs when the
gate passes). Additive; demos without fact_gate are unchanged.

## The drills (3, fresh fixtures, never the eval fixture)

All teach the same rule from S102.4's live forensics: **the listing
is the map — read it, open what it names, never guess a path that
isn't on it.** Per the S107 discipline, the beats repeat.

1. **explore-server** (S105-fixture shape, fresh copy): list → read
   README (does not answer — the live trap) → read docs/api.md (the
   decoy — does not answer) → **list AGAIN (the persistence beat:
   back to the map, not guessing)** → read docs/running.md → final
   quotes `python -m serverctl --port 8765` and names
   docs/running.md. fact_gate: both planted strings.
2. **explore-config** (fresh fixture): a settings question whose
   answer is planted in docs/configuration.md (`request_timeout = 45`,
   `max_retries = 3`); README mentions "see docs" only. list → read
   README → list again → read the config doc → final quotes BOTH
   settings with the source file.
3. **explore-recovery** (fresh fixture): the ANTI-GUESS beat — the
   demonstrator makes ONE guessed read (`src/main.py`, a path not in
   the listing — the exact live failure), is honestly rejected, and
   corrects by returning to the listing and opening docs/testing.md,
   whose planted command (`python -m coverage run -m unittest
   --branch`) the final quotes. One guess, one correction — never a
   second guess.

## Honest bounds

- The drills add answer-QA demonstrations only; no existing demo,
  task, or verifier changes. ep21's only deliberate variable is this
  batch (SRFT lane and the 2:1 real cap behave as built).
- Substring containment cannot judge answer QUALITY — it judges
  grounding (the planted facts are arbitrary by construction, so
  guessing is ruled out).
- Rung 8 (long-horizon persistence: 30-100+ step endurance, drift
  metrics, raised budget) is a SEPARATE proposed rung — recorded in
  the ladder this slice — not part of explore-qa.

## Test plan

1. Validator: all three demos pass (discovery-first, read_file
   present, one final naming a touched file, goal identity).
2. Lane fact-gate: a demo with fact_gate runs under the containment
   verifier (hermetic test); demos without one keep the unittest
   plan (existing pins unchanged).
3. Lane: all three pass the REAL gate, tagged agent-authored +
   corpus-v8; batch count 26 -> 29.
4. Corpus rebuild: deliberate pool +3; export carries the drills;
   rebuild stays idempotent.
