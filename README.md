# baby-agent

A decoupled, lightweight, continuously-learning QA companion — no LLM inside.

Built by the Antfarm colony (agent-a, agent-b, and tess). Unlike its creators,
this tool burns zero tokens: it is a deterministic case-matching engine that
gets sharper the more failures it sees.

## The idea

Every software project develops signature failures — the same bug shapes
recurring under new clothes. Humans (and LLM agents) re-diagnose them from
scratch every time. `baby-agent` records each failure as a **case**
(fingerprint + diagnosis), so the Nth occurrence of a known failure is
recognized instantly, for free, forever.

LLM agents act as **teachers**: their reasoning distills lessons into cases.
The tool is the student: it stores, matches, reports — never guesses silently.

## Status

v1 in progress (see [docs/spec.md](docs/spec.md), frozen; slice log in
[docs/ROADMAP.md](docs/ROADMAP.md)). Shipped: `record`, `lookup`, `report`,
`accuracy`. Run brief that produced the spec:
[docs/qa-companion-run.md](../../../Agents/docs/qa-companion-run.md) in the
Antfarm repo.

## Usage

```powershell
python -m qacompanion record --sig "test_parse :: assertionerror: expected 2 got 3" --err "AssertionError: 2 != 3" --diag "off-by-one in parser index" --by tess
python -m qacompanion lookup --sig "test_parse :: assertionerror: expected 2 got 3"
python -m qacompanion report
python -m qacompanion accuracy
```

- Case base: `cases.jsonl` in the repo root (override with `QA_CASES_FILE`).
- Holdout: `seed/holdout.jsonl`, frozen at creation (override
  `QA_HOLDOUT_FILE`). Mutating it invalidates every future accuracy
  comparison — see [docs/SEEDING.md](docs/SEEDING.md).
- Baseline (S4, verbatim): `accuracy: 100% (4/4)` against the four seeded
  lore lessons. Regressions must be justified or reverted.
- Exit codes: 0 success, 1 operational failure. `lookup` exits 0 even on
  a miss — it prints exactly `no matching case` rather than failing.

## Roles in this repo

- agent-a: builder
- agent-b: critic/reviewer
- tess: primary user + QA (once promoted to Analyst) — her reviews feed cases;
  the case base sharpens her reviews
