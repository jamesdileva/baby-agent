# S84 — bf16 with a clean audit: the v5 kwarg + setup-time sources

Status: landed 2026-09-25. Kit version `s84`.

## Problem (evidence, from the S83 audit output on Colab)

The S83 run got FURTHER than any 7B attempt: 169 records, mask 0.223,
339/339 weights loaded, 40.3M trainable params — then died at the
first backward with the same bf16 GradScaler error. The audit is the
diagnosis:

- `dtype audit: model.dtype=torch.float32 bf16_params=0` — ZERO bf16
  params pre-LoRA, yet bf16 grads at backward. So bf16 enters DURING
  training setup (LoRA adapters, bnb compute fallback, config
  default), not at load.
- `[transformers] torch_dtype is deprecated! Use dtype instead!` +
  `model.dtype=torch.float32` — the deprecated spelling NO-OPs on
  transformers 5.17 (neither fp16 nor the bf16 default; plain
  float32). Secondary suspect confirmed as live.
- `bnb_4bit_compute_dtype` effective value was never printed — the
  one silent fallback the S83 gate could not see.

## Fix (7B path only; proven 3B string form untouched)

1. **Version-proof dtype kwarg**: `dtype=torch.float16` on
   transformers v5 (signature-sniffed), `torch_dtype` fallback
   otherwise — the next deprecation break is pre-handled.
2. **Explicit config pin**: `model.config.torch_dtype =
   torch.float16` post-load — the bf16 default leaks into adapter
   dtypes and compute fallbacks if left in place.
3. **Extended audit**: effective `bnb_4bit_compute_dtype` from the
   post-load config (dict- or object-form, plus `hf_quantizer`
   fallback) with a bf16 gate on it; second gate post-LoRA censusing
   adapter dtypes (`bf16_lora=`). Either gate firing prints
   versions + the offending list and refuses before the trainer.

## Verification

- Kit pins: `"dtype"`, `config.torch_dtype = torch.float16`,
  `effective bnb_4bit_compute_dtype=`, `bf16_lora=`,
  `DTYPE GATE FAILED` (×3 sites).
- Suite 1687 OK (skipped=4), pyflakes clean.
- Colab rerun pending: fresh runtime, new `train_ep1.py` + 169-row
  `training.jsonl`, keep torchao uninstall. Expected next output is
  EITHER training loss (fixed) OR a gate naming adapters/compute —
  paste it back.
