# S94 — Strings-repair batch (Branch B of the ep13 fork)

Status: landed 2026-09-26. Corpus-only change; kit untouched (s92,
clip 0 stays — no churn on noise). Nothing for Colab to reuse: the
export is NEW (299 rows), so Colab uploads the fresh files.

## The fork resolution (Step 0)

Full 5-task ep13-q4 pinned verdict (temp 0 / seed 42):
calc 3/3, **strings 0/3 (deterministic, all max-iters)**,
json 3/3, cascade 3/3, **indirect 3/3 with zero demos** → 12/15.
ep13-strings flickering (1/3 then 0/3) while ep11 holds 3s, with
the clip OFF, doubly exonerates the clip for strings → **Branch B:
dilution confirmed**. Supporting count: authored batches added 5
json + 5 cascade drills and ZERO string drills (scripted
string_reverse sits at volume 1) — strings is the thinnest volume
in the modern corpus. Bonus findings: cascade 3/3 again
(stabilizing: 1/3 → 3/3 → 3/3), and rung-3 indirect solved
zero-shot (first pinned point, no demos — transfer, not luck, but
one point only).

## Batch (the variable)

Three string drills on fresh modules with fixture-inference
narratives (the test's expected value teaches the shape — the
recipe that broke the json wall): greeting (dropped name),
word_ops (empty join), text_utils (untouched input, with a genuine
wrong-turn read for the set's recovery beat). Validator + gate,
goal identity, finals naming touched files.

## Live

- Lane 13/13 passed, 0 rejected, 0 failed (real store).
- Curate 1302/2/1 (1305 experiences); export 299 = 294
  step-trainable + 5 SRFT — all 13 agent-authored demos present
  exactly once (an early scare was my own grep keys, not the
  export: two goals don't carry literal module names — distinct
  full texts, no dedupe collapse).
- Composition note: the export grew 194 → 299 mostly on recorded
  verdict successes (S41-gated, legitimate per the drip
  philosophy — but watched: eval-shaped trajectories now dominate).
- Suite 1695 OK (1687 + 8), pyflakes clean.

## Colab order

Fresh `training/training.jsonl` (299 rows) + s92 `train_ep1.py`
(UNCHANGED kit) → ep14, same 7B base → GGUF-LoRA import →
pinned head-to-head vs ep11-q4 (ep12/ep13 ride along if cheap).
Crown rule stands: confirmation required, never a single n=3.
