# Capability Ladder — baby-agent generations

Living artifact (S80). Each rung: the capability, its frozen eval
task, the demonstrations that teach it, and the graduation criterion.
**The anti-flaky gate: no rung's demonstrations are authored until
the rung below is stable** (3 consecutive verdicts inside its rate
band). Rates are per-task success rates (n=3, S74 harness).

## Rung table

| rung | capability | eval task | introduced | status |
|---|---|---|---|---|
| 1 | single-defect single-file | calculator / strings / json | S57 | calculator solved-band 0.33-1.0; strings 3/3 (ep11, perfect); json wall BROKEN by ep11 3/3 |
| 2 | persistence: two defects | defect-fix-cascade | S78 | 1/3 (ep11, first success — meets graduation threshold, stability pending) |
| 3 | cross-file dependency tracing | defect-fix-indirect | specified, not built | gated on rung 2 |
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

Bands: calculator 0.33-1.0 (solved-band), strings 0-1.0
(solved by ep11 3/3), json broke 0 → 1.0 (ep11).
ep9's own-day 3/3 did not reproduce —
the band is the honest measure, not a single verdict.

## Demonstration requirements per rung

- Rung 2: double-chain demos — chain → second failure → re-diagnose
  from scratch (never reuse the first diagnosis) → fix → final names
  BOTH fixes. Exist: agent-authored (S80: calc_ops; S82: string_ops).
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
