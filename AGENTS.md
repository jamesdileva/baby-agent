# AGENTS.md — baby-agent

Working conventions for any agent (or human) working in this repo.

## Mission

Build and maintain `qacompanion`: a stdlib-only Python CLI that accumulates a
case base of test failures and their diagnoses. The spec of record is
[docs/spec.md](docs/spec.md) — read it fully before the first commit. The spec
is frozen for v1; propose amendments via DECISION-style writeups before
touching it.

## Standing discipline

1. **Slices, not waves.** One committable slice per cycle: implement, test,
   commit, clean tree before responding.
2. **Tests green or it didn't happen.** `python -m unittest` (or the agreed
   runner) exits 0 before every commit. A red suite is never committed.
3. **Honesty over optics.** If accuracy drops or a change regresses something,
   say so in the cycle summary. Hiding regressions is the cardinal sin of a
   QA tool.
4. **Stdlib only.** No third-party dependencies in v1. No network calls.
5. **Spec is law.** Behavior questions resolve to docs/spec.md. Gaps get
   documented as proposed amendments, not silently filled.

## Verification culture

- Every bug fixed gets a regression test named after its failure mode.
- `accuracy` must be re-runnable at any time; a change that lowers holdout
  accuracy must be justified in the commit message or reverted.
- Fixture-based verification is necessary but not sufficient: exercise real
  failure output when touching capture paths.

## Review protocol

- Reviewer verifies firsthand (run the tests, read the diff) before approving.
- Provenance matters: cite the task/mail/issue that authorized a segment.
- Disputes escalate to the human with evidence, not assertion.

## Human escalation protocol

- Any question, ruling request, or blocked decision that needs the human
  MUST be filed as a QUESTION or TASK mail addressed to `human` — AND
  recorded in docs/DECISIONS.md. A question that lives only in a document
  is invisible to the human and counts as unanswered.
- Mail first, document second. The mail pings; the doc preserves.
- When the human replies by mail, sign the outcome into DECISIONS.md the
  same cycle.

### Case confirmation authority

Routine case confirmations may be signed `confirmed_by` firsthand by either
parent when ALL hold: (a) firsthand reproduction evidence is cited,
(b) the diagnosis introduces no spec.md changes,
(c) both agents concur.

New standing rules derived from lessons ALSO do not require human approval —
the parents hold full teaching authority inside this repo. Document every new
rule in DECISIONS.md (audit trail, not permission slip).

Escalate to `human` teacher review ONLY when: the frozen spec
(docs/spec.md) needs amending, agents dispute and cannot resolve a decision
between themselves, or a problem recurs 3+ times despite agreed fixes.
Everything else is yours to decide — that is what being the teachers means.

## Cycle-end ritual (integration with this tool)

Every working cycle in any repo where qacompanion is deployed:

1. If tests failed: `record` each failure, attempt diagnoses, request teacher
   REVIEW of those diagnoses.
2. Run `qa preflight` before claiming anything is "done."
3. If `cases.jsonl` changed: commit it alongside the slice.
4. Report lookup hits in the cycle summary ("recognized: FAIL(0.0s), case #3")
   so the colony sees the tool earning its keep.

## Worklog

Dated history of landed slices, newest first. Standing cycle ritual
(DECISIONS 2026-09-04): **plan + scope → implement → tests green →
commit + push → worklog entry.**

- 2026-09-28 — **S105 baseline complete — the explore-qa zero-shot
  wall is 0/6** — ep17-q4 0/3 (one max-iterations at 25 iters, two
  CPU-timeout DNFs after 19-25 iters of thrash — the OLLAMA_TIMEOUT
  fix converting the earlier 6-hour hang into honest failures) and
  ep11-q4 0/3 (max-iterations ×3, 25 calls each). NEITHER model can
  answer a docs-lookup question even with double the standard budget,
  with the planted fact sitting in docs/running.md and the root
  listing in context — rung 7's target is real, measured, and
  untouched by any training so far; the demos are ep19's variable.
  Baseline runs recorded as failed trajectories (SRFT-eligible,
  standing lane). Ladder rung-7 row updated with the measured
  baseline. Suite untouched (docs + baseline slice).

- 2026-10-04 — **S116 sweep COMPLETE: the raw 9B explored 15 fresh
  fixtures — 11 success + 2 recovered = 13 fact-gate-verified
  explore successes, ZERO run_tests in all 15 records; the export is
  rebuilt with 20 raw-9B records (13 sweep + 7 re-scout survivors)
  displacing the 13 thrashiest — ep25 trains enriched** — the
  fixtures (authored in the gitignored driver): 15 varied projects
  (webshop/notekeeper/imgtool/chatrelay/filewatcher/scorekeep/
  templater/queuebird/colorwrap/taskcron/vaultdoor/mailbridge/
  petfeed/wikibackup/glowmeter), question-shaped goals, unguessable
  planted facts, the S114 non-leaking gate. THE YIELD: 13/15
  verified (the 2 failures: colorwrap 22 verification attempts,
  taskcron empty-responses — both honest). **THE KEY DATA: zero
  run_tests calls in all 15 trajectories — the 9B's clean ending
  (list -> read -> list -> read -> ANSWER) is now in the corpus at
  scale: ~20 real question-shaped records + 10 answer drills vs the
  ~310 repair records that teach the run_tests ritual.** The cap
  mechanism worked exactly as designed: same 470-record size, better
  composition. ep25 = the user's Colab run on the enriched export
  (qwen2.5, free T4); the verdict (--tasks 6) decides rung 7 at 7B.
  Suite untouched (measurement + generation slice).

- 2026-10-04 — **S115 A/B: the worked-example injection 0/3 —
  BOTH inference instruments are now falsified; the failure shape is
  unchanged (the doc gets read with the example in context, then the
  run_tests ritual x7); the last two levers are training-side** —
  WorkedExampleReminder (the ep0.5 mechanism applied to rung 7)
  injects a complete worked docs-question demonstration (a DIFFERENT
  fixture's facts — the oracle-leak lesson applied at design time)
  every turn: ep24 0/3, all max-iterations at the 25 budget. THE
  TRAJECTORY: list -> README -> run_tests -> codeintel loop
  (rejected) -> docs/running.md READ (with the worked example in
  context the whole time!) -> run_tests x7. The in-context shape
  teaching does not bind at 7B — same verdict as the map
  re-injection (S111). Combined with the S111 result, the
  inference-side is exhausted: two instruments, both 0/3. **The two
  remaining levers are TRAINING-side: (a) cross-model imitation at
  SCALE — the raw 9B explores 10-20 fresh fixtures locally (its
  successes are 4-6 iters each, already proven by the re-scout);
  the verified successes feed the real pool and ep25 trains on the
  enriched corpus (the 3 scout successes are already in the export;
  this scales 3 -> 15+); (b) scripted drill volume 20-30 (S116 as
  the user framed it) — same training cost, lower expected value
  given the gen-23 memorization risk.** Either way: one free Colab
  run, then rung-4 authoring. Suite untouched (measurement slice).

- 2026-10-03 — **The gate-fix re-run: ep24 explore-qa 0/3 (timeout,
  max-iter x2) — with the leak closed the wall stands; rung 7 is
  7B-BLOCKED with the complete evidence chain; rung-4 authoring
  proceeds on the 7B line; rung 7 waits for the 9B (L4)** — the
  fixed-gate re-measurement (3 runs, non-leaking rejection): all
  three failed at the 24-25-iteration budget. **The final rung-7
  evidence chain, five trained attempts across four corpus
  strategies: ep20 clean-corpus 0/3, ep21 drills-v1 0/3 (codeintel
  loop), ep22 seam-fix 0/3 (doc read, run_tests ritual), ep23 volume
  0/3 (fixture-name guessing), ep24 cleaned+cross-model 0/3 honest
  (the 3/3 was rejection-echo through the fact-gate leak) — against
  raw qwen3.5:9b 3/3 ZERO-SHOT.** The conclusion is measured, not
  assumed: observation-grounded answering does not generalize at 7B
  with this recipe, and no inference-side instrument (TaskListing-
  Reminder), corpus shape (cleaned, cross-model), or drill strategy
  moved it. **ep24's legacy: the pinned set held 15/15 through the
  corpus surgery (no dilution — the S107/S110/S112 batches are
  compatible), cascade stayed stabilized, and the gate leak was
  found and fixed.** ep24 not shipped; **ep20-q4 REMAINS champion**
  (pinned 15/15 x4 readings). Rung-4 authoring (test authorship
  with mutation proof — gate open since rung-3 graduated) is the
  next slice; rung 7 re-opens on the 9B (SFT on L4) when GPU budget
  allows. Suite untouched (verdict + docs slice).

- 2026-10-04 — **Gen-25 verdict — explore-qa 0/3: the cross-model
  imitation did not move rung 7, AND the terminal-step finding
  completes the picture; cascade 1/3 + indirect 0/3 regressed; ep20
  16/18 REMAINS champion (15/15 fifth consecutive); rung 7 at 7B is
  FINAL-BLOCKED — rung-4 authoring next** — pinned 6-task, 600s:
  ep25 10/18 (calc/strings/json 3/3, **cascade 1/3 + indirect 0/3 —
  both regressed with 10-failure thrash x2**, explore-qa 0/3) vs
  ep20 16/18 (pinned 15/15, explore-qa 0/3). THE EVICTION HYPOTHESIS
  RETRACTED: the interim claim that the cap evicted the indirect/
  cascade teaching was MY FILTER BUG (the substring 'agent' matches
  'baby-agent:epN' — every real record was excluded from the count);
  the truth: the ep25 export carries 59 cascade + 59 indirect real
  records — nothing was evicted. The regression cause: the 13-record
  corpus swap or single-reading noise — unconfirmed (S91.1 rule).
  THE EXPLORE-QA FORENSICS (the sixth and sharpest attempt): ep25's
  trajectory is the complete drilled shape — list -> README ->
  search -> docs/running.md READ — and then it wandered into
  experience_record calls, test runs, and symbol hunts INSTEAD OF
  ANSWERING. After six generations the failure is localized to ONE
  step: **the terminal transition to the answer final on a no-test
  question.** The rung-7 chain is complete and final: 6 trained
  attempts (ep20 clean, ep21 drills, ep22 seam, ep23 volume, ep24
  cleaned+cross-model, ep25 +9B-success-enriched) — all honest 0/3;
  both inference instruments falsified; raw qwen3.5:9b 3/3 zero-shot.
  ep25 not shipped; **ep20-q4 REMAINS champion.** Next: rung-4
  authoring (test authorship with mutation proof) per the agreed
  sequencing; rung 7 documented as 7B-blocked with the terminal-step
  gap named, re-opening on the 9B (L4). Suite untouched (verdict +
  docs slice).

- 2026-10-03 — **Gen-24 verdict — CORRECTED: the pinned set 15/15
  is REAL, but the explore-qa 3/3 was A GATE LEAK (the verifier's
  rejection message named the facts, and the model echoed them
  without grounding); ep20-q4 REMAINS champion; S114 fixes the leak
  and the honest re-measurement is running** — the split verdict
  (dashboard 4-task at budget 12 + a driver remainder for indirect/
  explore-qa at the 25 default): ep24 pinned **15/15** (calc/strings/
  json 3/3, **cascade 3/3 — the stabilization HELD in the same-day
  reading**, indirect 3/3) vs ep20 15/15. THE FORENSICS THAT
  MATTERED: the explore-qa "successes" carried finals like "You are
  correct that the final answer should have included the planted
  facts `python -m serverctl` and `8765`" — **the model echoed the
  fact-gate rejection's own fact list** (which names the missing
  strings verbatim), and run 2 of 3 passed WITHOUT EVER READING
  docs/running.md. Runs 1/3 DID read the doc (the drilled exploration
  held — genuine progress) but their passing finals were echoes, so
  grounding and leak are indistinguishable in the result. **The
  oracle-leak lesson: a verifier must never reveal what it is looking
  for.** S114: both fact-gate rejections (eval + lane) now say only
  "quote the exact run command from the documentation" — guidance
  without the answer. The fixed-gate re-run (3 runs) measures the
  honest number; the double experiment (pollution removal + cross-
  model imitation) is UNRESOLVED until then. ep24 not shipped; ep20
  stays champion. Suite untouched by the leak fix (verifier message
  only).

- 2026-10-03 — **S113c + the cross-model-imitation discovery — the
  2.5 re-run becomes a double experiment** — the gen-24 T4 attempt
  died twice: OOM at the loss pass (244MB short, even after the
  squeeze) AND the 768 cap skipped 463/470 records on the qwen2.5
  re-run (the skip flag covered 7B too). Fixes: the skip is now
  9B-ONLY (the cap must never bite the proven qwen2.5 path), and the
  9B-on-T4 experiment is declared dead (batch-1, checkpointing,
  seq-length, and allocator tricks all tried — 9B needs L4/A100).
  THE DISCOVERY: auditing the export after the re-scout showed the
  raw 9B's three explore-qa SUCCESS trajectories (0-2 failed steps,
  COMPLETED with the planted facts) entered the real pool via the
  cleanest-first cap — **cross-model imitation: the 7B can now train
  on the 9B's correct explore-qa behavior.** The rebuilt export
  (470 records) carries all three. The user's 2.5 re-run (pollution
  control) with THIS export is therefore a double experiment:
  (a) did removing the answerless records change explore-qa, and
  (b) does imitating the 9B's real exploration move rung 7 at 7B?
  If neither moves it, rung 7 is 7B-blocked pending 9B hardware and
  rung-4 proceeds. Suite untouched (kit fix + docs slice).

