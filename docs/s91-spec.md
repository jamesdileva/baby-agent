# S91 — ep12 corpus: cascade batch 3 + clip restoration

Status: landed 2026-09-25. Corpus + one bundled kit change (human
direction: quality over attribution purity — the architecture
questions are answered, the bundle is judged head-to-head).

## Step 0: cascade pre-verdict (stability data, fluke check)

ep11-q4 cascade-only, n=3, budget 12: **0/3** — but a NEW failure
mode, not the old one: all three runs made **zero tool calls**
(finals were native-JSON-as-text
`{"name": "code_diagnostics", "arguments": {}}` — right tool, right
empty args, wrong envelope — rejected ×12 each). The model knows
the behavior and fumbled the protocol envelope: dialect confusion,
the S64 signature, not fix-capability failure. Cascade band for
ep11 now spans 0–0.33 across two verdicts (1/3, 0/3); rung-3 stays
gated. Batch 3 proceeds regardless (volume is the lever either
way), and every new textual-protocol success teaches the envelope
too.

## Batch 3 (main variable): rung-2 strengthening, fresh modules

Three double-chains — math_ops (subtract/divide), text_ops
(concat/exclaim), list_ops (first/total) — deliberately never
calc_ops, which shares the eval task's module (S80's cascade may
teach the instance more than the capability; string_ops is the
clean generalizer). Same discipline throughout: chain → second
failure → re-diagnose from scratch → final names BOTH fixes.

## Kit s91 (bundled second variable): clip restored

`max_grad_norm=1.0` for 7B again — S89's fp32 adapters pass
`unscale_()` fine, so S88's reason is gone and the standard
guardrail returns (if a run ever dies in the clip path, revert to
0 — one line, documented in the kit). Bonus: a green run with the
clip active confirms the S88/S89 diagnosis by evidence.

## Live

- Lane 10/10 passed, 0 rejected, 0 failed (real store).
- Curate 1172/2/1 (1175 experiences); export 194 = 190
  step-trainable + 4 SRFT — all 10 agent-authored demos present
  exactly once (substring overcounts are older scripted records
  sharing module names, verified).
- Suite 1687 OK, pyflakes clean.

## Colab order

Fresh `training.jsonl` (194 rows) + s91 `train_ep1.py` → ep12 on
the same 7B base → GGUF-LoRA import (S90 pipeline) → head-to-head
verdict ep12 vs ep11-q4, 4 tasks (stability point + exam in one).
