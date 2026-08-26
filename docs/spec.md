# qacompanion v1 — Spec of record (FROZEN)

Amendments require a written proposal before implementation. v2 may add
fields; renames are prohibited.

## Purpose

Accumulate test-failure cases (signature + diagnosis) so recurring failures
are recognized instantly and new ones get faster diagnoses over time.
Deterministic, stdlib-only, honest about what it does not know.

## Storage

`cases.jsonl` — one JSON object per line:

```json
{ "id": 1, "signature": "<normalized fingerprint>", "error_excerpt": "...",
  "diagnosis": "...", "times_seen": 3, "last_seen": "2026-08-26T00:00:00Z",
  "confirmed_by": "agent-b" }
```

- Ordered by `id`, strictly increasing, integers only
- `signature`: test name + first error line, paths baselined, whitespace
  collapsed, case-folded
- Load aborts with ValueError (naming the line number) on any malformed line

## Subcommands

| Command | Behavior | Exit |
|---------|----------|------|
| `record --sig S --err E --diag D [--by N]` | Insert or bump matching signature (`times_seen++`, update `last_seen`; `--diag` overwrites when provided) | 0 / 1 |
| `lookup --sig S` | Print highest-times_seen match, or exactly `no matching case` | 0 always |
| `report` | Total cases, top 5 by times_seen, stale (>30d since last_seen) | 0 |
| `accuracy` | Replay `seed/holdout.jsonl`: % of entries where lookup returns the recorded diagnosis | 0 |
| `export --out P` | Atomic copy of the case base | 0 / 1 |
| `import --in P` | Validate then atomically replace; corrupt input never touches live data | 0 / 1 |

## Honesty states (mandatory)

- **known** — match found: print case id, diagnosis, times_seen
- **unknown** — no match: print exactly `no matching case`
- **unsure** — signature collision between distinct cases: print both,
  append `AMBIGUOUS - teacher review required`

Silent guessing is prohibited.

## Seeded lore

The initial case base imports `seed/lore.jsonl` at S4: the colony's real
failure history (FAIL(0.0s) harness artifact, BOM-prefix crashes,
stale-installer custody, empty-repo tooling errors), so accuracy measures
against genuine lessons from day one.
