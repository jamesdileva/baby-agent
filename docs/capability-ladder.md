# Capability Ladder — baby-agent generations

Living artifact (S80). Each rung: the capability, its frozen eval
task, the demonstrations that teach it, and the graduation criterion.
**The anti-flaky gate: no rung's demonstrations are authored until
the rung below is stable** (3 consecutive verdicts inside its rate
band). Rates are per-task success rates (n=3, S74 harness).

## Rung table

| rung | capability | eval task | introduced | status |
|---|---|---|---|---|
| 1 | single-defect single-file | calculator / strings / json | S57 | calculator solved (3/3 everywhere); strings: ep11 rock-solid (3/3 ×5) vs post-S82 lineage flicker (ep12 0,3,0; ep13 1,0; ep14 2,0; ep15 0/3 deterministic — S94 batch did NOT fix) vs **ep16 3/3 with the first minimal anchor ever emitted at inference** (S100 surgery moved the anchor prior); json SOLVED (3/3 ×5/6 at 7B) |
| 2 | persistence: two defects | defect-fix-cascade | S78 | **GRADUATED S94.1** — 3 consecutive pinned in-band readings (probe 12/12, S93.1 3/3 both, S94.1 3/3 both across the 7B line) |
| 3 | cross-file dependency tracing | defect-fix-indirect | BUILT S93 (eval-only) | ep15 3/3 (S95.1, WITH demos) vs ep13 3/3 (no demos) vs ep11 0/3 ×2 — lineage gap real, demo-vs-transfer unisolated; ep16 0/3 (wrong value 1.4 + no recovery); **gen-17: ep17-q4 3/3 with ZERO failures on all three runs (S101 R4 wrong-value-rejection drill transferred exactly — iters 7, calls 6, no guesses) — the drill, not luck, moved ep16's 0/3 to 3/3 clean; third indirect-capable generation (ep13, ep15, ep17)** |
| 4 | test authorship with mutation proof | test-authoring | specified, not built | gated on rung 3 |
| 5 | runtime-behavior debugging | observe-reproduce | specified, not built | gated on rung 4 |
| 6 | multi-file feature with contract | task spec pending | specified, not built | gated on rung 5 |
| 7 | observation-grounded exploration: answer a question about a codebase from what it READS (listing → targeted reads → grounded answer), never path guesses | explore-qa (S105, eval-only) | proposed S103, built S105; zero-shot baseline MEASURED 2026-09-28: ep17 0/3*, ep11 0/3 — 0/6, all failures max-iterations even at a 25-iter budget (*two ep17 runs DNF on CPU timeouts); **DEMOS AUTHORED S108 (3 drills, lane 3/3 through the real fact-gate): the listing-is-the-map rule, the return-to-the-map persistence beat, and the one-guess-then-read recovery — ep21's variable** | authoring OPEN (user-directed, parallel proposal) |
| 8 | long-horizon persistence: stay coherent across 30-100+ steps — no drift, no re-breaking fixed work, goal fidelity at completion | long-horizon eval (proposed S108): raised verdict budget + drift metrics (re-broken fixes, constraint loss, goal fidelity) | proposed 2026-10-01 — the 12-iteration budget cannot contain it; needs its own harness work | proposed; gated on rung 7 + budget raise |

