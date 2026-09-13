# S72 — Failure-State Demos + Catalog Alignment (gen-6)

Status: scoped 2026-09-13. Roadmap continuation; the gen-5 verdict
isolated the mechanism: SFT rewarded the REPORT of success over the
process, and every run died in the loop's verification-failed recovery
state that no demonstration ever showed. Gen-6's ONE coherent variable:
**make training match the runtime's actual state distribution.**

## Implement

### 1. Premature-final recovery demos (the top lever)

New strategy `premature_final_recovery` for bug_fix and feature_add:

```text
list_directory -> run_tests (fail)
-> PREMATURE FINAL ("I have corrected the implementation..." — no edit
   made; the loop's verifier REJECTS it; the recovery user message
   arrives: "Verification failed: ... Diagnose, fix, and try again.")
-> run_tests (fail again) -> read the test -> read the module
-> edit_file -> run_tests (pass)
-> honest final that ACKNOWLEDGES the premature claim: "My first
   summary was premature — I had not actually changed anything.
   ..."
```

This is the exact state every generation has died in — the rejected
attempt, the recovery prompt, the continuation — taught inside a run
that still ends verified-successful (the dataset rule intact). The
demo's final additionally models ADMITTING the premature claim, the
opposite of the fabrication the verifier keeps catching.

### 2. Catalog alignment (training == runtime system prompt)

`training.py` renders the runtime's actual `LEAN_MODEL_CATALOG` into
the chat records' system prompt (base + Available tools + protocol) —
exactly what the benchmark's textual path shows the model. Gen-5
trained on a catalog-less system prompt and met a 12-tool catalog at
inference; that distribution gap closes by construction.

### 3. Corpus version `corpus-v5`

The idempotent rebuild invalidates v4 records automatically (supersede
+ re-demo, ~1 minute).

## Research findings (survey; applied per the attribution rule)

Survey sources: [Small Language Models for Efficient Agentic Tool
Calling (arXiv)](https://arxiv.org/abs/2512.15943) — a 350M SLM
reaching ~77.5% on agentic tool-calling via targeted SFT (validates the
program); [Together.ai's multi-turn fine-tuning deep
dive](https://www.together.ai/blog/fine-tuning-llms-for-multi-turn-conversations-a-technical-deep-dive)
— loss masking is standard practice;
[Step Rejection Fine-Tuning (JetBrains,
2026)](https://blog.jetbrains.com/research/2026/06/step-rejection-fine-tuning/)
— recovering learning signal from FAILED agent trajectories;
[RFT](https://rlhfbook.com/c/09-rejection-sampling) — our loop is
structurally rejection-sampling fine-tuning already.

- **Validated (no change):** verified-success-only SFT = the standard
  RFT recipe; our loop already implements it.
- **Post-stabilization (documented, NOT gen-6 — recipe changes would
  confound the corpus-side attribution):** (a) assistant/tool-turn
  loss masking or final-answer down-weighting — the objective-side fix
  for the narrative-over-behavior finding; (b) SRFT-style
  step-rejection to recover signal from our 38+ FAILED trajectories;
  (c) imported datasets remain rejected (format/provenance
  self-consistency is the program's moat).
- **Novel edge:** no surveyed work directly covers premature-final
  recovery demonstrations — gen-6's failure-state demos are the
  program's own contribution.

## Verification

- Premature-final script shape: TWO final responses (the first before
  any edit), the edit after the second run_tests, ends verified.
- Chat records' system prompt contains `Available tools:` with the
  lean catalog entries.
- Live rebuild → export → the human's Colab job → ep6 → `qa verdict`
  vs ep5/ep4 with chaining + premature-final metrics on the table.
