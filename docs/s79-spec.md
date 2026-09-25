# S79 — Base-Model Step-Up: Qwen2.5-Coder-7B

Status: scoped 2026-09-25. The research-backed move (see the roadmap
S79 section and the S72 survey): ~8B models reach state-of-the-art
tool-calling in constrained agentic workflows, and the program's own
scaling curve (1.5B fails everything → 3B solves calculator) says the
wall moves with scale. Same family, same tokenizer, same template
family — every known fixup carries over.

## Attribution (unchanged rule)

Same corpus (v8), same harness, same 4-task ladder. **ep11-7b vs
ep10-3b isolates the base-size variable.** Improvement is measured,
never assumed; a regression on any task is documented, not shipped.

## Kit changes (the only code surface)

1. **Base model as a script argument**: `python train_ep1.py ep11
   Qwen/Qwen2.5-Coder-7B-Instruct` — argv[2] overrides BASE_MODEL
   (default stays 3B so nothing breaks).
2. **QLoRA for 7B memory** (7B fp16 ≈ 14GB does not fit the free
   T4's 16GB with activations): `load_in_4bit` + nf4 + double
   quantization + `prepare_model_for_kbit_training` +
   `paged_adamw_32bit` — the standard free-T4 7B setup (Unsloth /
   LLaMA-Factory / DecodingML notebooks all run it).
3. **Everything else unchanged and verified carry-over**:
   assistant-only masking (same tokenizer/vocab across the family),
   the disk fixup (Qwen2.5-7B also ties embeddings — the fixup is
   already conditional on lm_head absence), legacy rope_theta patch,
   mask-ratio gate, sanity generation gate, generation-name argv.

## Import + conversion (the 0.34.4 world)

`convert_hf_to_gguf.py ep11-merged --outfile ep11.gguf --outtype
q8_0` (~8.1GB download) — or the smaller path: convert f16 then
`llama-quantize` to q4_K_M (~4.7GB, prebuilt linux binary from
llama.cpp releases, no compile). Optional experiment: `ollama create
--quantize int4` on the q8_0 GGUF (new v0.34.4 quantize types).
README documents both; Modelfile unchanged (FROM ./ep11.gguf).

## Inference reality (accepted)

qwen2.5-coder:7b q4 ≈ 4.7GB — the host runs llama3.1:8B today.
Slower tokens per second are explicitly deprioritized by the human;
agent loops take longer per verdict (the n=3 x 4-task verdict grows
correspondingly — run it unattended).

## Verification

- Kit pins: 4-bit loading present when argv[2] names a 7B base, mask
  machinery untouched, fixup conditional-untie logic present.
- The human's Colab job → ep11.gguf → local import → sanity probe →
  `qa verdict --models baby-agent:ep11,baby-agent:ep10 --tasks 4` —
  the scaling ledger records 1.5B → 3B → 7B on the identical ladder.
