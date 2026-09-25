# S80 — Agent-Authoured Demonstrations + the Capability Ladder

Status: scoped 2026-09-25. The human's direction: teach the model
directly from the agent's own capability — "smarter thinking from
you" — and future-proof the demonstration program so tests stop
landing 0/3 or flaky. Two deliverables: an authoring mechanism whose
author is swappable (agent now, any verified provider later), and the
capability ladder — the documented sequence of tests, the
demonstrations each needs, and the graduation criteria that gate
moving up.

## The core problem being solved (honest)

The demonstrations to date are TEMPLATED (declared defects, fixed
turn shapes, formulaic narratives). They taught protocol, discovery,
and failure recovery — measured, real — but they carry three limits:
(1) the reasoning in them is a template, not thinking, so the model
imitates the shape of diagnosis without the substance; (2) one
demonstration per pattern makes inference flaky (single-run
successes that don't reproduce — the gen-8/9 lesson); (3) the
program had no documented answer to "what comes after cascade."

## The Capability Ladder (the future-proofed test sequence)

Each rung: an eval task (frozen once introduced — yardstick rule),
the demonstration shapes it needs, and a graduation criterion. **No
rung's demonstrations are authored until the rung below is stable**
(3 consecutive verdicts inside its rate band) — this is the
anti-flaky gate: we never train toward a rung the model cannot stand
on.

| rung | capability | eval task | demonstrations needed | graduation |
|---|---|---|---|---|
| 1 | single-defect single-file | calculator / strings / json (done) | diagnostic chain + recovery | rate band established |
| 2 | persistence: two defects, chain runs twice | defect-fix-cascade (S78, done) | double-chain demos with "there may be more than one bug" reasoning; final names BOTH fixes | rate ≥ 1/3 in band |
| 3 | cross-file dependency tracing | defect-fix-indirect (new): bug in module A, failing test covers module B which imports A | demos that follow the import: read failing test → read B → code_imports/code_references → read A → fix A → rerun; teaches the workspace-context behavior | rate ≥ 1/3 in band |
| 4 | test authorship with mutation proof | test-authoring task (new): correct module, no tests; the written test must FAIL on the known bug and PASS on the fix | write-test → mutation-check demos (prove the test catches the defect) — teaching tests that test | mutant killed, suite green |
| 5 | runtime-behavior debugging | no failing test given: run the program, observe wrong output, write the reproduction first | observe → reproduce → diagnose → fix → verify | TBD at rung 4 graduation |
| 6 | multi-file feature with contract | feature across 2+ files honoring an existing interface | plan → touch each file → cross-verify | TBD |

Rungs 3-6 eval tasks are specified here and implemented one at a
time, each only when its graduation gate opens. The ladder is a
living artifact: `docs/capability-ladder.md` records per-rung rates
per generation, the stability bands, and the next-demo queue.

## Anti-flakiness protocol (why tests stop being 0/3 or unstable)

1. **Rates, never single runs** (S74, standing): n=3 minimum.
2. **Band tracking**: each task's rate band is recorded per
   generation; stability = 3 consecutive verdicts in-band. An
   out-of-band swing blocks further training until explained
   (the gen-7 lesson institutionalized).
3. **Graduation gating**: demonstrations for rung N+1 are authored
   only when rung N is stable — never training toward a rung the
   model cannot stand on (the gen-9 json lesson).
4. **Goal identity** (S78 lesson): every authored demo's goal carries
   the module + descent path so goal-dedupe cannot collapse volume.
5. **Demo quality validator** (new, deterministic): before an
   authored demo enters the corpus it must pass — the S41 gate (real
   verification), first-tool discovery, ≥1 recovery beat in ≥25% of
   a rung's set, diagnosis narrative references the actual observed
   evidence (test name/file it read), no fabricated claims (the
   verifier already refuses premature claims), unique anchors in any
   edit (the S78 cascade lesson).

## The authoring mechanism (author is swappable)

`build_corpus` gains the `agent-authored` lane: demonstrator scripts
authored by the agent (richer exploration orders, genuine wrong
turns, reasoning-depth narratives — the things templates cannot
produce), run through the REAL loop with the REAL gate, tagged
`agent-authored` with session provenance. The lane accepts any
provider as the author: in-session agent now, Gemini drips already
run the same path, and any future epN that can author its own demos
closes the loop. Volume is unlimited and quota-free.

## What the agent authors for the current walls (first batch)

- **json synthesis** (the 3B wall): demos whose diagnosis narrative
  explicitly walks the TEST FIXTURE — "the test constructs data as
  {settings: {timeout: 30}}, so the value lives one level down;
  the lookup must chain .get('settings', {}) before .get(key)" —
  teaching the inference step, not just the expression. Volume:
  enough variants that the pattern is over-learned.
- **cascade persistence** (rung 2): demos that run the chain, hit
  the second failure, re-diagnose from scratch (no reuse of the
  first diagnosis), and state both fixes in the final.
- Both batches pass the quality validator; both carry the
  mask-friendly turn structure the S76.3 pipeline expects.

## Deliberately deferred

- RL / GRPO-style online training (needs GPU-hours beyond Colab;
  revisit if a local GPU ever lands).
- Replayable full-state demonstrations (captures remain behavior
  traces — labeled, per D6).
- Rung 5-6 eval task implementation (specified, gated on rung 4
  graduation).

## Verification

- Ladder doc exists with rung table + graduation criteria.
- Quality validator: unit tests for each rule (discovery-first,
  recovery share, evidence-referencing narrative, unique anchors).
- First agent-authored batch: json + cascade demos pass the real
  gate, carry `agent-authored` + session provenance, and the corpus
  rebuild reports the lane separately.
- The ladder's own health: no rung's demonstrations authored while
  the rung below is out of band.
