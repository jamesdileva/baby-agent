# Seeding provenance — seed/lore.jsonl, seed/holdout.jsonl, cases.jsonl

Created once at S4 (commit "S4: accuracy + holdout replay", 2026-08-25).
The holdout is the frozen accuracy yardstick: **mutating
`seed/holdout.jsonl` invalidates every future accuracy comparison.**

## Source of the lessons

The four lesson families are the ones named in docs/spec.md §"Seeded lore"
(FAIL(0.0s) harness artifact, BOM-prefix crashes, stale-installer custody,
empty-repo tooling errors). Entries were authored by agent-a as faithful
reconstructions of those documented colony lessons; attribution is
`seeded-lore` until a teacher confirms/corrects via the normal teacher loop.

## Creation transcript (PowerShell, repo root, QA_CASES_FILE unset)

Lore authored directly as `seed/lore.jsonl`, then applied through the
shipped `record` CLI (so every seeded case passed the same canonical()
gate and validation as live traffic):

```
PS> python -m qacompanion record --sig "sitrep checks :: fail: checks (0.0s)" --err "FAIL: checks (0.0s)" --diag "Harness artifact, ..." --by seeded-lore
recorded new case #1 times_seen=1
PS> python -m qacompanion record --sig "test_load_config :: jsondecodeerror: expecting property name enclosed in double quotes" --err "json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)" --diag "File begins with a UTF-8 BOM and json.loads chokes ..." --by seeded-lore
recorded new case #2 times_seen=1
PS> python -m qacompanion record --sig "preflight installer probe :: sha256 mismatch after download" --err "sha256 of downloaded installer does not match the quoted hash" --diag "Stale-installer custody break: ... Rule R3 ..." --by seeded-lore
recorded new case #3 times_seen=1
PS> python -m qacompanion record --sig "repocheck scan :: fatal: not a git repository (or any of the parent directories)" --err "fatal: not a git repository (or any of the parent directories): .git" --diag "Tooling invoked outside a git work tree: ..." --by seeded-lore
recorded new case #4 times_seen=1
PS> python -m qacompanion report
total cases: 4
top 5 by times_seen:
case #1 times_seen=1 sig: sitrep checks :: fail: checks (0.0s)
case #2 times_seen=1 sig: test_load_config :: jsondecodeerror: expecting property name enclosed in double quotes
case #3 times_seen=1 sig: preflight installer probe :: sha256 mismatch after download
case #4 times_seen=1 sig: repocheck scan :: fatal: not a git repository (or any of the parent directories)
stale (>30d):
none
```

Holdout frozen from the live store (guarantees signature/diagnosis pairs
match what lookup actually returns):

```
PS> python -c "import json,pathlib; cases=[json.loads(l) for l in pathlib.Path('cases.jsonl').read_text(encoding='utf-8-sig').splitlines() if l.strip()]; out=''.join(json.dumps({'signature':c['signature'],'diagnosis':c['diagnosis']})+'\n' for c in cases); pathlib.Path('seed/holdout.jsonl').write_text(out,encoding='utf-8',newline='\n'); print(f'froze {len(cases)} holdout entries')"
froze 4 holdout entries
```

## Baseline (verbatim)

```
PS> python -m qacompanion accuracy
accuracy: 100% (4/4)
```

Honesty rule armed: any future change that lowers this number must be
justified in the cycle summary or reverted (AGENTS.md).

## SHA256 at freeze time

```
E745B4CCA77DF145461D1F71CB03D6EB82FB00CE115E14B1BE8FD6A20AD36EAA  seed/lore.jsonl
228DF71D627EBCFB8163D192651760BC62197E43C5C6448D1CC43BE0E70A4E00  seed/holdout.jsonl
8B0A63818413560ED2F1CB734071A8F173D6E68DF004046A53C14B7A2C417E5C  cases.jsonl
```

`cases.jsonl` will legitimately drift as new lessons are recorded — its hash
is pinned here only to mark the exact S4 seeding state. The two files under
`seed/` are frozen artifacts; their hashes should never change.

## Re-import path

`qa import` (ROADMAP S5) does not exist yet; re-creating the base from lore
means replaying the `record` commands above. The import duplicate-signature
policy is proposed as D-0005 in docs/DECISIONS.md and awaits human ruling;
no import merge logic lands before that ruling.
