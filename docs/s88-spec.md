# S88 — The clip path is the killer: no grad clipping on 7B

Status: landed 2026-09-25. Kit version `s88`.

## The turn (S87 Colab output)

The S87 cast worked — `adapter cast: 392 lora params -> torch.float16`,
`accelerator.mixed_precision=fp16`, `scaler_enabled=True` — and the
error CHANGED to something that names the mechanism:

```
grad_scaler.py:274-275: if (not allow_fp16) and
    param.grad.dtype == torch.float16:
    raise ValueError("Attempting to unscale FP16 gradients.")
```

Called from `trainer._clip_grad_norm →
accelerator.clip_grad_norm_ → unscale_gradients → scaler.unscale_()`
with `allow_fp16=False`. So on torch 2.11, `GradScaler.unscale_()`
(the grad-clip path) REJECTS fp16 grads — only `scaler.step()`
(`allow_fp16=True`) accepts them. The bf16 saga is over (adapters
are fp16 now); what kills the run is the CLIP calling the wrong
unscale entry point. The bf16 world never sees this because bf16
training uses no scaler at all — fp16-on-T4 is the dusty corner.

## Fix (7B path only; 3B keeps its proven 1.0)

`max_grad_norm=(0 if SEVEN_B else 1.0)`: the trainer skips
`_clip_grad_norm` entirely at 0, so `unscale_()` is never called and
`scaler.step()` (fp16-clean) does the unscaling. Clipping is a
stability nicety, not a requirement at lr 2e-4 LoRA — documented,
not hidden. Census broadened to `(NotImplementedError, ValueError)`
for the same fail-loud treatment.

## Verification

- Kit pins: `max_grad_norm=(0 if SEVEN_B else 1.0)`,
  `except (NotImplementedError, ValueError):`.
- Suite 1687 OK (skipped=4), pyflakes clean.
- Colab rerun pending: fresh runtime, new `train_ep1.py` +
  169-row `training.jsonl`. Expected: step/loss logs, no clip crash.
