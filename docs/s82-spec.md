# S82 — Agent-Authored Batch 2: json volume + second cascade

Status: landed 2026-09-25. No new mechanism (S80 stands); this is the
lane working as intended — the session authors, the validator + S41
gate decide.

## What (rungs 1–2 only; rung 3+ stays gated)

1. **json drill 4 (`session_store`, `session -> user`)**: two-level
   descent WITH a genuine wrong turn — first read `src/session_store.py`
   genuinely fails, the test fixture gives the real shape. Recovery
   beat for the json rung set (S80 spec: ≥1 recovery beat in ≥25%).
2. **json drill 5 (`retry_policy`, `retry`)**: clean single-level drill
   on a fresh module — volume for the synthesis pattern beyond S80's
   three (S78 lesson: volume teaches the expression; narratives teach
   the inference).
3. **cascade 2 (`string_ops`: `reverse` + `shout`)**: the persistence
   lesson on a second module so rung 2 is not a single-module trick —
   chain → second failure → re-diagnose from scratch → final names
   BOTH fixes.

All goals carry module + defect identity (S78 goal-dedupe lesson);
all finals name the files actually touched; all edit anchors match
their fixtures exactly once.

## Live

- Lane on the real store: 7 runs / 7 passed / 0 failed / 0 rejected.
- `qa curate`: 1138 experiences → ACCEPT 1135 / REVIEW 2 / REJECT 1.
- `qa build-training`: export 169 rows = 165 verified-success
  step-trainable + 4 SRFT prefixes (was 154 = 151 + 3); all 7
  agent-authored demos present and step-trainable.
- Honest notes: (1) the calc-cascade goal also appears in 6 verdict
  records (ep9/ep10 successes) — legitimate verified volume on the
  persistence shape, not double-counting of one run; (2) the 4
  re-run S80 demos recorded under fresh session suffixes, as designed
  (S63 session-unique goals; reinforcement merges only identical
  normalized goals).

## Colab order (answered)

YES, wait: upload the fresh `training/training.jsonl` (169 rows, built
this slice) before `%run train_ep1.py ep11 ...`, or ep11 trains without
these demos. S81 kit + S82 corpus ride the same Colab job.

## Verification

- `AgentAuthoredTests`: 7/7 validator + lane (pins updated 4 → 7).
- Full suite 1687 OK (skipped=4), pyflakes clean.
