# S76 — Gen-8: Assistant-Only Loss + the Import Pipeline Migration

Status: scoped 2026-09-24. Two changes, both kit-side — the corpus
stays frozen at v6, so the training DATA for gen-8 is byte-identical
to gen-7's and the only variable is the objective.

## Attribution (the standing rule)

- **Gen-8 = loss masking ONLY.** SRFT (failed-trajectory signal) is a
  dataset-recipe change and would confound an objective change — it is
  gen-9's single variable, judged against gen-8's rate-based baseline.
- The ollama import migration (below) is forced tooling, not a
  generation variable.

## 1. Assistant-only loss (the gen-5 mechanism fix)

Gen-5's verdict: SFT rewarded the REPORT of success over the process —
the final-answer narrative was the easiest sequence to imitate. The
structural reason: ~60-70% of every training record's tokens are
user/tool-observation turns, so most of the gradient mass teaches the
model to predict ENVIRONMENT output (useless at inference), and
imitation concentrates on whatever narrative text remains.

Fix (the literature-standard objective-side answer, per the S72 survey
— Together.ai multi-turn fine-tuning deep dive): train ONLY on
assistant-turn tokens. The kit script builds per-token labels with
non-assistant spans set to -100:

- system prompt: masked (context, not behavior)
- user goal: masked
- assistant [TOOL: ...] turns: TRAINED (the actions)
- user observation turns: masked (environment, not behavior)
- assistant final answers: TRAINED (with the <|im_end|> stop token, so
  stopping stays learned)

Concentrating the loss on actions shifts imitation toward doing. The
script prints a mask-ratio sanity gate (refuses to train at <10%
assistant tokens — a broken mask would otherwise train on nothing) —
the same refuse-to-ship-degenerate discipline as the sanity generation.

## 2. Import pipeline migration (forced by ollama 0.34.4)

Verified 2026-09-24 against the installed ollama: `ollama create` from
a safetensors directory now routes through the MLX importer and
REJECTS Qwen2ForCausalLM; `--quantize q4_K_M` no longer exists
(int4/int8/nvfp4/mxfp4 only). Per the release notes, safetensors
conversion is now llama.cpp tooling.

New post-training flow (README + ModelFile):
- Colab: `pip install gguf`, clone llama.cpp (converter is pure
  Python — no build), `convert_hf_to_gguf.py epN-merged --outfile
  epN.gguf --outtype q8_0` (half the fp16 download size, negligible
  quality cost; q4_K_M via prebuilt `llama-quantize` documented as the
  optional speed step)
- Local: `ollama create baby-agent:epN` with `FROM ./epN.gguf`
- The committed ModelFile recipe updates to the GGUF form

## Deliberately deferred

- SRFT (gen-9): mine the 46+ recorded FAILED trajectories for
  step-level signal per the JetBrains recipe.
- Fine-grained final-answer down-weighting (masking v2) — only if
  gen-8's rates show finals still over-imitated relative to calls.
- Ollama structured-output/thinking changes: not applicable to the
  epN family (Qwen2.5-Coder-3B is a non-thinking model).

## Verification

- Kit pins: the mask code (-100, role check, ratio gate) present in
  the generated script; README documents the llama.cpp path; ModelFile
  is GGUF-form.
- The human's Colab run: mask-ratio printout + sanity generation gate,
  then llama.cpp convert, `ollama create`, and
  `qa verdict --models baby-agent:ep8-q4,baby-agent:ep7-q4`
  (repetitions=3, budget 12) — same data, same base, one objective
  variable.
