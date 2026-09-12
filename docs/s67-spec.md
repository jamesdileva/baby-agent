# S67 — Gen-2 Training + Verdict Harness v2

Status: scoped 2026-09-12. Roadmap: docs/ROADMAP-agentlite.md §S67.
The gen-2 model (baby-agent:ep2, trained on the S66 corpus — 122
records) is imported and speaking; this sprint judges it fairly and
makes protocol quality MEASURABLE instead of anecdotal.

## Already done by the hardened kit (verified on import)

The first export through the S64-verdict-day kit needed NO local
surgery: config untied, rope_theta legacy key present, lm_head explicit
(435 tensors). Both variants created locally (fp16 9.0 s, q4 6.0 s on
the sanity probe) and both answer correctly.

## Implement

1. **Protocol-quality metrics** (`evaluation.protocol_metrics`), computed
   from recorded trajectories' captured steps:
   - `discovery_first_rate`: share of runs whose first tool call is
     `list_directory` (gen-1's missing behavior);
   - `with_calls_rate`: share of runs that emitted any parsed tool
     calls at all (gen-1's parent emitted zero under either contract);
   - `failed_file_reads`: guessed-path rate (reads/edits that failed
     with file-not-found — the "guessing" signature from the gen-1
     verdict; recovery-tagged demos deliberately contain one, so
     benchmark runs are the honest population);
   - `success_rate` + tool-failure counts.
2. **The verdict**: `run_benchmark` across the THREE S57 evaluation
   tasks (calculator / string reverse / JSON lookup) for ep2-q4 and
   ep1-q4 under their trained textual contract, recorded as
   trajectories; `compare()` flags per-task regressions/improvements.
3. **Baselines from the recorded gen-1 verdict day** (same benchmark,
   recorded): parent qwen2.5-coder:3b (0 calls either contract),
   qwen3:4b native (6 calls, 1502 s, FAILED), ep1 gen-1 textual
   (6 calls, 62 s, FAILED).

## Deliberately deferred

- The full 12-run cross product including the slow models (qwen3:4b and
  the parent need 10-25 CPU-minutes per task) — the recorded
  single-task baselines stand in; a full grind can be launched
  overnight if wanted.
- ep0.5 injection A/B (S68 scope).

## Verification

Metrics are unit-tested on synthetic trajectories; the verdict table is
reported honestly whatever it says, and generation-over-generation
regressions are called out explicitly.
