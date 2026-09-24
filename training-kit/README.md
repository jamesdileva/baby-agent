# baby-agent:ep1 training kit

qacompanion stays stdlib-only — this kit runs on EXTERNAL free compute
(no billing, same ruling as the Gemini free tier):

- **Google Colab** (free T4): upload `training.jsonl` +
  `train_ep1.py` via the FILES PANEL (left sidebar folder icon — NOT
  into a cell), then:
    `!pip install -U transformers peft datasets trl accelerate`
    `!pip uninstall -y torchao`   # Colab ships an old torchao; recent
    # peft RAISES on it instead of ignoring it (optional dependency)
    `%run train_ep1.py`
- **Kaggle** (free 30 GPU-hours/week): same two files, P100/T4 kernel.

## After training (script outputs `ep1-merged/`)

**ollama 0.34.4+ dropped direct safetensors import (MLX-only converter)
and the old quantize types — conversion through llama.cpp is now
REQUIRED** (verified 2026-09-24; see docs/s76-spec.md):

1. Zip and download (Colab):
    `!zip -r epN-merged.zip epN-merged`
2. Convert to GGUF (same Colab session, before or after download —
   the converter is pure Python, no build):
    `!pip install gguf`
    `!git clone --depth 1 https://github.com/ggml-org/llama.cpp`
    `!python llama.cpp/convert_hf_to_gguf.py epN-merged \
        --outfile epN.gguf --outtype q8_0`
   (q8_0 ≈ half the fp16 size, negligible quality cost. Optional
   speed step: q4_K_M via a prebuilt llama-quantize binary from
   llama.cpp releases — `llama-quantize epN.gguf epN-q4.gguf q4_K_M`.)
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
