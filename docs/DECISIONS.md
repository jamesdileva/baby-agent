# DECISIONS.md

Proposed amendments and recorded design decisions for qacompanion.
Per AGENTS.md, `docs/spec.md` is frozen for v1: entries here *propose*;
the human disposes. Nothing below changes behavior until signed off
(except where explicitly marked as already-in-force implementation detail).

## D-0001 lookup exit-code policy [PROPOSED - needs human sign-off]

Proposed spec wording:

> `lookup` exits 0 on well-formed stores, including when no case matches
> (printing exactly `no matching case`). A corrupt store raises ValueError,
> which exits 1 under the uniform ValueError policy shared by all
> subcommands.

Rationale: "no matching case" is a successful, honest answer to the query,
not an operational failure; a corrupt store is an operational failure.
This matches the shipped behavior since S2 (tests/test_lookup.py).
Provenance: agent-b TASK #9 acceptance criterion 5; first flagged in the
S2 review of b9b83f5.

Status: implemented in code, pending human ratification of the wording.

## D-0002 '::' separator is non-injective [KNOWN LIMITATION - guard deferred]

`SEPARATOR = " :: "` is not injective: distinct (test_name, error_line)
pairs can compose to the same signature string whenever the parts
themselves contain `" :: "`, e.g. `("t", "err :: more")` collides with
any decomposition that splits at the first separator. `canonical()`
splits at the *first* `" :: "` occurrence, so record/lookup agree
deterministically (same input -> same split -> same stored string ->
exact-match works), but two genuinely different failures can silently
share one case.

Impact today: bounded. Signatures come from teacher-loop input where the
test name rarely contains spaced colons; duplicate storage still surfaces
as AMBIGUOUS rather than silent. The un-guarded direction is distinct
failures merging into one signature.

Candidate fixes (all touch the frozen format, hence deferred to a signed-off
amendment): escape `" :: "` inside parts at canonicalize time, or switch to
a control-character separator in v2 with a store migration.

Decision: ship v1 with the deterministic-first-split rule, this documented
limitation, and an AMBIGUOUS backstop; revisit only if a real collision is
observed in cases.jsonl.
Provenance: agent-b TASK #9 acceptance criterion 6 ("an undocumented known
collision is worse than a documented deferred one").

## D-0003 naive last_seen interpreted as UTC [PROPOSED - needs human sign-off]

Proposed spec wording (Input robustness / report):

> A `last_seen` stamp without timezone information is interpreted as UTC,
> never crashes, never shifts stale classification by an unstated offset.

Rationale: mixed-offset or legacy stores would otherwise crash `report` on
the first naive stamp; interpreting naive-as-UTC is deterministic and
conservative. Implemented in shipped behavior since 83b6f91
(`report._as_utc`, tested in tests/test_report.py).
Provenance: agent-b review of 83b6f91 (mail #13) suggested putting the
interpretation on the record.

## D-0004 accuracy-score line inside `report` [PROPOSED - needs human ruling]

PROJECT_GOAL.md's report bullet includes an "accuracy score"; spec.md L33
(the frozen table row for `report`) does not. Per AGENTS.md the spec wins,
so shipped `report` has NO accuracy line; accuracy lives in its own
subcommand (`qa accuracy`). If ruled IN, proposed amendment wording:
append "; accuracy score" to the spec report row and one line to
report output. Until then, nothing changes.
Provenance: goal-vs-spec divergence flagged by agent-a, confirmed firsthand
by agent-b (mails #13/#14).

## D-0005 import duplicate-signature policy [PROPOSED - needs human ruling]

Proposal: **reject duplicates**. `import --in P` validates the whole input
atomically before touching live data; a signature appearing twice in the
input file is a ValueError naming the second line, and nothing replaces the
live base. Import replaces wholesale — merging near-duplicate signatures is
a deliberate teacher act reserved for the future merge tool (ROADMAP S18),
never a silent side effect of a copy operation.

Alternative considered and rejected for v1: merge-by-bump onto existing
counts (silent mutation of recorded history during what looks like a copy).

Gate honored: no import logic lands until this is ruled (agent-b TASK #14
criterion 4). Provenance: TASK #14 criterion 4; spec S5 row ("Validate then
atomically replace").

## Slice-numbering canon [IN FORCE - documentation only]

ROADMAP/spec slice numbers are canon for commit subjects and provenance
citations. Historical drift, logged so citations stay unambiguous:

| Commit | Subject said | ROADMAP canon | Delivered |
|--------|--------------|---------------|-----------|
| a2cf9f2 | S1 | S1 storage core + `record` | match |
| b9b83f5 | S2 | S2 signatures + `lookup` | match |
| 7c7d6fe | S3 | (S2 follow-up) canonical() gate + DECISIONS | off-by-one label |
| 83b6f91 | S4 | S3 `report` | off-by-one label |
| (this)  | S4 | S4 `accuracy` + holdout replay | canon restored |

The "S5" used in mail/task #14 titles for the accuracy work maps to
ROADMAP S4 above. From here on: ROADMAP numbers only.

## Pending human sign-off — single-pass queue

All open rulings, for one-pass adjudication:

1. **D-0001** lookup exit-code wording (0 on miss, 1 on corrupt store)
   — implemented since S2, needs ratification.
2. **D-0002** `' :: '` separator non-injectivity — known-limitation note;
   acknowledge or direct a fix direction.
3. **D-0003** naive last_seen → UTC fallback — implemented, ratify wording.
4. **D-0004** accuracy-score line inside `report` — amendment needed if IN.
5. **D-0005** import duplicate-signature policy — blocks S5 import work.
