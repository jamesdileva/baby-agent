# S47.1 — opencode Session Mining: Design Spec

Follow-up to [s47-spec.md](s47-spec.md); human-directed: "can baby-agent
learn from my already-made projects?" One slice, stdlib only (`sqlite3`
is stdlib), read-only over opencode's data.

## The corpus (measured 2026-09-04)

`C:\Users\j\.local\share\opencode\opencode.db` (8 GB SQLite, SST
opencode): 1,170 sessions / 42,530 messages / 171,746 parts across 21
projects, spanning 2026-07-30 → now. **Two session shapes** (volume
measured per directory):

- **marathon projects**: surfhop (2 sessions, 1,694 messages),
  dinner-menu-generator (1 session, 2,483 messages), sentinel (~28
  sessions, 50k parts), worldsim, WorkFlow-Toolkit — few sessions, huge
  ones. Session count is meaningless as a value proxy here.
- **turn-spawn projects**: antfarm spawns a session per agent turn —
  385 tiny sessions (~26 parts each) whose goals repeat.

Design consequence: the miner is **volume-aware** (records
message/part counts into the experience context), caps per-experience
action lists, and relies on the store's normalized-goal reinforcement
so antfarm's repeating turn-goals merge into few high-times_seen
patterns instead of flooding the store.

## Module layout

```text
qacompanion/agent/opencode_mine.py    # OpencodeMiner
tests/test_agent_opencode_mine.py     # synthetic SQLite fixture
```

## Miner

```text
OpencodeMiner(db_path)
    .sessions(directory=None)   -> rows (id, directory, title, times)
    .mine_session(row)          -> Experience | None   (None = trivial)
    .mine(directory=None, store=None, dry_run=False) -> stats
```

Mapping per session:

- **goal**: first user-message text part (≤200 chars); title fallback;
  no user text and no tool parts → trivial, skipped.
- **actions**: ordered tool-part names, capped at 50 (total count kept).
- **session_id**: the opencode session id (provenance — the store keeps
  it so any experience traces back to its source session).
- **context**: `{source: "opencode", directory, message_count,
  part_count, tool_count, model}` — the volume signals curation needs.
- **outcome**: honestly `partial` for every mined session (success is
  not yet provable from the DB) with low confidence (0.3); refinement is
  curation's job (S62), not the miner's guessing.
- **project metadata**: `ProjectMetadata.detect(directory)` languages /
  project_type when the directory still exists (read-only walk);
  otherwise omitted.
- Reinforcement goes through `ExperienceStore.record` (normalized-goal
  dedupe — antfarm's repeating turn prompts converge into few
  high-times_seen patterns).

Read-only discipline: the DB opens with `mode=ro` URI; the miner never
writes to opencode's files. Tests use a synthetic fixture DB built with
the same schema — the real database is never touched by the suite.

## Stats + live import

`mine()` returns `{sessions_seen, mined, reinforced, skipped_trivial,
by_directory}`. First run: `dry_run=True` for a safe preview, then the
real import into `experience.jsonl` (runtime artifact — gitignored like
digest.jsonl; the mined corpus stays local).

## Testing strategy (tests/test_agent_opencode_mine.py)

Synthetic DB with the real schema: two marathon sessions (many
messages/parts incl. tool + text parts), one turn-spawn pattern
(repeated identical goals), one trivial session (no user text, no
tools), one session whose project directory doesn't exist.

- Goal extraction (first user text), title fallback, trivial skip.
- Action ordering + cap; context volume counts.
- Reinforcement across repeated turn-goals (store-level dedupe).
- Directory filter; dry_run writes nothing; stats honest.
- Read-only proof: the fixture DB is byte-identical after mining.

Expected suite growth: 1277 → ~1290 OK.

## Exit criteria

A dry-run preview over the real DB reports honest stats; the import
populates experience.jsonl with curated experiences traceable to their
source sessions; the suite never touches the real database. Full suite
green; preflight clean.
