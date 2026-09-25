# S89 — Adapters to fp32: the only dtype the clip path accepts

Status: landed 2026-09-25. Kit version `s89`.

## The deduction (S88 census on Colab)

The S88 run printed the complete truth table:

- cast held: `param histogram={float32: 59, uint8: 196, float16: 476}`
  (476 = 392 adapters + 84), zero bf16 anywhere
- `grad histogram={float16: 392}` — the S87 fp16 cast produced fp16
  grads, as designed
- crash MOVED to `_get_grad_norm → clip_grad_norm_(inf) →
  unscale_ → ValueError: Attempting to unscale FP16 gradients`
  (the S88 `max_grad_norm=0` skipped only the first of TWO clip
  calls — the norm-logging call clips unconditionally)

So torch 2.11's `unscale_()` accepts exactly one grad dtype on this
path: fp32 (fp16 raises ValueError, bf16 has no sm75 kernel). The
S87 fp16 target moved sideways (NotImplementedError →
ValueError), not forward. The fix is the third dtype: fp32 — the
standard mixed-precision master-weight recipe (fp32 weights, fp16
compute), 161MB for 40M params.

## Fix (7B path only; 3B untouched)

Cast every `lora_` param to `torch.float32` after SFTTrainer
construction (post-construction casts stick — the S87 fp16 census
held). `max_grad_norm=0` stays (one change per slice; the inf-clip
in `_get_grad_norm` now passes with fp32 grads; restoring 1.0 is a
candidate follow-up once ep11 trains).

## Verification

- Kit pins: `lora params -> torch.float32`.
- Suite 1687 OK (skipped=4), pyflakes clean.
- Colab rerun pending: fresh runtime, new `train_ep1.py` +
  169-row `training.jsonl`. Expected: `adapter cast: 392 lora
  params -> torch.float32`, then step/loss logs.
