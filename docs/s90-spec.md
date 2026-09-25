# S90 — 7B import via the GGUF-LoRA merge pipeline (no 15GB dequant)

Status: landed 2026-09-25. Kit version `s90`.

## The news

Training RAN (S89 closed the dtype saga). The failure moved to
import: `convert_hf_to_gguf.py ep11-merged` dies with
`NotImplementedError: Quant method is not yet supported:
'bitsandbytes'` — the merged dir keeps bnb Linear4bit layers +
`quantization_config`. And NO, it is not the `q8_0` outtype: the
converter refuses the INPUT before quantizing anything.

## Why not just dequantize the merged dir

Full fp16 7B = 15.2GB (per the Colab download log). That fits
neither the T4 (14.56GB) nor free-Colab CPU RAM (~12.7GB). A
script-side full dequant would trade a converter error for an OOM.

## The path (verified against current llama.cpp)

Merge at the GGUF level, which streams and never materializes 15GB.
No retraining — the `epN-adapter` dir is the import artifact:

1. Base weights → GGUF f16:
   `convert_hf_to_gguf.py <base-HF-dir> --outfile base.gguf
   --outtype f16` (reuses the training download from the HF cache)
2. Adapter → GGUF LoRA: `convert_lora_to_gguf.py epN-adapter
   --outfile epN-lora.gguf` (needs only the base CONFIG from the
   hub; our adapters touch q/k/v/o/gate/up/down only, so the
   tied-embedding lm_head restriction does not apply)
3. Build once (CPU is fine, one-shot):
   `cmake -B llama.cpp/build -S llama.cpp &&
   cmake --build llama.cpp/build --target llama-export-lora -j`
4. Merge: `llama-export-lora -m base.gguf --lora epN-lora.gguf
   -o epN.gguf`, then optional `llama-quantize` (q8_0 ≈ 8.1GB,
   q4_K_M ≈ 4.7GB for 7B)

## Kit changes (7B path; 3B direct-convert untouched)

- Post-merge census: surviving `Linear4bit` count +
  `quantization_config` presence printed; if either remains, the
  run SAYS the dir is not directly convertible and points at the
  pipeline (no silent broken artifact).
- Config fixup strips a STALE `quantization_config` only when zero
  Linear4bit survived (tensors already fp16, config alone would
  refuse conversion).
- README convert section split: 3B direct path vs 7B GGUF-LoRA
  path; adapter zip step added.

## Verification

- Kit pins: `merge census:`, `Linear4bit`, stale-config pop,
  `convert_lora_to_gguf.py` + `llama-export-lora` in README.
- Suite 1687 OK (skipped=4), pyflakes clean.
- Live convert pending on Colab (existing ep11-adapter, no
  retraining).
