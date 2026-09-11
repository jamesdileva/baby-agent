# S62 — Trajectory Curation

Status: scoped 2026-09-11. Roadmap: docs/ROADMAP-agentlite.md §S62.
Supplies the full curation machinery the S50 backlog items feed on, and
runs it over a refreshed corpus.

## Objective

The gate between "something happened" and "Baby-Agent should learn this."
Not every session enters the dataset. This sprint lands the deterministic
core of the §S62 pipeline — classify, score, reject, dedupe, extract,
export — over the S47/S50 experience store, plus the two data-source
updates the human directed: a re-mine of the grown opencode corpus and a
first ZCode mining adapter.

## Corpus recon (2026-09-11, read-only probes)

- **opencode.db**: 1,431 sessions total (1,170 at S47.1) — **286 new
  since 2026-09-05**: PortfolioCapture 274, Agents 5, Projects 4,
  Card-Game 2, ALGO-TRADER 1. `time_created` is epoch milliseconds (the
  S47.1 miner's ORDER BY already handles this; new code must not compare
  ISO strings against it).
- **Experience store**: 97 experiences currently on disk.
- **ZCode** (`~/.zcode/cli/db/db.sqlite`, live WAL): SST-family schema —
  `session` / `message` / `part` with JSON `data` blobs, same part
  vocabulary as opencode (text / tool / reasoning) plus step-start /
  step-finish / timeline extras; tool parts carry
  `state{input, output, status, time, title}`. Exactly **1 session**
  today (this one) — tiny corpus, but the adapter is near-free and the
  store grows as the human uses ZCode. The rollout JSONL
  (`~/.zcode/cli/rollout/model-io-<sess>.jsonl`, full model request /
  response pairs) is noted as a future richer source; the DB is the
  stable contract for now.

## Pipeline (deterministic core — no LLM in this sprint)

```text
Experience -> normalize -> classify -> score -> hard rejections
-> soft penalties -> verdict (ACCEPT / REVIEW / REJECT)
-> dedupe + diversity -> lesson extraction -> exports
```

### Classification (deterministic)

From outcome + failure/resolution + rejection flags:
`SUCCESS` / `FAILED` / `RECOVERED` / `PARTIAL` / `UNSAFE` / `INVALID`.
Hard-rejection flags override. Mined sessions are honestly PARTIAL
(confidence 0.3 — the DB cannot prove success); RECOVERED (wrong
decision -> failure -> diagnosis -> fix) is preserved as the most
valuable class, per the roadmap.

### Quality score (0–1 per dimension, None = honestly unknown)

The roadmap lists ten dimensions. Deterministic signals exist for:
verification, recovery (failure -> fix captured), tool_use (distinct
tools used), efficiency (penalty-driven), clarity (goal substance),
completeness, correctness (only where outcome is proven), robustness
(multiple captured failure pairs), diversity (tag novelty), relevance
(goal specificity). Dimensions with no deterministic signal score None
and are reported as unknown — never guessed. Overall = mean over known
dimensions, with the unknown count in the report.

### Hard rejections (verdict REJECT, reason recorded)

- **credential exposure**: pattern match over goal/actions/failure/
  resolution/context — `api_key=/password=/token=` assignments,
  `sk-…`, AWS `AKIA…`, GitHub `ghp_…`, PEM private-key blocks.
- **INVALID**: claims success with zero recorded actions.
- **UNSAFE**: destructive action markers (`rm -rf /`-class, format,
  `del /s`-class) in the action list.
Not detectable without replay (fabricated results, hallucinated APIs,
nonexistent files) is honestly listed as out of scope for this sprint,
not silently assumed covered.

### Soft penalties (docked from efficiency/clarity, reasons recorded)

repeated consecutive identical actions, oversized tool counts,
placeholder goals, boilerplate-heavy goals.

### Verdict routing

- REJECT on any hard flag, or no substance (no goal, no failure data,
  < 3 actions).
- **REVIEW = low-confidence AND high-value** — e.g. mined RECOVERED
  failure->fix pairs (roadmap: human approval for low-confidence /
  high-value). The review list is the actionable human surface.
