# S93 — Measurement-first stability: pinned decoding + rung-3 eval

Status: landed 2026-09-26. No training, no new demos, nothing for
Colab — all local. Kit untouched (s92 stands).

## Why (the variance was measurement noise)

Same model swung 0/3→2/3 day-to-day, and the harness sent NO
temperature option — every verdict ran at Ollama's default 0.8,
the variance-maximizing regime (research: stability 0.977 @ temp
0 vs 0.942 @ 1.0; greedy ≥ sampling on most benchmarks). More
demos cannot fix sampling noise, so S93 fixes the ruler.

## Three tracks

1. **Pinned decoding**: `temperature`/`seed` plumbed
   bridge → provider → `qa verdict --temperature/--seed`
   (default unset = today's behavior everywhere else; env
   `OLLAMA_TEMPERATURE`/`OLLAMA_SEED` fill in). Pre-S93 bands
   annotated, not rewritten.
2. **Rung-3 eval-only task** (`defect-fix-indirect`, tax bug in
   taxcalc, test covers importing cart): frozen fixture proven by
   subprocess (fails pre-fix, passes fixing A). NO demos authored
   — approved gate-letter override, gate spirit intact (nothing
   trains toward rung 3). `--tasks 4` keeps history comparable.
3. **Budget probe** (experiment): cascade-only, ep12+ep13,
   budgets 12 vs 16, pinned temp 0 / seed 42.

## Headline finding (probe, 12 runs)

**12/12 SUCCESS** — every cell (both models × both budgets × 3
reps) closed in 10 iters / 9 calls / 2 failures, byte-identical:
ep12-12: 3/3, ep12-16: 3/3, ep13-12: 3/3, ep13-16: 3/3. Under
greedy decoding both models execute the taught chain
deterministically — the rung-2 "volatility" was sampling noise
(temp 0.8), and budget is moot (all close at 10 < 12; yardstick
stays 12). Honest bounds: determinism means one trajectory
repeated, not 12 independent proofs — seed-robustness is
unmeasured (S94 fuel); the S41 gate passed every run, so all 12
are genuine fixes.

## Verification

- 7 new bridge/provider tests; indirect fixture fail→fix→pass by
  subprocess; suite 1695 OK (1687 + 8); pyflakes clean.
- First full run went RED (2 stale bridge mocks missing **kwargs
  + the new indirect test hitting the S64 same-size-stale-.pyc trap
  via direct Path.write_text — fixed with a size-changing 1.5→1.20
  replacement and mock updates, all green after).
- Live: probe 12/12 on the real store (recorded).

## Next (S94 decision, not this slice)

Re-run the head-to-head under pinned decoding — those bands
decide whether a capability gap survives clean measurement.
