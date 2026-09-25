# S77 — Gen-9: SRFT Prefix Learning + Nested-Lookup Coverage Expansion

Status: scoped 2026-09-24. Roadmap continuation. The gen-8 verdict
(3/9, 33.3%) put calculator and strings on the board; json is the
standing wall (0/3), and the evidence says why.

## The json wall, from the recorded evidence

ep8's json trajectories decompose into two failure modes:

1. **The synthesis step.** Run 3 executed the ENTIRE trained chain —
   tests, test-file read, module read — and applied an edit that still
   failed verification. The chained-`.get` fix
   (`data.get("settings", {}).get(key)`) is a two-hop pattern: infer
   the nesting from the TEST fixture, then write a novel expression.
   Calculator/strings fixes are one-token flips; this requires
   composing new code. 8-16 demonstrations is thin for expression
   synthesis.
2. **Productive-but-discarded trajectories.** The discovery phases of
   the json failures are exactly the behavior we want (list, read
   test, read module) — but the success-only training gate throws
   every failed run away, including their good prefixes. 60+ recorded
   failed trajectories contain real, verified-productive exploration.

## Gen-9 scope (two levers, both aimed at the wall — attributed
## per-task)

Calculator/strings act as controls: if they hold, the changes are
json-attributable; if they regress, the verdict says so.

### 1. SRFT prefix lane (the mechanism change)

Step-Rejection Fine-Tuning, adapted (JetBrains 2026 recipe; our
dataset-separation rule intact): failed trajectories carry
verified-productive PREFIXES. New training lane in `training.py`:

- Source: the CURATED export's FAILED-class trajectories (never raw
  experience; no hard flags; captured steps required).
- **Prefix rule (deterministic):** steps up to and including the last
  `read_file` BEFORE the first `edit_file`/`write_file` — the full
  discovery+diagnosis chain. Everything after (the failed edit, the
  fabricated final) is masked entirely, and NO final answer is trained
  (the run has none that is honest).
- Runs with no edit: the whole exploration prefix trains.
- Provenance: `srft-prefix` in the chat metadata + exclusion-style
  accounting in the report ("srft_prefix_records: N from M failed
  trajectories"). The lane never touches cases.jsonl and never
  upgrades a failed run's outcome — it teaches process without
  teaching wrong conclusions.
- Loss masking applies as standing (assistant-only within the prefix).

### 2. Nested-lookup coverage expansion (the data lever)

`nested_lookup` grows from 1 variant to 4 (all verifiable, all
faithful to the S57 task's shape — chained descent into a named
section):

- v0 (existing): settings section, exact eval-task shape.
- v1: alternate section name (`database`), same pattern.
- v2: two-level descent (`data.get("a", {}).get("b", {}).get(key)`)
  — generalizes the chain.
- v3: section-may-be-missing → default (`data.get("settings",
  {}).get(key, "unknown")`).
Each with the S71/S72 recipe: diagnostic chain (tests fail → read
test → read module → derive the fix), recovery variants, goal variety.
corpus-v7 bump → idempotent rebuild.

### Deliberately not in gen-9

- RL/GRPO-style online training (the surveys' next frontier) — needs
  GPU-hours we route through Colab; revisit after gen-9 rates.
- Editing the json eval task itself (the benchmark is frozen; it is
  the yardstick).

## Verification

- SRFT lane unit tests: prefix rule (stops at first edit, includes the
  last read), masking (no final trained), provenance labels, report
  counts; a failed-with-no-edit case; hard-flagged failures excluded.
- Coverage tests: the three new variants each verify via the real
  loop; corpus-v7 invalidation.
- Live: rebuild → export → the human's Colab job (assistant-only loss
  + SRFT lane) → ep9 → `qa verdict --models baby-agent:ep9,baby-agent:ep8`
  — **the primary metric is the json task's success rate**;
  calculator/strings are the controls.
