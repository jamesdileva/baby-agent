# Capability Ladder — baby-agent generations

Living artifact (S80). Each rung: the capability, its frozen eval
task, the demonstrations that teach it, and the graduation criterion.
**The anti-flaky gate: no rung's demonstrations are authored until
the rung below is stable** (3 consecutive verdicts inside its rate
band). Rates are per-task success rates (n=3, S74 harness).

## Rung table

| rung | capability | eval task | introduced | status |
|---|---|---|---|---|
| 1 | single-defect single-file | calculator / strings / json | S57 | calculator solved (3/3 everywhere); strings solid ep11 (3/3 x3), volatile ep12 (0/3, 3/3); json SOLVED (3/3 x5/6 at 7B) |
| 2 | persistence: two defects | defect-fix-cascade | S78 | volatile everywhere (ep11: 1/3, 0/3, 2/3, 0/3; ep12: 1/3, 2/3; ep13: 1/3) — best 2/3, stability NOT met |
| 3 | cross-file dependency tracing | defect-fix-indirect | BUILT S93 (eval-only) | 3/3 zero-shot first pinned point (S94 ep13 — transfer, demos still gated) |
| 4 | test authorship with mutation proof | test-authoring | specified, not built | gated on rung 3 |
| 5 | runtime-behavior debugging | observe-reproduce | specified, not built | gated on rung 4 |
| 6 | multi-file feature with contract | spec'd, not built | gated on rung 5 |

## Rate ledger (per generation, per rung-1 task)

| gen | model | calculator | strings | json |
|---|---|---|---|---|
| 8 | ep8 (loss masking) | 2/3 | 1/3 | 0/3 |
| 9 | ep9 (SRFT + coverage) | 3/3 | 0/3 | 0/3 |
| 10 | ep10 (volume + filter) | 1/3 | 2/3 | 0/3 |
| 9 | ep9 (SRFT + coverage) | 3/3 | 0/3 | 0/3 |
| 10 | ep10 (volume + filter) | 1/3 | 2/3 | 0/3 |
| 11 | ep11-q4 (7B + batch 2) | 3/3 | 3/3 | 3/3 |
| 12 | ep12-q4 (batch 3 + clip) | 3/3 | 0/3 | 2/3 |
| 11 | ep11-q4 re-verdict (same day) | 3/3 | 3/3 | 3/3 |
| 13 | ep13-q4 (clip 0 test) | 3/3 | 1/3 | 3/3 |
| 12 | ep12-q4 re-verdict (same day) | 3/3 | 3/3 | 3/3 |
| 11 | ep11-q4 re-verdict (3-way day) | 3/3 | 3/3 | 3/3 |

Bands: calculator 1.0 (solved — 3/3 everywhere, every gen); strings
solid for ep11 (3/3 x3 verdicts), volatile for ep12 (0/3 then 3/3);
json SOLVED at 7B (3/3 in 5 of last 6 readings across ep11/ep12/ep13).
ep12's verdict-day strings 0/3 did not reproduce — the S91.1
regression call is withdrawn as variance (see DECISIONS: never
convict on a single n=3).

## Demonstration requirements per rung

- Rung 2: double-chain demos — chain → second failure → re-diagnose
  from scratch (never reuse the first diagnosis) → fix → final names
  BOTH fixes. Exist: agent-authored (S80: calc_ops; S82: string_ops;
  S91: math_ops, text_ops, list_ops — fresh modules, never calc_ops).
- Rung 1 holding (S94): string drills — fixture-inference narratives
  (the test's expected value teaches the shape) + one recovery
  beat. Exist: agent-authored (S94: greeting, word_ops,
  text_utils).
- Rung 3: import-following demos — failing test → module B →
  code_imports/code_references → module A → fix A. To author.
- Rung 4: write-test → mutation-check demos (the test must FAIL on
  the known defect). To author.

## Authoring runbook (for ANY agent — this session, muse-spark, epN)

Authoring is untrusted-by-design. The quality validator
(`qacompanion.agent.ep1.validate_demonstration`) and the S41
verification gate are the only trust; the author cannot poison the
corpus.

1. Read docs/s80-spec.md (this program) and the rung table above.
2. Author the demo: a script of ToolCalls + one final ModelResponse,
   plus the fixture files it writes. Rules the validator enforces:
   discovery-first (list_directory or run_tests), the module is
   read, exactly one non-empty final, the final names a file it
   actually touched, every edit anchor matches its fixture exactly
   once, the goal carries identity (module + defect, no generic
   filler).
3. Run the lane: `build_agent_corpus(store, python=sys.executable)`
   (add your demo to `agent_authored_demos()` or pass `demos=`). The
   gate + validator run automatically; verified passes are tagged
   `agent-authored`.
4. Record the batch in this file's ledger; the next `qa
   build-training` picks it up.

Subjects stay CODING-ONLY by direction: deeper rungs of the same
discipline, not new domains.

## Measurement regime (S93)

Verdicts pin decoding (temperature 0, seed 42 — pre-S93 verdicts ran
the Ollama default 0.8; bands are annotated, not rewritten).
Pinned probe 2026-09-26: cascade 12/12 (ep12+ep13 × budgets 12/16)
— the rung-2 variance was sampling noise. Budget stays 12 (all
successes closed in 10 iters).
Pinned verdict S93.1: cascade 3/3 BOTH (capability real — rung-2
first pinned point, 2 more needed); ep12 strings 0/3 deterministic
(real deficit vs ep11's 3/3 ×4 — flicker pattern 0,3,0);
indirect baseline ep12 0/3, ep11 1/3 (no demos, as designed).
