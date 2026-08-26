# Roadmap — qacompanion v1

Spec of record: [docs/spec.md](spec.md). One slice per cycle: implement,
tests green, commit, clean tree.

## S1 — Storage core + `record`

`cases.jsonl` writer/loader with strict validation (non-int id, non-object
record, missing fields → ValueError). `record` adds or bumps `times_seen`.

**Exit:** record works against a temp file via env override; corrupt-store
test proves no partial writes on load failure.

## S2 — Signature normalization + `lookup`

Fingerprint function: test name + first error line, whitespace/path
normalized. `lookup` prints best case (highest times_seen) or exactly
`no matching case`. Never fabricates.

**Exit:** identical failures normalize to equal signatures across path/case
variations; unknown signature returns the no-match sentinel.

## S3 — `report`

Table output: total cases, top 5 by times_seen, stale cases (>30d since
last_seen).

**Exit:** golden-output test on a fixture case base.

## S4 — `accuracy` + holdout replay

`holdout.jsonl` created at S4 start (curated past failures). Replay: % of
holdout where lookup returned the right diagnosis. Number must be re-runnable
forever; regressions must be justified or reverted.

**Exit:** accuracy runs green on fixture holdout ≥ the seeded baseline;
documented in README.

## S5 — `export` / `import`

Safe round-trip (no-locking copies, atomic replace). Corrupt import rejected
without clobbering the live case base.

**Exit:** round-trip byte-stability test; corrupt-import rejection test.

## S6 — Teacher loop, documented and exercised

Docs: how parents confirm/correct diagnoses after real failures (corrections
overwrite diagnosis, bump times_seen; new lessons create cases). Exercise one
live loop against a real failure and record it in DECISIONS.md.

**Exit:** live loop recorded; README quickstart matches reality.

## Future (out of v1)

- Fuzzy/signature-clustering match tier
- tess-facing REVIEW integration once she reaches Analyst

## Skills ladder (v1.1) — core QA, taught as code

Each skill is one module under `qacompanion/skills/` (D7 seams), one sprint,
tests-first, shipped independently. Every skill encodes a QA lesson this
colony already paid for. Start only after S6 definition-of-done.

### S7 — Auto-capture hook

`qa run -- <cmd>` wraps any command: nonzero exit → parse output → auto-
`record` failures. Turns manual recording into ambient capture.

**Exit:** wrapped pytest/npm failures land in the case base untouched;
zero-exit runs record nothing.

### S8 — Flaky skill

Track signatures that later pass without a fix: flake-rate per case, flagged
in `report`. Teaches: not every red is broken.

**Exit:** pass-after-fail sequences update flake stats; chronic flakes (>50%
pass rate) surface separately from real regressions.

### S9 — Environment skill

Classify ENOENT / version-mismatch / permission errors into environment
diagnoses ("tool missing", "wrong cwd", "empty repo") instead of generic
storage. Direct descendant of the npm-ENOENT and FAIL(0.0s) lessons.

**Exit:** fixture suite of environment failures classifies correctly;
unknown classes stay honest (`unsure`).

### S10 — Regression skill

A signature that returns after ≥N clean passes is a regression, distinct
from a new failure. Surface prominently; link to its last-green date.

**Exit:** seeded history reproduces regression detection; report separates
regressions from first-time failures.

### S11 — Preflight skill

Encode the colony's standing QA rules as executable checks: installer/
artifact SHA256 quoted-in-transcript before probe (R3), no BOM in configs,
clean tree before claiming done. `qa preflight` runs the checklist.

**Exit:** each rule has a violation fixture and a passing fixture; checklist
output names the rule violated.

