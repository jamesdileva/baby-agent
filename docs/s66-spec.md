# S66 — Demonstrator 2.0 (Gen-2 corpus)

Status: scoped 2026-09-12. Roadmap: docs/ROADMAP-agentlite.md §S66.
Builds the gen-2 training corpus from the gen-1 verdict evidence: the
model acquired perfect syntax from 26 records but flailed at tasks,
because the demos taught answer-reading, not discovery.

## The four corpus design fixes

### 1. Explore-first (every demonstration)

New turn shape for all categories: `list_directory` → `read_file` the
DISCOVERED module → work → verify → final answer naming the file and
what was done. The gen-1 demonstrator opened the file the script
already knew, so the model learned to guess names (it searched for an
invented `test_failing` in the benchmark instead of listing `.`).

### 2. Recovery demonstrations (new class, ~1/3 of records)

A scripted wrong turn: `read_file` a hallucinated path (`src/<module>`)
→ the real file-not-found observation → correction to the real path →
success. Tagged `recovery-demo`. The roadmap names recovered
trajectories the most valuable class; gen-1 had zero. The observations
stay REAL (the loop executes every call — the wrong read genuinely
fails).

### 3. Category expansion (bug_fix + 5 more, all verifiable)

- **feature_add** (3 variants): the module is a marker comment; the
  demo replaces it with the declared implementation (surgical edit of
  the marker line).
- **build_repair** (1 variant): unclosed call in `broken_mod.py`; the
  demo reads the broken source, fixes the line, tests pass.
- **dependency** (1 variant): `billing.py` imports missing `helpers`;
  the demo's recovery is natural — run tests (ModuleNotFoundError) →
  read `helpers.py` (not found!) → read `billing.py` → create
  `helpers.py` → tests pass. `write_file` for NEW files (creation is
  not a surgical-edit case).
- **testing** (1 variant) and **regression** (1 variant): write a NEW
  unittest file pinning correct behavior, run it.
- Levels 1..8 (bug_fix decoys kick in at level ≥3). Deferred per
  roadmap: docs/refactor (no honest verification gate for prose).

Corpus math: 40 + 24 + 8 + 8 + 8 + 8 = **96 new records** (plus the 26
gen-1 records already in the store — the training set crosses 100).

### 4. Goal-phrasing variety

3 paraphrase templates per category (goal text with {module}/{func}
slots), selected by (variant + level) — the model learns intent, not
one goal formula; as a side effect near-duplicate records become
distinct goals.

## Implementation shape

- `ScriptedDemonstrator` becomes a thin script-carrier
  (`__init__(self, script)`); category script builders produce the turn
  list (explore-first ordering, recovery insertion, category edits).
- `build_corpus(experience_store, python, levels=1..8)` iterates
  {category: variant count}; recovery when (variant + level) % 3 == 0;
  same S63 chain (curate → build-training) and honest stats.
- Tests: every record's first captured step is `list_directory`;
  recovery-tagged share ≥ 25%; all records eligible + step-trainable;
  per-category probe (one run each) asserting the category-specific
  fix lands; determinism.

## Pins

- Every demonstration still runs through the REAL loop, REAL
  subprocess tests, and the S41 gate — only verified passes become
  records.
- Observations are never fabricated: the recovery turn genuinely fails
  on disk.
- Provenance stays `scripted-demo` (+ `recovery-demo` tag).
- The old 5-turn bug_fix contract is superseded; tests updated with the
  contract change noted.

## Run plan

Full gen-2 corpus build (~96 runs, ≈5-6 min), curate, build-training,
kit export — reported with honest numbers. Colab retrain is S67 (the
human's one job per generation).
