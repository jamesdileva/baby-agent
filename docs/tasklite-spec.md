# tasklite — Capstone Project Spec (DRAFT)

A minimal, stdlib-only Python CLI for tracking personal tasks. Built as the
qacompanion capstone project: every development cycle exercises a qacompanion
skill end-to-end.

## Design philosophy

- Stdlib only (matching qacompanion v1 discipline)
- Single-file storage (`tasks.jsonl`), one JSON object per line
- Deterministic, honest, no magic
- Every failure during development is recorded, diagnosed, and recalled

## Storage

`tasks.jsonl` — one JSON object per line:

```json
{"id": 1, "title": "Write spec", "status": "todo", "created": "2026-08-26T00:00:00Z", "done_at": null}
```

- `id`: non-negative integer, strictly increasing
- `title`: non-empty string
- `status`: `"todo"` | `"done"`
- `created`: UTC ISO-8601 timestamp
- `done_at`: UTC ISO-8601 timestamp or null

Load aborts with ValueError (naming the line number) on any malformed line.
Stale/duplicate IDs are rejected. Atomic writes (write-to-temp, rename).

## Subcommands

| Command | Behavior | Exit |
|---------|----------|------|
| `tasklite add <title>` | Append a new task (status=todo, created=now) | 0 |
| `tasklite list` | Print all tasks: `#id [status] title` (todo first, then done) | 0 |
| `tasklite done <id>` | Set status=done, set done_at=now; error if already done or unknown id | 0 / 1 |
| `tasklite delete <id>` | Remove task from store; error if unknown id | 0 / 1 |
| `tasklite show <id>` | Print full task JSON (id, title, status, created, done_at) | 0 / 1 |

### Exit contracts

- 0: success
- 1: operational failure (bad input, unknown id, already done, corrupt store)

## Development plan (capstone exercise)

Each slice below uses at least one qacompanion skill:

1. **Slice 1 — Storage core + full CRUD** *(shipped)*
   - All 5 subcommands implemented: `add`, `list`, `done`, `delete`, `show`
   - Skills exercised: `qa preflight` before commit, `qa run` to capture any
     test failures, `qa journal add` to record the design decision
   - Exit: full lifecycle works; strict validation; atomic writes; BOM/CRLF
     tolerance; corrupt-store errors honest (41 tests)

2. **Slice 3 — CLI integration + edge cases + concurrency** *(current)*
   - Skills exercised: `qa run` to capture failures, `qa lookup` to check
     if any failure is recognized
   - Exit: CLI integration tests (exit codes, stderr, list ordering);
     edge cases (unicode titles, huge titles, empty title via CLI);
     concurrent-write tolerance verified; redundant import cleanup

3. **Slice 4 — Report + accuracy**
   - Skills exercised: `qa report` on tasklite's own test suite
   - Exit: tasklite has a case base of its development failures

## Capstone success criteria

Per ROADMAP: "the project ships with zero repeated diagnoses — everything new
was taught, everything taught was recalled."

Concrete measures:
- All test failures during development are recorded in qacompanion's case base
- `qa report` shows the tasklite development failure history
- `qa accuracy` confirms no repeated failure goes unrecognized
- Every qacompanion skill is exercised at least once during development
- The project builds and all tests pass at the final commit

## DECISION POINT: spec.md subcommand table

The frozen spec.md Subcommands table lacks rows for:
preflight, locate, snapshot, repocheck, journal, digest, mine, school, merge,
teach, flakes, run.

If the capstone requires qacompanion to expose all skills via CLI, these rows
must be added to spec.md (requires human ruling per AGENTS.md). If the capstone
scope is limited to CLI-exposed skills only, the list above is sufficient.

**Recommendation:** flag this in the human's next review as an explicit decision
point. The capstone can proceed with CLI-exposed skills only; the spec gap
amendment can follow if the human rules to expand scope.
