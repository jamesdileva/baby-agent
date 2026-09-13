# S74 — Repeated-Run Verdicts (measurement before training)

Status: scoped 2026-09-13. The gen-7 verdict exposed the measurement
problem: ep6's calculator success did not reproduce at the same
budget, so n=1 verdicts cannot distinguish capability from sampling
luck at this capability level. Gen-8's recipe experiments (loss
masking, SRFT) would be meaningless against noisy single runs.

## Implement

- `run_verdict(..., repetitions=3)`: every provider × task combination
  runs N times; the metrics population covers all repetitions (the
  store slice is computed from a pre-run snapshot, not a tail count).
- Per-task results report **success counts** ("2/3") alongside the
  per-run details; the headline metric becomes **success RATE**.
- `format_verdict` renders counts + rates; `--repetitions` on the CLI
  (default 3).
- No corpus change (frozen at v6); no model change. This is the
  measurement upgrade the gen-7 verdict demanded.

## Verification

- Injected-fake tests: repetitions × tasks records land; the metrics
  population math holds; rates render.
- Live re-baseline: ep6-q4 vs ep7-q4 at n=3 × 3 tasks (18 runs,
  budget 12) — the first verdict whose numbers are rates, and the
  direct test of whether gen-7's regression was real or variance.

## Sequencing (the gen-8 question, answered)

1. This harness upgrade + live re-baseline (no Colab).
2. Gen-8 = loss masking (assistant-only loss in the training kit) —
   the research queue's objective-side fix for narrative-over-
   behavior — attributed against rate-based baselines.
3. SRFT (failed-trajectory signal) after that; imported datasets
   remain rejected.
