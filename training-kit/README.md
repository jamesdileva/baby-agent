# baby-agent:ep1 training kit

qacompanion stays stdlib-only — this kit runs on EXTERNAL free compute
(no billing, same ruling as the Gemini free tier):

- **Google Colab** (free T4): upload `training.jsonl` +
  `train_ep1.py` via the FILES PANEL (left sidebar folder icon — NOT
  into a cell), then:
    `!pip install -U transformers peft datasets trl accelerate`
    `!pip uninstall -y torchao`   # Colab ships an old torchao; recent
    # peft RAISES on it instead of ignoring it (optional dependency)
    `%run train_ep1.py ep10`   (arg 1 names the generation — outputs
    land in ep10-adapter/ and ep10-merged/; default: ep1)
    `%run train_ep1.py ep11 Qwen/Qwen2.5-Coder-7B-Instruct`   (S79:
    arg 2 selects the base — 7B trains in 4-bit QLoRA on the T4; add
    `!pip install bitsandbytes` for the 4-bit path)
    S81 7B OOM runbook (T4 15GB): Runtime → Restart runtime first
    (a re-run in the same runtime keeps the old model allocated);
    `%env PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`;
    7B runs batch 1 x accum 8 with checkpointing (slower, fits).
- **Kaggle** (free 30 GPU-hours/week): same two files, P100/T4 kernel.

## After training (script outputs `ep1-merged/`)

**ollama 0.34.4+ dropped direct safetensors import (MLX-only converter)
and the old quantize types — conversion through llama.cpp is now
REQUIRED** (verified 2026-09-24; see docs/s76-spec.md):

1. Zip and download (Colab):
    `!zip -r epN-merged.zip epN-merged`
    `!zip -r epN-adapter.zip epN-adapter`   (S90: the 7B import path
    needs the ADAPTER dir — keep it)
2. Convert to GGUF (same Colab session, before or after download —
   the converter is pure Python, no build):
    `!pip install gguf`
    `!git clone --depth 1 https://github.com/ggml-org/llama.cpp`
    3B path (fp16 merged dir converts directly):
    `!python llama.cpp/convert_hf_to_gguf.py epN-merged \
        --outfile epN.gguf --outtype q8_0`
    (q8_0 ≈ half the fp16 size, negligible quality cost. Optional
    speed step: q4_K_M via a prebuilt llama-quantize binary from
    llama.cpp releases — `llama-quantize epN.gguf epN-q4.gguf q4_K_M`.)
    7B path (S90: the merged dir keeps bnb quantization, which the
    converter refuses — full fp16 dequant is 15.2GB and fits neither
    the T4 nor free-Colab RAM — so merge at the GGUF level, which
    streams and never materializes 15GB; no retraining, the adapter
    dir is the import artifact):
    `!python llama.cpp/convert_hf_to_gguf.py <base-HF-dir> \
        --outfile base.gguf --outtype f16`   (base weights dir;
    reuses the training download from the HF cache when present)
    `!python llama.cpp/convert_lora_to_gguf.py epN-adapter \
        --outfile epN-lora.gguf`   (needs only the base CONFIG —
    fetched from the hub via adapter_config.json; our adapters
    touch no embeddings so the tied-head restriction does not apply)
    `!cmake -B llama.cpp/build -S llama.cpp` then
    `!cmake --build llama.cpp/build --target llama-export-lora -j`
    (CPU build is fine — one-shot merge, no GPU needed)
    `!llama.cpp/build/bin/llama-export-lora -m base.gguf \
        --lora epN-lora.gguf -o epN.gguf`
    (then optional `llama-quantize epN.gguf epN-q4.gguf q4_K_M` —
    q8_0 ≈ 8.1GB, q4_K_M ≈ 4.7GB for 7B)
3. Download `epN.gguf`, then locally:
       Modelfile:  FROM ./epN.gguf
       `ollama create baby-agent:epN -f Modelfile`
4. evaluate HONESTLY with the repo harness:
   `qa verdict --models baby-agent:epN-q4,<previous-gen>-q4`
   (repetitions=3, budget 12) — per-task success rates + protocol
   metrics; regressions are called out, never shipped silently
5. a generation that forgets old lessons is documented, not shipped
   silently (roadmap honesty rule)

## Provenance

The corpus is tagged: `scripted-demo` records are scripted curriculum
demonstrations (real loop, real test execution, declared defects);
model-tagged records come from real provider runs. ep1 trained on
scripted demos teaches protocol and procedure — the S55 finding says
that is exactly what general small models lack.
