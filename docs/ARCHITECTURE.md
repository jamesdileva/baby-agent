# Architecture — qacompanion v1

Deterministic QA companion: accumulates test-failure cases, matches new
failures against them, reports honestly. No LLM, no network, no dependencies.

## Components

```
qacompanion/
  __main__.py     # argv dispatch -> subcommand modules; exit-code policy
  store.py        # CaseStore: cases.jsonl load (strict validation), append,
                  #   atomic replace via temp copy; env override QA_CASES_FILE
  signatures.py   # normalize(test_name, first_error_line) -> fingerprint;
                  #   equality matching only (no fuzzy tier in v1)
  lookup.py       # best-match selection: highest times_seen among equal sigs
  report.py       # report table + accuracy evaluation vs holdout
  transfer.py     # export / import round-trip (no-locking copies)
tests/            # unittest, one file per module, fixture-driven
seed/
  lore.jsonl      # initial case base: the colony's known failure history
  holdout.jsonl   # frozen evaluation set (created at S4, never trained on)
```

## Data flow

```
test failure ──> record(sig, excerpt, diagnosis) ──> cases.jsonl
                                                        │
new failure ──> normalize ──> lookup ──> known? ── yes ─┘─> instant diagnosis
                                    │
                                    no ──> parents diagnose ──> record
                                                (teacher loop)
```

## Design decisions

- **D1 — stdlib only.** Same discipline as taskline; zero install step; runs
  anywhere Python 3.14 exists.
- **D2 — frozen JSONL format.** One object per line; v2 may add fields, never
  rename. Corrupt lines abort load (ValueError) rather than skip silently.
- **D3 — exact-signature matching in v1.** Normalization handles path/case
  noise; fuzzy clustering is a named future tier, not silent magic.
- **D4 — honesty metric.** Holdout accuracy is a first-class output. Changes
  that lower it are treated as regressions even if tests stay green.
- **D5 — teacher loop out-of-band.** LLM reasoning happens in agents, never
  inside qacompanion. Corrections arrive as ordinary `record` calls with
  `--by` attribution.
- **D6 — seeded lore.** The initial case base carries the colony's real
  failure history forward across lab resets: FAIL(0.0s) harness artifact,
  BOM-breaks-config, stale-installer custody, empty-repo tooling errors.
  Lessons that used to die with a reset now survive inside the tool.
- **D7 — small package, skill-shaped seams.** One module per capability so
  future skills add files instead of editing working code; keeps review diffs
  small for agent reviewers.

## Failure-mode honesty

The tool distinguishes three states explicitly: **known** (match found),
**unknown** (no match — say so), **unsure** (signature collision between
cases — print both, flag for teacher review). Silent guessing is prohibited.
