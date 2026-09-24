# lab.db mining handoff — wire colony transcripts into the training corpus

Status: investigation done (2026-09-15, verified read-only against live DBs).
Next: zcode session to re-verify, then implement.

## 1. The opportunity (one paragraph)

Every antfarm colony cycle ends with its full OpenCode session transcript
(messages + parts JSON: prompts, tool I/O, reasoning, patches, final output)
saved into `lab.db`'s `session_transcripts` table — 160/160 eligible sessions,
zero capture failures. Session GC then *deletes* those sessions from
`opencode.db`, which is the only corpus baby-agent mines today
(`--source opencode|zcode`). So the colony's cleanest, best-labeled training
data sits in a table nothing reads. Wire it in.

## 2. Verified findings (re-verify all of §4 before implementing)

- F1. baby-agent has NO lab.db miner: zero matches for
  `lab.db|session_transcripts|labdb|lab_db` in source. Mining entry point is
  `qa mine-sessions --source opencode|zcode`
  (`qacompanion/__main__.py` ~line 516; adapters:
  `qacompanion/agent/opencode_mine.py`, `qacompanion/agent/zcode_mine.py`).
- F2. `qa gemini-drip` is live-generated benchmark data, NOT mined history.
  `qa digest` mines colony *files* (DECISIONS.md, git logs, *.log) — not lab.db.
- F3. Live lab.db (`%APPDATA%\@antfarm\shell\antfarm-home\project\lab.db`,
  `PRAGMA user_version` = 6): 146 `done` + 14 `timed_out` sessions, ALL with
  transcripts; 11 `failed` intentionally without (left alive, never GC'd);
  0 `session_gc_failed` events. Live config: `sessionGc: true`,
  model `opencode/muse-spark-1.3-contributor-free`.
- F4. Transcript shape: JSON array of `{info: {role}, parts: [...]}`; part
  vocab `text|tool|reasoning|patch|step-start|step-finish` — identical to what
  `OpencodeMiner` already parses. Done avg ~120KB/10 msgs (max seen ~593KB,
  43 msgs); timed_out avg ~29KB/4 msgs (partial work).
- F5. GC is destructive in opencode.db (spot check: `ses_f61c35a51…` → 0 rows
  in `session`, 0 in `part`). lab.db is the only copy post-GC.
- F6. muse-spark stores EMPTY reasoning text (15/15 parts empty in sampled
  cycle-83 session; mimo control 11/11 non-empty). `tokens_reasoning` still
  counted. Miner impact: nil — it never consumes reasoning parts (user text +
  tool names + error→patch only). Decisions/tool traces/patches fully intact.
- F7. Known lab.db hygiene gap (antfarm-side, optional): `sessions` rows keep
  `opencode_session_id = ''`; the real id lives only in
  `session_transcripts.opencode_session_id`.

## 3. Why lab.db beats re-mining colony sessions from opencode.db

- No boilerplate problem: transcripts are pre-filtered to genuine cycles —
  no `SITUATION REPORT` preambles, no ×321 resume loops, no <100-part
  goal-less skips that plague the opencode-side colony view.
- Honest outcome labels: `done|timed_out|failed` + tokens/cost/summary per
  cycle, vs the miner's blanket `outcome="partial", confidence=0.3`
  ("the DB cannot prove success").
- Bonus correction signals nearby (future enrichment, NOT v1): critic
  block/close moves (negative examples), orchestrator WARNING teaching loop
  (correction pairs), mail threads (deliberation), memory snapshots.

## 4. Re-verification checklist (run read-only; real DBs never touched by tests)

- [ ] `rg -n "lab\.db|session_transcripts|labdb" qacompanion/ tests/ docs/` → expect zero source hits
- [ ] `sqlite3 <lab.db> "SELECT status, COUNT(*), SUM(transcript-present) …"` →
  expect done 1:1, timed_out 1:1, failed 0 (counts will have grown; ratios matter)
- [ ] Pick newest transcript id; confirm JSON shape `{info,parts}` + part-type
  histogram includes `tool`/`patch` for a `done` session
- [ ] Pick a GC'd `opencode_session_id` from transcripts; confirm 0 rows in
  `opencode.db` `session`/`part` (proves F5, justifies the work)
- [ ] Confirm `OpencodeMiner` ignores `reasoning` parts (proves F6 ⇒ no spark gap)

Reference paths: miner `baby-agent/qacompanion/agent/opencode_mine.py`;
adapter pattern `zcode_mine.py` (27 lines: tag + DB path);
lab.db schema `Agents/packages/db/src/migrate.ts` (M006),
repo `Agents/packages/db/src/repositories.ts` (`TranscriptRepo`).

## 5. Implementation direction (proposal — zcode decides)

- New `LabDbMiner(OpencodeMiner)` in `qacompanion/agent/`, following
  `ZcodeMiner`: override `SOURCE_NAME = "labdb"`, default path to the
  antfarm-home `lab.db`, read-only `mode=ro` URI like the base class.
- Session source: `session_transcripts JOIN sessions` (NOT opencode tables).
  Reuse `_user_text`/`_tool_actions`/`_error_patch` against the transcript
  JSON (parts already in hand — no message/part table joins needed).
- Outcome mapping (replaces blanket partial/0.3): `done` → keep miner default
  or promote confidence; `timed_out` → `partial` (partial work, honest);
  skip `failed` (no transcript) — or mine as `failed` if a future transcript
  exists. Curator rules stay the judge of success, per S50 discipline.
- CLI: `--source labdb` alongside `opencode|zcode`; stats gain per-status
  counts. Docs: `quick-reference.md` one-liner.
- Conventions (non-negotiable, per repo discipline): fixture-first — build a
  synthetic lab.db-shaped fixture; real DBs never touched by tests; every
  failure a structured error; trivial/boilerplate policy documented like S47.
- Out of scope for v1: mail/board/memory enrichment (§3 bonus), dashboard
  transcript viewer (antfarm-side), `opencode_session_id` backfill (F7).

## 6. Open questions for the implementing session

1. Confidence values for done/timed_out ЛабDb experiences (curator input welcome)?
2. Size cap: largest transcripts ~600KB — mine whole or bound tool windows
   (miner already caps at `MAX_ACTIONS = 50`)?
3. Dedupe vs opencode-source colony sessions already in the store (same
   opencode id as provenance — reuse `session_id` field so the store's
   normalized-goal reinforcement merges instead of double-counts)?