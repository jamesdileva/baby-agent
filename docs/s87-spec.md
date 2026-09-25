# S87 — The census convicts: post-construction adapter cast to fp16

Status: landed 2026-09-25. Kit version `s87`.

## The conviction (S86 census output on Colab)

The failure census named all 392 offenders:

- `param dtype histogram={float32: 59, uint8: 196, float16: 84,
  bfloat16: 392}` — every `...lora_A/B.default.weight` bf16
- `grad dtype histogram={bfloat16: 392}` — same 392
- `autocast default=torch.float16`, `config.torch_dtype=torch.float16`

Against the earlier gates: adapters were fp32 at the S85 probe
(392 fp32 grads) and bf16 at the first clip. Nothing in torch
mutates param dtype during forward/backward, and the pasted
`train()` frames show no prep of their own — so the fp32→bf16 cast
happens inside SFTTrainer construction/prepare. Case closed on the
*site*; the *motive* (which 5.17/peft-0.21 path prefers bf16) no
longer matters.

## Fix (7B path only; 3B proven path untouched)

Cast every `lora_` param to fp16 AFTER SFTTrainer construction with
an attesting print (`adapter cast: N lora params -> torch.float16`).
Post-construction placement covers the caster wherever it sits in
setup; fp16 adapters match the proven 3B recipe. Also fixed the
precision-flags probe live: SFTConfig on 5.17 has NO
`half_precision_backend` (getattr-guarded) — that flag will
actually print next run.

## Verification

- Kit pins: `adapter cast:`, `lora params -> torch.float16`.
- Suite 1687 OK (skipped=4), pyflakes clean.
- Colab rerun pending: fresh runtime, new `train_ep1.py` +
  169-row `training.jsonl`. Watch for `adapter cast: 392 ...` then
  training loss. If the census ever fires again, its histogram
  tells us whether the cast held.
