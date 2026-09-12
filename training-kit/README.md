# baby-agent:ep1 training kit

qacompanion stays stdlib-only — this kit runs on EXTERNAL free compute
(no billing, same ruling as the Gemini free tier):

- **Google Colab** (free T4): upload `training.jsonl` +
  `train_ep1.py`, `pip install -U transformers peft datasets trl
  bitsandbytes`, run the script.
- **Kaggle** (free 30 GPU-hours/week): same two files, P100/T4 kernel.

## The loop (roadmap §S64)

1. `qa curate && qa build-training` in the repo -> `training/training.jsonl`
2. train on external compute -> LoRA adapter
3. merge adapter -> GGUF -> `ollama create baby-agent:ep1 -f Modelfile`
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
