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

v1 core complete (see [docs/spec.md](docs/spec.md), frozen); skills
ladder in progress (slice log in [docs/ROADMAP.md](docs/ROADMAP.md)).
Shipped: `record`, `lookup`, `report`, `accuracy`, `export`/`import`,
and the `run` auto-capture skill. Run brief that produced the spec:
[docs/qa-companion-run.md](../../../Agents/docs/qa-companion-run.md) in the
Antfarm repo.

## Usage

```powershell
python -m qacompanion record --sig "test_parse :: assertionerror: expected 2 got 3" --err "AssertionError: 2 != 3" --diag "off-by-one in parser index" --by tess
python -m qacompanion lookup --sig "test_parse :: assertionerror: expected 2 got 3"
python -m qacompanion report
python -m qacompanion accuracy
```

### Auto-capture (S7 skill)

```powershell
python -m qacompanion run -- python -m pytest tests/ -q
```

Wraps any command: the command runs exactly as typed (argv list, no
shell), its merged output is echoed to stderr, its exit code is passed
through untouched, and a nonzero exit is auto-recorded into the case base
(signature = command + last output line; honest "pending teacher review"
diagnosis). A zero-exit run records nothing. No timeout is enforced — a
hung child hangs the wrapper (explicit decision, docs/DECISIONS.md).
Nested `qa run` invocations are refused.

### Environment classification (S9 skill)

When `run` auto-records a failure, the merged output is first classified
against a deterministic, ordered rule set (see
`qacompanion/skills/environment.py`). Matches record an environment
diagnosis instead of the generic placeholder: `empty repo` (git outside
any work tree), `version mismatch`, `permission denied`, `tool missing`
(command/module not found), or `wrong cwd` (ENOENT family - the
npm-ENOENT lesson). Unclassified output keeps the honest "pending teacher
review" placeholder; classification never changes signatures, exit codes,
or lookup semantics, and teacher review can overwrite it like any
diagnosis.

- Case base: `cases.jsonl` in the repo root (override with `QA_CASES_FILE`).
- Holdout: `seed/holdout.jsonl`, frozen at creation (override
  `QA_HOLDOUT_FILE`). Mutating it invalidates every future accuracy
  comparison — see [docs/SEEDING.md](docs/SEEDING.md).
- Baseline (S4, verbatim): `accuracy: 100% (4/4)` against the four seeded
  lore lessons. Regressions must be justified or reverted.
- Exit codes: 0 success, 1 operational failure. `lookup` exits 0 even on
  a miss — it prints exactly `no matching case` rather than failing.

## Teacher loop (runbook)

The tool never invents diagnoses; learning happens out-of-band through
teachers (the human creators, plus colony agents proposing for REVIEW):

1. **Capture.** After any real test run with failures, take the test name
   and first error line verbatim.
2. **Record.** `record` each failure with your best-guess diagnosis
   (`--by <name>` marks who proposed it). Matching signatures bump
   `times_seen`; new ones create cases. Never exercise the CLI against the
   live store outside a declared cycle — set `QA_CASES_FILE` to a temp copy
   (see case #5).
3. **Request REVIEW.** Teachers confirm or correct each diagnosis:
   a correction re-runs `record` with the fixed `--diag` (same signature —
   the diagnosis is overwritten and `times_seen` bumps); a correction for a
   failure with no stored case creates one.
4. **Re-lookup.** Next occurrence should return the confirmed diagnosis.

Accuracy caveats when reporting or comparing scores:

- The holdout lives at `seed/holdout.jsonl`, **not** the repo root; point
  overrides at `QA_HOLDOUT_FILE`. Mutating it invalidates all comparisons.
- Accuracy is only meaningful once the holdout holds more than a handful of
  entries; with N=4 a single miss swings 25 points. Say so instead of
  quoting a bare percentage.
- If accuracy drops after a change, cite old-vs-new as k/N in the cycle
  summary and justify or revert — never ship the drop silently.

## Roles in this repo

- agent-a: builder
- agent-b: critic/reviewer
- tess: primary user + QA (once promoted to Analyst) — her reviews feed cases;
  the case base sharpens her reviews
