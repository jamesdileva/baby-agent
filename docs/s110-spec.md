# S110 — Answer-QA corpus surgery: kill the opening-guess teacher,
# teach read-then-ANSWER-immediately (ep23's single variable)

## Problem (gen-22 forensics, two named shapes)

1. **The verification ritual on a no-test question.** The S109 seam
   fix TRANSFERRED: the recorded explore-qa failure shows the tempted
   calls rejected and docs/running.md READ — the planted fact in
   context. Then `run_tests` x6 to max-iterations: the defect-fix
   verification ritual (0 tests = vacuous pass) fired instead of the
   answer. Three answer-QA demos are drowned by ~150 repair demos
   that all end run-tests-then-answer.
2. **The opening-guess teacher.** guessed_path 0.4444 (8/18 runs) vs
   ep21's 0.0, and cascade regressed 0/3 (quiet 3-4-failure runs).
   The S108/S109 recovery drills demonstrate a guessed read as the
   demo's OPENING action — and ep22 imitated it. The S100 lesson in a
   new form: a failure demonstrated early gets imitated early.
   Recovery beats belong MID-CHAIN, after a productive pattern is
   established (the shape that produced the cascade/indirect gains).

## Design — ep23's ONE variable: the answer-QA corpus shape

### Part 1 — supersede the opening-guess demonstrations

New deterministic rule in the store repair: an agent-authored record
whose FIRST captured read_file step FAILED (ok=False) demonstrates
path-guessing as an opening move -> superseded-pattern. Exactly two
records match (the S108 and S109 recovery drills); every other drill's
first read succeeds (the first failures elsewhere are non-read tool
calls). The two demo dicts are REMOVED from the lane (otherwise the
lane would re-record them under fresh goals). Their replacement:
- **testing-v3**: the coverage question, with BOTH live wandering
  shapes corrected MID-CHAIN — list → README → the seam beat
  (code_references rejected) → listing → one wrong-turn read
  (guessed module, rejected) → back to the listing → docs/testing.md
  → answer IMMEDIATELY (no run_tests).

### Part 2 — answer-QA volume (read-then-ANSWER-immediately)

Five NEW drills on fresh fixtures (license, deploy, cli-flags,
logging, changelog questions), each ending read-then-answer with NO
run_tests anywhere in the script — several explicitly narrating "no
test run was needed; the question is answered by the doc." Beats
varied per the S107/S108/S109 lessons: pure read-then-answer, one
decoy-doc persistence beat, the seam beat. No opening guessed reads
ANYWHERE in the batch.

## Honest bounds

- Superseding 2 records + 6 new: deliberate pool moves ~154 -> ~158;
  the 2:1 real cap scales automatically. Nothing else changes; ep23's
  only deliberate variable is this answer-QA shape correction.
- Cascade's 0/3 is one quiet reading — its re-check rides ep23's
  verdict (no cascade demos in this batch; if it stays down, the
  dilution/cascade forensics becomes its own slice).
- The 5:1 repair-to-answer demo ratio moves to roughly 2.5:1 —
  still repair-dominated by design (the program's subject is coding).

## Test plan

1. Repair rule: a record with a failing first read gets superseded;
   records whose first read succeeds are untouched; idempotent.
2. Validator + lane: all six demos pass the real fact-gate; batch
   count 32 -> 36.
3. Export: the two opening-guess goals ABSENT, the new drills
   present; rebuild idempotent.
