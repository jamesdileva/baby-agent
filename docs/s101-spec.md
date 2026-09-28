# S101 — Wrong-value recovery drill (the ep16 indirect lesson)

## Mechanism (re-probe, evidenced)

Seed-42 verdict: ep16 indirect 0/3 (taxcalc 1.5 → 1.4, needs 1.2;
cart compensated with inlined `p * 1.4`; stale retry; death).
Seed-43 re-probe: 1/3 (rep2 clean 7/6/0 at 1.2; reps 1+3 the
identical 1.4-guess + cart-compensation + stale-retry instance).
5 of 6 runs share one systematic instance — a biased value guess
with no re-derivation — not sampling noise. ep11 fails
differently (edits the wrong file first); ep15 guessed 1.2.
The rung-3 shape (follow the import) is intact; the arithmetic
derivation is not.

## Recipe

- **R4** in `agent_authored_demos` (fresh order/fees modules —
  never taxcalc/cart per S91, never the S95 rung-3 modules):
  import-follow → wrong-value edit 1.5 → 1.4 (applies, suite
  rejects for real) → re-read the test → derive 36/30 = 1.2 →
  corrective edit → pass. All anchors match, so no
  `recovery_anchors` declaration (the defect is arithmetic, not
  anchoring); the final narrates the derivation rule (derive from
  the test's expectation, never guess). `agent-authored` tag
  carries it through the deliberate path automatically.
- No validator or training-code changes (existing rules cover the
  shape); lane/test counts 19 → 20.
- **Out:** ep17 corpus via the standing lane → curate → export;
  Colab order: fresh `training.jsonl` + s92 kit (unchanged) →
  ep17 → pinned 5-task verdict vs ep11-q4 (with indirect
  re-probe at a second seed to confirm the lesson generalized).

## Acceptance

- R4 validates + verifies live; lane/test pins at 20; full suite
  exits 0; export counts recorded.

## Live result (2026-09-27)

- Lane: 1 run (R4, new goal), passed, 0 rejected, 19 skipped.
  Recorded trajectory shows the wrong-value edit applied
  (ok=True), suite rejecting it, re-read, corrective edit, pass —
  tagged `agent-authored` (deliberate path, no failed tool turns
  to strip).
- Export: 1512 trajectories, 412 eligible/step-trainable;
  deliberate 188, real kept 188, **capped 36** (verdict runs grew
  the real pool; cleanest-first cut deeper), **stripped 65**;
  SRFT 6. Export **382 = 376 + 6** (was 380).
- Suite 1739 OK (1738 + 1 new), pyflakes clean.
- Colab order stands: fresh 382-row training.jsonl + s92 kit →
  ep17 → pinned 5-task verdict vs ep11-q4 with an indirect
  second-seed re-probe.
