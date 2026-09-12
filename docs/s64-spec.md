# S64 — Baby-Agent Ep1 (corpus first; training hardware-gated)

Status: scoped 2026-09-11. Roadmap: docs/ROADMAP-agentlite.md §S64.

## Objective

Resurrect the generations idea now that data quality (S62) and the
training pipeline (S63) exist. The ep1 process from the roadmap:

```text
real agent sessions + apprenticeship corpus + demos
-> curate -> training dataset -> fine-tune / adapt
-> baby-agent:ep1 -> benchmark -> improvement? (yes/no)
```

The S55 finding defines ep1's purpose: the training data teaches the
textual tool protocol that general small models lack — the unlock for
local brains, which retesting (this sprint, below) still confirms are
latency-bound, not plumbing-bound.

## Hardware finding (probed 2026-09-11)

The machine has an **AMD Radeon RX 6400 (4 GB, RDNA2, no CUDA)**.
Local fine-tuning is impractical: ROCm-on-Windows for RDNA2 is not a
usable training stack and 4 GB is below QLoRA working size for even a
2B base. The free-tier Gemini daily caps (20 requests/day/model) also
cap model-generated data at a few benchmark passes per day. This does
NOT block S64 — it changes the order:

1. **Corpus** (this sprint, hermetic, no LLM, no quota): generate
   verified step-trainable demonstrations through the REAL loop and
   REAL test execution, honestly labeled.
2. **Training kit** (this sprint): a self-contained fine-tuning script
   + instructions the human can run on free external compute (Colab /
   Kaggle — no billing, same ruling as Gemini free tier). The script
   lives in the repo as an artifact; qacompanion itself gains no
   third-party dependency.
3. **ep1 evaluation** (harness already exists — S57
   `run_evaluation` + `compare()`): base vs ep1 on the identical model ×
   task cross product; regressions documented; no improvement = the
   attempt is recorded as failed (roadmap honesty rule).
4. **ep0.5 adaptation** (slice 2, no gradients): retrieval-
   injection of full step-trainable demonstrations into the loop for
   similar goals — measurable on any provider today.

## Slice 2 — ep0.5 demonstration injection (no GPU, no quota)

The adaptation half of "fine-tune / adapt": when the retriever surfaces
a VERIFIED experience that carries captured steps, the context assembly
renders it as a full worked example (goal → `[TOOL: ...]` steps with
observation heads → final answer) inside the memory block. The model
learns by imitation-in-context instead of gradient updates.

- `ep1.format_demonstration(...)` renders the block (bounded: ≤6 steps,
  capped chars, provenance-labeled with the model tag).
- `MemoryLayer` experience results carry `steps` / `final_answer` /
  `model` additively (legacy data has none — byte-identical behavior).
- `MemoryRetriever(demonstrations=True by default)`: only SUCCESS-
  outcome, step-carrying experiences render as worked examples;
  everything else stays a one-line summary.
- `run_benchmark` gains additive `context_builder=None` passthrough for
  the A/B harness.
- **Acceptance experiment (human-directed):** qwen3:4b benchmark WITHOUT
  injection (already recorded: failed, 883.5 s, 6 iterations) vs WITH —
  the corpus's calculator demonstration matches the benchmark goal.
  Honest outcome either way.

## Slice 3 — dashboard brain selection

The S52 server's default provider factory builds an OllamaProvider
(the latency-bound locals). Additive: `QA_AGENT_PROVIDER=gemini`
selects GeminiModelProvider so a dashboard session shows a working
brain; default unchanged.

## Corpus generation (deterministic demonstrations)

The S60 curriculum declares its defects BY CONSTRUCTION
(`_bug_fix_fixture` variant table: module, function, correct body,
defective body, test case) and S57's benchmark runs them through the
real S37 loop with real subprocess test execution. Combining them:
`qacompanion/agent/ep1.py` runs scripted demonstrator providers over
the bug_fix variants × levels (+ the three S57 default fixtures):

- the demonstrator inspects → runs tests (fail) → edits the DECLARED
  defect (real old_string/new_string from the variant table) → runs
  tests (pass) → states the diagnosis as its final answer;
- every run goes through `run_benchmark` with the S41 verification
  gate, so only genuinely-passing demonstrations become records;
- recordings carry the S63 session-unique suffix and an honest
  `scripted-demo` model tag — the corpus teaches protocol and
  procedure, and its provenance says exactly what it is;
- `build_corpus(...)` → S63's curate + build-training chain →
  `training.jsonl`. Seeded and deterministic; same seed = identical
  corpus.

Scope note: the bug_fix family + the three default fixtures are the
seed corpus. Other curriculum categories (feature_add, build_repair,
dependency) need per-category demonstrators — a follow-up slice, listed
honestly in the report.

## Training kit (external compute)

`training-kit/train_ep1.py` + `training-kit/README.md`: single-file
QLoRA SFT over the exported `training.jsonl` (chat format from S63),
base model = Qwen2.5-Coder-3B-Instruct (the runtime's local family),
documented dependencies (transformers/peft/datasets/trl — installed in
the training environment only, never in qacompanion). The README
documents the full loop: export dataset → train → produce
`baby-agent:ep1` GGUF → `ollama create` → evaluate with
`run_evaluation([base, ep1])` → `compare()` decides improvement
honestly.

## Local retest (this sprint, human-directed)

Brief qwen3:4b retest on the S48 benchmark (lean catalog, native-only
prompting, OLLAMA_THINK=false, 300s/turn, 6 iterations): the isolated
2-tool native probe still works (correct call, ~83 s/turn on CPU).
The benchmark run's outcome is recorded as data either way — the S63
capture makes a failure a full trajectory. Expectation per S55:
latency-bound, not plumbing-bound.

## Pins

- Only genuinely-verified demonstrations enter the corpus (the S41
  gate is the proof, the S63 gate is the filter).
- Provenance is honest: scripted demos are labeled scripted; model-
  generated demos are labeled with the model.
- ep1 is never assumed better: the S57 compare() verdict is the only
  acceptance surface.
- qacompanion stays stdlib-only; training tooling lives outside it.

## Verification

1. Corpus builder: deterministic, hermetic tests; a seeded run produces
   records that all pass curation eligibility and are step-trainable.
2. Training kit: file generation tested (dataset path, README
   instructions present, script imports nothing from qacompanion).
3. The retest lands as recorded data with honest metrics either way.
