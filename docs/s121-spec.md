# S121 — Rung 4: test authorship with mutation proof
# (ep27's training variable, authored on the ep26 champion base)

## Scope

Rung 4 of the ladder (open since rung-3 graduated): the model
AUTHORS tests, not just passes them. The capability: given a module,
write a real unit test with specific expected values — and PROVE the
test works by mutation: deliberately break the module, show the test
FAILS, restore, show it PASSES. A test that cannot fail is a test
that tests nothing.

## The demo shape

    list_directory -> read_file(module) -> write_file(test) ->
    run_tests (PASS: the code is correct) ->
    edit_file (the MUTATION: break the target function) ->
    run_tests (FAIL: the proof!) ->
    edit_file (the RESTORE: exact inverse) ->
    run_tests (PASS) -> final naming the test file + the proof

## The validator (mutation_proof declaration)

validate_demonstration gains `mutation_proof: Optional[Dict]`
({test_file, module, target}). Rules (structural, on the simulated
state + call sequence):
1. the declared test file was written and survives to the end;
2. the test content asserts the target function with LITERAL
   expected values (assert* + target name + digits — no
   "assert true" shells);
3. the script contains an inverse edit PAIR on the module
   (mutate: old=X/new=Y, then restore: old=Y/new=X) with a
   run_tests between them and a run_tests after the restore;
4. every anchor still matches exactly once at its point (the
   existing anchor machinery).

## The REAL proof (the lane, not the validator)

The lane's benchmark run executes the script for real — the
captured run_tests steps carry the actual suite outcomes. After the
run, build_agent_corpus inspects them for mutation_proof demos:
- >= 3 run_tests steps;
- the run_tests FOLLOWING the mutation edit must show a FAILING
  suite (exit_code != 0);
- the FINAL run_tests must show a passing suite (exit_code == 0).
A demo whose test does not catch the mutant is rejected ("mutation
proof failed") even though the run itself completed — the run proves
the harness works, the outcomes prove the test works.

## The batch (3 drills, fresh modules)

1. **calc_pro**: add + multiply; mutation flips multiply's `*` to
   `-`; the multiply test (4x3=12) catches it.
2. **textpro**: shout + whisper; mutation appends "!" to shout's
   return; the shout test (HEY) catches it.
3. **stats**: mean + total; mutation flips `/` to `//`; the mean
   test (7/2=3.5) catches it (integer division gives 3).

## Honest bounds

- The demos are additive (new-axis records); the ep26 champion's
  corpus is untouched — ep27 trains on the rebuilt export with the
  rung-4 batch as its single variable.
- The mutation is authored by the demo (the model role), not random
  — deterministic, reversible, anchor-unique.

## Test plan

1. Validator: the declared mutation_proof passes for a correct
   demo; a test-less-in-target demo is rejected; a missing
   mutate/revert pair is rejected.
2. Lane: all three pass the real gate; the post-run mutation check
   rejects a demo whose test fails to catch the mutant (hermetic
   test with a deliberately weak test file).
3. Batch count 36 -> 39; export rebuild carries the batch.
