# S71 — Demonstrator 3.0 (the diagnosis chain)

Status: scoped 2026-09-12. Roadmap continuation; the gen-4 verdict
named the remaining gap precisely: no diagnosis chaining — the models
rerun failing suites without reading the failing file, because every
demonstration's edit derives from demonstrator-omniscience. Gen-5
teaches ONE coherent lesson: **derive the fix from the evidence**.

## Scope discipline (human-directed)

One coherent variable for gen-5: the demonstrator redesign. Session
mining (opencode/zcode) continues as the standing memory loop but
cannot affect training (unverified partials are permanently excluded
from the training export); Gemini drips continue daily as the standing
real-record loop. Neither is a gen-5 variable — the verdict attributes
cleanly to the lesson change.

## The three refinements (one lesson)

### 1. Diagnosis-chain scripts (every fix category)

Canonical bug_fix chain — the edit is DERIVED, not remembered:

```text
list_directory -> run_tests (fail; output names the failing test)
-> read_file the TEST file (what is expected)
-> read_file the MODULE (what the code actually does)
-> edit_file (the smallest change closing the gap)
-> run_tests (pass)
-> final answer walking the chain: "the test expected X; the code
   did Y; I changed ... and the suite passes"
```

feature_add/build_repair get the same chain; build_repair additionally
opens with **code_diagnostics** (argument-free, workspace-wide — the
tool gen-3 invented arguments for) so the syntax-error file is
DIAGNOSED before it is read. dependency keeps its natural
missing-module recovery and adds reading the TEST file for the
expected format.

### 2. Rational recovery ordering

The wrong turn moves BEFORE discovery in every recovery variant:
guess the path first → real file-not-found → THEN the systematic
chain. Gen-3's `explore_recovery` taught "list, then guess anyway" —
noise. The guess is now a rational first hypothesis that the evidence
overturns.

### 3. Tool coverage where natural

code_diagnostics (build_repair), file_metadata (feature_add), and the
test-file reads give the offered tools demonstrated, correctly-argued
appearances — gen-3's invented `code_diagnostics(path=...)` became
impossible to learn from because no demo ever showed the real call.

## Measurement (the experiment)

New protocol metric: **diagnosis_chaining_rate** — among benchmark
runs whose trajectory contains a failed `run_tests` step, the share
where a `read_file` follows within 2 steps. Gen-3/gen-4 recorded runs
sit at ~0; gen-5's number is the experiment. Guessed-path and
discovery-first rates stay on the table.

Corpus version `corpus-v4`: the idempotent rebuild invalidates the
v3 records automatically (supersede + re-demo, ~1 minute).

## Verification

- Strategy-script tests per category (the chain order asserted,
  code_diagnostics argument-free, wrong-turn-before-discovery).
- Metric unit tests on synthetic trajectories.
- Live rebuild → export check → the human's Colab job → ep5 →
  `qa verdict` against ep4/ep3 with the new metric on the table.
