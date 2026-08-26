# Implementation guide — qacompanion v1

Runtime: Python 3.14, stdlib only. Structure: small package (see
[ARCHITECTURE.md](ARCHITECTURE.md) D7).

## Setup

```
cd C:\Users\j\Projects\baby-agent
python -m venv .venv                # optional; stdlib runs on system python
.venv\Scripts\activate
python -m unittest discover -s tests -v
```

## Commands

```
python -m qacompanion record --sig SIG --err EXCERPT --diag TEXT [--by NAME]
python -m qacompanion lookup  --sig SIG
python -m qacompanion report
python -m qacompanion accuracy
python -m qacompanion export  --out PATH
python -m qacompanion import  --in PATH
```

- Case file: `cases.jsonl` in repo root by default; override with
  `QA_CASES_FILE` env var (tests always use the override — never touch real
  data).
- Exit codes: 0 success; 1 operational failure (bad input, unreadable store);
  load-time corruption raises ValueError (exit via traceback is acceptable in
  v1).

## Build order

Follow [ROADMAP.md](ROADMAP.md) S1→S6 strictly. Each slice:

1. Tests first (fixture-driven; `tests/fixtures/` holds sample stores)
2. Implementation until green: `python -m unittest discover -s tests`
3. One commit per slice, message prefixed `S<n>:`
4. Clean tree before ending the cycle

## Conventions

- Modules never print except `__main__.py` dispatch and report/lookup output
  formatters — keep logic pure where practical.
- All dates ISO-8601 UTC.
- Signatures normalize: strip absolute paths to basenames, collapse
  whitespace, lowercase test names.
- Every bug fix ships with a regression test named after its failure mode.

## Slice notes

- **S1**: `store.py` + `record`. Validation rejects: non-int id, non-object
  line, missing signature/diagnosis. Corrupt store → ValueError naming the
  line number.
- **S2**: `signatures.py` + `lookup`. Fixture proves path/case variations of
  the same failure collide correctly.
- **S4**: create `seed/holdout.jsonl` from real colony failure history
  (see seeded lore); freeze it — accuracy compares against this forever.
- **S6**: teacher-loop runbook lands in README; exercise one live correction
  and record it in DECISIONS.md.

## Seeded lore

`seed/lore.jsonl` starts the case base with the colony's documented history:
FAIL(0.0s) wrong-cwd harness artifact, BOM-prefix config crashes,
stale-installer custody failures, empty-repo tooling errors. Import it at S4
completion (`import --in seed/lore.jsonl`) so accuracy has something honest
to measure against.
