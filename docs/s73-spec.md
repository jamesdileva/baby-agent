# S73 — Gen-7: Coverage-Targeted Demonstrators (strings + nested lookup)

Status: scoped 2026-09-13. The gen-6 milestone (first trained-
generation SUCCESS — calculator at budget 12) showed the recipe works;
the two remaining failures are the tasks the corpus never covered:
**string reverse** (string_utils: `return text` instead of
`return text[::-1]`) and **nested lookup** (config_parser:
`return data.get(key)` instead of `data.get("settings", {}).get(key)`).
Both shapes are S57 default-task defects the demos never mirrored.

## Scope (one coherent variable)

Gen-7's variable: **coverage expansion targeting the unhit eval-task
shapes**. The diagnostic chain, recovery ordering, failure states, and
catalog alignment stay exactly as gen-6 (corpus-v5 recipes) — the NEW
demos reuse them verbatim with new fixtures. Research-informed recipe
experiments (loss masking, SRFT) stay queued for gen-8 — gen-7
attributes cleanly to coverage.

## Implement

### 1. Two new demonstrator categories (S57-mirrored fixtures)

- **string_reverse** (1 variant × levels 1-8): string_utils.py contains
  `def reverse(text): return text` with a test asserting
  `reverse("abc") == "cba"`. Diagnostic chain: list → tests (fail) →
  read test → read module → edit (`return text` → `return text[::-1]`)
  → tests → final.
- **nested_lookup** (1 variant × levels 1-8): config_parser.py contains
  `def lookup(data, key): return data.get(key)` with a test asserting
  the nested path. Chain identical; edit: `return data.get(key)` →
  `return data.get("settings", {}).get(key)`.

Both follow the S71/S72 rules: explore-first, diagnosis chain, recovery
variants (guess-before-discovery), quote-free commands, corpus-v6 tag.

### 2. Verdict defaults (already landed)

`run_verdict` default budget 12 (the taught chain is 7-9 turns;
gen-6's calculator win came at 7 — budget 6 starved it). 15 was
considered and rejected: more CPU wall-clock timeout risk without
teaching benefit; 12 covers the premature-recovery variant's 9-11
turns.

### 3. Deliberately NOT in gen-7 (post-stabilization queue)

- Loss masking / assistant-only loss (objective-side fix for
  narrative-over-behavior — now testable BECAUSE gen-6 succeeded; a
  gen-8 recipe experiment).
- SRFT-style failed-trajectory signal (46+ recorded failures waiting).
- Imported datasets: still rejected (format/provenance moat).

## Verification

- Per-category tests (the mirrored fixes land; quote-free; the chain
  order holds).
- corpus-v6 invalidation + rebuild (~1 minute, 112 runs).
- Live: export → Colab → ep7 → `qa verdict --models
  baby-agent:ep7-q4,baby-agent:ep6-q4` at the 12 budget — the
  experiment: do the previously-unhit tasks now succeed?
