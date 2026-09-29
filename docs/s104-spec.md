# S104 — Cascade stability: the re-anchor drill + the schema-fallback
# beat (ep18's single training variable)

## Problem (forensics on the gen-17 two-reading verdict)

Cascade 0/6 for ep17 (both seeds, identical failure anatomy) against
ep11's 4/6. Two distinct walls, named from the recorded trajectories:

- **W1 — the schema-error loop (ep17's shape).** The model invents
  arguments for the codeintel tools (`code_diagnostics(path=...)`,
  `code_symbols(name="add")`), receives "invalid arguments" back, and
  then repeats the IDENTICAL invalid call to max-iterations — 8x in
  every failed run. It never reads `calc_ops.py` (77 bytes, both
  defects). ep11 shows the same loop occasionally (its failed runs
  include a code_symbols x7 stretch) but usually falls back to
  read_file after one error.
- **W2 — the self-ambiguating fixture (every generation's shape).**
  The cascade fixture is `add: return a - b` (defect) and
  `multiply: return a + b` (defect). Fixing add produces a SECOND
  `return a + b` in the file, so the multiply edit's natural anchor
  `return a + b` now matches 2x and edit_file rejects it
  ("add surrounding lines"). ep11's failed runs show it re-reading
  and retrying the same ambiguous anchor to exhaustion instead of
  re-anchoring. No generation has been TAUGHT the re-anchor move.

## Design — ep18's ONE variable: two recovery beats on fresh modules

### Beat 1 — the re-anchor drill (W2)

Self-ambiguating fixtures on FRESH modules (never calc_ops — S91/S95;
never taxcalc/cart, invoice/.../basket):

- `metrics.py`: `total: return a - b` (defect), `difference:
  return a + b` (defect). Fixing total creates the collision for
  difference's anchor — the exact cascade-fixture shape.
- `scale.py`: `grow: return n - 1` (defect), `shrink: return n + 1`
  (defect). Same shape, second instance.

Script shape: list → run_tests (both fail) → edit defect-1 (unique
anchor, lands) → run_tests (one still fails) → edit defect-2 with the
naive anchor → REJECTED at runtime (matches 2x — the deliberate beat)
→ read_file (fresh observation) → widened edit anchored on the
`def` line (unique) → run_tests (both pass) → final naming the file
and the re-anchor reasoning ("my first anchor matched twice — I
widened it with the def line").

### Beat 2 — the schema-fallback (W1)

Woven into both drills' diagnosis step: one deliberate
`code_diagnostics(path=<module>.py)` call with an invented argument →
honest "invalid arguments" observation → the script falls back to
read_file (which the diagnosis chain needs anyway). The corpus
teaches: an invalid-args error is a signal to switch to reading, not
to retry the same call. (The S103.1 recovery ladder now catches the
loop in dashboard sessions; the demos teach the model not to need
it in benchmarks, which run bare.)

### Validator extension — the third anchor class

`validate_demonstration` gains `ambiguous_anchors: Optional[List[str]]`
(additive, default empty — existing callers unchanged):

- a declared ambiguous anchor must genuinely match >= 2 in current
  content (not 0, not 1 — a single match means the "ambiguity" is
  staged, and a 0 match is the S100 stale shape, not this one);
- it must be followed by a successful corrective edit on the same
  path whose anchor matches exactly once;
- symmetric with recovery_anchors: declared-but-fake = rejected;
  declared-and-consumed = the record teaches the recovery.

### Tooling note

The rejected ambiguous edit changes nothing at runtime (edit_file
errors before mutating), so the state simulation skips it exactly
like a stale miss.

## Honest bounds

- The drills teach recovery from the two OBSERVED failure modes; they
  do not make cascade easier (the fixture keeps both defects and the
  collision).
- ep18's corpus changes ONLY by this batch (+ the usual verdict-run
  real-pool cap). One variable, per the standing rule.
- The S100 training-side rule (deliberate beats kept; failed turns
  stripped only from undeliberate records) applies unchanged.

## Test plan

1. Validator: declared ambiguous anchor matching 2x + corrective edit
   -> valid; matching 1x -> rejected ("staged"); matching 0x ->
   rejected (that is the stale shape, wrong declaration); corrective
   edit missing -> rejected.
2. Existing validator pins unchanged (recovery_anchors behavior).
3. Lane: both drills pass the real benchmark (the gate runs the
   actual fixture), tagged agent-authored.
4. Corpus rebuild: the batch enters the curated export; counts
   recorded in the worklog.
