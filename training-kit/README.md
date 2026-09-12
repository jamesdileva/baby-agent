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

1. Zip and download it (Colab):
    `!zip -r ep1-merged.zip ep1-merged`
2. On your PC, turn it into an ollama model — ollama reads the
   safetensors directory directly (Qwen2 architecture is supported):
       Modelfile:  FROM ./ep1-merged
       `ollama create baby-agent:ep1 -f Modelfile`
3. GGUF fallback (if your ollama version refuses): llama.cpp's
   `convert_hf_to_gguf.py ep1-merged --outfile ep1-f16.gguf
   --outtype f16`, then `FROM ./ep1-f16.gguf` in the Modelfile.
4. evaluate HONESTLY with the repo harness (S57):
   base vs ep1 on the identical model x task cross product;
   `compare()` flags regressions AND improvements per task
5. a generation that forgets old lessons is documented, not shipped
   silently (roadmap honesty rule)

## Provenance

The corpus is tagged: `scripted-demo` records are scripted curriculum
demonstrations (real loop, real test execution, declared defects);
model-tagged records come from real provider runs. ep1 trained on
scripted demos teaches protocol and procedure — the S55 finding says
that is exactly what general small models lack.