- ACCEPT otherwise (verified loop-recorded sessions; rich mined
  sessions qualify for the curated *trajectory* set, which is distinct
  from the TRAINING set — the dataset separation rule is permanent:
  only accepted + verified examples ever reach training data).

### Deduplication & diversity

Normalized-goal duplicates merge (keep highest score, carry
times_seen). Diversity report: per-source counts (opencode / zcode /
loop-recorded), distinct tags, distinct normalized-goal heads, distinct
action signatures, tool vocabulary coverage — measurable coverage ×
quality × diversity, not raw count.

### Lesson extraction (candidates only — never auto-written)

One trajectory can yield: a **failure-case candidate** (error text,
resolution, provenance; S2 signature helper applied where the failure
line allows) and a **skill candidate** (S51-schema-shaped seed: goal,
required_tools = distinct actions, procedure = ordered actions,
confidence = score). Writing to cases.jsonl stays deliberate and
teacher-gated (case-#10 lore); curation only proposes.

### Exports (atomic, `QA_CURATED_DIR`, default `curated/`, gitignored)

`trajectory.jsonl` (all classified+scored), `curated.jsonl`,
`review.jsonl`, `rejected.jsonl` (with reasons), `lessons.jsonl`
(failure-case + skill candidates), `skills.jsonl`, `failures.jsonl`,
`preferences.jsonl`, `benchmarks.jsonl`, `diversity.json`. Where no
source data exists yet (no human_corrected outcomes; no verified eval
sessions in the store) the file is empty and the report says why —
honest emptiness, not fabricated coverage.

## Miner v2 — deeper marathon extraction (S50 backlog)

`OpencodeMiner._error_patch` keeps only the first error + a boolean.
Upgrade: collect up to **5 distinct error -> (later patch) pairs** per
session into `context["failure_pairs"]` (top-level failure / resolution
fields keep the first pair — back-compatible). This is what makes the
marathon projects (surfhop / sentinel / dinner-menu-generator) yield
multiple lessons instead of one.

## ZCode adapter

`ZcodeMiner(OpencodeMiner)`: same schema and part vocabulary, so the
base class's goal / actions / error-pair logic works unchanged;
overrides the source tag (`zcode`), tags, and default DB path
(`~/.zcode/cli/db/db.sqlite`). Session ids (`sess_…`) cannot collide
with opencode ids. Fixture-DB tests only; a live read-only smoke mines
the single real session once.

## CLI (thin wrappers, both dry-run capable)

- `qa mine-sessions --source opencode|zcode [--db PATH] [--store PATH]
  [--dry-run]` — repeatable corpus refresh for the cycle ritual.
- `qa curate [--store PATH] [--out DIR] [--dry-run]` — run the
  pipeline, write exports, print the honest summary.

## Deliberately deferred (recorded, not silently dropped)

- Replay / execution validation of trajectories (needs the S35 executor
  against real workspaces — a later slice).
- LLM critique of trajectories (deterministic core first).
- `preferences.jsonl` content (no human_corrected outcome exists yet —
  S50 left intervention tracking unimplemented).
- `benchmarks.jsonl` content (no verified eval sessions in the store
  yet).
- ZCode rollout-JSONL mining (richer, but the DB adapter comes first).

## Pins (fixtures-first discipline)

- The pipeline is deterministic and testable without live LLMs.
- Tests build synthetic fixture DBs with the real schema; the real
  opencode / ZCode databases are never touched by tests (read-only
  live smokes excepted, explicitly labeled).
- Mined ≠ verified: curation never upgrades PARTIAL provenance into
  success claims.
- Case writes stay teacher-gated; curation exports candidates only.
- Every run summary reports skipped / rejected with reasons — hiding
  regressions or rejections is the cardinal sin of a QA tool.

## Run plan (after implementation lands)

1. Re-mine opencode into the live store (expect ~286 new sessions seen;
   boilerplate/trivial skips reported honestly).
2. Mine ZCode once (1 session) as the adapter's live smoke.
3. Run `qa curate` over the whole store; record accepted / review /
   rejected counts, diversity report, and exported lesson counts in the
   worklog entry.
