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
