# S85 — Runtime bf16 hunt: autocast probe + grad census gate

Status: landed 2026-09-25. Kit version `s85`.

## Problem (evidence, from the S84 audit output on Colab)

The S84 run printed a FULLY CLEAN audit and still died:

- `model.dtype=torch.float32`, `config.torch_dtype=torch.float16`,
  `bf16_params=0`
- `effective bnb_4bit_compute_dtype=torch.float16`
- `lora_params=392`, `bf16_lora=0`
- then the same 8-frame GradScaler bf16 death at the first backward.

Clean params + clean adapters + clean compute + bf16 grads ⇒ the
source is RUNTIME, not weights. Prime suspect: the process autocast
default on torch 2.11 (the trainer's autocast context is the one
place left that can mint bf16 from clean inputs).

## Fix (7B path only; 3B proven path untouched)

One micro-batch forward+backward under explicit fp16 autocast BEFORE
the trainer, 7B-only:

1. Print the process default cuda autocast dtype; if bf16, pin fp16
   via `torch.set_autocast_dtype` / `torch.set_autocast_gpu_dtype`
   (whichever exists) for the trainer run.
2. Census grad dtypes BY NAME into a histogram; `GRAD GATE FAILED`
   naming the bf16 offenders, else `zero_grad` + cache clear and
   training proceeds. Either outcome diagnoses: bf16 here under
   fp16-autocast = a rogue explicit-bf16 op (named); clean here +
   trainer crash = the trainer's autocast default is bf16 (pinned
   above for the run).

## Verification

- Kit pins: `autocast probe`, `get_autocast_dtype`,
  `grad dtype histogram=`, `GRAD GATE FAILED`.
- Suite 1687 OK (skipped=4), pyflakes clean.
- Colab rerun pending: fresh runtime, new `train_ep1.py` +
  169-row `training.jsonl`. The new `autocast probe:` lines are the
  ones to paste back.