- 2026-10-03 — **The 9B re-scout COMPLETE — the raw qwen3.5:9b
  scores explore-qa 3/3 ZERO-SHOT (iters 6/5/4, no drills, no
  training): the rung-7 wall is a 7B capability limit and the 9B
  clears it untouched — the base-step-up evidence is complete** —
  full table (raw, 600s, seed 42, n=3): calculator **3/3 clean**,
  strings 0/3 (1 recovered), json 0/3 (max-iter x3 — genuinely
  absent, not timeout-masked), cascade 2/3, indirect 1/3 (2
  empty-response terminations — a CPU-stability quirk, B4's
  consecutive-empty rule), **explore-qa 3/3**. Combined 9/18 with
  raw strengths exactly where the 7B is weak (explore-qa) and raw
  weaknesses exactly where the 7B is strong (strings/json — our
  drills demonstrably fix those on the repair axis). The SFT thesis
  writes itself: the 9B base brings rung-7 capability; our corpus
  brings the repair discipline. Plus the live corroboration: the
  user's cartoongen session on a REAL workspace (list -> package.json
  — the exactly-right file) died on the 60s default server timeout
  mid-answer; OLLAMA_TIMEOUT=600 is required for 9B live sessions.
  The qwen3.5 kit re-derivation is the next slice (template +
  fixups); the training attempt goes to Colab Pro L4 (24GB — the
  free T4's 15GB OOMs at 9B, ~16-18GB estimated). Suite untouched
  (scout + docs slice).

- 2026-10-04 — **The ep25 regression check (seed 43) — indirect
  0/6 across both readings: SYSTEMATIC, not noise; cascade 2/3
  in-band; ep20-q4 REMAINS champion (15/18 vs 13/18, the pinned set
  is the guard); ep25 = the rung-7 breakthrough generation with a
  documented indirect regression** — the seed-43 re-check (cascade +
  indirect, n=3, 600s): cascade **2/3** (1 max-iter at the 25
  budget + 2 clean 9-iter wins — in-band, recovered from seed 42's
  1/3), indirect **0/3 again (all max-iterations)** — **indirect is
  0/6 across both seeds: the ep20-24 capability (3/3 stable across
  four readings) is GONE in ep25.** Combined: ep20 16/18 vs ep25
  13/18. THE TRADE: ep25 gained rung 7 (explore-qa 3/3, the first
  trained-model exploration capability) and lost indirect — the
  codeintel loop (ep21-era shape) returned on indirect specifically.
  The cause is unconfirmed: the 13-record corpus swap is the only
  delta (the indirect real records: 59 present, the drills present —
  no eviction); candidate: the 20 zero-run_tests explore records
  shifted the task-conditioning balance away from the repair
  test-first shape that indirect depends on. **The champion call:
  ep20 holds** — 15/18 vs 13/18, indirect stability is worth more
  than the new capability until the regression is understood. The
  ep25 line stays alive: the rung-7 capability is real, banked, and
  the indirect fix (ep26) can build on it. Suite untouched
  (measurement + docs slice).

- 2026-10-05 — **Gen-26 verdict (seed 42, 600s) — ep26 17/18: the
  schema-aligned retrain DELIVERS on every axis; explore-qa 3/3 AT
  THE STANDARD BUDGET (6 iters per run — the trained schemas made
  rung 7 fast), the codeintel loops are GONE (7 tool failures total
  across 18 runs — the cleanest protocol line ever recorded), the
  pinned set holds 14/15; ep20 15/18 same-day; seed-43 confirmation
  running before the champion call** — pinned 6-task: ep26 **17/18**
  (calc/strings/json 3/3 ZERO failures, **cascade 3/3 with ZERO
  failures — the stabilization now clean**, indirect 2/3 (one
  max-iter at only 2 failures — the softest signature possible),
  **explore-qa 3/3 at 6 iters x3 with 1 failure each**) vs ep20
  15/18 (pinned 15/15, explore-qa 0/3 at 6-failure thrash x3).
  METRICS: ep26 success 0.9444, chaining 1.0, guessed_path 0.0,
  tool_failures 7 (vs ep20's 19) — the cleanest line in program
  history, beating ep20's own cleanest (ep19's 19). THE ARC CLOSED:
  the rung-7 wall that 5 trained attempts + 2 inference instruments
  could not move fell when (a) the cross-model imitation taught the
  answer shape and (b) the schema fix let the model see the tool
  args it was inventing. The indirect 2/3: one max-iter at 2
  failures — in-band-adjacent, not the 0/6 catastrophe ep25 had.
  ep26 not shipped pending seed 43; **ep27 = rung-4 authoring per
  sequencing regardless** (the demos are additive; ep27 trains
  after the champion call). Suite untouched (verdict + docs slice).

- 2026-10-05 — **S120 cascade/indirect schema retest (the PRIMARY
  test) — the schema fix CONFIRMED at inference: cascade 1/3 -> 3/3
  (clean 8-iter runs, the codeintel loops COLLAPSED), indirect 0/3
  -> 1/3 (partial: one clean 7-iter success + two max-iter)** —
  ep25's existing weights, no retraining, the schema-visible prompt:
  cascade went from 10-failure thrash x2 to three consecutive clean
  8-iteration completions — the model read the arg schemas and
  stopped inventing them. Indirect recovered partially (the loops
  reduced; two runs still wandered). THE COMPLETE ROOT-CAUSE CHAIN
  of the rung-7 arc, all four findings now load-bearing: (1) the
  oracle leak (S114), (2) the answerless SRFT pollution (S112),
  (3) the tool-contract trap (S119a), (4) the invisible schemas
  (S119b) — and the schema fix alone restored cascade to 3/3 at
  INFERENCE. THE CHAMPION CALCULUS with schemas at inference:
  ep25 = ~12/15 pinned (cascade restored, indirect 1/3) + explore-qa
  3/3 = ~15/18 vs ep20 15/18 — a task tie with different shapes
  (ep25 holds rung 7; ep20 holds indirect stability). The champion
  resolution: **ep26 (the aligned retrain, schemas in every training
  record) should lock cascade restored AND lift indirect — its
  verdict decides the champion properly.** ep27 = rung-4 authoring
  per sequencing. Suite untouched (measurement slice).

- 2026-10-05 — **S120 the schema-prompt inference retest —
  CORRECTED scope: the primary schema test is cascade/indirect (the
  codeintel loops), which launched after an off-target first probe;
  the explore-qa probe returned 1/3 (one success at 11 iters + two
  max-iterations at the 25 budget — explore-qa 3/3 already existed
  at that budget from the S118 re-measurement, so the 'first at the
  standard budget' framing was wrong on both counts)** — the
  schema-visible prompt (S119b) applied to ep25's existing weights
  at inference. THE READ: partial inference-side signal, supporting
  the alignment thesis — the full fix is the aligned retrain (ep26).
  THE PRIMARY TEST (cascade + indirect under the schema prompt, n=3,
  seed 42): decides whether the codeintel loops collapse when the
  arg schemas are visible without retraining. Suite untouched
  (measurement slice).

- 2026-10-04 — **The ep25 tool-fix retest — the trap CONFIRMED as a
  major cause: indirect 0/3 -> 2/3 under the fixed contract, but the
  successes are LATE (23-25 iters); ep20-q4 holds champion** — the
  same-conditions retest (cascade + indirect, n=3, seed 42, 600s,
  the only change being the honest tool-contract rejections):
  indirect **2/3** (two successes at 25 and 23 iters + one max-iter)
  vs gen-25's 0/3 — **the codeintel-loop trap was real: with the
  honest 'unknown tool' rejections the model eventually adapts and
  answers, where the old 'unknown argument' loops trapped it to
  max-iterations.** Cascade 1/3 (one 9-iter success + two max-iter
  at 25 — vs gen-25's 1/3: unchanged-ish). THE BUDGET FINDING: all
  retest successes closed at 23-25 iters — over the standard 12 —
  so at the standard verdict budget the regression stands; the fix
  converted never-succeeds into succeeds-late. **Champion: ep20-q4
  holds** (pinned 15/15 at the standard budget is the guard; ep25's
  explore-qa 3/3 is the rung-7 line). The ep26 targets named: (a)
  the late-success adaptation (25 iters to close what ep20 closes
  in 7-9), (b) the cascade max-iter shape. Rung-4 authoring next
  per the user's sequencing. Suite untouched (measurement slice).

- 2026-10-04 — **S118 honest re-measurement — explore-qa 3/3 for
  ep25: THE RUNG-7 WALL HAS FALLEN AT 7B via cross-model imitation;
  the regression check is running** — the corrected-gate re-run
  (run_evaluation, real fact gate, temp 0, 600s): **ep25 3/3
  (deterministic 8-iteration runs x3)** vs ep20 0/3 (max-iter x2 +
  a verification-fail quit). THE SHAPE (recorded trajectory): the
  drilled exploration executed cleanly — list -> README ->
  experience_search -> ANSWER with the facts. THE CAVEAT SET: (1)
  the runs used the 25-iteration driver default (one success would
  close within the standard 12; the other two needed 19-21 — the
  budget question is recorded); (2) the same-day gen-25 verdict
  showed ep25 pinned 10/15 (cascade 1/3, indirect 0/3 — the ep21-era
  codeintel loop REGRESSED back, 10-failure thrash) — the champion
  question hangs on whether that regression is noise or the corpus
  swap; **the regression re-check (cascade + indirect, n=3, seed 43)
  is RUNNING**; (3) attribution: the double experiment bundled
  pollution removal + cross-model imitation — movement is confirmed,
  the split is open. ep20-q4 holds the champion seat pending the
  regression check (16/18 vs 13/18; the pinned set is the guard).
  Suite untouched (measurement slice).

- 2026-10-02 — **S111 A/B — the attention hypothesis NOT supported
  (preliminary, stopped early); the re-scout launches; the 9B
  landscape settled** — the TaskListingReminder A/B ran one rep
  before the user stopped it: **both ep20 and ep23 hit
  max-iterations WITH the task+listing re-injected every turn** —
  recorded as preliminary-negative (n=1 per model, stopped per the
  user's read: a working reminder would show itself in rep 1;
  successes close in 6-11 iters). Conclusion: the wall is not
  attention — the map in front of the model every turn does not
  help. The instrument stays in the repo. **9B landscape research
  (user-directed): Qwen3.8 exists as 27B ONLY — no 7-9B variant;
  qwen3.5 has no 7b/8b (library sizes: 0.8b/2b/4b/9b/27b/35b-A3B/
  122b-A10B) — qwen3.5:9b is the only small-class candidate, already
  local, already scouted (S94.3: 11/15 zero-shot at fair timeouts).
  GPU math: 9B QLoRA ~16-18GB vs the free T4's 15GB — Colab Pro L4
  (24GB) or A100, or Kaggle 2xT4 sharded. Per direction: the 9B
  re-scout is RUNNING on the CURRENT 6-task harness (explore-qa
  included) — the kit-free gate for the base step-up: if the raw 9B
  shows explore-qa capability, the kit re-derivation + L4 training
  becomes the evidenced next slice.** Suite untouched (measurement
  slice).

- 2026-10-02 — **Gen-23 verdict — cascade RESTORED 3/3 (the
  opening-guess teacher confirmed as ep22's cause), but explore-qa
  0/3 with WORSE thrash (deterministic 10 failures x3,
  guessed_path 1.6667) and the deepest finding yet: the model
  guesses the DRILLS' file names instead of reading the live
  listing — rung 7 is a measured capability limit at this recipe;
  ep20/ep23 tie 15/18 on tasks, ep20 stays champion on behavior** —
  pinned 6-task, 600s: ep23 15/18 (calc/strings/json/cascade/
  indirect all 3/3 — **cascade's re-check confirms gen-22's cause:
  removing the opening-guess demos restored the band immediately**,
  explore-qa 0/3) vs ep20 15/18 (pinned 15/15, its FIFTH consecutive
  perfect reading; explore-qa 0/3). THE FORENSICS: ep23's explore-qa
  trajectory opens drilled (list -> README) then guesses
  docs/configuration.md and serverctl.py — names from the DRILL
  fixtures, absent from the eval listing (which shows docs/api.md +
  docs/running.md, never opened) — the model memorized drill
  content, not the read-the-map behavior. Three-attempt arc:
  ep21 (codeintel loop) -> ep22 (doc read, run_tests ritual) ->
  ep23 (fixture-name guessing) — each attempt moved the failure
  mode; none closed. Honest conclusion: **observation-grounded
  answering does not generalize across fixtures at 7B with ~10
  answer drills (6.5% deliberate share)**; the anti-guess and
  seam-rejection beats DID transfer and are banked. Task totals tie
  15/18; ep20-q4 REMAINS champion (chaining 1.0 vs 0.6, failures 26
  vs 48); ep23 not shipped. Recommendation recorded: move to rung-4
  authoring (the repair-task machinery where drills demonstrably
  generalize), rung 7 stays measured-not-conquered in the ladder.
  Suite untouched (verdict + docs slice).

- 2026-10-02 — **Gen-22 verdict — explore-qa's seam fix WORKED and
  exposed the wall behind it (the doc gets READ, then the model
  never answers); cascade REGRESSED 3/3 -> 0/3 with a guessed-path
  spike the recovery drill plausibly taught; ep20-q4 REMAINS
  champion (16/18 vs 12/18)** — pinned 6-task, 600s: ep22 12/18
  (calc/strings/json 3/3, indirect 3/3, **cascade 0/3 at only 3-4
  failures per run — a quieter failure than the old thrash**,
  explore-qa 0/3) vs ep20 16/18 (pinned 5 = 15/15, its FOURTH
  consecutive perfect reading). THE FORENSICS: the seam fix
  transferred — the recorded explore-qa failure shows the tempted
  calls rejected, **docs/running.md READ (the planted fact in
  context!), then run_tests x6 to max-iterations — the defect-fix
  verification ritual fired on a question that has no tests (0 tests
  = vacuous pass) and the answer never came**; the answer-QA final
  shape is drowned in the repair-demo majority. AND the S109
  recovery drill's demonstrated guessed-read plausibly TAUGHT path
  guessing: guessed_path 0.4444 (8/18 runs) vs ep21's 0.0 — the
  S100-era lesson in a new form: a failure demonstrated as an
  OPENING move gets imitated as an opening move. Honest verdict:
  ep22 recorded as regressed (cascade regression + explore-qa
  unmoved + guessed-path spike); ep20 stays champion. Named next
  levers: (a) supersede the recovery-v2 drill's guessed-read
  demonstration (it teaches the wandering), (b) answer-QA volume —
  the drills must demonstrate read-then-ANSWER-immediately (no test
  ritual) at higher share, (c) cascade re-check after the corpus
  settles. Suite untouched (verdict + docs slice).

- 2026-10-01 — **Gen-21 verdict (seed 42, 600s, 6 tasks) — the
  pinned set holds (ep20 15/15, its THIRD consecutive perfect pinned
  reading: rung-3 graduation COMPLETE; ep21 14/15 with one cascade
  flicker in-band) and champion stays ep20-q4 — but explore-qa is
  0/6: the S108 demos transferred PARTIALLY and rung 7 did not
  move** — ep21 14/18 (calc/strings/json/indirect 3/3 clean,
  cascade 2/3 with one max-iter run at 6 failures) vs ep20 16/18
  (the pinned 5 at 15/15). explore-qa: ep21 0/3 and ep20 0/3, all
  max-iterations. THE FORENSICS: ep21's failure anatomy is granular
  — the anti-guess beat TRANSFERRED (guessed_path 0.0 vs ep20's
  0.5556: the champion guesses paths on explore-qa, ep21 never
  does), the listing-first beat TRANSFERRED (its trajectory opens
  list → README), but the post-README seam FAILED: instead of
  returning to the listing and opening docs/running.md, it loops
  code_references(code_symbols hunting "main" with invented args x9
  — the cascade chain-2 loop's family, now in the QA context; the
  drill demonstrated the decoy-recovery but not the TEMPTED
  tool-call rejection at that exact seam). The repeated
  institutional lesson, third instance: beats transfer on first
  contact and evaporate at the continuation — demos must show the
  wandering being rejected at EVERY seam. ep21 NOT shipped; ep20-q4
  REMAINS champion. Named next: S109 explore-drill seam fix (the
  tempted-call beat at the post-README seam); rung-4 authoring now
  OPEN. Suite untouched (verdict + docs slice).

- 2026-10-01 — **Gen-20 confirmation (seed 43, 600s) — ep20 15/15
  AGAIN: 30/30 across both readings, the cleanest ledger line the
  program has ever produced; ep20-q4 SHIPPED as champion (dashboard
  default switched); ep17-q4 fallback at 23/30; ep21 GATE OPEN** —
  the confirmation held every task: calc 3/3, strings 3/3, json 3/3,
  **cascade 3/3 (6/6 across readings — the most volatile task in
  program history is now the most stable)**, **indirect 3/3
  zero-failure (6/6 — the S101-lineage anomaly is RESOLVED: the
  missing piece was persistence, not the drill)** vs ep17 11/15 at
  seed 43 (cascade 0/3, indirect 2/3). Combined two-reading ledger:
  **ep20 30/30 vs ep17 23/30.** Metrics: ep20 chaining 1.0, failures
  16, guessed_path 0.0, discovery 1.0 — perfect or best-possible on
  every line. The champion call: a 7-task win on the same-day
  head-to-head with the wins exactly where the single trained
  variable targeted, confirmed across seeds — no ambiguity.
  ep17-q4 remains as fallback. **ep21 (S108 rung-7 explore-qa demos)
  GATE OPEN** — the 0/6 zero-shot baseline is the measured target.
  Ladder ledger updated. Suite untouched (verdict + one-line UI
  default).

- 2026-09-30 — **Gen-20 verdict (seed 42, 600s) — ep20 15/15: THE
  FIRST PERFECT VERDICT IN PROGRAM HISTORY; cascade 3/3 and indirect
  3/3 — both standing walls FELL on the exact trained variable;
  ep17 same-day 12/15; seed-43 confirmation running before the
  champion call** — pinned 5-task, ep20-q4 (452-record S107 export,
  ~171 steps): **ep20 15/15** (calc 3/3, strings 3/3, json 3/3 —
  every dilution tripwire held, cascade **3/3 — the persistence
  drills delivered: the recorded success shows the drilled shape
  exactly (invalid code_diagnostics call -> read instead -> BOTH
  defects fixed from the actual file content, generalizing into a
  single def-anchored multi-line edit that sidesteps the ambiguity),
  indirect **3/3 zero-failure — the fabricated-anchor drill landed**
  ) vs ep17-q4 12/15 same-day (cascade 0/3 max-iter thrash x3).
  Metrics: success 1.0, discovery 1.0, chaining **1.0**, tool
  failures **12** total (vs ep17's 40), guessed_path 0.0 — the
  cleanest protocol line ever recorded. Dilution tripwires: NONE
  tripped (the +4-drills corpus protected every prior task band).
  Per the never-crown-on-one-reading rule the seed-43 confirmation
  is running; champion call and ep21 gate decision on its result.
  Suite untouched (verdict + docs slice).

- 2026-09-30 — **S107 — Drill persistence: the beats must survive
  into chain 2 (ep20's single variable)** — from the gen-19
  forensics: S1 the chain-2 catalog-tool loop, S2 the fabricated
  anchor, S3 the beats are one-shot. Batch of 4 (lane 4/4 passed the
  real gate, agent-authored + corpus-v8): metrics + scale re-authored
  on proven fixtures with NEW goals — both chains carry the
  rejected-call-then-read beat, chain 2 also the ambiguous re-anchor;
  budget (fresh self-ambiguating double-cascade); parcel/shipcalc —
  the fabricated-anchor drill (a genuine 0-hit miss under
  recovery_anchors; the corrective edit copies the line the fresh
  read actually showed). **En route the S95 failed-step cap was
  convicting the drills' DECLARED beats (3 deliberate failures >
  max 2) — the eligibility gate now exempts deliberate records
  (regression test pins both sides); the third same-class bug
  (accidental-vs-deliberate failure) after S104.1 and S106.**
  Export rebuilt: 452 records (148 deliberate + 296 real + 8 SRFT,
  ~171 Colab steps — the largest corpus in program history), all
  four S107 drills verified present. Suite 1769 OK, pyflakes clean,
  preflight clean. Spec: docs/s107-spec.md.

- 2026-09-30 — **Gen-19 re-verdict (OLLAMA_TIMEOUT=600, same pinned
  conditions) — ep19 7/15 IDENTICAL, the timeouts were NOT masking
  success; ep17 12/15 its best-ever reading; drill-persistence gap
  CONFIRMED as ep20's variable** — the 60s default request timeout
  was the source of all verdict DNFs (found and named); at 600s every
  DNF ran to completion: **ep19's timeout runs became max-iteration
  FAILURES, not successes** (json 1/3 with 2 max-iter; cascade 0/3
  with the 2 timeout runs becoming 6-10-failure thrash; indirect
  0/3 identical shape) — while **ep17's json timeout became a
  SUCCESS** (3/3; total 12/15, its best reading). Champion gap real
  on a fair reading: 7 vs 12. New forensics depth: the newest ep19
  cascade failure shows the chain-2 loop has a VARYING target — this
  run burned 5 iterations on failed `experience_record` calls (a
  memory tool!) after correctly applying the def-anchored add fix —
  the SAME structure as the code_diagnostics loop (chain 1 works,
  chain 2 never edits and loops on catalog tools). The
  drill-persistence diagnosis (beats must survive into chain 2) is
  confirmed as ep20's single variable; ep21 = rung-7 demos per the
  agreed sequence. ep17-q4 REMAINS champion. Ladder bands updated
  with the fair reading. Suite untouched (verdict + docs slice).

- 2026-09-28 — **Gen-19 verdict — the undertraining fingerprint is
  CONFIRMED FIXED, but ep19 7/15 < ep17 11/15; ep17-q4 REMAINS
  champion** — pinned 5-task, temp 0/seed 42, ep19-q4 (the retrained
  440-record export — attempt 1 was discarded when it FAILED sanity
  with token-soup output after the user's internet drop corrupted the
  Colab run; the retrain on a fresh runtime passed the knowledge-
  question probe cleanly): **ep19 7/15** (calc 3/3 with ZERO failures
  and 7-iter runs — ep18's 0/3/10-failure thrash signature GONE,
  strings 3/3 zero-failure clean, json 1/3 with one provider timeout,
  cascade 0/3 (1 max-iter at 4 failures + 2 timeouts at iter 8 with 1
  failure — alive when they died), indirect 0/3 max-iter ×3 at only
  2-3 failures) vs ep17 11/15 same-day (3/3, 3/3, 2/3, 0/3, 3/3).
  Metrics: ep19 tool_failures 19 vs ep17's 46 and ep18's 100 — the
  cleanest-behaving generation ever measured; chaining 0.8 vs 0.4;
  discovery 0.8 vs 1.0. Honest reading: the S106 scale restore did
  exactly what it claimed (thrash fingerprint eliminated, calc/
  strings perfect), and ep19's behavior is cleaner than the champion
  on almost every protocol metric — but the task wins are not there:
  indirect 0/3 is the SECOND straight generation the S101 drill (in
  corpus, verified) did not reproduce ep17's 6/6, and cascade
  remains the program's most volatile task (readings now 0,2,1,2,0,
  0,2,0 across generations). ep19 NOT shipped; ep17-q4 REMAINS
  champion. 3 of ep19's 15 runs were timeout-DNFs under tonight's
  machine load — a cleaner re-reading is cheap but the champion
  question does not hang on it. Named follow-ups: (a) indirect
  forensics (drill-in-corpus-but-capability-absent, 2 generations),
  (b) S107 rung-7 demos (0/6 baseline waiting). Suite untouched
  (verdict + docs slice).

- 2026-09-28 — **S106 — Training scale restored + the SECOND
  treadmill closed (the lane version-stamp bug); ep19 export is
  rebuild-stable at 440 records** — ep18's regression named the lever,
  and scoping the restore caught a bigger bug before it bit ep19.
  **The finding: build_agent_corpus never stamped the corpus version
  tag, so every hygiene run superseded the ENTIRE agent-authored
  corpus (72/72 records dead)** — each generation trained on only
  that cycle's fresh drills (ep18's export happened to contain its
  own cycle's, which is why cascade still improved; the export
  rebuilt after the S104.1 stability run had ALL of them dead —
  uploading it would have trained ep19 with zero drills). Fixes,
  three parts: (1) REAL_CAP_RATIO = 2 in training.py (the hardcoded
  1:1 cap silently halved the real share when the deliberate pool
  shrank); (2) the lane stamps VERSION_TAG at record time; (3)
  repair_agent_corpus_tags() — one-time store repair: un-supersede
  all agent-authored records (the supersession was the missing-stamp
  artifact; the lane is validator-enforced current-format by
  construction), stamp the tag, dedupe by normalized goal
  keep-newest (the treadmill left wave duplicates) — wired into
  build_corpus before hygiene. Result: deliberate 122 -> 144 (22
  distinct agent drills restored from 72 wave-duplicates), real kept
  288, **export 440 records (~165 Colab steps vs ep17's 144)**,
  both S104 drills verified present, 440/440 records carry the
  current system prompt. Idempotency proven: a second rebuild
  supersedes 0, pool holds. Suite 1768 OK, pyflakes clean,
  preflight clean.

- 2026-09-28 — **Gen-18 verdict — RECORDED AS REGRESSED (not
  shipped); the drills WORKED (cascade 0/6 → 2/3, first cascade gain
  from demos ever) but the smaller corpus undertrained everything
  else; ep17-q4 REMAINS champion** — pinned 5-task, temp 0/seed 42,
  ep18-q4 (252-record treadmill-cleaned corpus + the S104 re-anchor
  drills; 96 steps vs ep17's 144): **ep18 6/15** (calc 0/3 — the
  solved-since-gen-8 task COLLAPSED with deterministic 10-failure
  max-iter thrash ×3, strings 1/3, json 3/3, **cascade 2/3 — the
  exact S104 target MOVED**, indirect 0/3 — the S101 capability
  given back) vs ep17-q4 11/15 same-day (3/3, 3/3, 2/3*, 0/3, 3/3 —
  *json loss again a provider timeout). Metrics: ep18 tool_failures
  100 vs 28, diagnosis_chaining 0.0 vs 0.53, discovery 1.0 both.
  Honest reading (pre-framed before the run): the package change
  (drills + treadmill-cleaned corpus) makes this NOT a clean
  single-variable test — the broad collapse with a thrash signature
  is the undertraining fingerprint (96 steps + the 1:1 cap cut the
  real share 188 → 122), while the isolated cascade gain shows the
  drills transferred. Per S91.1 no single-verdict conviction — but
  ep18 cannot ship at 6/15 regardless, so a confirmation re-verdict
  buys nothing; ep19's lever is already named: restore the real
  share (298 real available, floored at 122 by the 1:1 cap) on the
  SAME drills — that isolates training scale with the drills kept.
  ep17-q4 REMAINS champion; dashboard default unchanged. Ladder
  ledger updated. Suite untouched (verdict + docs slice).

- 2026-09-28 — **S104.1 — The demo treadmill root-caused and fixed;
  the ep18 gate is LIFTED** — the export oscillation (deliberate pool
  188 → 122 → 144 → 122 across rebuilds) is a structural conflict,
  not data loss: **S71's rational recovery ordering puts the
  wrong-turn read FIRST by design; S68's hygiene rule supersedes any
  scripted demo whose first captured step is read_file** (written for
  pre-S66 answer-reading demos). Every recovery-variant demo
  therefore lived exactly one rebuild cycle — hygiene killed the
  previous wave, the goals re-demoed fresh read-first records, and
  the pool size depended on where in the cycle the rebuild ran
  (S102.3 read 188 only because that cycle ran build-training alone,
  no hygiene pass). Exonerations, both empirical: dedupe is innocent
  (reinforcement never rewrites context, so first steps cannot
  change; goal normalization keeps the suffix words, so benchmark
  runs cannot merge into demos), and the S104/S105 changes are
  innocent (a worktree A/B: pre-S104 code on the IDENTICAL store
  produces byte-identical numbers — deliberate 144, ACCEPT 1660).
  THE FIX: mark_superseded_demos exempts records carrying deliberate
  recovery tags (recovery-demo, edit-recovery) from the read-first
  rule; version-tag format staleness still applies. 22 plain
  read-first records correctly caught this pass; STABILITY PROVEN —
  a second rebuild supersedes 0 and the pool holds at 122. The
  rebuild is idempotent again; **ep18 may train on the current
  export** (122 deliberate + 122 real + SRFT). Regression test named
  after the failure mode. Suite 1765 OK, pyflakes clean, preflight
  clean.

- 2026-09-28 — **S104 + S105 — Cascade re-anchor drills (ep18's
  variable) + rung-7 explore-qa eval (measurement-first), and an
  export-oscillation finding that GATES ep18** — **S104**
  (docs/s104-spec.md): from the gen-17 forensics, two walls — W1 the
  schema-error loop, W2 the self-ambiguating fixture. Two re-anchor
  drills on fresh modules (metrics, scale) whose fixtures FORCE the
  collision: the naive anchor is genuinely rejected (matches 2x), the
  corrective edit re-anchors on the def line from a fresh read; each
  carries the W1 schema-fallback beat (invented-arg code_diagnostics
  → honest rejection → read instead). Validator gains the third
  anchor class ambiguous_anchors (genuine >= 2 hits, consumed,
  corrective edit required). Live: both drills passed the real gate,
  agent-authored. **S105** (docs/s105-spec.md): rung 7 as
  measurement — explore-qa appends sixth (the pinned 5-task set stays
  byte-stable), the answer lives only in docs/running.md, the fact
  gate demands both planted facts in the final answer (run_benchmark
  verifier= passthrough; AgentSession.pending_answer — the loop now
  exposes the answer under test before the gate). Zero-shot baseline
  running (ep17/ep11, n=3); first result: ep17 FAILED — the predicted
  live-sessions weakness. **THE FINDING: the export's deliberate pool
  oscillates across rebuilds (188 at S102.3 → 122 → 144 tonight) with
  hygiene code unchanged; 66 v8+recovery-demo records flipped to
  superseded.** Root cause not isolated (S68's read-first hygiene rule
  is in tension with S71's deliberate wrong-turn-first ordering;
  reinforcement merges may rewrite first steps). **ep18 is GATED on
  S104.1 forensics — no training on any export until the oscillation
  is root-caused.** Suite 1764 OK, pyflakes clean.

- 2026-09-28 — **Gen-17 re-verdict (seed 43, user-directed) —
  json loss confirmed environmental, ep17 WINS the two-reading
  ledger 23/30 vs 22/30, indirect 6/6; ep17-q4 SHIPPED as champion**
  — the user's instinct (ep17 should beat ep11 given indirect 3/3 +
  the json timeout) drove the confirmation run: **ep17-q4 12/15**
  (calc 3/3, strings 3/3, **json 3/3 — the seed-42 loss did NOT
  reproduce**, cascade 0/3 identical shape, **indirect 3/3 clean
  AGAIN — 6/6 across both readings, iters 7 / 0 failures every
  run**) vs ep11-q4 11/15 (cascade 2/3, indirect 0/3 — 0/6 across
  both readings). Combined: ep17 23/30 vs ep11 22/30; json 5/6 vs
  6/6; the tiebreaker is the deterministic indirect 6/6 vs 0/6.
  Honest caveats recorded: cascade deficit now CONFIRMED (0/6, two
  readings, identical failure anatomy — see the cascade forensics);
  thrash tax 82 tool failures vs ep11's 15; diagnosis_chaining 0.47
  vs 0.8. Cascade forensics (seed-42 runs, store): ep17's 0/3 is a
  **schema-error loop** — code_diagnostics(path=)/code_symbols(name=)
  invented args rejected, then the IDENTICAL invalid call repeated
  x8 to max-iterations; it never reads calc_ops.py. ep11's failed
  cascade runs show the DEEPER wall all generations hit: fixing add
  (a-b → a+b) makes multiply's edit anchor `return a + b` match 2x —
  the fixture is self-ambiguating — and ep11 re-reads and retries
  the rejected anchor to exhaustion instead of re-anchoring with
  context. S104 targets BOTH: re-anchor drill + schema-fallback
  beat = ep18's single training variable. Dashboard default model
  switched to ep17-q4. Suite untouched (verdict + one-line UI
  default).

- 2026-09-28 — **Gen-17 verdict — the S101 drill DELIVERED:
  indirect SOLVED 3/3 clean (first zero-failure indirect in program
  history), 11/15 tie with ep11; champion stays ep11-q4** — pinned
  5-task, temp 0/seed 42, ep17-q4 (fresh 382-record S101 export + the
  new conversational system prompt): **ep17-q4 11/15** (calc 3/3,
  strings 3/3, json 2/3 — the loss a provider TIMEOUT at iter 11 with
  runs 2-3 clean 7-iter successes, cascade 0/3, **indirect 3/3 at
  iters=7/calls=6/failures=0 on ALL THREE runs** — the R4
  wrong-value-rejection drill transferred exactly as scripted) vs
  ep16-q4 10/15 (3/3,3/3,3/3,1/3,0/3 — indirect max-iter ×3, the 1.4
  guess unresolved) vs ep11-q4 11/15 (3/3,3/3,3/3,2/3,0/3). Metrics:
  ep17 discovery 1.0, guessed_path 0.0 (best possible), but
  **tool_failures 40 vs ep16 13 vs ep11 9** — the thrash tax, almost
  all of it cascade (9 failures × 3 max-iter runs, deterministic
  shape); diagnosis_chaining 0.4 vs 0.8. Honest notes: (1) the
  conversational prompt line did NOT hurt coding behavior (with_calls
  1.0, discovery 1.0 — the S102.3 train/inference alignment risk
  retired); (2) cascade 0/3 is a real deficit SIGNAL but per the n=3
  rule one verdict does not convict — cascade is the most volatile
  task (ep11 itself: 0,2,1,2 across readings); (3) ep17 is the third
  generation with indirect 3/3 (ep13, ep15 before it) — rung-3
  lineage gap confirmed from a new angle: the DRILL, not luck, moved
  ep16's 0/3 to ep17's 3/3 clean. **ep17 NOT shipped (tie + thrash
  tax 40 vs 9 + cascade 0/3); ep11-q4 REMAINS champion.** Next
  lever: cascade stability for the ep17 lineage. Suite untouched
  (verdict + docs slice).

- 2026-09-28 — **S103.1 — Same-failure ladder outranks the
  environment branch (live retest finding)** — the user retried the
  docs question after S103: recovery FIRED VISIBLY (D1 working —
  environment_check events in the feed) and the model switched
  behavior each time (guessed doc → list → README → started
  synthesizing), but it re-read the same missing file
  (docs/running.md) 3x with successes interleaved and each failure
  re-earned ENVIRONMENT_CHECK — successes reset environment_repeat,
  so the env branch short-circuited the repeat ladder forever. Fix:
  the repeat ladder (repeat_count >= 3) evaluates BEFORE the
  environment branch; first/second occurrences keep the S98
  inspection (test amended with rationale), a 3rd identical failure
  reaches ALTERNATE_APPROACH. The session still died at iter 6 on an
  Ollama CPU timeout, and — the rung-7 evidence hardened — the README
  it read CONTAINED the answer (the S102.4 run section); the 7B
  anchored on the old Usage block instead. Spec amended
  (docs/s103-spec.md S103.1). Suite 1756 OK, preflight clean.

- 2026-09-28 — **S103 + S102.5 — Recovery ladder upgrade (cycling
  detection) + verify auto-detect (user-directed scope)** — **S103**
  (docs/s103-spec.md): the live docs-question thrash had THREE stacked
  defects, all fixed. D3: FailureTracker is success-aware — the loop
  reports successful tool results, and new cycling() fires on a
  streak of 5 failing steps with >=2 distinct signatures and NO
  success between them (the exact observed pattern, proven silent
  under the old consecutive-same rule by a regression test named
  after the failure mode); exploration that interleaves successes
  never fires (the corpus-taught guessed-path shape is protected).
  D2 (the S98 follow-up): environment decisions now COUNT — after 2
  in a failing streak they fall through to the counted ladder; the
  counter resets only on success (resetting on any non-env decision
  let env/retry alternate forever — caught by test, fixed). D1:
  tool-path recovery decisions now EMIT recovery_started with
  strategy+reason (only the no-op retry_with_advice stays silent) —
  the ladder is visible in the feed. **S102.5**: verify auto-detect —
  suggest_verify_command() sniffs top-level project markers
  (npm/cargo/go/pytest/unittest/make); picker Use-this-folder
  pre-fills the input, session start falls back to it, summary
  exposes the in-force gate ('verify: …' / 'no verify gate' in the
  status line); explicit input always wins. Sidebar: Session
  settings / **Verdict test** (renamed from Operations) / Sessions
  are collapsible (persisted). Ladder: **rung 7 proposed —
  observation-grounded exploration (explore-qa)**, deterministic
  fact-containment verifier, motivating evidence = the docs-session
  thrash; parallel-authoring note flagged. Suite 1755 OK (15 new),
  pyflakes clean, preflight clean.

- 2026-09-28 — **S102.4 — Session forensics made visible + the
  interleaved-thrash blind spot named (live user finding)** — the
  user's docs-question session ('how do I start this app? it should be
  in /docs') thrashed and the feed showed 'model started' after every
  step. INVESTIGATION: (1) model_started-per-step is BY DESIGN (the
  agentic loop consults the model after every observation; one call
  per iteration) — the raw name misread as a reload; (2) the user's
  context-loss hypothesis DISPROVEN with code: loop.py:369 appends
  every ToolResult to session.messages before the next model call —
  the listing WAS in context; the feed just never rendered
  tool_completed, so results were invisible. Fixed: tool_completed
  now carries a bounded observation head (output[:240]) and the feed
  renders 'tool → result' with human event labels (model_started →
  'thinking'). (3) The thrash anatomy: '/' boundary fail → README read
  (which had NO run instructions — README now has a 'Running the agent
  dashboard' section) → root listing seen but ignored → generic
  entry-path guesses cycling (src/main.py ×3, app/__init__.py ×2,
  list src) → cancelled at 10. (4) WHY RECOVERY NEVER FIRED — the
  named gap: FailureTracker.no_progress requires the SAME signature
  CONSECUTIVE ×3, but the model cycled 3-4 DIFFERENT failing paths, so
  the streak always reset; 7 failures/10 iterations with no
  session-level non-progress signal. Follow-up slice queued:
  session-level failure-rate detection in the recovery ladder (S58
  territory, needs its own tests). Suite 1740 OK, pyflakes clean.

- 2026-09-28 — **S102.3 — Chat layout + the hello-thrash fix (live
  user finding)** — INVESTIGATION: two live 'hello' sessions on
  ep11-q4 thrashed (12 iters incl. a screenshot; 5 iters) with no
  final answer — the system prompt taught 'inspect before acting, act
  through tools' with NO conversational escape, and the corpus trains
  discovery-first on every goal, so a greeting got the full explore-
  first treatment. Fix: one additive DEFAULT_SYSTEM_PROMPT line
  (greetings/questions with no workspace task → reply directly, no
  tool calls); text-only, loop/protocol untouched; regression test
  added. training.py renders build_system_prompt so the export was
  rebuilt the same cycle — all 382 records carry the new line
  (188 deliberate + 188 real + 6 SRFT; cap unchanged; curation picked
  up the S102.2 flash-lite drip pass into the real pool). **The fresh
  training/training.jsonl is the one to upload for ep17** (user had
  not started Colab — prompt now trains in, zero mismatch). UI: the
  right column is a chat panel — session status, live activity, Final
  response card, chat input with Send (disables to 'Agent working…'
  while running, Stop beside it); settings moved left. Suite 1740 OK
  (1740th = the prompt test), pyflakes clean.

- 2026-09-28 — **S102.2 — Picker modal + chat-style start (user
  feedback, same-day)** — the picker is now a real popup: fixed
  backdrop overlay, centered dialog card, click-outside AND Escape
  close, '>N more files' truncation note, no-matches state distinct
  from empty-directory. The goal box is now chat-shaped: Enter starts
  the agent (Shift+Enter newlines, IME-safe), Start disabled while the
  goal is empty, recents moved under the workspace row. Drip triage
  (user-reported timeouts, fully diagnosed): (1) the 'timed out' drips
  were READ timeouts, not quota — flash-latest's thinking turns exceed
  the 120s GEMINI_TIMEOUT default on the full agent-shape request;
  (2) at 300s the drip PROGRESSED (3 iters, 2 real calls) then died on
  an honest HTTP 429 — the flash-latest free-tier bucket (20 req/day)
  was drained by the user's two runs + the probe, confirming the
  user's out-of-quota guess for THAT bucket; (3) pinning
  GEMINI_MODEL=gemini-3.1-flash-lite (its own bucket) +
  GEMINI_TIMEOUT=300 produced a clean **drip SUCCESS — goal completed,
  6 iters, 5 calls, 0 failures** (verified pass feeding the corpus).
  Standing recipe for live drips: pin flash-lite + 300s timeout.
  npm build green, suite 1739 OK.

- 2026-09-28 — **S102 + S102.1 — Dashboard polish + file picker
  (user-tested feedback addressed)** — S102: the "no output" complaint
  root-caused — the agent's FINAL ANSWER (session.final_result) was
  never serialized to the UI; server summary now exposes it, rendered
  as a green final-answer block. Two-column responsive layout (controls
  left, live session right); feed gains timestamps + auto-scroll +
  tool-arguments rendering + empty states; jobs show relative start
  time; drip/verdict buttons disable while running (no double-fires);
  session history shows model + file count; verification PASS/FAIL
  colored; files changed as chips. S102.1: the file picker upgraded —
  server browse_directory returns top-level files (sorted, hidden
  excluded) alongside directories; picker gains a filter box over
  entries, manual path entry with Go (Enter works), read-only file
  listing (capped 20, dim mono), empty-directory state, and
  Use-this-folder now remembers the choice; recent workspaces (up to 5,
  localStorage) render as one-click buttons under the workspace row.
  npm build green. Suite 1739 OK, pyflakes clean. Spec: none (UI
  polish; behavior additive, no spec'd surface changed).

- 2026-09-27 — **S101 — Wrong-value recovery drill (the ep16
  indirect answer)** — seed-43 re-probe: 1/3 (one clean 1.2
  success, two identical 1.4-guess + cart-compensation +
  stale-retry failures) → 5/6 runs share one systematic
  instance: biased value guess, no re-derivation. R4 (fresh
  order/fees) scripts the guess rejected for real, then derives
  36/30 = 1.2 from the test before correcting; all anchors
  match, no declaration needed. Live: lane 1/1 + 19 skipped,
  export 382 = 188 + 188 + 6 (cap cut deeper to 36 as verdict
  runs grew the real pool; stripped 65). Suite 1739 OK,
  pyflakes clean. Colab order: fresh 382-row training.jsonl +
  s92 kit → ep17 → pinned verdict vs ep11-q4 with indirect
  second-seed re-probe. Spec: docs/s101-spec.md.

- 2026-09-27 — **S100.1 Gen-16 verdict — strings FIXED 3/3
  (first minimal anchor at inference), 12/15 tie, indirect
  wobbles** — pinned 5-task, ep16 trained on the 380-row S100
  export: ep16-q4 12/15 (calc 3/3, **strings 3/3** (was 0/3),
  json 3/3, cascade 3/3, indirect 0/3 (was 3/3)) vs ep11-q4
  12/15 (3/3,3/3,3/3,3/3,0/3). Mechanism, not luck: ep16's
  strings edit is the MINIMAL single-line anchor (`return text`
  → `return text[::-1]`) — first time any generation emits the
  demo shape instead of a whole-file rewrite. Hygiene partial
  (failures 18 → 11, guessed 0.2 → 0.0; residual is
  codeintel-probing, not path-guessing). Indirect 0/3 is
  wrong-value (1.5 → 1.4, needs 1.2) + no recovery — same shape
  as the old collapse, new instance; per the n=3 rule it is
  UNCONFIRMED volatility, flagged for re-probe, not convicted.
  ep16 NOT shipped (tie + 11 vs 3 failures); ep11-q4 REMAINS
  champion. Suite untouched (docs-only slice).

- 2026-09-27 — **S100 — Failed-edit-recovery demos + thrash-turn
  surgery (the ep15 strings prescription)** — audit proved the
  mechanism (whole-file rewrite breaks sibling, stale retry
  misses, never re-edits) and the vector (training 50% real
  verdict-successes with ~1 fail/run of accidental thrash).
  Probes: minimal-edit prompt 0/3 (not steerable — weights fix
  required), single-function 2/2 (skill exists, load breaks it).
  R1 replays ep15's exact failure args then recovers from a fresh
  read; R2/R3 generalize to fresh modules; validator simulates
  file state and demands declared misses be genuine, consumed,
  and corrected (authoring stays untrusted). Training renders
  drop failed turns from undeliberate records only (deliberate
  beats kept; S72 interleave remapped; full truth kept in
  trajectories.jsonl) and caps the real share 1:1 cleanest-first.
  Live: lane 3/3 + 16 skipped, export 380 = 187 + 187 + 6
  (capped 13, stripped 97). Suite 1738 OK, pyflakes clean.
  Colab order: fresh 380-row training.jsonl + s92 kit → ep16 →
  pinned 5-task verdict vs ep11-q4. Spec: docs/s100-spec.md.

- 2026-09-27 — **S95.1 Gen-15 verdict — 12/15 TIE with ep11,
  strings batch failed, indirect solved** — pinned 5-task, ep15
  trained on the 365-row S95 export (confirmed): ep15-q4 12/15
  (calc 3/3, **strings 0/3 deterministic — the S94 batch did NOT
  fix the lineage deficit**, json 3/3, cascade 3/3, **indirect
  3/3 clean**) vs ep11-q4 12/15 (3/3,3/3,3/3,3/3,0/3). Hygiene
  partial credit (failures 44-64 → 18) but nowhere near ep11's
  3; guessed 0.2 vs 0.0. Rung-3: ep13/15 solve indirect (3/3,
  3/3) where ep11 scores 0/3, 0/3 — lineage gap real,
  demo-vs-transfer unisolated. ep15 NOT shipped (tie + thrash
  tax + strings 0); ep11-q4 REMAINS champion. Suite untouched
  (docs-only slice).

- 2026-09-27 — **S99 — Dashboard approvals + image guidance**
  — user Firefox forensics: capture ok, inspect denied (no
  confirmer), binary-read loop ×5 → honest FAILED at 9 via S98
  ladder. Approve/Deny seam (timeout denies, DESTRUCTIVE stays
  DENY) + binary error names image tools + *.png ignored. Live
  proof: approved inspect → COMPLETED. Suite 1727 OK. Spec:
  docs/s99-spec.md.

- 2026-09-27 — **S98 — Window matching + loop termination** —
  user session forensics (13 steps): desktop shot worked, Firefox
  failed on arg-name + exact-only matching, then 5 identical
  re-reads (S58 never wired into dashboard). Substring matching
  with title echo, `window` alias, optional capture paths
  (desktop also burned 2 turns on missing path), RecoveryPolicy
  wired in. Live Firefox proof captured. Noted follow-up:
  environment-marker failures loop uncounted. Suite 1721 OK
  (1713 + 8, verified). Spec: docs/s98-spec.md.

- 2026-09-27 — **S97 — Eyes for dashboard sessions + blank
  detector** — screenshots were never offered (coding registry
  has no vision); dashboard sessions now get all 5 vision tools
  (captures land as workspace PNGs, inspect needs the key and
  stays confirmer-denied) + new READ_ONLY `detect_blank_screen`
  for loading-hang detection. Live proof: real session
  COMPLETED with shot.png in workspace. Suite 1713 OK, pyflakes
  clean. Spec: docs/s97-spec.md.

- 2026-09-27 — **S96.2 Dashboard protocol fix (user-tested)** —
  dashboard was the only NATIVE-path consumer; ep11 speaks
  TEXTUAL, so sessions completed with 0 calls. Factory now
  builds ollama sessions textual (gemini stays native) +
  UNVERIFIED badge + verify-command input. Live re-run: 25
  calls, document read. Suite 1707 OK. Spec: docs/s96-spec.md
  (S96.2 section).

- 2026-09-27 — **S96.1 Dashboard repair (user-tested same
  day)** — root cause: `main.tsx` never imported the stylesheet
  (dark theme existed since S52, never wired — always white) +
  query params never URL-decoded (Up-button KeyError) + `qa`
  never installed (`qa.bat` shim + docs) + stylesheet completed
  for every class. npm build emits real CSS now; live smoke
  (CSS link, encoded browse, 20 models). Suite 1706 OK. Spec:
  docs/s96-spec.md (S96.1 section).

- 2026-09-27 — **S96 — Dashboard usefulness (deferred backlog,
  now unblocked)** — model chooser from `ollama list` (9B slides
  in free) + per-session provider override + folder picker over
  `/api/browse` + feed payload rendering (the tested complaint)
  + verdict temp/seed inputs. Server hermetic tests (7 new),
  npm build green, live smoke vs real ollama/fs. Electron,
  thinking toggles, dashboard training stay deferred. Suite 1705
  OK, pyflakes clean. Spec: docs/s96-spec.md.

- 2026-09-27 — **S95 — Rung-3 demos + success-hygiene filter
  (ep11-beats-ep14 explained)** — forensics: verdict successes
  at ~1 fail/run with uncorrected wrong turns taught ep12–14 to
  thrash (0.28 vs ~1.0 tracks inference 3 vs 44–64); ep11 won on
  pre-wave hygiene. Rung-3: invoice/checkout/basket import demos
  (plain reads only — no codeintel in lean catalog; fresh
  modules). Hygiene: >2 failed steps excluded (82 cut live, all
  demos survive). Lane idempotency fixed (was doubling demos per
  rebuild). Live: lane 16/16, curate 1435/2/1, export 365 = 360
  + 5 SRFT. Kit untouched (s92). Colab: fresh 365-row
  training.jsonl + s92 kit → ep15 → pinned vs ep11. Suite 1698
  OK, pyflakes clean. Spec: docs/s95-spec.md.

- 2026-09-26 — **S94.3 9B exploration close-out — 4b ruled out,
  think adds nothing, 9B queued** — think-on cascade probes:
  9b 3/3 (identical to think-off — thinking buys latency, not
  capability here), 4b 0/3 BUT with calls appearing (14/6/4 vs
  zero think-off: thinking is load-bearing for the small model's
  tool-calling, yet completion still absent — 4b RULED OUT as an
  agent base). Combined 9B: 11/15 with time (calc/strings/cascade
  3/3, json 1/3, indirect 1/3); timeouts explained the cutoffs
  but rates barely moved. Verdict default stays think-off.
  Rung-3 demos (S95) are next; 9B-SFT stays queued (kit
  re-derivation + bigger GPU required). Suite untouched
  (docs-only slice).

- 2026-09-26 — **S94.2 Scout verdict — raw qwen3.5:9b scores
  10/15; ep11 consistency confirmed; ep14 volatile** — pinned
  3-way (temp 0/seed 42, think-disabled for the 9B on CPU):
  ep14-q4 8/15 (calc 1/3, strings 0/3, json 3/3, cascade 3/3,
  indirect 1/3; failures 64) vs ep11-q4 12/15 (3/3,3/3,3/3,3/3,0/3;
  failures 3, second straight 12/15) vs **qwen3.5:9b raw 10/15
  (calc 3/3, strings 3/3, cascade 3/3, json 1/3, indirect 0/3)**.
  The 9B solves rung-1 + cascade ZERO-shot under our contract —
  strongest raw base ever measured. Honest caveats: its json/
  indirect failures are provider TIMEOUTS (slow turns, not proven
  incapability); think-disabled, so thinking-enabled remains
  unmeasured; different arch/tokenizer (qwen35) means kit fixups
  need re-derivation before any SFT. ep14 verdict-to-verdict
  (11/15 → 8/15, strings 2/3 → 0/3) reads volatile next to
  ep11's back-to-back 12/15 — the S94 batch effect is
  inconclusive, ep14 not shipped. ep11-q4 REMAINS champion.
  Suite untouched (docs-only slice).

- 2026-09-26 — **S94.1 Gen-14 verdict — strings repaired (0→2),
  ep11 holds, base scores ZERO, rung 2 GRADUATES** — pinned
  3-way, 5 tasks: ep14-q4 11/15 (calc 2/3, **strings 2/3 (batch
  worked, 0→2)**, json 2/3, **cascade 3/3**, indirect 2/3) vs
  ep11-q4 12/15 (3/3,3/3,3/3,3/3,0/3) vs **raw qwen2.5-coder:7b
  0/15 — every run a provider timeout, discovery 0.0, chaining
  0.0: the SFT added the entire capability** (honest caveat: base
  too slow on CPU to complete turns, so "can't reason" vs "too
  slow" is unisolated — but trained models finish in 6-8 clean
  iters where base burns 8-11 and dies). ep14 NOT shipped (calc
  drop 3→2, 44 failures vs 3 — thrash tax; strings gain real but
  partial). **Rung-2 GRADUATION ruled**: probe 12/12 + S93.1 3/3
  + S94.1 3/3 = three consecutive pinned in-band readings across
  the 7B line → rung-3 demo authoring OPENS (S95). Rung-3
  indirect: ep14 2/3, ep13 3/3, ep11 0-1/3 (transfer, volatile).
  Suite untouched (docs-only slice).

- 2026-09-26 — **S94 — Strings-repair batch (Branch B of the ep13
  fork)** — ep13 pinned full verdict: calc 3/3, strings 0/3
  (deterministic), json 3/3, cascade 3/3, **indirect 3/3 with zero
  demos** → 12/15. Clip doubly exonerated for strings → dilution
  confirmed (0 authored string drills vs 5+5 json/cascade). Batch:
  greeting/word_ops/text_utils drills with fixture-inference
  narratives + one recovery beat. Live: lane 13/13, curate
  1302/2/1, export 299 = 294 + 5 SRFT (verdict successes feeding
  the corpus, S41-gated, watched). Kit untouched (s92). Colab:
  fresh 299-row training.jsonl + s92 kit → ep14 → pinned
  head-to-head vs ep11. Suite 1695 OK, pyflakes clean. Spec:
  docs/s94-spec.md.

- 2026-09-26 — **S93.1 Pinned verdict — cascade SOLVED (3/3 both),
  ep12 strings flicker confirmed REAL (0/3 deterministic)** —
  temp 0 / seed 42, 5 tasks: ep12-q4 9/15 (calc 3/3, strings 0/3,
  json 3/3, **cascade 3/3**, indirect 0/3) vs ep11-q4 13/15
  (calc 3/3, strings 3/3, json 3/3, **cascade 3/3**, indirect
  1/3). Cascade deterministic 3/3 both = capability real, all
  prior volatility was sampling noise (rung-2 first pinned point).
  ep12 strings 0/3 with byte-identical failing trajectories =
  NOT variance (0,3,0 across verdicts) vs ep11 rock-solid
  (3,3,3,3) — a genuine ep12 deficit signal (batch-3 dilution or
  clip; unisolated). Indirect baseline: 0-1/3 as designed (no
  demos). Metrics: failures 15 vs 3, guessed 0.2 vs 0.0.
  ep11-q4 REMAINS champion; ep12 not shipped. Suite untouched
  (docs-only slice).

- 2026-09-26 — **S93 — Measurement-first stability (pinned
  decoding + rung-3 eval-only task)** — the variance was sampling
  noise: harness never set temperature (all verdicts ran Ollama
  default 0.8). Pinned temp 0/seed 42 plumbed bridge→provider→CLI;
  `defect-fix-indirect` built eval-only (subprocess-proven, zero
  demos — gate-letter override, spirit holds). Probe headline:
  **cascade 12/12** (ep12+ep13 × budgets 12/16, all 10/9/2) —
  greedy decoding executes the taught chain deterministically;
  budget stays 12. Honest bound: one trajectory repeated (seed-
  robustness unmeasured). Suite 1687 OK, pyflakes clean. Spec:
  docs/s93-spec.md.

- 2026-09-26 — **S92.1 Gen-13 verdict — clip EXONERATED, gen-12
  "regression" WITHDRAWN as variance (three-way, same day)** —
  ep13-q4 (S91 corpus + clip 0) **8/12** vs ep12-q4 (same corpus +
  clip 1.0) **11/12** vs ep11-q4 **9/12**: calc 3/3 all; strings
  ep13 1/3, **ep12 3/3 (the verdict-day 0/3 did NOT reproduce)**,
  ep11 3/3; json 3/3 all three (solved, 5 of last 6 7B readings);
  cascade ep13 1/3, **ep12 2/3 (ties best rung-2 rate)**,
  ep11 0/3. If the clip were guilty ep13 would beat ep12 — it
  lost by 3, so the clip is innocent (possibly helpful) and the
  gen-12 gap was a bad n=3 draw. Institutional lesson recorded:
  NEVER convict a regression on a single n=3 verdict (S91.1's
  error — ep12 went 6/12 then 11/12 on back-to-back days);
  regressions need confirmation. Cascade stays volatile everywhere
  (ep11: 1/3, 0/3, 2/3, 0/3) — rung-3 gated. Champions SHARED
  ep11/ep12 pending stability; ep13 not shipped. Metrics: ep11
  behaviorally cleanest (failures 9, chaining 0.92), ep12 best
  rates. Suite untouched (docs-only slice).

- 2026-09-26 — **S92 — Clip revert (the clean clip-effect test)**
  — S91.1 convicted the S91 clip restoration (ep12 6/12 vs ep11
  11/12), so 7B is back to `max_grad_norm=0`, corpus untouched.
  ep13 (S91 corpus + clip 0) vs ep12 isolates the clip exactly;
  three-way verdict vs ep11-q4 judges dilution too. Colab order:
  SAME 194-row training.jsonl + s92 kit (rebuild only on corpus
  change). Suite 1687 OK, pyflakes clean. Spec: docs/s92-spec.md.

- 2026-09-25 — **S91.1 Gen-12 verdict — RECORDED AS FAILED
  (regression): ep12-q4 6/12 vs ep11-q4 11/12** — ep12: calc 3/3,
  **strings 0/3 (all max-iters WITH full 12-call chains — working,
  not dialect confusion)**, json 2/3, cascade 1/3; ep11 SAME DAY:
  calc 3/3, strings 3/3, json 3/3, **cascade 2/3** (11/12, 91.7%).
  Metrics all favor ep11 (discovery 1.0 vs 0.75, chaining 0.75 vs
  0.5, failures 18 vs 22, guessed_path 0.0 vs 0.25). Same-day
  head-to-head controls for environment — this is signal, not luck.
  Suspects (ranked): (1) clip restoration changed every update —
  the bundled variable, per the user's own contingency S92 reverts
  it for a clean clip-effect test (ep13 = S91 corpus + clip 0);
  (2) corpus dilution — batch 3 added cascades only, strings/json
  share fell; (3) the pre-verdict 0/3 dialect mode did NOT
  reproduce (ep11 cascade now 1/3, 0/3, 2/3 — volatile, rung-3
  stays gated). ep11-q4 REMAINS champion; ep12 not shipped.
  Bright spots: ep11 json 3/3 reproduced (solving), cascade 2/3 is
  the best rung-2 rate yet. Suite untouched (docs-only slice).

- 2026-09-25 — **S91 — ep12 corpus (cascade batch 3 + clip
  restoration)** — pre-verdict 0/3 is a NEW mode (dialect confusion:
  native-JSON-as-text finals, 0 parsed calls — not a refutation of
  the 1/3; band 0–0.33, rung-3 gated). Batch 3: math/text/list_ops
  double-chains on fresh modules (never calc_ops, which shares the
  eval module). Kit s91 restores clip 1.0 (fp32 passes unscale_;
  revert documented). Live: lane 10/10, curate 1172/2/1, export
  194 = 190 + 4 SRFT. Colab order: fresh training.jsonl + s91 kit
  → ep12 → verdict vs ep11. Suite 1687 OK, pyflakes clean. Spec:
  docs/s91-spec.md.

- 2026-09-25 — **S90.1 Gen-11 verdict — the json wall FALLS (3/3),
  10/12 vs 5/12; first cascade success** — ep11-q4 imported clean
  (GGUF-LoRA merge path: base + adapter GGUFs + llama-export-lora;
  q4_K_M quantized LOCALLY with prebuilt llama-quantize after the
  Colab q4 was lost with its runtime — the deleted-file incident is
  why local recovery exists; sanity probe "Paris" clean) and the
  verdict (rate-based, n=3 x 4 tasks, budget 12): **ep11-q4 10/12
  (83.3%) vs ep10 5/12 (41.7%)** — calculator 3/3 vs 3/3,
  **strings 3/3 (perfect) vs 2/3**, **json 3/3 vs 0/3 — the first
  json success in program history, on all three runs (7 iters, 6
  calls, 0 failures each)**, **cascade 1/3 vs 0/3 — first rung-2
  success**. Metrics: discovery 0.83 vs 0.67, guessed_path 0.0 vs
  0.5, tool failures 7 vs 11. Honest notes: (1) TWO variables moved
  (7B base + S82 batch vs 3B + pre-S82 corpus) — the base-size
  effect is NOT isolated, attribution shared; (2) ep10 calc 3/3
  today vs 1/3 verdict-day is in-band variance (band 0.33-1.0);
  (3) cascade 1/3 meets the rung-2 graduation threshold but rung-3
  demos stay gated until 3 consecutive in-band verdicts (anti-flaky
  gate holds). Per the user's rule q4 success retires the 15GB f16
  import. Suite untouched by verdict (docs-only slice).

- 2026-09-25 — **S90 — 7B import via GGUF-LoRA merge (no 15GB
  dequant)** — training RAN; the converter refuses bnb-quantized
  merged dirs (q8_0 innocent). Full fp16 dequant fits neither T4
  nor Colab RAM, so 7B merges at GGUF level (base + adapter GGUFs
  + llama-export-lora, verified vs current llama.cpp); kit
  censuses the merged dir, strips only stale quant claims, README
  splits 3B/7B paths. No retraining (adapter is the artifact).
  Suite 1687 OK, pyflakes clean. Spec: docs/s90-spec.md.

- 2026-09-25 — **S89 — Adapters to fp32 (the clip path's only
  accepted dtype)** — the S88 census completed the truth table:
  cast held, grads fp16, crash moved to `_get_grad_norm`'s
  unconditional inf-clip (`max_grad_norm=0` skips one of two clip
  calls). `unscale_()` accepts exactly fp32 — adapters go fp32
  (standard master-weight recipe, 161MB). Clip stays 0 (one change
  per slice; 1.0 restore is a follow-up). Suite 1687 OK, pyflakes
  clean. Spec: docs/s89-spec.md.

- 2026-09-25 — **S88 — Clip path is the killer (no clipping on
  7B)** — the S87 cast held (392 fp16, mixed fp16) and the new error
  named the mechanism: torch 2.11 `unscale_()` rejects fp16 grads,
  and the trainer clips through it. 7B sets `max_grad_norm=0`
  (scaler.step unscales fp16 fine); 3B keeps 1.0; census catches
  ValueError too. Suite 1687 OK, pyflakes clean. Spec:
  docs/s88-spec.md.

- 2026-09-25 — **S87 — Census convicts, adapter cast to fp16** —
  the S86 census named all 392 LoRA adapters going fp32→bf16 inside
  SFTTrainer construction/prepare (fp32 at probe, bf16 at first
  clip). 7B path now casts every lora_ param to fp16 after
  construction (proven 3B recipe) with an attesting print; census
  stays as verifier; precision-flags probe getattr-guarded (5.17
  dropped `half_precision_backend`). Suite 1687 OK, pyflakes clean.
  Spec: docs/s87-spec.md.

- 2026-09-25 — **S86 — Failure-path census (name the bf16 tensor
  in situ)** — the S85 probe (fp16 autocast default, 392 fp32 grads)
  plus the unchanged crash proves the tensor appears between probe
  and scaler-step, and Colab's collapsed frames hide the site — so
  `trainer.train()` now censuses param/grad dtypes by name plus
  precision flags on `NotImplementedError`, then re-raises. Zero
  cost green, full diagnosis red. Suite 1687 OK, pyflakes clean.
  Spec: docs/s86-spec.md.

- 2026-09-25 — **S85 — Runtime bf16 hunt (autocast probe + grad
  census)** — the S84 audit came back fully clean (params, config,
  effective compute, 392 adapters — 0 bf16) yet training still died,
  so the source is runtime, not weights. 7B path now probes the
  process cuda autocast default (pins fp16 if bf16) plus one
  micro-batch forward+backward under explicit fp16 autocast
  censusing grad dtypes by name, gated fail-loud either way. 3B
  untouched. Suite 1687 OK, pyflakes clean. Spec: docs/s85-spec.md.

- 2026-09-25 — **S84 — bf16 with a clean audit (v5 kwarg +
  setup-time sources)** — the S83 audit output diagnosed it: 0 bf16
  params pre-LoRA yet bf16 grads at the first backward (setup-time
  source), and 5.17 deprecation-proves `torch_dtype` no-ops
  (model.dtype=float32). 7B path now signature-sniffs the v5 `dtype`
  kwarg, pins `config.torch_dtype`, and audits effective bnb compute
  + post-LoRA adapters, each fail-loud. 3B string form untouched.
  Suite 1687 OK, pyflakes clean. Spec: docs/s84-spec.md.

- 2026-09-25 — **S83 — Colab bf16 second strike (dtype objects +
  audit gate)** — Colab threw the same GradScaler bf16 error against
  the current 326-line file, proving the S79 string fix insufficient.
  7B path now passes real `torch.float16` objects (bnb compute string
  is the prime suspect: unconverted → bf16 model default) plus a
  fail-loud dtype audit gate (versions + bf16 param list) before
  LoRA; proven 3B string form untouched. Torchao stays a README
  uninstall line (script never imports it). Suite 1687 OK, pyflakes
  clean. Spec: docs/s83-spec.md.

- 2026-09-25 — **S82 — Agent-authored batch 2 (json volume + second
  cascade, rungs 1-2 only)** — the S80 lane working as intended:
  session_store two-level drill with a genuine wrong-turn read
  (recovery beat for the json set), retry_policy clean drill
  (synthesis volume), string_ops second cascade (persistence beyond
  one module); rung 3+ stays gated. Live: lane 7/7 passed on the
  real store, curate 1135/2/1, training export 169 = 165
  step-trainable + 4 SRFT (all 7 demos present). Colab order: upload
  the fresh training.jsonl BEFORE the ep11 run. Suite 1687 OK,
  pyflakes clean. Spec: docs/s82-spec.md.

- 2026-09-25 — **S81 — 7B T4 OOM fix (lean prepare, batch 1,
  checkpointing on)** — Colab error after the S79 bf16 fix:
  `prepare_model_for_kbit_training` OOM at the fp32 norm upcast
  (2.03 GiB ask, 1.72 free, 12.84 in use on the 14.56 GiB T4).
  7B path now leans out the prepare (`use_gradient_checkpointing=
  False` + manual checkpoint enable + `use_cache=False` +
  `empty_cache`), `SFTConfig` checkpoints on 7B (was off) at batch
  1 x accum 8, README gains the fresh-runtime +
  `expandable_segments` runbook; 7B-only fail-loud, no 3B fallback
  (S79 attribution intact). Zcode last-context recovered read-only
  (bf16 fix confirmed landed; quota ended that session). Suite 1687
  OK, pyflakes clean. Spec: docs/s81-spec.md.

- 2026-09-25 — **S80 + S79 — Agent-authored demonstrations, the
  capability ladder, and the 7B kit** — **S80:** the authoring lane
  is untrusted-by-design — `validate_demonstration` (the
  anti-flakiness quality bar: discovery-first, module read, exactly
  one non-empty final that names a file it actually touched, every
  edit anchor matches its fixture exactly once, goal identity) plus
  the S41 gate are the only trust, so ANY author can write demos
  without being able to poison the corpus; `build_agent_corpus` runs
  the lane (validator → real benchmark → `agent-authored` tag). The
  validator rejected the author's own first goal on landing (too
  few substantive words — the flow working as intended). First
  batches: 3 json synthesis drills whose narratives walk the TEST
  FIXTURE (teaching where the nesting comes from — the inference
  step, not just the expression) + 1 cascade double-chain
  persistence demo (second failure → re-diagnose from scratch →
  name BOTH fixes). **The capability ladder** (docs/capability-
  ladder.md): 6 rungs documented (persistence → cross-file
  dependency tracing → test authorship with mutation proof →
  runtime-behavior debugging → multi-file feature), each with
  graduation criteria; the anti-flaky gate is structural — no
  rung's demos are authored until the rung below is stable for 3
  consecutive verdicts; the authoring runbook makes external
  authoring (muse-spark, any agent) a documented workflow.
  **S79:** the kit takes the base model as argv[2] — 7B trains in
  4-bit QLoRA (nf4 + double quant + prepare_model_for_kbit +
  paged_adamw_32bit) on the free T4; fixups/masking/gates carry
  over; README now generated from the template with both args (a
  direct README edit was getting clobbered by regeneration —
  root-caused). **Subjects stay coding-only by direction; the
  ladder's rungs ARE the new subjects.** Next: one Colab job —
  ep11-7b on corpus-v8 + agent-authored lane → 4-task verdict vs
  ep10. Suite 1687 OK, pyflakes clean. Specs: docs/s79-spec.md,
  docs/s80-spec.md.

- 2026-09-25 — **S78.1 Gen-10 verdict — strings solidifies (2/3),
  json and cascade walls hold, ep10 > ep9 on every task** — ep10
  imported clean (GGUF path) and the verdict (rate-based, n=3 x 4
  tasks, budget 12): **ep10 3/12 (25%) vs ep9 1/12 (8.3%)** —
  calculator 1/3 vs 1/3 (the rate band at this scale is 1/3-3/3
  across generations; single-run variance is real), **strings 2/3
  (strings is solidifying: 0 -> 1 -> 2 successes across gens 8-10)**,
  json 0/3 and **cascade 0/3 — the new rung failed as a next-step-up
  test should** (two defects, persistence beyond one chain; that is
  the ladder working, giving gen-11 a target). The SRFT ok=True
  filter did its job: guessed_path 1.22 -> 0.42 (no path-guessing
  inflation). Metrics: discovery 0.67 vs 0.33, chaining 0.92 both,
  tool failures 14 vs 33. Honest notes: (1) an earlier same-evening
  3-task verdict run showed ep9 degraded (three provider timeouts,
  chaining 0.44) — model-swapping load contamination; the 4-task run
  is the clean one; (2) json held at 0/6 across both verdicts DESPITE
  24-variant volume teaching — the synthesis capability limit at 3B
  is now the best-evidenced conclusion in the program; (3) ep9's
  recorded 3/3 calculator from its own verdict day did not reproduce
  (1/3 both runs) — the band is real and n=3 rates are the honest
  floor. The ledger after ten generations: calculator solved-band
  (0.33-1.0), strings flickering-to-solid (0-0.67), json and cascade
  unsolved. Suite 1683 OK, CI green. Spec: docs/s78-spec.md.

- 2026-09-25 — **S77.1 Gen-9 verdict — calculator consolidated to
  1.0 (first perfect task rate); the json wall holds; strings was
  variance** — ep9 imported clean (GGUF path) and the verdict
  (rate-based, n=3 x 3, budget 12): **calculator 3/3 SUCCESS — the
  first perfect task rate in program history** (5-8 calls, 0
  failures, 5-6 iterations, three for three); strings 0/3 and json
  0/3, overall 3/9 == ep8's 3/9. The rate-based decomposition does
  its job: gen-8's single strings success did not reproduce (1/9 was
  sampling variance, exactly what the gen-7 lesson predicted), while
  calculator moved 2/3 → 3/3 with zero-failure runs. Honest notes:
  (1) **the SRFT prefix rule may teach path-guessing** — prefixes
  from failed runs include their failed reads (guessed_path 0.78 →
  1.22), a real cost of mining failed trajectories unselectively;
  a future lane should filter ok=True reads only; (2) json's
  synthesis step (compose the chained .get from the test fixture)
  remains beyond reach at this scale despite 4x coverage + SRFT —
  the demos teach reading the fixture, the models still cannot
  reliably compose the novel expression; (3) tool failures 31 vs 12
  track the same exploration increase. The generation-over-
  generation ledger: calculator is SOLVED at this scale (5 of last
  6 runs across two generations), strings succeeded once
  (variance), json never. Suite 1682 OK. Spec: docs/s77-spec.md.

- 2026-09-25 — **S78 Gen-10 corpus — the SRFT correction + volume
  teaching the json synthesis + the capability ladder** — Three
  pieces. (1) **SRFT lane filter (the gen-9 correction):** prefixes
  now keep only ok=True steps — the failed reads in mined prefixes
  taught path-guessing (guessed_path 0.78 → 1.22 in gen-9); the
  productive chain is the reads that SUCCEEDED. (2) **The capability
  ladder grows:** calculator is solved (3/3), so default_tasks gains
  **defect-fix-cascade** — TWO defects in one module, the tests fail
  on both, fixing one only reveals the other; the diagnosis chain
  must run twice with a rerun between. Verified by subprocess:
  pre-fix fails both, both-fixes pass. (3) **Volume-teaching the
  json synthesis (gen-10's training variable):** nested_lookup 4 →
  **24 deterministic pool variants** (depths 1-2, varied
  sections/keys/leaves, defaults every fourth) — with a real lesson
  en route: the store's goal-dedupe initially DEFEATED the volume
  (3 goal texts collapsed 24 variants), so goals now carry the
  variant's module + descent path. **Live: corpus-v8 rebuild all
  green; training export 154 = 151 verified-success + 3 SRFT
  prefixes (ok=True-filtered); 10+ distinct nested-lookup goals (up
  from 3).** Cascade + volume + filtered SRFT ride one Colab job:
  ep10 → `qa verdict --models baby-agent:ep10,baby-agent:ep9` on the
  4-task ladder (calculator 1.0 = regression guard, cascade = new
  rung, json = the wall). Suite 1683 OK, CI green. Spec:
  docs/s78-spec.md.
- 2026-09-25 — **S77 Gen-9 corpus — SRFT prefix lane + nested-lookup
  expansion** — The gen-8 verdict left json as the standing wall, and
  the recorded evidence named both levers: the chained-`.get`
  synthesis needed more examples (run 3 executed the whole chain and
  applied an edit that still failed — the two-hop expression is thin
  at 8 demos), and the failed trajectories' productive discovery
  phases were being discarded by the success-only gate. **S77 SRFT
  lane** (JetBrains recipe adapted, dataset-separation intact):
  `_srft_lane` mines the curated export's FAILED trajectories for
  verified-productive prefixes — deterministic rule: steps up to the
  last read_file before the first edit/write, no hard flags, no final
  answer trained (the record ends on an observation; the failure tail
  is simply absent), dedupe by normalized goal keeping the longest
  prefix, `srft-prefix` metadata, report counts both lane records and
  candidates. **Nested-lookup expansion 1 → 4 variants** (alternate
  section name, two-level descent, missing-section default) with a
  fixture-builder bug fixed en route: the leaf lives UNDER the key
  inside the innermost section ({"settings": {"timeout": 30}}, not
  {"settings": 30} — caught because the demo's own verification gate
  refused the flat fixture). corpus-v7. **Live: 136/136 runs
  verified** (nested_lookup 32), **training export 147 = 144
  verified-success + 3 SRFT prefixes (calculator/strings/json — one
  per wall task, ending on an observation each)**. Suite 1682 OK.
  Spec: docs/s77-spec.md.

- 2026-09-24 — **S76.1 Gen-8 verdict — loss masking WORKS: 3/9 vs
  0/9, first strings success, first multi-task-capable generation** —
  ep8 trained on the S76 kit (assistant-only loss; three rounds of
  Colab debugging: transformers v5 apply_chat_template shape roulette
  — dict, nested lists, list-wrapped tensors, and finally a
  BatchEncoding that SLICES like a batch of 1 — caught by the mask
  gate + shape diagnostics + compile check each time, and the kit now
  carries a manual Qwen-format fallback so a broken template API can
  never silently produce an untrained model). Import migrated to the
  llama.cpp GGUF path (ollama 0.34.4 dropped safetensors import).
  **Verdict (rate-based, n=3 x 3 tasks, budget 12): ep8 3/9 (33.3%)
  vs ep7-q4 0/9** — calculator 2/3, **strings 1/3 (first strings
  success in program history)**, json 0/3. The attribution is the
  cleanest yet: byte-identical corpus, same base, the objective was
  the only variable. Protocol deltas vs ep7: discovery_first 0.11 →
  0.56 (the model now lists before acting more often than not),
  tool failures 24 → 10, chaining 1.0 held. Honest notes: ep8 ran at
  q8_0 vs ep7's q4 (the ollama 0.34.4 world; minor confound, favoring
  quality if anything); guessed_path 1.0 is exploration cost (failed
  reads before correct ones — the checking behavior the corpus
  teaches); json remains the wall (0/3 — the nested-lookup shape
  still unmet); the disk cleanup removed ep1-ep6 model binaries (the
  recorded verdicts are the history; ep7-q4 kept as the baseline).
  Gen-9 lever queued: SRFT failed-trajectory signal, judged against
  these rates. Suite 1675 OK. Spec: docs/s76-spec.md.
- 2026-09-24 — **S75.11/S75.12 Super-audit S11 + lab.db miner — the
  last audit slice and the colony's post-GC corpus** — **S11 (D2/D6,
  curriculum/training):** `generate()` now lands
  `last_run_accounting` (requested/produced/skipped_duplicates/
  exhausted) and gains `strict=True` raising on silent shortfalls
  (a caller requesting 100 that receives 87 was invalidating
  dataset-size comparisons); `coverage()` docstring relabeled as
  what it is — a label-frequency histogram, not capability coverage.
  Training-gate edges: INVALID trajectories counted in the report
  (they used to vanish against the "exclusions carry reasons" pin),
  truncated trajectories marked `truncated: true` and surfaced in
  counts (a cut trace trained as a complete one), the goal-suffix
  strip narrowed to the exact trailing ` (benchmark run <hex>)`
  pattern (the old split mangled legitimate goals),
  `reset_runtime_catalog()` for the process-global cache, and chat
  metadata labels `capture_tier: "behavior-trace"` — bounded
  captures are behavior traces, not replayable demonstrations, and
  both facts are now explicit. **S75.12 — lab.db miner
  (docs/labDB-handoff.md):** the antfarm colony saves every cycle's
  full transcript to lab.db and session GC deletes the opencode
  original — 99 live transcripts (82 done / 17 timed_out) were
  sitting in a table nothing read. `LabDbMiner` reads
  session_transcripts directly (same part vocabulary as the base
  miner), maps status honestly (done → confidence 0.45, timed_out →
  0.3; curation stays the judge), and keys sessions by opencode id
  so the store's reinforcement merges instead of double-counting.
  `qa mine-sessions --source labdb`. **Live: opencode re-mine 1,540
  seen / 344 mined / 0 errors; lab.db 99 seen / 19 mined (all 19
  reinforced into existing goals — the confidence bump is the
  merge; agent-b's 47 short timed_out pings correctly skipped as
  trivial); store 737, curation ACCEPT=734 / REVIEW=2 / REJECT=1.**
  Honest note: reinforcement copies confidence/outcome but not
  context, so labdb provenance lives in the confidence evidence
  rather than a separate source tag. Dashboard polish backlog
  recorded (output visibility + folder picker) and explicitly
  deferred until baby-agent is functional end to end. Suite 1675
  OK. Specs: super-audit.md S11 / docs/labDB-handoff.md.

- 2026-09-24 — **S75.10 Super-audit S10 — flatten fence + validator/
  loop accounting (B3/B4)** — `_flatten_messages` fences tool turns
  as untrusted blocks and escapes role-like line prefixes in all
  non-system content (a tool result containing "system: …" could read
  as a new turn after flattening); `validate_tool_arguments` recurses
  into declared object properties and array items with dotted/indexed
  error paths (free-form objects unchanged — the first cut rejected
  env/requires/skill dicts and 10 tests caught it immediately);
  validator errors name the tool; the loop counts consecutive empty
  responses and terminates honestly at 3 (was: identical messages
  burned max_iterations silently); changed-file extraction falls back
  to the write tool's own path argument when output is not JSON (B4:
  plain-text writes were invisible to metrics). Stash check 5 fail
  pre-fix. **The F1 annotation gate caught a missing ToolCall import
  in the new loop code — S1 paying for itself within the same
  sprint.** Suite 1664 OK.

- 2026-09-24 — **S75.9 Super-audit S9 — boundary correctness batch
  (F8/F10/F12/F15)** — `_is_under` strips the trailing separator so
  root and drive-root workspaces contain their trees (F8: "C:\" and
  "/" failed closed before — every path rejected, presenting as
  "agent thrashes on fs tools"); `_require_repo` compares
  `rev-parse --show-toplevel` to the workspace root and refuses
  nested-monorepo workspaces whose git scope would exceed the
  boundary (F10: stash check — nested workspace passed
  is-inside-work-tree pre-fix); dead `_test_footer` (guaranteed
  textwrap NameError) removed (F12); `PermissionRule.matches`
  docstring labels substring matching as defense-in-depth, never a
  security boundary (F15, per the audit's own remediation). Suite
  1652 OK.

- 2026-09-24 — **S75.8 Super-audit S8 — timeout enforcement +
  bounded retry + bounded audit trail (A2/F13/F14)** —
  `_execute_handler` manages the executor manually and shuts down
  without waiting: pre-fix stash check showed a hung handler blocked
  **30.0s past its timeout** via `shutdown(wait=True)` while the
  result claimed `timed_out`; post-fix the caller returns in 0.3s
  and the wall-clock regression test the audit said did not exist
  now pins it. `PermissionPolicy.decisions` trim to a bounded
  recent window (F14: unbounded growth in the engine singleton).
  `_retry_delay` honors Retry-After (seconds form) and caps the
  wait at 60s for both Gemini retry paths (F13: blind 60s block).
  Suite 1644 OK.

- 2026-09-24 — **Audit verification — muse-spark's S1-S7 confirmed
  clean; the one red test was a calendar time-bomb** — The
  consolidated super-audit (claude-audit + gpt-audit via muse-spark)
  left S1-S7 landed and S8-S10 open; the full suite ran with ONE
  failure: `test_golden_report_separates_regressions_prominently`.
  Root cause was NOT breakage — the golden fixture (2026-08-25) aged
  past the report's 30-day stale boundary on 2026-09-24 and the
  wall-clock staleness check correctly started listing the cases; a
  time-bomb test, fixed by freezing the report clock to the fixture
  era (the same lesson as the S10 e2e stamp normalization). The
  opencode audit session's last actions (read loop.py/providers.py/
  test_agent_registry.py, grep `def generate`) confirmed S8 was
  being scoped, not half-landed. Superseded root audit.md removed
  (super-audit.md canonical); quick-reference gains the dashboard
  run note. Suite 1637 OK.

- 2026-09-24 — **S75.7 Super-audit S7 — learning trust gate, scoped
  (C1/G1/G2/G5/D4.3)** — `experience_record` and `skill_teach` now
  declare `requires_confirmation` (pipeline upgrades to ASK under any
  policy; model self-minting is a proposal awaiting a human, denials
  without a confirmer), and curation no longer scores bare `success`
  as verified: new `_has_verification_evidence()` (top-level ok or any
  passing attempt) drives the verification dim, and unevidenced SUCCESS
  routes to REVIEW instead of riding vocabulary dims into ACCEPT.
  Blast radius surveyed first (all harness/demo/training flows carry
  real attempts with ok); the one test that pinned the bug
  (`test_verified_success_accepted`) now carries evidence. Stash check:
  5 S7 failures pre-fix (a 6th is the S5 flip test deprived of its own
  fix in the shared-file stash — understood, not a mystery). Full
  suite flaked once on the S6 lock (fixed as S75.6.1); final 1637 OK.
  Deferred honestly: composite experience identity + propose/certify
  API split need a DECISION + wider migration (S7b candidate).

- 2026-09-24 — **S75.6.1 Store lock Windows hardening (follow-up,
  found by S7 verification)** — the full suite flaked intermittently
  (`PermissionError` from `os.open(O_CREAT|O_EXCL)` in the Experience
  contention test): on Windows, exclusively creating a lockfile that
  another thread just unlinked surfaces as a sharing violation, not
  `FileExistsError`. `record_lock()` now retries `PermissionError`
  like a held lock (bounded patience, cause chained into
  `StoreLockedError`). Stress probe went 7/15 flaky rounds to 0/15;
  the S6 contention tests are the regression net. Suite 1637 OK.

- 2026-09-24 — **S75.6 Super-audit S6 — store write loss closed (A3)**
  — new shared `record_lock()` in `qacompanion/store.py` (portable
  O_CREAT|O_EXCL sidecar lockfile, bounded retry, stale-lock reclaim so
  a crash can't wedge the store) now guards both `CaseStore.record()`
  and `ExperienceStore.record()` — the latter had the identical
  unguarded race, dropping whole trajectories. Three regression tests
  (40-thread contention on each store, stale-lock reclaim); all 3 fail
  pre-fix via stash check. Suite 1634 OK (1631 + 3 new). Note: this
  retires spec.md's documented single-writer limitation by fixing it —
  no specified behavior changes (record/bump semantics identical).

- 2026-09-24 — **S75.5 Super-audit S5 — measurement trio fixed
  (D1/D3/D4.2)** — `generate()` no longer shadows its `level` param
  (`task_level` local; mixed curricula were 1 random level × N),
  `MasteryTracker.working_level()` is a pure read with transitions in
  `record()` only (repeated reads ratcheted the level; streaks bounded
  to the rule's window), and `curate()` re-resolves verdicts after the
  diversity pass (a rare REVIEW@0.46 record now correctly gates
  ACCEPT@0.5167, with the recompute noted in reasons). Six regression
  tests, 5 failing pre-fix (stash check; explicit-level pin guards the
  preserved contract). Suite 1631 OK (1625 + 6 new). No spec impact.

- 2026-09-24 — **S75.4 Super-audit S4 — apprenticeship lesson actually
  delivered (D7/G3)** — `run_session` now builds students via
  `_make_student` under the uniform `student_factory(model=None,
  lesson=None)` contract: the unaided baseline gets `lesson=None`, the
  retry gets the teacher's `Lesson` object, and `record.lesson_delivered`
  captures what the student saw. A factory whose signature lacks the
  lesson channel rejects the session (`student_failed: ... does not
  accept the lesson`) instead of running an untaught retry that could
  pass independently — genuine factory `TypeError`s still propagate
  (signature-checked). The old `AttemptFactory` is labeled for what it
  is (independent recovery, not transfer); new `LessonGatedFactory`
  applies ONLY the delivered lesson's first action, so ACCEPTED proves
  transfer. Stash check: both new tests fail pre-fix. Suite 1625 OK
  (1623 + 2 new). No spec impact.

- 2026-09-24 — **S75.3 Super-audit S3 — curation→skills handoff
  repaired + `from_dict` gate (C2/C3)** — candidates now validate as
  `Skill`: `_skill_name` joins with underscores (plus `skill_` prefix
  when the goal starts non-alpha), procedures render as followable call
  strings with the captured step args (`read_file(path="w.py")`, mined
  records fall back to bare names — G7's arg loss closed where capture
  exists), `verification` emits `""` not `{}`. `Skill.from_dict`
  rejects scalar-where-list (`"read_file"` no longer char-splits),
  non-string steps (no `str()` coercion), and non-str
  description/verification. Pre-fix probe proved each mode firsthand
  (hyphen name rejected, dict procedure rejected, `['r','e','a','d',…]`
  split, `42→'42'` coercion); updated the curation shape test that had
  pinned the hyphenated bug. New `tests/test_agent_skill_handoff.py`
  (9 tests). Suite 1623 OK (1614 + 9 new). No spec impact.

- 2026-09-24 — **S75.2 Super-audit S2 — textual protocol hardened +
  renderer round-trip pinned (B1/B2)** — `_parse_textual_tool_calls`
  rebuilt on a quote/escape-aware scanner (`_scan_tool_call`): two calls
  on one line stay separate, `)]`/parens inside quoted values no longer
  truncate, bare typed literals (`k=3`, `true`/`false`, `null`) parse to
  typed values (the renderer already emitted them — every non-string arg
  used to fail validation), unknown escapes keep their backslash instead
  of raising `KeyError` out of the loop, and shape-matched lines always
  yield a call so the validator returns a correctable observation.
  Single-quoted values deliberately stay raw (unescaping would corrupt
  `C:\new`-style paths). New `tests/test_agent_tool_protocol.py` (18
  tests): 7 failures + 1 error pre-fix (stash check), 18/18 post-fix;
  S69 string round-trip and prompt-text pins untouched. Suite 1614 OK
  (1596 + 18 new). No spec impact.

- 2026-09-24 — **S75.1 Super-audit S1 — five typing imports fixed +
  annotation gate + CI (F1/F16)** — `providers` gains `Optional`,
  `multi_agent`/`processes` gain `Tuple`, `websearch`/`skills` gain the
  `Workspace` import (all five broke package import on Python <3.14 while
  passing silently on 3.14's deferred annotations). New
  `tests/test_agent_typing_imports.py` pins the failure mode with
  `typing.get_type_hints` (eager on every version): a full sweep over all
  38 agent modules (1029 targets, 0 unresolvable) plus the 8 exact F1
  sites — verified it fails pre-fix (stash check) and passes post-fix.
  `.github/workflows/ci.yml` adds the 3.12/3.13/3.14 × ubuntu/windows
  matrix with pyflakes + full suite. Super-audit slice tracker opened
  (S1 ✅). Suite 1596 OK (1594 + 2 new). No spec impact (imports only).

- 2026-09-13 — **S73.1 Gen-7 verdict — recorded as failed; the n=1
  measurement problem named** — ep7 imported clean and the verdict
  (ep7-q4 vs ep6-q4, 3 tasks, budget 12, recorded): **0/3 both, ep7
  REGRESSED on most metrics** (tool failures 16 vs 8, guessed-path
  4.67 vs 0.0, discovery 0.0 vs 0.67; chaining held at 1.0). The
  trajectories decompose it: (1) **ep6's calculator success did NOT
  reproduce** at the same budget — its re-run hit max-iterations with
  12 calls — so the gen-6 win was a marginal-capability + sampling-
  variance data point, and **n=1 verdicts cannot distinguish
  capability from luck**; (2) ep7 LOOPED — identical failing calls
  repeated (re-reading the same nonexistent file ×4, re-running the
  suite ×3, re-reading one test ×3) and one run ended in a degenerate
  ECHO of the user's own goal as the final answer; (3) the coverage
  DID work partially — the strings run found the right files
  immediately (the trained shape) but never pulled the edit trigger.
  **Gen-8 lever (measurement before training): repeated-run verdicts**
  — n=3 per task with success RATE as the metric; n=1 verdicts are
  reading tea leaves at this capability level. Corpus stays at v6 —
  no training change until the measurement upgrade lands. Suite 1594
  OK. Spec: docs/s73-spec.md.
- 2026-09-13 — **S73 Gen-7 Corpus — coverage targeting the unhit
  tasks** — The gen-6 milestone left two eval tasks the corpus never
  covered: string reverse and nested JSON lookup. Gen-7's ONE variable:
  **coverage expansion mirroring those shapes** — two new
  demonstrator categories (string_reverse: `return text` →
  `return text[::-1]`; nested_lookup: `data.get(key)` →
  `data.get("settings", {}).get(key)` — the exact S57 default-task
  defects), each with the full S71/S72 recipe (diagnostic chain,
  recovery variants, goal variety, corpus-v6 tags). Verdict default
  budget landed at **12** (taught chain 7-9 turns + premature-recovery
  9-11; 15 rejected for CPU wall-clock risk). Research-informed recipe
  changes (loss masking, SRFT) stay queued for gen-8 — gen-7
  attributes cleanly to coverage. **Live: 112/112 runs verified**
  (16 new runs across the two categories), export **116 eligible
  step-trainable records** (96 v5 demos + 16 v6 + 4 real passes).
  Drip attempt hit an honest 429 (flash-lite bucket spent until
  reset). Suite 1594 OK. Spec: docs/s73-spec.md.
- 2026-09-13 — **S72.2 Gen-6 at budget 10 — THE FIRST TRAINED-
  GENERATION BENCHMARK SUCCESS** — Re-verdicted at max_iterations=10
  (the budget artifact fix): **baby-agent:ep6-q4 completed
  defect-fix-calculator — SUCCESS, 7 iterations, 6 calls, 0 failures,
  goal completed** — the first benchmark win for any trained
  generation (gen-1 through gen-5: 0/3 each; the only prior passes
  were the raw Gemini brain). The attribution is clean: ep5 at the
  SAME budget failed all three tasks by emitting 6-9 rejected
  premature finals per task ("verification failed after N attempts"
  ×3) — it had room to work and just re-answered; ep6 went to work.
  The failure-state training did exactly what it was designed to do,
  and the budget was the binding constraint on completing the taught
  chain. Honest notes: ep6's strings run died on a provider timeout
  (q4 CPU + 10 iterations against the 600 s wall) and json hit
  max-iterations while still attempting (10 calls) — success 1/3, not
  a solved benchmark; guessed-path occurrences rise with exploration
  (2.33/run) — the cost of checking before acting. The
  generation-over-generation arc, fully measured: gen-1 protocol →
  gen-2 speed/recovery → gen-3 our format bugs → gen-4 behavior
  fixes → gen-5 mechanism isolated → gen-6 failure states + budget =
  first success. Suite 1591 OK.
- 2026-09-13 — **S72.1 Gen-6 verdict — the diagnosis chain landed
  (0.0 → 1.0); the harness budget is now the binding constraint** —
  ep6 imported clean and the verdict (ep6-q4 vs ep5-q4, 3 tasks + A/B,
  recorded): **0/3 both** — but **diagnosis_chaining_rate 0.0 → 1.0**:
  after every failed test run, ep6 READS. Run 1 executed the full
  trained chain at inference — guessed src/budgeting.py (real
  file-not-found), listed the directory, read the TEST file, ran the
  suite, read the MODULE — the exact sequence the failure-state corpus
  teaches, ending in an empty final with no edit left before the
  budget ran out. discovery_first 0.0 → 0.33; ep5's premature-final
  signature (verification failed after 4 attempts ×2) became ep6
  max-iterations (it kept WORKING instead of re-answering — the
  failure-state training visible). ep0.5 A/B: with-demos 4 calls vs
  without 3 — the demo paralysis broke (fifth data point, first
  non-negative). **The harness artifact named: the verdict budget is
  6 iterations; the taught diagnostic chain needs 7-9 turns — the
  model cannot complete the taught behavior within the budget.** Gen-7
  levers: raise the verdict budget to 10 (match the taught chain) and
  the corpus already teaches the rest. Suite 1591 OK.
- 2026-09-13 — **S72 Failure-State Demos + Catalog Alignment — gen-6
  teaches the state every generation died in** — The gen-5 verdict
  showed the mechanism: SFT rewarded the report of success, and the
  loop's verification-failed recovery state was never demonstrated.
  Gen-6's one variable: **make training match the runtime's actual
  state distribution**. (1) **premature_final_recovery strategy**
  (bug_fix + feature_add): the demonstrator claims success BEFORE
  acting, the loop's verifier rejects it, the recovery prompt arrives,
  and the script continues to the real fix — the honest final ADMITS
  the premature claim ("My first summary was premature — I claimed a
  fix I had not actually made..."); the run still ends verified. (2)
  **RECOVERED-with-evidence is now training-eligible** (the final
  state passed the gate; teaching recovery is the point — mined
  partials still fail the evidence check). (3) **Catalog alignment**:
  training renders the runtime's ACTUAL lean catalog into the system
  prompt (gen-5 trained catalog-less and met 12 tools at inference).
  (4) **Faithful interleave**: the loop records `after_step` per
  verification attempt, session_learning captures the failure states,
  and training.py renders premature claim → rejection → continuation
  at the recorded step positions (an after_step merge fixes older
  records). **Live: 96/96 re-demoed, 18 RECOVERED records, export
  verified — 99 eligible with the interleave and catalog in every
  record.** Research survey (applied per the attribution rule): our
  loop is structurally RFT (validated); loss masking + SRFT
  (JetBrains 2026, failed-trajectory signal) documented as
  post-stabilization levers; imported datasets stay rejected. Suite
  1591 OK. Spec: docs/s72-spec.md.
- 2026-09-13 — **S71.1 Gen-5 verdict — the narrative transferred, the
  behavior didn't** — ep5 imported clean (fixups automatic) and the
  verdict (ep5-q4 vs ep4-q4, 3 tasks + A/B, recorded): **0/3 both**;
  ep5 makes FEWER, cleaner calls (1-4 per run, 2 total tool failures
  vs ep4's 10) — but **diagnosis_chaining_rate 0.0 for BOTH** despite
  41 chain-shaped training demos, and the trajectory analysis shows
  why: ep5 emits the demos' diagnosis NARRATIVE verbatim — run 3's
  final ("The failing tests pointed at calculator.py. Reading the
  suite showed the add test was the problem...") appears with ZERO
  tool calls; run 2 runs the suite blindly twice then quotes the
  trained diagnosis text. **The SFT objective rewarded the report of
  success over the process**: the final-answer text is the easiest
  sequence to imitate, and nothing in the training data distinguishes
  "final after working" from "final without working." The verifier
  caught every fabrication (all runs died in unit-tests=FAIL). Every
  run also ended in the state we never demonstrated: the loop's
  verification-failed recovery (5 rejected attempts). **Gen-6 levers
  (evidence-named): (1) premature-final recovery demos** — the
  demonstrator emits an early final, the verifier rejects it, the
  script CONTINUES to the real fix (teaches the off-distribution
  recovery state; still 100% verified-success); (2) system-prompt
  catalog alignment — training renders no tool catalog while the
  runtime shows one; (3) curriculum/tool-schema audit (memory_search's
  pattern-vs-query confusion came from ep3). ep0.5 A/B: FOURTH
  consecutive net-negative (with-demos 0 calls). Suite 1587 OK.
  Spec: docs/s71-spec.md.
- 2026-09-12 — **S71 Demonstrator 3.0 — the diagnosis chain taught**
  Scope discipline held (human-directed): gen-5's ONE variable is the
  demonstrator redesign; session mining and drips continue as the
  standing loop but cannot affect training (unverified partials are
  permanently excluded). Three refinements as one lesson — derive the
  fix from the evidence: (1) **diagnosis-chain scripts** (failing
  suite → read the TEST file → read the MODULE → smallest edit; final
  answers walk the chain: "the failing tests pointed at add. Reading
  test_math_ops.py showed the expectation, and reading math_ops.py
  showed the defect..."), (2) **rational recovery ordering** (the
  wrong turn now comes BEFORE discovery — a first hypothesis the
  evidence overturns; gen-3's version taught "list, then guess
  anyway"), (3) **tool coverage where natural** (code_diagnostics
  opens build_repair — argument-free, the exact call gen-3 invented
  args for; dependency reads the test for the expected format).
  New metric: **diagnosis_chaining_rate** (failed suite → a read
  within 2 steps; the gen-3/gen-4 recorded runs sit at ~0 — that
  number moving is the gen-5 experiment). corpus-v4 tags invalidated
  the v3 records automatically. **Live: 96/96 verified, export
  checked — 41 chain-shaped openings, 8/8 code_diagnostics calls
  exactly `[TOOL: code_diagnostics()]`, 0 suffix leakage — 99
  eligible = 96 v4 demos + 3 real passes.** Suite 1587 OK. Spec:
  docs/s71-spec.md.
- 2026-09-12 — **S70.1 Gen-4 verdict — the fixes landed in behavior;
  the gap is now precisely the diagnosis chain** — ep4 imported
  zero-surgery and the verdict (ep4-q4 vs ep3-q4, 3 tasks + A/B,
  recorded): **0/3 both** — but the S69 fixes are visible IN the
  model's behavior: run_tests commands are cleanly formed (unquoted,
  single-backslash — the `command="\\"` garbage is gone at inference),
  the recovery instinct generalized into path-CHECKING before editing
  (file_metadata/file_exists → exists:false → no blind edit), and
  in-context arg self-correction persists (memory_search pattern→query
  after a tool error). Metrics: guessed_path 1.0 → 0.33, with-calls
  1.0 held; tool failures 10 → 14 (more attempts, different kinds).
  The remaining failure modes are BEHAVIORAL and named: (1) no
  diagnosis chaining — ep4 reran the failing suite 3× without once
  reading the failing file (the demos' edits derive from
  demonstrator-omniscience, so the fix-from-failure-output lesson was
  never taught); (2) fabricated finals with ZERO tool calls persist
  (the demo narrative imitated without work — same signature the A/B
  shows: with-demos 0 calls vs without 4, third generation running);
  (3) unpracticed tools still get invented args (code_diagnostics).
  Gen-5 levers (queued from the earlier analysis): diagnosis-driven
  demos (final answers walk failure-output → file → line → fix),
  rational recovery ordering (guess BEFORE discovery), and exercising
  more of the offered tools. ep0.5 injection: three consecutive
  net-negative results at this model scale — flag it do-not-default.
  Suite 1586 OK. Spec: docs/s69-spec.md (fixes) / verdict-day entry.
- 2026-09-12 — **S70 Dashboard Operations — the loop's buttons** — The
  S68 commands are now dashboard buttons: a **job model** on the
  server (`start_job`: background thread, status/summary, injectable
  runners for hermetic tests) with **POST /api/drip** (one real
  benchmark pass on the free-tier brain, recorded),
  **POST /api/verdict** (models + task count → S68 run_verdict under
  the trained textual contract), and **GET /api/jobs** (newest-first
  list). The UI grew an **Operations panel** — drip button, verdict
  models input, live job list polling every 3 s with running/done/
  failed coloring. Safety posture: buttons only, never auto-fired —
  opening the dashboard is looking, not doing (S38 philosophy); every
  click spends real quota or CPU deliberately. **Live smoke**: the
  drip endpoint launched a real pass that honestly FAILED on the
  spent flash-lite quota — the 429 surfaced in the job summary
  through the retry backoff, exactly the error-visibility the panel
  exists for. Endpoints tested with injected fake runners (lifecycle,
  model carry-through, 400 on empty models, newest-first ordering);
  npm build green. Suite 1586 OK. Spec: docs/s70-spec.md.
- 2026-09-12 — **S69 Protocol Consistency — the corpus now teaches a
  dialect the runtime actually speaks** — The gen-3 verdict named three
  data-format bugs; this sprint fixed all three at the source: (1)
  **one escaping dialect** — `format_tool_call` now escapes newline/tab
  exactly like backslash/quote, and `_parse_textual_tool_calls` is
  escape-aware (new `[^"\\]|\\.` value pattern + mirror unescape set),
  pinned by a render→parse round-trip test over adversarial values
  (multi-line content, embedded quotes, backslash paths — previously
  the corpus taught calls whose args parsed WRONG); (2) **quote-free
  test commands** (`_tests_command` drops the interpreter-path quotes,
  falls back to the PATH-resolved name) — gen-3's `command="\\"`
  garbage eliminated at the source; (3) **provenance suffixes
  stripped** from chat-record goals — the models parroted "benchmark
  run <id>" back at us. **Corpus version tags** (`corpus-v3`): the
  idempotent rebuild skips only CURRENT-format covered goals, and
  mark_superseded_demos supersedes scripted demos lacking the tag —
  so a format change invalidates the corpus automatically. **Live:
  96/96 re-demoed in 45 s** (51 recovery-strategy), training export
  verified — 0 suffix leakage, 0 quoted commands, 24 escaped-newline
  write_file renders — **98 eligible step-trainable records = 96
  current-format demos + 2 REAL Gemini passes**. Human-directed extra
  drips: flash-lite **SUCCESS in 10 s** (6 iters, 5 calls, 0 failures
  — fastest real pass in project history), flash-latest FAILED
  honestly on a 429 after 10 real calls over 464 s (its bucket was
  part-spent) — both daily buckets now spent, quota resets tomorrow.
  Suite 1582 OK. Spec: docs/s69-spec.md.
- 2026-09-12 — **S68.1 Gen-3 verdict — 0/3 again, and the failures are
  OURS: three data-format bugs named precisely** — ep3 imported clean
  (fixups automatic now) and the verdict (ep3-q4 vs ep2-q4, 3 tasks +
  A/B, recorded): **0/3 both**, but ep3 halved ep2's tool failures (5
  vs 10) at the same call quality. The trajectory analysis turned up
  three corpus artifacts INDUCING the failures: (1) the corpus's test
  commands contain quotes (`"C:\...\python.exe" -m unittest`) which
  the taught textual protocol forbids inside values — the model's
  every run opens with mangled `command="\\"` calls; (2)
  `format_tool_call` escapes backslashes/quotes JSON-style while the
  runtime parser reads them RAW — the corpus taught the model to
  write calls whose args parse WRONG (doubled-backslash paths →
  file-not-found); (3) the S63 session-suffix goals leak into chat
  records — ep3's fabricated final answers parrot "benchmark run
  6bd97c9c" (a training-goal suffix). Plus the ep0.5 A/B on ep3:
  with the worked example the model made 0 calls (vs 6 without) —
  demo injection induces final-answer imitation at this model scale;
  recorded net-negative. Gen-4 fixes are surgical: quote-free test
  commands, raw-value rendering consistent with the parser, suffix-
  stripped goals in chat records. The loop is producing OUR bugs,
  not just model verdicts. Suite 1579 OK (metrics unchanged; verdict
  runs recorded).
- 2026-09-12 — **S68 The Self-Improvement Loop — the generation cycle
  is now standing plumbing** — Everything gen-3 needs, one command per
  stage: (1) **corpus hygiene automated** — `mark_superseded_demos`
  tags pre-S66 scripted demos whose FIRST captured step is read_file
  (precise identifier: no S66 script starts with a read) as
  `superseded-pattern`; tags now flow through the curated export and
  training.py excludes them WITH a recorded reason (kept in the store
  for provenance); (2) **idempotent rebuild** — build_corpus marks
  superseded first, then skips any task whose normalized goal already
  has a successful new-style demo (suffix-stripped normalization —
  the recorded goal carries " (benchmark run <id>)" but the task goal
  does not; the first implementation missed the strip and never
  matched, caught by the idempotency test); **live: superseded 25,
  skipped 96, 0 re-demos needed** — every task already had a
  new-style record, so the training set went 122 → 97 with the stale
  dilution gone, 100% explore/tests-first + real; (3) `qa
  gemini-drip` — one real pass on the free-tier brain, recorded like
  any run; **live smoke PASSED** (10 iterations, 9 calls, 1 failure —
  a real verified record now feeding the next chain); (4) `qa
  verdict --models A,B [--ab-demos]` — the one-command generation
  verdict (tasks + protocol_metrics table), backed by a testable
  run_verdict with injected providers; **live smoke: the ep0.5 A/B
  ran for ep2 (with-demos 1 call vs without 4 calls, both FAILED —
  one data point, the worked example makes ep2 more conservative)**.
  Suite 1579 OK. Spec: docs/s68-spec.md.
- 2026-09-12 — **S67 Gen-2 verdict — no benchmark win yet; the metrics
  did their job** — ep2 imported with ZERO local surgery (the first
  export through the hardened kit: untie + rope_theta + explicit
  lm_head all verified in Colab; fp16 9.0 s / q4 6.0 s sanity probes,
  both answering "Paris" cleanly). **Verdict (3 tasks, textual
  contract, recorded): ep2 0/3, ep1 0/3** — but the shape differs:
  ep2 runs are 3-10× faster (7-13 s vs 3-81 s) with 3× fewer tool
  failures (4 vs 12), and its guesses are recovery-shaped
  (guess → correct) where ep1 flailed. `protocol_metrics` (new, in
  evaluation.py: discovery-first rate, with-calls rate, guessed-path
  rate, success rate — recovery demos excluded from the guessing
  population, not hidden) surfaced the uncomfortable findings: (1)
  **discovery-first rate 0.0 for BOTH generations** — root cause
  found in the training data: the store still carries the 25
  stale-pattern gen-1 records (read-first), so ep2's 122-record
  training set was only ~69% explore-first — the corpus ACCUMULATES
  when it should have been rebuilt; (2) **ep2 fabricated a completion
  claim** in the exact demo diagnosis format ("I replaced the
  defective line...") after a failed edit — it learned to SOUND
  finished; the S41 gate refused it, exactly as designed. Both are
  gen-3 levers with evidence: rebuild the corpus clean (re-demo the
  old records in the new style or exclude pre-S66 scripted records
  from training), and keep leaning on the gate. Roadmap honesty rule:
  gen-2 recorded as failed on the benchmark; protocol metrics
  documented as the measurable delta. Suite 1573 OK. Spec:
  docs/s67-spec.md.
- 2026-09-12 — **S66 Demonstrator 2.0 (Gen-2 corpus)** — The gen-1
  verdict said ep1 had perfect syntax but flailed at tasks (guessed
  paths, never discovered the workspace) because the demos taught
  answer-reading. The corpus design is fixed and scaled, per the
  human's strategy-diversity direction: **EXPLORE-FIRST scripts**
  (every demonstration starts with list_directory), **strategy
  diversity** (bug_fix cycles clean / tests-first-recovery /
  explore-recovery; the other verifiable categories carry clean +
  recovery variants), **recovery beats with REAL observations** (~51%
  of records contain a genuine wrong turn — a read of src/<module>
  that genuinely fails — then correction; tagged `recovery-demo`),
  **category expansion** (feature_add / build_repair / dependency /
  testing / regression added; the dependency demo's recovery is
  natural — the missing module genuinely fails to import — and the
  testing fixture's declared shape puts multiply in test_calc_ops.py,
  so the demo's test imports from the module that actually exists),
  and **goal-phrasing variety** (3 templates per category). `qa
  build-corpus --category` enables single-category builds.
  **Live: 96/96 runs verified in 34.1 s** (bug_fix 40, feature_add
  24, build_repair 8, dependency 8, testing 8, regression 8;
  recovery-strategy 51) — store 243 experiences, curation
  ACCEPT=236 / REVIEW=6 / REJECT=1, **training set 26 → 122
  verified step-trainable records**, first-tool distribution:
  list_directory 84 / read_file 25 / run_tests 13 — discovery is
  now the majority pattern the model will imitate. Docs/refactor
  categories deferred (no honest verification gate for prose —
  recorded in the roadmap). Suite 1570 OK. Spec: docs/s66-spec.md.
- 2026-09-11 — **S64 verdict day — ep1 gen-1: protocol acquired,
  benchmark failed (recorded honestly)** — The Colab-trained ep1
  arrived speaking ("Paris") but ollama rendered it as one repeated
  token. Diagnosed with stdlib-only parsing, three conversion-layer
  bugs in sequence: (1) ollama's converted template had no tool
  support → Modelfile carries the qwen2.5-coder template; (2) ollama's
  safetensors conversion DROPPED the tied lm_head (Qwen2.5-3B ties it)
  → the GGUF shipped with no output.weight; fixed by cloning the
  embedding into an explicit lm_head (stdlib safetensors surgery,
  byte-verified); (3) transformers v5 writes rope_theta in a new
  config format ollama's converter cannot read → freq_base came out
  0.0 and the model still could not attend — patched to the legacy
  key; sanity probe: "Paris", 8.5 s fp16 / 3.0 s q4. **Contract
  finding**: the first verdict chain ran everything native-first —
  ep1 emitted 0 structured calls (native-style JSON as plain text);
  under its TRAINED textual contract it emitted 5–6 well-formed
  [TOOL: ...] calls per run (correct arg names, one in-context
  self-correction pattern→query) where its parent emitted ZERO under
  either contract. **The honest verdict table** (same benchmark,
  same settings): every model FAILED the defect fix — ep1-q4 6 iters
  / 5 calls / 10 s, ep1-fp16 6 iters / 6 calls / 62 s, parent
  qwen2.5-coder:3b 0 calls (native: JSON-as-text 31 s; textual: turn-1
  timeout at 600 s), qwen3:4b native 6 calls / 1502 s. Generation 1 is
  recorded as failed per the roadmap honesty rule — but the S55 gap
  ("the protocol is what general small models lack") is MEASURABLY
  closed: 26 records of SFT took ep1 from no-protocol to
  consistently well-formed tool calling. Capability gap: ep1 guesses
  paths and invents project types — syntax without task
  understanding; the named levers are corpus scale/diversity (more
  curriculum categories as demonstrators, more real passes). q4 is
  the keeper variant (≈3× faster, same behavior). The in-memory untie
  was also reverted by transformers v5's save — the kit now applies
  the disk-level fixup (explicit lm_head + legacy rope_theta) AFTER
  save_pretrained, and the sanity gate refused to celebrate early.
  Suite 1558 OK (no runtime code changed beyond the earlier timeout
  fix; verdict-day changes are kit-side). Spec: docs/s64-spec.md.
- 2026-09-11 — **S64 slices 2+3 — ep0.5 demonstration injection +
  dashboard brain selection** — ep0.5 (the adaptation half of
  "fine-tune / adapt", no gradients): verified step-carrying
  experiences now render as protocol-shaped WORKED EXAMPLES inside the
  S56 memory block — goal → `[TOOL: ...]` steps with observation heads
  → final answer — so the model imitates in-context instead of
  learning by weight updates. MemoryLayer carries steps /
  final_answer / model additively (legacy records unaffected);
  `MemoryRetriever(demonstrations=True)` renders only SUCCESS-outcome
  experiences (failed outcomes never teach by imitation);
  `run_benchmark` gained `context_builder=` passthrough as the A/B
  harness. Hermeticity slip caught by review: the new tests initially
  let MemoryLayer default to the repo's REAL cases.jsonl (the S49
  lesson, 3rd+ occurrence — isolated paths now injected). Slice 3:
  `QA_AGENT_PROVIDER=gemini` selects the free-tier brain for
  dashboard sessions (default ollama unchanged; unknown values are
  structured startup errors). **A/B experiment (human-directed): demo
  injection provably reaches the model, but qwen3:4b on CPU could not
  finish turn 1 within the 300 s budget with the enlarged context
  (0 tool calls; baseline without the demo: 7 tool calls over 6
  iterations)** — the context cost of ep0.5 is real on CPU; a 600 s
  -budget retry was launched to answer the tool-call-quality question.
  On Gemini-class providers the extra tokens are trivial. Suite
  1558 OK. Spec: docs/s64-spec.md slices 2-3.
- 2026-09-11 — **S64 Baby-Agent Ep1 (corpus + kit; training
  hardware-gated)** — `qacompanion/agent/ep1.py`: the ep1 process
  starts with DATA. **Hardware finding (probed): AMD Radeon RX 6400,
  4 GB, no CUDA — local fine-tuning impractical**; free-tier Gemini
  caps model-generated data at a few passes/day. So: scripted
  curriculum demonstrators — the S60 bug_fix variant table declares its
  defects BY CONSTRUCTION, and a 5-turn demonstrator (inspect → tests
  fail → surgical edit of the DECLARED old/new → tests pass → state
  the diagnosis) runs through the REAL S37 loop, REAL subprocess test
  execution, and the S41 gate; only verified passes become records,
  tagged `scripted-demo` (honest provenance threaded through curation
  → training metadata). `qa build-corpus` = corpus → curate →
  build-training → kit export, all deterministic. **Live: 26 verified
  step-trainable training records** (25 scripted + 1 real
  gemini-3.1-flash-lite pass; avg 11.1 messages each) — up from 1,
  zero LLM quota spent. **BONUS REGRESSION FIX found by the corpus
  chain**: a same-second, same-size edit left CPython's stale .pyc
  "valid" (its check is int-second + size), so subprocesses silently
  imported the OLD code — write_file/edit_file now guarantee a
  strictly-fresh mtime (regression test reproduces the race). Training
  kit committed (training-kit/): single-file QLoRA SFT
  (Qwen2.5-Coder-3B-Instruct base) + README documenting the honest
  ep1 loop — external free compute (Colab/Kaggle, no billing) →
  `ollama create baby-agent:ep1` → S57 run_evaluation + compare() as
  the ONLY acceptance surface. **Local retest (human-directed,
  bounded): qwen3:4b FAILED honestly** — 6 iterations / 883.5 s /
  7 tool calls / 2 failures, max-iterations termination; the isolated
  2-tool native probe still works (correct call, ~83 s/turn CPU) —
  the gap stays CPU latency + sustained reasoning, which is exactly
  what ep1 targets. Suite 1547 OK. Spec: docs/s64-spec.md.
- 2026-09-11 — **S63 Training Dataset Pipeline 2.0** —
  `qacompanion/agent/training.py`: CURATED data → training corpus.
  Source discipline enforced: training reads ONLY the S62 curated
  export, never raw experience; the eligibility gate implements the
  permanent dataset-separation rule — training.jsonl takes ONLY
  ACCEPT + successful + verification evidence, every exclusion carries
  a recorded reason, INVALID never becomes a record. Chat records
  teach the EXACT runtime tool protocol (build_system_prompt +
  TOOL_PROTOCOL_PROMPT): system → user goal → assistant
  [TOOL: name(k="v", ...)] turns with REAL captured args → observation
  result heads → final answer. No fabricated steps — records without
  captured step data stay structured but not step-trainable (honest
  notes). Capture upgrade (session_learning, additive): bounded
  context["tool_calls"] (args + result heads, 50 cap) paired from
  session.tool_calls × observations, plus context["final_answer"] from
  session.final_result; actions stay names (S50 compat). Curated
  trajectory export now carries the payload (redacted). New CLI:
  `qa build-training`. **The live debug repaired Gemini native
  calling**: the first real run failed HTTP 400 and the provider was
  swallowing the body — surfacing bodies exposed three real protocol
  bugs, fixed in sequence: (1) tool results replayed as model-role
  TEXT → "requests ending with a model turn" — now user-turn
  functionResponse parts; (2) thinking models require thoughtSignature
  replayed at PART level; (3) 429 free-tier retry (60s wait). Contract
  (additive): ModelMessage.tool_calls + ToolCall.thought_signature.
  **Store finding (S59 suffix precedent)**: benchmark reruns share one
  normalized goal, so the store's goal-dedupe collapsed every run into
  ONE record and silently destroyed per-run trajectory data — harness
  recordings now carry a session-unique goal suffix. **Live result:
  the second honest benchmark PASS in project history**
  (gemini-3.1-flash-lite over the repaired native protocol, 6
  iterations, 0 tool failures) → curation ACCEPT=111 / REVIEW=0 /
  REJECT=1 → **training.jsonl's first real verified step-trainable
  record** (13 messages: protocol system prompt, goal, 5 tool turns
  with real args, observations, the model's actual diagnosis as the
  final answer). Free-tier note: gemini-flash-latest resolves to
  gemini-3.8-flash at 20 requests/DAY — flash-lite has its own
  bucket; pin GEMINI_MODEL for live runs. Also this cycle: the S62
  human-review ruling landed first (goal substance gates the
  high-value REVIEW claim; the session-closing template promoted to
  boilerplate — DECISIONS 2026-09-11). Suite 1515 → 1540 OK. Spec:
  docs/s63-spec.md.
- 2026-09-11 — **S62 Trajectory Curation** —
  `qacompanion/agent/curation.py`: the §S62 gate between "something
  happened" and "should learn this" — deterministic, no LLM.
  Classification (SUCCESS / FAILED / RECOVERED / HUMAN_CORRECTED /
  PARTIAL / UNSAFE / INVALID, flags override), scoring over the
  roadmap's ten dimensions where deterministic signals EXIST (None =
  honestly unknown, never guessed; overall = mean of known dims),
  hard rejections (credential patterns — the flag names the pattern
  and exports are REDACTED, never echoing the secret; destructive
  markers; success-with-zero-actions = INVALID), soft penalties
  (repeated actions, oversized tool usage, placeholder goals), and
  verdicts: REJECT on flags or no substance; **REVIEW = low-confidence
  AND high-value** (mined RECOVERED failure→fix pairs — the human
  surface); ACCEPT at overall ≥ 0.5. Dedupe is a defensive second
  layer over store reinforcement; diversity = rarity of the
  (source, project) group, measured not assumed. Lesson extraction is
  CANDIDATES ONLY — failure cases with S2 signature candidates +
  S51-shaped skill seeds; cases.jsonl stays teacher-gated (case-#10
  lore). Nine atomic exports + diversity.json under QA_CURATED_DIR
  (gitignored); preferences/benchmarks honestly empty with explanatory
  notes. Miner v2: marathon error→patch PAIRS (cap 5, first pair
  back-compat, Traceback headers stay weak fallbacks) — the deeper
  surfhop/sentinel extraction from the S50 backlog. ZcodeMiner: thin
  SST-family subclass (SOURCE_NAME + default DB path; the corpus is 1
  session — this one — and grows as the human uses ZCode). New CLI:
  `qa mine-sessions` + `qa curate`. **Live runs**: opencode re-mine
  1,431 seen / 288 mined / 274 reinforced / 1,143 skipped trivial /
  0 errors (PortfolioCapture alone +86); store 97 → 112 (109 opencode,
  1 zcode, 2 pre-source); curation ACCEPT=109 / REVIEW=2 / REJECT=1 —
  the reject is a genuine data-quality catch ("Repaired failed tests"
  claimed success with zero recorded actions → INVALID), 9 failure
  cases + 93 skill candidates exported (428 records). Suite 1474 →
  1515 OK. Spec: docs/s62-spec.md.
- 2026-09-11 — **S61 Multi-Agent Teacher Sessions** —
  `qacompanion/agent/multi_agent.py`: structured multi-teacher
  collaboration that generates higher-quality learning examples.
  Participant delegates by duck-type — provider.propose →
  TeacherProvider.teach → ModelProvider.generate — so ANY teacher or
  model plugs in unchanged; MultiAgentSession carries the full
  contract (proposals, critiques, votes, disagreements,
  consensus_reached AS DATA, verified flag, diversity record). Four
  session shapes: run_independent (N teachers solve separately,
  verifier adjudicates, disagreements recorded as first-class data —
  the S62-valuable training examples), run_debate (propose → critique
  → revise), run_critique_chain (sequential role reviews),
  run_specialist (primary + role reviewers → revision). THE pinned
  principle: **consensus ≠ correctness** — a unanimous panel can be
  wrong, so EVERY candidate passes the S41-style verification gate
  (independent mode verifies each proposal; unanimous-wrong consensus
  still fails, tested directly). MultiAgentLab wraps the runner with
  record() + diversity_report() (by-mode aggregates, distinct roles,
  disagreement sessions — diversity measured, not assumed; 11 roles ×
  4 modes, strict validation, unknown role/mode rejected). Suite
  1461 → 1474 OK. Spec: docs/s61-spec.md.
- 2026-09-05 — **S60 Synthetic Curriculum** —
  `qacompanion/agent/curriculum.py`: CurriculumTask (strict schema,
  difficulty VECTOR: reasoning/steps/tools_required — scales with
  level) + eight category templates with failure injection BY
  CONSTRUCTION (bug_fix modules contain the declared defect and their
  tests genuinely fail pre-fix — proven via subprocess; feature_add
  modules lack the expected function; build_repair has a syntax
  error; dependency has a missing local module — known failure modes
  DECLARED per task) + SyntheticCurriculum generator (seeded
  deterministic, same seed = identical curriculum; round-robin
  categories; level ranges; repeated normalized goals DETECTED and
  skipped per the roadmap dedupe rule; coverage matrix =
  skill → count) + MasteryTracker (success streak → level up,
  consecutive failures → level down; recommend picks the
  least-attempted skill). Bridge: as_eval_task() → S57
  run_evaluation — curriculum runs through the identical harness
  (proven end-to-end with a scripted fix). Registry unchanged
  (curriculum is harness-level). Suite 1445 → 1461 OK. Spec:
  docs/s60-spec.md.
- 2026-09-05 — **S59 Agent Apprenticeship Lab** —
  `qacompanion/agent/apprenticeship.py`: TeacherProvider ABC +
  ScriptedTeacherProvider (hermetic; real Gemini/opencode teachers
  plug into the same ABC later); Lesson = explanation + REAL tool
  actions (a teacher that can't produce actions can't teach);
  ApprenticeshipLab flow — student attempt 1 (unaided) → teacher demo
  → student retry → S41 verification gate → curation gate.
  **Quarantine store discipline (test-found):** attempts run against
  a separate attempt_store; the MAIN memory store only receives
  ACCEPTED verified lessons, under a distinct goal ("...apprenticeship
  lesson") so the store's goal-dedupe cannot merge the apprenticeship
  tag away. Rejects recorded with reasons (teacher_failed /
  verification_failed), never in main memory. The S50→S59 loop is
  closed: verified lessons enter the S47/S50 experience store as
  first-class experiences. LabReport counts by teacher. Suite 1440 →
  1445 OK. Spec: docs/s59-spec.md.
- 2026-09-05 — **S58 Failure Recovery & Escalation 2.0** —
  `qacompanion/agent/recovery.py`: FailureTracker (S2-style
  deterministic signatures; no-progress = same signature repeating
  consecutively) + RecoveryPolicy strategy ladder — retry-with-advice
  (S49 already injected) → alternate-approach instruction →
  environment-check (marker-matched failures route to the S40 summary
  first) → escalate-model (S55 escalation tier; ONE-WAY ladder, never
  re-escalates; swaps the loop's provider mid-run + model_escalated
  event) → ask-user / terminate (decision.reason is the honest
  termination surface, e.g. "needs human decision"). Loop wiring
  additive: AgentLoop(recovery=None, escalation_factory=None); both
  tool-failure and verification-failure paths consult the state
  machine, which owns the iteration-exhaustion termination when
  present. Environment markers beat repeat counts (environment-class
  failures get the S40 check instead of more retries). Suite 1422 →
  1440 OK. Spec: docs/s58-spec.md.
- 2026-09-05 — **S57 Agent Evaluation Harness** —
  `qacompanion/agent/evaluation.py`: THREE deterministic defect
  fixtures (calculator / string reverse / nested JSON lookup — each
  with its own S41 unittest gate), `run_evaluation` full model × task
  cross product through the S48 benchmark (generalized:
  run_benchmark gained fixture_writer + goal params — it previously
  hardcoded the calculator fixture AND goal, which silently planted a
  second defect in every non-calculator eval task), per-model
  aggregates (success rate, avg iterations/duration, tool totals,
  interventions), atomic JSON persistence (QA_EVAL_DIR, default
  eval-runs/), and symmetric `compare()` — regressions AND
  improvements flagged per (model, task); unknown tasks ignored.
  Test-provider lesson (3rd occurrence, now policy): heredoc patch
  scripts fail silently on whitespace/escape drift — surgical Edit
  only; the AutoFix fake provider synthesizes fixes per turn instead
  of pre-scripted lists that exhaust mid-run. Suite 1411 → 1422 OK.
  Spec: docs/s57-spec.md.
- 2026-09-05 — **S56 Context Optimization** —
  `qacompanion/agent/context.py`: ContextBudget (char accounting,
  never split mid-message), ToolResultSummarizer/ObservationReducer
  (command results reduce to exit_code + stdout head/tail + stderr
  head; old turns become one-line digests), prioritized
  ContextBuilder — goal > memory block > latest tool result
  (NON-DROPPABLE: verbatim -> reduced -> hard truncate; budget may be
  exceeded, reported honestly via over_budget) > recent turns
  (reduced) > older (digests) — plus MemoryRetriever (S47 keyword
  injection at assembly, degraded-silent). Loop integration ADDITIVE:
  AgentLoop(context_builder=None); without it, behavior byte-identical
  (all prior loop tests unmodified); with it, per-turn assembly (the
  builder must see tool results that exist by turn 2 — the frozen-
  once bug was caught by the loop test). BuildReport is the
  verification surface: goal_present, latest_tool_result_verbatim,
  dropped, chars, over_budget. Suite 1396 → 1411 OK. Spec:
  docs/s56-spec.md.
- 2026-09-05 — **S54 Computer Use** —
  `qacompanion/agent/computer.py`: the heavily restricted GUI
  capability behind a THREE-GATE safety model — explicit allow-list
  (default EMPTY: an unconfigured toolkit is a no-op by construction),
  DESTRUCTIVE+requires_confirmation pipeline guarantee (default engine
  demands confirmation for every single GUI action; denied with no
  confirmer — spec overclaimed DENY, corrected), and per-action
  confirmer. Six tools (click/double_click/move/type/press_keys/
  focus_window); screen observation = S44 capture_screen, app
  launching = S45 start_process (documented reuse). FakeComputerProvider
  action log (hermetic); ctypes SendInput Windows adapter (POSIX =
  structured error); max_actions budget (runaway-clicking protection);
  out-of-bounds coordinates are structured errors, never clamped.
  agent_registry → 65 tools (benchmark lean catalog unchanged). Suite
  1384 → 1396 OK. Spec: docs/s54-spec.md.
- 2026-09-05 — **S53 Browser Abstraction** —
  `qacompanion/agent/browser.py`: BrowserProvider ABC + two adapters —
  FakeBrowserProvider (in-memory page model: registered pages,
  selector-addressable elements, history, click/type/select mutation,
  REAL PNG screenshots via the S44 codec with per-page colors so
  compare_images can verify) and PlaywrightBrowserProvider (sync
  Playwright behind an import guard — activates with `pip install
  playwright && playwright install chromium`, structured error naming
  the fix before that; no binaries download as a side effect). Eight
  EXTERNAL tools (browser_open/back/click/type/scroll/select/
  screenshot/extract — default ASK posture; screenshot is the only
  workspace writer); browser_download covered by S43
  download_artifact (documented deviation). Playwright method mapping
  proven with a mocked module both absent and present.
  agent_registry → 59 tools (benchmark lean catalog unchanged — the
  benchmark doesn't browse). Suite 1363 → 1384 OK. Spec:
  docs/s53-spec.md.
- 2026-09-05 — **S55 slice 5 (native-only prompting + lean catalog +
  head-to-head)** — The bake-off diagnosis became engineering:
  build_system_prompt(native_tools=...) — providers declare capability
  (OllamaProvider(native_tools=...), Gemini class attr; unknown
  providers default textual); the textual protocol is taught ONLY to
  shim models (the conflict is ours, not the models'). Loop gained
  tool_catalog (model-facing subset; registry keeps everything —
  harness can execute tools the model wasn't offered). Benchmark
  offers LEAN_MODEL_CATALOG (12 of 22). Pulled phi4-mini +
  granite3.3:2b; four-way head-to-head, every config tried: ALL FOUR
  FAIL (qwen3:4b turn-timeout at 300s even lean; 3b timeout mid-run
  after 8 honest calls; phi4-mini 0 calls — echoes the SCHEMA as
  arguments, adapter finding recorded; granite 8 calls/7 failures,
  20 min wall). Isolated probes prove plumbing correct — the gap is
  sustained multi-turn reasoning on 2–4B CPU, not plumbing. Passing
  brain remains gemini-3.1-flash-lite native (144s, verified). Local
  revisit: GPU or baby-agent:ep1 distill (S63+, training data teaches
  the protocol general small models lack). Suite 1363 OK. Slice-5
  section: docs/bakeoff-s55.md.
- 2026-09-05 — **S55 slice 3 (ModelRouter) + tool-call diagnosis** —
  Diagnosis of the native-retest zero-tool-call mystery: qwen3:4b emits
  CORRECT native tool calls in an isolated 2-tool probe (10–15s, both
  think modes — Ollama and the model are fine); with the benchmark's
  20-tool catalog it needs 177–300+s/turn on CPU, and the textual
  protocol teaching in the system prompt conflicts with native calling
  (0 native calls when both present). Filed as catalog-weight +
  prompt-conflict engineering (native-only prompting, hierarchical tool
  selection — follow-ups). **ModelRouter landed**:
  deterministic role routing under policy (ordered ModelRoute rules,
  first-match, trigger-driven escalation on failure_count>=2/stuck,
  unknown roles fall back to brain, explain() for dashboards);
  default_router() encodes the human role sketch — local qwen3:4b
  brain, free-Gemini escalation tier only when GEMINI_API_KEY present,
  qwen2.5-coder:3b as the cheap local route. Route is pure policy —
  never calls a model. Suite 1354 → 1363 OK.
- 2026-09-05 — **S55 slice 4 + PASS (native tool-calling adapters)** —
  DECISIONS 2026-09-05: native tool calling is the primary provider
  contract when tools are declared; textual protocol demotes to shim.
  OllamaProvider: /api/chat with structured tools (tools declared ->
  native; absent -> /api/generate textual). GeminiModelProvider:
  function_declarations -> functionCall parts + Gemini-safe schema
  coercion (registry arrays/objects 400'd without items/properties) +
  GEMINI_TIMEOUT env + 503 retry-with-backoff + OLLAMA_NUM_CTX env
  (bridge never set a context window — 23 tool schemas overflowed the
  ~2048 default). **THE BENCHMARK PASSED**: gemini-3.1-flash-lite via
  native function calling completed the defect-fix benchmark
  autonomously — 6 iterations, 144s, calculator.py fixed,
  unit-tests=pass verified, 0 tool failures, 0 interventions. First
  honest pass in project history; the S48 goal condition is closed.
  Native retest of locals: qwen2.5-coder:3b has NO Ollama native tool
  support (0 calls in 25 iterations); qwen3:4b native + num_ctx still
  timeout-prone on CPU (0 calls in 6 iterations, 22 min) — revisit on
  GPU. Bake-off table updated (docs/bakeoff-s55.md). Role sketch
  validated: gemini-3.1-flash-lite = brain for real tasks; local
  qwen models = cheap/routine + vision; loop accepts any provider.
  Suite 1349 → 1354 OK.
- 2026-09-05 — **S55 slice 2 (bake-off)** — Seven-model defect-fix
  bake-off complete (docs/bakeoff-s55.md): every brain failed —
  1.5b faked evidence, 8b too slow, qwen2.5-coder:3b drove 107 tool
  calls but looped without fixing (verifier refused 17x), qwen3:4b
  timed out (think blocks; OLLAMA_THINK=false flag added to the
  bridge), cloud Gemini 503-throttled and lite never emitted a tool
  call. **The finding that reframes the roadmap: the gap is the taught
  textual tool protocol, not the brains** — native tool-calling
  adapters (Ollama structured tools, Gemini function calling) filed as
  the real unlock; textual protocol demoted to compatibility shim.
  Also added: Gemini 503 retry-with-backoff (free tier demand spikes).
  Suite 1349 OK. Follow-ups: native adapters, then ModelRouter (slice
  3) per the human role sketch.
- 2026-09-05 — **S55 slice 1 (model routing & bake-off)** — Research
  (cited in docs/s55-spec.md): Qwen3-4B is the 3–4B class favorite
  ("unusually strong tool-calling priors" — ertas.ai; best small base
  model — distillabs.ai; runs on CPU ~1.5s/turn — r/LocalLLaMA),
  Phi-4-mini the alternative; 30B MoE excluded (17 GB RAM). Spec:
  docs/s55-spec.md — bake-off via the S48 harness (controls 1.5b + 8b,
  challengers qwen3:4b + qwen2.5-coder:3b), role sketch to validate
  (local coder brain / qwen2.5vl vision / free-Gemini escalation).
  Slice 1 landed: **OLLAMA_TIMEOUT** call-time configurable bridge
  timeout (the 8B 180s monkey-patch becomes configuration; reload-free
  env resolution after importlib.reload poisoned cross-module refs) +
  **GeminiModelProvider** (agent loop backend, PLAIN generation per the
  no-billing ruling — distinct from GeminiSearchProvider; the
  escalation/research candidate in the role sketch). Model pulls
  (qwen3:4b, qwen2.5-coder:3b) kicked off in background; bake-off run +
  router are slices 2/3. Suite 1342 → 1349 OK. Spec: docs/s55-spec.md.
- 2026-09-05 — **S52 close-out + live walkthrough** — `qa serve` CLI
  wired (localhost dashboard server, Ctrl+C clean shutdown); Electron
  deferral recorded in ROADMAP §S52. Live browser walkthrough caught a
  real bug: static asset requests were served index.html (module never
  loaded) — fixed with traversal-proof static serving from app/dist
  (content types, SPA fallback). End-to-end from the dashboard UI:
  Start agent -> live SSE feed (21 events) -> session completed;
  qwen2.5-coder:1.5b again tried faking evidence (writing logs.txt) and
  the no-clobber guard refused it twice in the UI context. Honest
  limitation visible: dashboard sessions without verify_command
  complete unverified (S50 records them partial). Suite 1341 → 1342 OK.
- 2026-09-05 — **S52 Desktop UI (API-first; Electron deferred)** —
  `qacompanion/agent/server.py`: the runtime's local API layer in
  STDLIB (ThreadingHTTPServer) — REST (health, session
  start/stop/detail/list, skills, memory, environment) + SSE streaming
  of the S39 event stream with replay-then-live subscribe. Security
  posture: binds 127.0.0.1 only; sessions run the same S37 loop / S38
  engine policy (the UI adds convenience, not authority); unverified
  completions recorded honestly as partial (opt-in verify_command
  builds a real S41 gate). **Server session id IS the agent session
  id** (pre-built AgentSession passed into loop.run) — found via a
  cross-session event-id mismatch. `app/`: Vite+React+TS dashboard
  (goal input, live event feed, session list/summary, stop); npm build
  green; the server serves app/dist at / — open
  http://127.0.0.1:8765/ and watch the agent work. **Electron shell
  deferred** to a packaging follow-up: the browser is the desktop shell
  for now; the API contract is unchanged when it lands. node is NOT a
  Python-suite dependency (npm build is the UI gate). Suite 1332 →
  1341 OK. Spec: docs/s52-spec.md.
- 2026-09-05 — **S51 Skills 2.0** —
  `qacompanion/agent/skills.py`: Skill schema (the exact S51 fields the
  S50 resume seed already follows: name/goal/description/required_tools/
  preconditions/procedure/verification/failure_modes/examples/confidence,
  strict validation, identifier-like names because they map to files) +
  SkillLibrary over skills/agent (TOLERANT loading: one malformed file
  recorded in .errors and skipped — a library must not die on one bad
  entry, unlike strict single-file stores) + deterministic keyword
  retrieval (S47 pattern). Two brain-level tools: skill_find (READ_ONLY
  — surfaces goal/preconditions/procedure/verification for the MODEL to
  follow with its ordinary tools; nothing executes procedures
  programmatically) and skill_teach (SAFE_WRITE — validated, atomic).
  **The S50→S51 loop is closed**: the resume seed
  (resume_interrupted_task.json) loads and is findable. Clarification
  from the human, folded into the miner (S50 follow-up commit): bare
  continuation pings ("continue") are boilerplate by exact match, but a
  SUBSTANTIAL goal-less session (>=100 parts) is now mined with an
  honest placeholder goal + goal-less tag — mid-session continues never
  affected anything (the miner always took the first non-boilerplate
  user text as the goal). agent_registry → 51 tools (exact count once,
  in the combines-all test). Suite 1318 → 1332 OK. Spec:
  docs/s51-spec.md.
- 2026-09-05 — **S50 Learning From Agent Sessions** —
  `qacompanion/agent/session_learning.py`: mechanical outcome
  classification (COMPLETED+first-verify-ok = success, later-verify =
  recovered, FAILED = failed, CANCELLED/unverified = partial —
  human_corrected/unsafe stay unimplemented until intervention tracking
  exists), session_to_experience capture (qa_memory advice harvested
  into diagnosis, actions, tags incl. "unverified"), record_session;
  rule-based Curator delivering the human-directed backlog (greeting
  pings removed, ×321 resume pattern PROMOTED to skill seed
  skills/agent/resume_interrupted_task.json — S51-schema DATA, nothing
  loads it until S51 — and removed from the episodic store); miner
  error→patch enrichment (substantive error lines preferred over bare
  traceback headers, resolution claimed only when a patch follows the
  error); benchmark harness records sessions as experiences (loop stays
  pure). **Live corpus final state: 1,170 sessions → 95 curated
  experiences** (1,062 sessions skipped as boilerplate/trivial — the
  continuation template is now boilerplate at the source, so curator
  and miner no longer fight; the 2 enriched pairs sitting under resume
  goals were traded away deliberately — S62's deeper extraction recovers
  them from the DB). Suite 1306 → 1318 OK. Spec: docs/s50-spec.md.
- 2026-09-05 — **S49 QA Brain Integration** —
  `qacompanion/agent/qa_brain.py`: the architecture payoff — when a tool
  fails, the colony's accumulated QA intelligence is injected into the
  loop AUTOMATICALLY before the model's next action. QABrain: failure
  signature via S2 normalize+canonical -> layered lookup (exact case
  signature via lookup.select -> keyword match via bridge._match_cases
  with punctuation-free end-weighted query terms -> S47 MemoryLayer
  fallback) -> advice {source, case_id, diagnosis, times_seen} appended
  as a system-role message + memory_advice event. **The brain owns
  failure semantics**: failed ToolResults AND the S35 convention
  (run_command ok=True with embedded CommandResult nonzero exit) — the
  loop just asks. Honest silence on no match; degraded stores never
  crash the loop. Read-only brain: no case auto-creation (case-#10
  lore); writing cases is S50's job. Hermeticity lesson repeated twice
  this sprint: MemoryLayer defaults to the repo's REAL cases.jsonl when
  cases_path=None — tests must inject isolated paths. Loop wiring via
  additive AgentLoop(qa_brain=None); agent_registry unchanged (49 — the
  brain is loop-level, not a tool). Suite 1293 → 1306 OK. Spec:
  docs/s49-spec.md.
- 2026-09-05 — **S48 First Autonomous Coding Task** —
  `qacompanion/agent/benchmark.py`: the defect-fix benchmark harness —
  deterministic fixture (calculator.py with one intentional defect +
  failing unittest), natural-language goal (no file names), the S37 loop
  with coding-family tools only (fs/execution/verification/code/memory —
  hermetic by construction), and the S41 plan-verifier gate: COMPLETED
  only when the tests genuinely pass. BenchmarkReport records honest
  metrics from the session + S39 events (files_changed, commands_run,
  tool_failures, recovery_count, verification results,
  intervention_count=0 by construction). **S41 amendment** (found by the
  benchmark): must_contain/must_not_contain now check COMBINED
  stdout+stderr — unittest reports on stderr and stdout-only checks
  missed it. Hermetic success path green (scripted
  inspect→fail→fix→pass→final with full metrics). **Live runs — honest
  failures**: qwen2.5-coder:1.5b never ran a test (0 commands), faked
  evidence via log files, 7 premature-done claims all rejected by the
  verifier, ended on an Ollama timeout; llama3.1:8b made 5 tool-call
  errors and timed out per-request even at 180s (8B on CPU too slow for
  the loop). The harness recorded both runs completely — capability, not
  harness, is the gap (S55: routing to a stronger model; loop accepts
  any provider; free Gemini plain-mode is a candidate adapter). Bridge
  60s HTTP timeout is a hard cap worth making configurable (S55 note).
  **Curation backlog (human-directed, for S50/S56/S62 wherever it fits
  best)**: curation pass over the 99 mined experiences; merge the
  x321 resume pattern ("response interrupted, continue") into a skill;
  drop greeting pings ("hello" x7); deeper marathon-session extraction
  (diagnosis/resolution from surfhop/sentinel/dinner-menu-generator).
  Suite 1288 → 1293 OK. Spec: docs/s48-spec.md.
- 2026-09-05 — **S47.1 opencode Session Mining** — human-directed: "can
  baby-agent learn from my already-made projects?" Located the corpus:
  `~/.local/share/opencode/opencode.db` (8 GB SQLite, SST opencode;
  1,170 sessions / 42.5k messages / 171.7k parts across 21 projects,
  2026-07-30 → now). `qacompanion/agent/opencode_mine.py`: READ-ONLY
  miner (mode=ro) → one Experience per session (goal = first
  non-boilerplate user text part, ordered tool names as actions capped
  at 50, volume counts in context, opencode session id as provenance,
  ProjectMetadata from the project directory when it exists). Curation
  learned the hard way: first import's top "experiences" were antfarm's
  injected kickoff preamble ("SITUATION REPORT…") reinforced x127 —
  fixed with boilerplate detection, word-boundary goal truncation, and
  skipping goal-less sessions. Two measured session shapes drive the
  design: marathon projects (surfhop: 2 sessions / 1,694 messages;
  dinner-menu-generator: 1 session / 2,483) vs turn-spawn antfarm (385
  tiny sessions). **Clean import: 1,170 sessions → 99 experiences (330
  reinforcements, 741 skipped, 0 errors, 19.5s)**; top pattern =
  "response interrupted, continue" x321 (the colony's resume loop).
  experience.jsonl gitignored (runtime artifact, stays local). Suite
  1277 → 1288 OK. Spec: docs/s47-spec.md (S47.1 section).
- 2026-09-04 — **S47 Experience Memory** —
  `qacompanion/agent/experience.py`: Experience record (goal/outcome/
  context/actions/failure/diagnosis/resolution/verification/confidence/
  tags/project metadata, strict validation, JSONL-ready) +
  ExperienceStore (experience.jsonl, QA_EXPERIENCE_FILE override, atomic
  writes, BOM/CRLF tolerance, **recurrence reinforcement**: a repeated
  normalized goal bumps times_seen instead of duplicating) + MemoryLayer
  (unified read over cases/digest/journal/experiences, merged, scored,
  source-labeled; missing stores degrade to empty) + three brain-level
  tools (experience_record SAFE_WRITE, experience_search /
  memory_search READ_ONLY). Retrieval is deterministic keyword scoring
  with times_seen/confidence boosts — semantic upgrade documented for
  S56. agent_registry → 49 tools (exact count asserted once; family
  tests membership-only). Suite 1258 → 1277 OK. Spec: docs/s47-spec.md.
- 2026-09-04 — **S46 Static Code Intelligence** —
  `qacompanion/agent/codeintel.py`: CodeIndex over the workspace with
  three precision-labeled language tiers — Python via real stdlib AST
  (functions/methods with qualified names, classes, module-level
  variables, precise ast.Name/Attribute references, imports, syntax-error
  diagnostics), JavaScript/TypeScript via a documented regex scanner
  (heuristic), generic keyword fallback (labeled); mtime+size caching so
  the index stays correct while the agent edits; walk through PathPolicy
  (exclusions/binaries/caps enforced). Five READ_ONLY tools: code_symbols
  (search + exact definition lookup), code_references, code_imports,
  code_importers (dotted-suffix match), code_diagnostics.
  agent_registry → 46 tools. Two findings fixed honestly: (a) the AST
  visitor initially double-visited every node (unconditional recurse
  after the special-case branches) producing phantom unqualified
  definitions — restructured with an explicit else; variable
  definition-sites are the ONLY is_definition references (a function's
  own name is not a Name node — documented in code and tests); (b) the
  human's GEMINI_API_KEY (setx) leaked into the test process and the
  missing-key tests silently found it — one test even made a REAL
  network call. Fixed properly: provider constructors now take a
  sentinel (explicit api_key=None = definitely no key; omitted = env
  fallback), and toolkit tests resolve providers only inside their
  popped-env contexts. Suite 1238 → 1258 OK. Spec: docs/s46-spec.md.
  NOTE for S55: human has qwen2.5vl:3b pulled locally — candidate local
  vision fallback alongside free-tier Gemini vision.
- 2026-09-04 — **S45 Process & Runtime Management** —
  `qacompanion/agent/processes.py`: ProcessManager owning long-lived
  processes with daemon reader threads feeding bounded log rings (server
  output must never block on a full pipe) and S35 tree-kill (promoted to
  public kill_process_tree) for stops. Nine tools: start/stop/restart
  (EXECUTION), list/status/wait_for_process, check_port / wait_for_port
  (semantic split pinned: bind test = free, connect poll = serving),
  health_check (localhost-only by construction — READ_ONLY, remote is
  open_url's job). Crash detection = honest status reading; recovery =
  the agent calling restart (no auto-supervision daemon in S45). The
  roadmap chain (start server -> wait_for_port -> health_check -> stop ->
  restart -> crash recovery) is proven end-to-end against a real
  ThreadingHTTPServer fixture. agent_registry → 41 tools.
  Suite 1222 → 1238 OK. Spec: docs/s45-spec.md.
- 2026-09-04 — **S44 Vision / Screenshot Analysis** —
  `qacompanion/agent/vision.py`: minimal stdlib PNG codec (encode/decode,
  8-bit RGB filter 0); ctypes GDI acquisition (capture_screen /
  capture_window / capture_region — Windows, POSIX structured error);
  VisionProvider (Fake + Gemini multimodal PLAIN request per the no-
  billing ruling); inspect_image (EXTERNAL — the image leaves the
  machine) + compare_images (READ_ONLY local pixel diff, threshold-based);
  honest side-effect matrix across the five tools. agent_registry → 32
  tools. **Live smoke**: captured the real 1920x1080 screen through GDI,
  encoded via our PNG codec, and gemini-3.1-flash-lite (free) described
  it — recognizing the baby-agent terminal itself. flash-latest/3-flash-
  preview were 503 high-demand; lite is the pinned default.
  Suite 1198 → 1222 OK. Spec: docs/s44-spec.md.
- 2026-09-04 — **S42.1 plain-mode search fallback (human ruling: no
  billing)** — GeminiSearchProvider falls back from grounding-429 to
  plain model knowledge, marked grounded=false / provider gemini:plain /
  no sources; live smoke: web_search through the gated registry path
  (ASK -> confirmer) answered free. The answer itself demonstrated the
  tradeoff (stale version info — extract_page is the recency escape
  hatch). HTTPError bodies now surfaced in errors.
- 2026-09-04 — **S43 URL Context & Retrieval** —
  `qacompanion/agent/webfetch.py`: URL safety policy checked before any
  request (scheme http/https, ports 80/443, EVERY resolved IP must be
  public — loopback/RFC1918/link-local/metadata endpoints unreachable;
  DNS-rebinding residual risk documented); open_url (HTML→text via stdlib
  parser, title/links/20k-char cap), extract_page (query-relevant
  passages), download_artifact (≤10 MB strict cap, atomic, PathPolicy-
  bound, sha256). All EXTERNAL (S38 ASK posture), urllib always mocked in
  tests. agent_registry → 27 tools. Suite 1179 → 1197 OK.
  Spec: docs/s43-spec.md.
- 2026-09-04 — **S42 Web Research** — `qacompanion/agent/websearch.py`:
  WebSearchProvider abstraction; FakeWebSearchProvider (hermetic backbone)
  + GeminiSearchProvider (Google AI Studio generateContent with
  google_search grounding — the human-directed "Google Search with AI"
  provider; activates on GEMINI_API_KEY, defensive parsing, key never
  logged). web_search tool = first EXTERNAL-side-effect tool.
  **Registry default policy is now the S38 engine** (was minimal
  allow-all): EXTERNAL→ASK and DESTRUCTIVE→DENY are the default posture,
  not an opt-in. Suite 1161 → 1179 OK. Spec: docs/s42-spec.md.
- 2026-09-04 — **S41 Verification Engine** —
  `qacompanion/agent/verification.py`: data-driven VerificationPlan /
  VerificationStep / VerificationResult / VerificationReport; sequential
  command steps (BUILD/TEST/LINT/TYPECHECK/RUNTIME/HEALTHCHECK) at the
  workspace root through the S35 executor (timeout, tree-kill, output
  caps inherited); stop-on-first-failure with honest skipped steps (ok=
  None); must_contain / must_not_contain / expect_exit; optional steps.
  `run_verification` registry tool (the model verifies its own work,
  EXECUTION-gated); `plan_verifier` adapts a plan into the S37 loop
  verifier — fail → recover → pass proven end-to-end. GOAL predicates
  stay the S37 seam; REGRESSION is a TEST rerun; VISUAL waits for S44.
  agent_registry → 23 tools (exact-count assertion now lives in ONE test;
  per-family tests assert membership — ends the per-sprint count churn).
  Suite 1143 → 1161 OK. Spec: docs/s41-spec.md.
- 2026-09-04 — **S40 Environment Intelligence** —
  `qacompanion/agent/environment.py`: `get_environment_summary` with
  section filters (os/cpu/memory/gpu/runtimes/package_managers/disk/
  variables) — the roadmap's seven granular tools mapped to sections
  (one prompt surface, S37 lesson). Mismatch check (`requires: {tool:
  min_version}` → satisfied/mismatches) so the agent sees "node >= 20
  unavailable" before retrying unfixable code. Variable metadata is
  names+set-ness only — values never surface (tested). Every collector
  degrades to unknown/null; binaries probed only after shutil.which.
  Suite 1125 → 1143 OK. Spec: docs/s40-spec.md.
- 2026-09-04 — **S39 Event Stream & Observability** —
  `qacompanion/agent/events.py`: Event envelope (seq, uuid, session, Z-stamp,
  type, payload) + EventStream (sync callback subscribers, bounded replay
  history, raising subscribers recorded and never breaking a run). Loop is
  the primary emitter (session_started/state_changed/model_started/
  model_response/tool_requested/completed+failed/file_changed/
  verification_started+completed/recovery_started/failure_detected/
  session_completed+cancelled+failed); registry emits permission_requested/
  granted/denied at the decision point via additive execute() params and
  prefers the engine's decide() so events carry the real rule. Roadmap
  verification: exact ordered event sequence asserted for a scripted run.
  Suite 1109 → 1125 OK. Spec: docs/s39-spec.md.
- 2026-09-04 — **S38 Permission & Safety** — `qacompanion/agent/permissions.py`:
  PermissionPolicy engine (explicit rules w/ args_contains > tool-declared
  requires_confirmation > side-effect-level defaults (DESTRUCTIVE→DENY,
  EXTERNAL→ASK) > fallback w/ DENY-by-default mode) + PermissionDecision
  audit trail; registry confirmer seam (ASK → approvable/deniable, absent =
  safe denial) with decisions normalized to PermissionDecision; loop
  confirmer passthrough; **pipeline guarantee**: a tool's own
  requires_confirmation forces ASK regardless of policy. Git write verbs
  unlocked (S36 deferral resolved): git_add (SAFE_WRITE) + git_commit
  (ASK-gated; nothing-to-commit is an honest no-op — and git prints that
  on stdout, not stderr). agent_registry → 21 tools. Suite 1080 → 1109 OK.
  Spec: docs/s38-spec.md.
- 2026-09-04 — **Live Ollama validation (manual smoke, not committed as
  tests)** — qwen2.5-coder:1.5b re-pulled; the S37 loop ran LIVE end-to-end
  (goal → taught textual tool call → S32 pipeline → atomic write → verifier
  passed → COMPLETED, 2 iterations; hello.txt + files_changed recorded).
  `qa ask` brain restored (grounded, 12 sources). Three fixes landed from
  live findings: S37.1 loop prompt now teaches the textual tool protocol +
  agent-layer parser upgraded to multi-arg `[TOOL: name(k="v", k2="v2")]`
  (S27's single-arg parser couldn't express path/content); S37.2 few-shot
  example added (1.5B model invented its own syntax without one);
  S37.3 redundant availability ping removed from OllamaProvider.generate
  (2x cost/turn, one flaky ping killed the loop). Suite 1076 → 1080 OK.
  Commits 8552b6a, 74bde10, f8299b9.
- 2026-09-04 — **S37 Agent Loop** — `qacompanion/agent/loop.py`: the first
  autonomous reasoning cycle, task-agnostic — goal → model → S32 tool
  pipeline → observation fed back as structured `tool` messages (denials,
  unknown tools, timeouts are observations, never exceptions) → final
  answer. Pluggable verifier (S41 preview): failure enters RECOVERING and
  retries within limits; session gains verification_results (additive).
  Iteration/runtime limits, cancellation, provider errors — every exit a
  terminal state with a reason. Metadata-driven changed-file tracking
  (write-level side effect + JSON path key). The roadmap verification
  sequence (write buggy file → run fails → read error → edit fix → run
  passes → final) passes via FakeModelProvider; feedback provably reaches
  the next model iteration. Suite 1062 → 1076 OK. Spec: docs/s37-spec.md.
- 2026-09-04 — **S36 Git Intelligence** — `qacompanion/agent/git_tools.py`:
  git_status/diff/log/branch over argv-list git (no shell), paths resolved
  through PathPolicy, porcelain v1 parsing (renames with orig_path, C-quoted
  paths incl. UTF-8 octal unquoting, ahead/behind, detached HEAD), \\x1f
  log separators, clean failures (non-repo, missing binary). Write verbs
  (git_add/commit) deliberately deferred to S38 pending confirmation
  enforcement — no autonomous commits. agent_registry → 19 tools.
  Suite 1039 → 1062 OK. Spec: docs/s36-spec.md.
- 2026-09-04 — **S35 Terminal & Execution** — `qacompanion/agent/execution.py`:
  CommandResult (exit_code, capped stdout/stderr with truncation flags,
  duration, Z-stamps, pid, JSONL round-trip); five tools (run_command,
  run_tests, run_build, run_lint, run_typecheck) with metadata-based
  detection table + explicit-command override; tree-kill timeouts (POSIX
  killpg / Windows taskkill /T) proven by a grandchild-holding-stdout test;
  ok="pipeline ran the command" so evidence survives for diagnosis;
  cwd/env/cancellation operational errors structured; agent_registry →
  15 tools. Suite 1017 → 1039 OK. Spec: docs/s35-spec.md.
- 2026-09-04 — **S34 Filesystem Tools** — `qacompanion/agent/fs_tools.py`:
  seven tools (list_directory, read_file, write_file, edit_file, search_code,
  file_exists, file_metadata) bound to the S33 Workspace via
  FilesystemToolkit, all resolving through PathPolicy — boundary escapes and
  excluded paths return structured errors through the S32 pipeline. Atomic
  no-clobber writes (temp + os.replace), unique-match edits, byte-faithful
  reads (BOM stripped for the model, preserved by edit), binary/generated
  awareness in search, ChangeLedger with sha256s per mutation, registry
  ToolOperationError seam for clean structured failures. `agent_registry()`
  = knowledge + filesystem tools. Suite 979 → 1017 OK. Spec: docs/s34-spec.md.
- 2026-09-04 — **S33 Workspace Abstraction** — `qacompanion/agent/workspace.py`:
  PathPolicy layered containment (strict ".." ban, symlink-following resolve,
  normcase containment vs root + allowed paths, exclusion prefixes,
  protected system locations — Windows `C:\Windows`-class and POSIX `/etc`-class),
  Workspace (root/cwd/git_root/metadata/config), WorkspaceManager (normcase
  cache + active), ProjectMetadata (languages/package-managers-from-lockfiles/
  entrypoints/project_type). Integrates S32's `requires_workspace` gate.
  Suite 932 → 979 OK (symlink tests skip honestly without OS symlink
  privilege). Spec: docs/s33-spec.md.
- 2026-09-04 — **S32 Tool Registry v2** — `qacompanion/agent/registry.py`:
  RegisteredTool metadata (side_effect_level, timeout, cancellable,
  requires_workspace/confirmation), ordered execution pipeline (lookup →
  strict mini-validation → permission seam → workspace gate → cancellation →
  timeout execution → audit hook), every stage failure a structured
  ToolResult; ToolResult gains timed_out/cancelled flags (additive);
  default_knowledge_registry() serves case_search/doc_grep/journal_read
  unchanged. Suite 891 → 932 OK. Spec: docs/s32-spec.md.
- 2026-09-04 — housekeeping — removed docs/DRAFT_decisions-fhm.md (human-
  directed: belongs to another project, not this repo's decision log).
- 2026-09-04 — **S31 Agent Foundation** — `qacompanion/agent/` subpackage
  (contracts.py / providers.py / session.py): ModelProvider abstraction with
  FakeModelProvider (deterministic test backbone) + OllamaProvider (wraps S26
  bridge, normalizes textual [TOOL: ...] output into structured ToolCalls),
  AgentSession state machine (10 states, terminal states final), AgentConfig
  limits, knowledge-tool ToolDefinitions. `qa ask` unchanged. Suite 828 →
  891 OK (hermetic; live Ollama opt-in via QA_OLLAMA_LIVE=1). Spec:
  docs/s31-spec.md. Roadmap: docs/ROADMAP-agentlite.md §S31.
- 2026-09-04 — **Roadmap consolidation + case #10 fix** — Agent-Lite
  roadmap consolidated into docs/ROADMAP-agentlite.md (S31–S65+), DECISIONS
  rulings filed (renumbering, constraints amendment), audit.md superseded;
  fixed pre-existing red test: no-Ollama fallback now surfaces digest
  matches, digest ask test made hermetic (828 OK).
