# S86 — Failure-path census: naming the bf16 tensor in situ

Status: landed 2026-09-25. Kit version `s86`.

## Problem (evidence, from the S85 probe output on Colab)

The S85 probe closed every weight-side door and the crash persisted:

- autocast default = `torch.float16` (not bf16)
- grad histogram under explicit fp16 autocast: 392 grads, ALL fp32
- then the same 8-frame GradScaler bf16 death.

Plus a hard constraint from the tool: Colab collapses the middle
traceback frames, so the crash SITE is unreadable — only `main()` and
`grad_scaler.py` are visible. Blind fixing is exhausted; the next
failure must diagnose itself.

## Fix (7B path only; 3B proven path untouched)

1. **Always-on precision flags** before training: `fp16=`, `bf16=`,
   `half_precision_backend=`, `accelerator.mixed_precision`,
   scaler enabled — the trainer/accelerator config is the last
   unobserved actor, now observed.
2. **Failure-path census**: `trainer.train()` wrapped in
   `try/except NotImplementedError` — on catch, print the param
   dtype histogram, every bf16 param BY NAME, the grad dtype
   histogram, every bf16 grad BY NAME, autocast default +
   config dtype, then re-raise (fail-loud preserved). Zero cost when
   green; the whole diagnosis when red. No more collapsed frames.

## Verification

- Kit pins: `FAILURE CENSUS`, `precision flags:`, `bf16 grad:`,
  `mixed_precision`.
- Suite 1687 OK (skipped=4), pyflakes clean.
- Colab rerun pending: fresh runtime, new `train_ep1.py` +
  169-row `training.jsonl`. Paste back the `precision flags:` line
  and, if it fires, the `FAILURE CENSUS` block — the bf16 tensor's
  name ends the hunt.
