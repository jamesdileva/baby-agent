# S107 — Drill persistence: the beats must survive into chain 2
# (ep20's single training variable)

## Problem (forensics on the gen-19 double reading, 600s fair runs)

ep19's chain-1 behaviors are drilled and working; chain 2 never
starts. Three named shapes, each from a recorded trajectory:

- **S1 — the chain-2 catalog-tool loop (cascade).** After the first
  fix lands cleanly (ep19 applied the def-anchored add edit — the
  S104 re-anchor shape WORKING), the second diagnosis never edits:
  the model loops on rejected catalog-tool calls instead — invalid
  `code_diagnostics(path=...)` x3 in one reading, failed
  `experience_record` x5 in another. The loop's TARGET varies; the
  structure (chain 2 = tool-loop instead of read+edit) is constant.
- **S2 — the fabricated anchor (indirect).** Discovery is perfect
  (`code_importers(module=...)` with the right module), the source
  module is read — then the edit anchor is INVENTED from memory
  (`return amount * 2`; the file says otherwise), rejected as
  not-found, and the model re-reads the file three times while
  retrying the same fabricated anchor. It re-reads without ever
  COPYING what it read.
- **S3 — the beats are one-shot.** The S104 drills demonstrate the
  schema-fallback and re-anchor beats ONCE (chain 1). Nothing teaches
  the model that the beats apply AGAIN in the second diagnosis
  chain — so under a second failure the behaviors evaporate.

## Design — ep20's ONE variable: drills whose chain 2 carries the beats

All fresh-goal authoring in the untrusted lane (validator + gate),
fixtures per the S95 lesson (never the eval modules; the S104
fixtures metrics/scale are reused with NEW goal phrasings — the
lesson is new, the fixture is proven).

### Beat placement (the core change)

The extended double-cascade drills demonstrate, in BOTH chains:
invalid-codeintel-call → honest rejection → READ instead. Chain 2's
beat sits exactly where the live model loops: after the second
failing test run, the demonstrator makes the invalid call, receives
the rejection, and goes straight to the module read and the edit.
The final narrative names the persistence rule: "the same rule held
in the second chain — after a fix, diagnose by reading, not by
calling tools."

### S2 coverage — the fabricated-anchor drill (indirect shape)

A two-module import chain where the first edit anchor is a
FABRICATION (matches 0 times — the S100 recovery_anchors mechanism
covers this exactly: a declared miss must be genuine, consumed, and
followed by a corrective edit on the same path). The corrective edit
anchors on the line the fresh read actually showed. The narrative:
"my first anchor was remembered, not read; re-reading and copying
the actual line fixed it."

### Batch

1. **metrics (fixture reused, new goal)** — both chains carry the
   schema-fallback beat; chain 2 additionally carries the ambiguous
   re-anchor (as S104 did).
2. **scale (fixture reused, new goal)** — same structure, second
   instance.
3. **budget (fresh module)** — the self-ambiguating double-cascade
   (`spend: a + b` defect, `save: a - b` defect; fixing spend makes
   save's anchor ambiguous), both chains with beats.
4. **parcel/shipcalc (fresh indirect pair)** — the fabricated-anchor
   drill above.

## Honest bounds

- The drills do not change the eval tasks, the fixtures, the
  verifier, or any other corpus member — ep20's only deliberate
  variable is this batch (the standing SRFT lane and the 2:1 real
  cap behave as built).
- The beats teach RECOVERY actions; they do not make the tasks
  easier (both defects remain; the collisions remain).
- ep21 (rung-7 explore-qa demos) stays gated on ep20's verdict.

## Test plan

1. Validator: all four demos pass (recovery_anchors consumed for the
   fabricated anchor; ambiguous_anchors genuine for the cascades).
2. Existing validator/recovery pins unchanged; batch count pin
   22 -> 26.
3. Lane: all four pass the REAL benchmark gate, tagged
   agent-authored + corpus-v8 (the S106 stamp).
4. Corpus rebuild: deliberate pool grows by 4; rebuild stays
   idempotent (second run supersedes 0); export carries the new
   drills (goal-search verified).
