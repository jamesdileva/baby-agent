# S83 — Colab bf16, second strike: dtype objects + audit gate

Status: landed 2026-09-25. Kit version `s83`.

## Problem (evidence)

Colab kept throwing the SAME `NotImplementedError:
_amp_foreach_non_finite_check_and_unscale_cuda not implemented for
'BFloat16'` — against `/content/train_ep1.py:324-326`, which matches
the 326-line S81 kit file exactly. So Colab WAS running the current
file: the S79 `torch_dtype="float16"` fix is in it and is NOT
sufficient. The GradScaler trace names no module, so the fix was
shooting blind.

Prime suspect (visible in the kit): `bnb_4bit_compute_dtype` was the
STRING `"float16"`, not a `torch.dtype`. The 3B path proves the
`from_pretrained` string form works (ep8/9/10 trained) — there is no
such proof for the bnb compute-dtype string. If the installed
bitsandbytes stores it unconverted, dequant compute falls back to the
model default — Qwen2.5-7B's config default is bf16 — and bf16
activations/adapter grads reach the fp16 GradScaler: exactly this
crash. (Secondary suspect, same class: transformers v5 deprecating
`torch_dtype` → `dtype`.)

## Fix (7B path only; proven 3B string form untouched)

1. **Real dtype objects**: `import torch` in `main()`;
   `bnb_4bit_compute_dtype=torch.float16`,
   `torch_dtype=torch.float16`.
2. **Dtype audit gate, fail-loud, Colab-observable**: after load +
   prepare, BEFORE LoRA/training, print transformers/peft/torch/
   bitsandbytes versions, `model.dtype`, and every bf16 param
   (capped at 10 lines); `sys.exit("DTYPE GATE FAILED ...")` on any
   bf16. The next Colab failure — if any — names its culprit directly
   instead of dying 8 frames deep in torch/amp.

## Unchanged

S81 lean prepare, batch 1 x accum 8, checkpointing on, 7B-only
fail-loud, torchao stays an uninstall line in the README runbook (it
was already there; the script never imports it).

## Verification

- Kit pins: `bnb_4bit_compute_dtype=torch.float16`,
  `torch_dtype=torch.float16`, `bf16_params=`, `DTYPE GATE FAILED`.
- Suite 1687 OK (skipped=4), pyflakes clean.
- Colab rerun pending: fresh runtime, new `train_ep1.py` + 169-row
  `training.jsonl`, keep `!pip uninstall -y torchao`. If the gate
  fires, paste the versions + bf16 list back — that output IS the
  diagnosis.