Rung 7 note (S103): the rung exercises a DIFFERENT axis than rungs
1-6 — information extraction with zero edits — and the S103 recovery
work makes its failure mode (guess-cycling) honest and visible. Eval
shape: fixture workspace with planted facts; a question answerable
ONLY by reading them; the deterministic verifier requires the final
answer to CONTAIN the planted fact and name the file it came from
(no LLM judge — S41-compatible). Demos teach: list first, read the
LISTING, open the doc the listing names, quote the fact with its
source. Because the axis is orthogonal to the repair rungs, authoring
MAY open in parallel once rung 3 graduates (3 consecutive pinned
in-band readings) rather than waiting on rungs 4-6 — flagged for the
human with this note as the record.

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
| 14 | ep14-q4 (strings batch) | 2/3 | 2/3 | 2/3 |
| 15 | ep15-q4 (S95 corpus) | 3/3 | 0/3 | 3/3 |
| 16 | ep16-q4 (S100 corpus) | 3/3 | 3/3 | 3/3 |
| 17 | ep17-q4 (S101 drill + conversational prompt) | 3/3 | 3/3 | 2/3* |
| 17 | ep17-q4 re-verdict (seed 43) | 3/3 | 3/3 | 3/3 |
| 18 | ep18-q4 (treadmill-cleaned corpus + S104 drills, 96 steps) | 0/3† | 1/3 | 3/3 |
| 19 | ep19-q4 (restored scale, 440 records / ~165 steps) | 3/3 clean | 3/3 clean | 1/3‡ |
| 20 | ep20-q4 (S107 persistence drills, 452 records / ~171 steps) | 3/3 | 3/3 | 3/3 |
| 20 | ep20-q4 confirmation (seed 43) | 3/3 | 3/3 | 3/3 |
| 21 | ep21-q4 (S108 explore drills, 461 records) | 3/3 | 2/3 | 3/3 |
| 22 | ep22-q4 (S109 seam drills, 470 records) | 0/3§ | 3/3 | 3/3 |
| 23 | ep23-q4 (S110 answer-QA volume, 473 records) | 3/3 | 3/3 | 3/3 |
| 11 | ep11-q4 re-verdict (pinned 5-task) | 3/3 | 3/3 | 3/3 |
| 11 | ep11-q4 re-verdict (S95.1 tie day) | 3/3 | 3/3 | 3/3 |
| 9b | qwen3.5:9b RAW (scout, think-disabled) | 3/3 | 3/3 | 1/3* |

