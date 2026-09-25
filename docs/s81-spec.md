# S81 — 7B T4 OOM Fix: Lean k-bit Prepare + Batch 1

Status: landed 2026-09-25. Kit version `s81`.

## Problem (evidence)

Colab T4 (14.56 GiB) running
`%run train_ep1.py ep11 Qwen/Qwen2.5-Coder-7B-Instruct` died in
`peft.utils.other.prepare_model_for_kbit_training` at
`param.data = param.data.to(torch.float32)`:
tried 2.03 GiB with 1.72 free, 12.84 in use (12.56 allocated).
This is the error AFTER the S79 bf16 fix (`torch_dtype="float16"`)
landed — the run got past the GradScaler crash into the prepare peak.

Known mechanism (peft #3265/#3293, bnb #1569): the full prepare
upcasts norms to fp32 (+0.5–1 GB transient) and the allocator cache
holds the peak. On a 15 GB T4 with 12+ GB already allocated, the
upcast is the load-bearing allocation. 12.5 GB pre-prepare also
points at a stale runtime (re-run without restart) and fragmentation
(the error itself suggests `expandable_segments:True`).

## Fix (7B path only, 3B untouched)

1. **Lean prepare**: `prepare_model_for_kbit_training(...,
   use_gradient_checkpointing=False)`, then
   `model.gradient_checkpointing_enable(use_reentrant=False)` +
   `model.config.use_cache = False` + `empty_cache()` before/after
   (with `gc.collect()`). Maintainer-sanctioned for constrained GPUs;
   trades the fp32-norm stability margin for fitting.
2. **Checkpointing on for 7B**: `SFTConfig(gradient_checkpointing=True)`
   (was `not SEVEN_B` = off — the hungriest path had the main
   activation saver disabled).
3. **Batch 1 x accum 8** for 7B (was 2 x 4; same effective batch),
   keep `paged_adamw_32bit`, `fp16`, nf4 + double quant, masking,
   gates, disk fixups.
4. **Fail loudly**: no silent 3B fallback — preserves the S79
   attribution (`ep11-7b vs ep10-3b` isolates base size).
5. **Runbook in README** (template-generated): restart runtime first,
   `%env PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`,
   `!pip install bitsandbytes`.

## Verification

- Kit pins: `use_gradient_checkpointing=False`,
  `gradient_checkpointing_enable`, `use_cache = False`,
  `empty_cache()`, `expandable_segments` in README.
- Suite 1687 OK (skipped=4), pyflakes clean.
- Colab rerun pending: fresh runtime → ep11-merged → sanity gate →
  GGUF → `qa verdict --models baby-agent:ep11,baby-agent:ep10` (n=3 x 4).

## Honest notes

- Lean prepare skips PEFT's default fp32-norm upcast; if loss is
  unstable, the documented alternative is full prepare + CPU offload
  (`max_memory`), still 7B-only.
- Same corpus-v8 + agent-authored lane, same 4-task ladder; S80 ladder
  gates unchanged (rungs 3+ gated on rung 2 stability).
