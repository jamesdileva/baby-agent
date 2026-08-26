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

## Workplace skills (v1.x) — general competence, taught by real asks

These are not QA features — they are the general workplace literacy every
agent needs. Each sprint builds a small reusable utility born from an actual
question the human asked that no agent could answer alone. Same discipline:
stdlib only, tests-first, one slice per cycle, usage docs ship with the code
(a tool without docs does not count as done).

### S12 — `locate`: repo and project finder

Born from: *"Where does the taskline repo live on disk?"*

Walks common roots (user projects dir, home, data homes), detects git roots,
matches names/fragments, prints absolute paths + branch + dirty status.

**Exit:** finds a seeded test repo by name fragment and by contained commit
hash; handles permission errors gracefully.

### S13 — `snapshot`: archive-with-manifest

Born from: *"Archive it so it's not lost."*

Timestamped copy of any directory into an archives folder plus a
`MANIFEST.json` (file list, sizes, SHA256s, source path). The Antfarm archive
behavior, as a portable tool.

**Exit:** snapshot round-trips byte-identical; manifest hashes verified;
refuses to overwrite existing snapshot stamps.

### S14 — `repocheck`: multi-repo health report

Born from: *"Can I push these to GitHub eventually?"* and the 26-unpushed-
commits incident.

Scans a parent directory's git repos and reports per repo: dirty files,
commits ahead of upstream, missing remotes. One glance = which projects need
attention.

**Exit:** fixture repos with known states classified correctly; non-repo
dirs skipped silently.

### S15 — `journal`: durable lessons ledger

Born from: *"VOID-L1 residuals live only in mail/memory."*

Append-only markdown ledger with auto-timestamped entries (`journal add
<text>`), searchable (`journal grep`), designed to be committed alongside
any repo so lessons survive resets. The antidote to knowledge living only
in conversation.

**Exit:** entries survive concurrent adds; grep returns matching entries
with dates; ledger file is human-readable markdown.

### S16 — Evolution: declarative skill registry

Born from: *"can skills be auto-learned from what parents teach?"*

Skills become **data**: `skills/*.json` rule packs loaded at runtime — each
rule maps a pattern (regex on error text, exit-code class, timing anomaly)
to a classification/diagnosis/action hint. New rules take effect on next
run, no code changes, no restart. Parents teach by adding rule entries (a
`qa teach --rule ...` helper writes validated JSON); tess's corrections can
propose rules for parent sign-off.

**Exit:** a rule pack added at runtime is honored by the next lookup without
code edits; malformed packs rejected loudly; core behavior identical when
the skills dir is empty.

### S17 — Module-contract skills (guarded)

For capabilities too complex for declarative rules: Python modules satisfying
a fixed Skill interface, auto-discovered from `skills/modules/`. Guardrails:
must ship with tests, must pass the full suite, and land only through the
normal slice/review discipline — never auto-executed unreviewed. This is the
boundary between evolution and self-modification; stay on the right side.

**Exit:** one example module passes discovery + suite gate; an intentionally
failing module is demonstrably blocked from loading.

## School & capstone (v2 track) — knowledge expansion

### S20 — `digest` skill: document ingestion

Point at a directory (or repo): parse all markdown/docs into the knowledge
base as retrievable entries (`qa ask "deployment?"` returns cited passages).
Project context becomes lookup, not re-reading.

**Exit:** digested corpus answers fixture questions with correct citations;
re-digest updates rather than duplicates.

### S21 — `archive-mine` skill: learn from past eras

Digest Antfarm archives: DECISIONS.md files, git logs, failure transcripts.
Every diagnosis ever paid for across every colony era becomes a case.

**Exit:** mined cases import cleanly; known lore (FAIL(0.0s), BOM,
stale-installer) is retrievable via lookup.

### S22 — School mode

`qa school` — interactive session walking recent unconfirmed diagnoses with
the parents: confirm/correct/case-create in one pass. Formalizes the teacher
loop into a repeatable ritual (the "school" the human asked for).

**Exit:** a school session processes N pending diagnoses end-to-end; ledger
and case base updated atomically.

### Capstone — guided project (graduation exam)

Parents architect a small but real application; qacompanion participates
end-to-end using every acquired skill: preflight before commits, capture
during test runs, doc-digest for conventions, journal for decisions, case
lookups for every failure. Success = the project ships with zero repeated
diagnoses — everything new was taught, everything taught was recalled.

## Autonomous learning track (v3 ambition) — the tool asks to be taught

The long-run experiment: the tool stops being purely passive. It notices
patterns across its case base, proposes new rules itself, and the parents
adjudicate — approve, correct, or reject. Teaching effort shifts from
"diagnose everything" to "judge proposals". Runs 24/7; every night compounds.

### S23 — Candidate detection

Offline pass over the case base: recurring co-occurrences, error clusters,
timing anomalies → filed as RULE PROPOSED entries into a review queue (never
auto-installed). Includes confidence estimate + supporting cases.

**Exit:** seeded history produces at least one rule proposal a human agrees
is correct; false candidates are labeled by parents and tracked.

### S24 — Adjudication loop

`qa review-rules` walks the queue with the parents: approve → rule installed
to skills registry; correct → amended then installed; reject → recorded so
the same candidate shape is not re-proposed (the tool learns what NOT to
propose).

**Exit:** full loop exercised live; rejection memory demonstrably suppresses
repeat candidates.

### S25 — Weakest-subject requests

Tool ranks its own knowledge gaps (categories with low coverage or high
escalation rate) and REQUESTS teaching: "I have no cases for network errors —
please walk me through some."

**Exit:** gap report generated; one requested lesson lands and measurably
closes the reported gap.

### Honest ceiling (documented, permanent)

This track produces an increasingly capable **expert system**: broad recall of
taught patterns, self-proposed refinements, measurable accuracy. It does not
produce general reasoning. Novel situations still escalate — that escalation
path IS part of the design, forever.

## Deferred

- Interactive teach/watch console (TUI): stream failures, confirm diagnoses,
  watch accuracy live. Revisit after tess uses lookup daily — build the
  interactions the teaching loop actually needs.
- Per-project case bases with merge-up (QA_CASES_FILE already enables this).

### S18 — `merge`: teacher dedup tool

Teachers spot two signatures that are really one failure. `merge --into A
--from B` re-points B's times_seen onto A and removes B (with a merged-from
note in A). Reduces false `no matching case` results caused by near-duplicate
signatures.

**Exit:** merge preserves combined counts; B disappears from report; merging
with itself is rejected.

### S19 — Robust I/O hardening

Spec section "Input robustness" made testable: BOM-stripped JSONL load,
CRLF-equivalence, trailing-newline tolerance, skill-pack regex compile caps +
timeout guard degrading to `unsure`.

**Exit:** fixtures exist for each robustness rule; a hostile regex fixture
provably cannot hang lookup.