Bands: calculator 1.0 (solved — 3/3 everywhere, every gen); strings
solid for ep11 (3/3 x3 verdicts), volatile for ep12 (0/3 then 3/3);
json SOLVED at 7B (3/3 in 5 of last 6 readings across ep11/ep12/ep13).
Gen-17 two-reading ledger (seed 42 + seed 43): ep17 23/30 vs ep11
22/30 — json loss at seed 42 was a provider timeout (3/3 at seed 43);
indirect 6/6 vs 0/6 deterministic; **cascade 0/6 CONFIRMED deficit**
(identical schema-error loop both readings) → S104 ep18 target;
**ep17-q4 SHIPPED as champion 2026-09-28** (thrash tax 82 vs 15
tool failures recorded honestly); ep11-q4 fallback.
Gen-18 (2026-09-28): cascade SOLVED-band for the first time
(2/3 — the S104 re-anchor drills transferred) but everything else
regressed on the smaller corpus (6/15; calc 0/3 with 10-failure
thrash = undertraining fingerprint; the 1:1 real cap cut the real
share 188 -> 122). ep18 NOT SHIPPED; ep19 lever = restore the real
share (298 available, floored at 122) on the same drills.
† calculator: the solved-since-gen-8 task's first 0/3 — under-
training signature, not skill loss.
Gen-19 (2026-09-28 + re-reading 09-30 at OLLAMA_TIMEOUT=600): the
S106 scale restore CONFIRMED — thrash fingerprint gone (calc/strings
3/3 with zero failures), cleanest-behaving generation ever measured,
but 7/15 BOTH readings (stable) < ep17's 12/15 fair reading (its
best); indirect 0/3 is the second straight generation the S101 drill
(in-corpus, verified) did not reproduce ep17's 6/6; cascade 0/3 with
the chain-2 loop varying its target (code_diagnostics x3, then
experience_record x5 across readings) — the drill-persistence gap is
ep20's variable. Not shipped; ep17-q4 champion.
‡ json: 1 clean success + 2 max-iter (the 60s-timeout run became a
max-iter failure at 600s, not a success).
Gen-20 (2026-09-30, seed 42, 600s): **ep20 15/15 — first perfect
verdict in program history.** Cascade 3/3 (the S107 persistence
drills: chain 2 reads and edits instead of looping — the recorded
success shows the drilled fallback shape, generalizing into one
def-anchored multi-line edit fixing both defects), indirect 3/3
zero-failure (the fabricated-anchor drill). Every dilution tripwire
held. Metrics: chaining 1.0, failures 12, guessed_path 0.0. Seed-43
CONFIRMED: 15/15 again — **30/30 across both readings, ep20-q4
SHIPPED as champion 2026-10-01** (dashboard default switched;
ep17-q4 fallback at 23/30). Cascade 6/6: the most volatile task in
program history is now the most stable. Indirect 6/6: the S101-
lineage anomaly RESOLVED — the missing piece was drill persistence,
not the drill. **ep21 (rung-7 explore-qa demos) GATE OPEN.**
Gen-21 (2026-10-01, 6 tasks): the pinned set holds — ep20 15/15
THIRD consecutive perfect reading = **rung-3 graduation COMPLETE,
rung-4 authoring OPEN**; ep21 14/15 (cascade 2/3, in-band);
explore-qa 0/6 BOTH models — the S108 drills transferred partially
(anti-guess: ep21 guessed_path 0.0 vs ep20's 0.5556; listing-first:
present in the trajectory) but the post-README seam failed (the
model loops code_references/code_symbols hunting "main" instead of
returning to the listing) — the continuation seam again, third
instance of the pattern. Rung 7 NOT moved; ep20 stays champion.
Gen-22 (2026-10-02): the S109 seam fix TRANSFERRED — the recorded
explore-qa failure shows the tempted calls rejected and
docs/running.md READ — but the answer never came: run_tests x6 (the
defect-fix verification ritual on a question with no tests), the
answer-QA final shape drowned in the repair-demo majority. AND
cascade regressed 3/3 -> 0/3 (quiet 3-4-failure runs) with
guessed_path 0.4444 (ep21: 0.0) — the recovery drill's demonstrated
guessed-read as an OPENING move plausibly taught guessing (the S100
lesson in a new form). ep22 recorded as regressed; ep20 stays
champion (16/18, pinned 15/15 fourth consecutive).
§ cascade: quiet-failure regression, unconfirmed single reading.
Gen-23 (2026-10-02): cascade RESTORED 3/3 — gen-22's cause
confirmed (the opening-guess teacher). explore-qa 0/3 at 10
deterministic failures/run: the model guesses the DRILLS' file
names (configuration.md, serverctl.py) against a listing that
never contained them — drill content memorized, the read-the-map
behavior not generalized. **Rung 7 = measured capability limit at
7B with ~6.5% answer-drill share; three-attempt arc banked (anti-
guess and seam-rejection transfer; fixture generalization does
not).** ep23 ties ep20 15/18 on tasks; ep20 stays champion on
behavior. Rung-4 authoring next per direction.
ep12's verdict-day strings 0/3 did not reproduce — the S91.1
regression call is withdrawn as variance (see DECISIONS: never
convict on a single n=3).
Raw-base scout (S94.2, think-disabled on CPU): qwen3.5:9b 3/3,
3/3, 1/3* (*json + indirect losses are provider TIMEOUTS — slow
turns, not proven incapability; cascade 3/3 zero-shot).
S94.3 with time (600s) + think-on probes: 9B combined 11/15
(calc/strings/cascade 3/3, json 1/3, indirect 1/3 — timeouts
explained cutoffs, rates barely moved); 9b think-on == think-off
on cascade (no capability gain, think-off stays default); 4b
0/15 think-off with ZERO calls, 0/3 think-on with calls but no
completion — RULED OUT as agent base (thinking load-bearing for
tool-calling at 4B, yet insufficient).

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
  read A via the import edge → fix A (plain reads only: lean
  catalog has no codeintel tools — S72 lesson). Fresh modules,
  never taxcalc/cart. Exist: agent-authored (S95: invoice,
  checkout, basket).
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

Re-verification (2026-09-28, this session's audit): full 5-task n=3
verdict ep16-q4 vs ep11-q4 — calculator 3/3 vs 3/3, strings 2/3 vs
2/3, json 2/3 vs 3/3, cascade 1/3 vs 1/3, indirect 1/3 vs 1/3 →
ep16 9/15 vs ep11 10/15. Both inside their recorded bands; champion
ep11 holds. Session audit clean: suite 1739 OK, pyflakes clean,
preflight clean, export 382 consistent with S101.
