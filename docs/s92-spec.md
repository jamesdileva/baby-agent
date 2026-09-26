# S92 — Clip revert: the clean clip-effect test

Status: landed 2026-09-26. Kit version `s92`. Corpus unchanged from
S91 (194-row export stands).

## Why (the S91.1 conviction)

Gen-12 verdict: ep12 (S91 corpus + clip 1.0) 6/12 vs ep11 (older
corpus + clip 0) 11/12, with strings collapsing 3/3 → 0/3 on full
working chains, same day. Two suspects: the clip (touched every
gradient update) and corpus dilution (batch 3 added cascades only).
This slice isolates the first: ep13 trains on the IDENTICAL S91
corpus with clip reverted to 0, so ep13 vs ep12 measures the clip
effect exactly (per the human-approved contingency — if the clip
was innocent, ep13 ≈ ep12 and dilution becomes suspect #1).

## Change (one line + version + pins)

`max_grad_norm=(0 if SEVEN_B else 1.0)` on the 7B path; 3B keeps
1.0 as ever. Restore 1.0 in the future only on verdict evidence,
never on theory.

## Verification

- Kit pins: `max_grad_norm=(0 if SEVEN_B else 1.0)`.
- Suite 1687 OK (skipped=4), pyflakes clean.
- Colab order: SAME 194-row `training.jsonl` (rebuild only if the
  corpus changed — it did not) + s92 `train_ep1.py` → ep13 →
  verdict vs ep12 AND ep11-q4 (three-way judges both suspects:
  ep13 ≈ ep12 ⇒ clip innocent/dilution guilty; ep13 ≈ ep11 ⇒ clip
  guilty).
