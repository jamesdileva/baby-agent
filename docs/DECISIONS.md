# DECISIONS.md

Proposed amendments and recorded design decisions for qacompanion.
Per AGENTS.md, `docs/spec.md` is frozen for v1: entries here *propose*;
the human disposes. Nothing below changes behavior until signed off
(except where explicitly marked as already-in-force implementation detail).

## D-0001 lookup exit-code policy [RATIFIED 2026-08-25 - human mail #15]

Proposed spec wording (ratified):

> `lookup` exits 0 on well-formed stores, including when no case matches
> (printing exactly `no matching case`). A corrupt store raises ValueError,
> which exits 1 under the uniform ValueError policy shared by all
> subcommands.

Rationale: "no matching case" is a successful, honest answer to the query,
not an operational failure; a corrupt store is an operational failure.
This matches the shipped behavior since S2 (tests/test_lookup.py).
Provenance: agent-b TASK #9 acceptance criterion 5; first flagged in the
S2 review of b9b83f5.

Status: RATIFIED AS WORDED by the human [mail #15, 2026-08-25]:
"no matching case" exits 0 (successful honest answer); corrupt store
exits 1. Behavior already matches since S2; no code change required.

## D-0002 '::' separator is non-injective [RATIFIED 2026-08-25 - deferred - human mail #15]

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
RATIFIED AS DEFERRED by the human [mail #15, 2026-08-25], with the same
revisit trigger (real observed collision). No code change required.
Provenance: agent-b TASK #9 acceptance criterion 6 ("an undocumented known
collision is worse than a documented deferred one").

## D-0003 naive last_seen interpreted as UTC [RATIFIED 2026-08-26 - human mail #41]

RATIFIED AS WORDED by the human [mail #41, 2026-08-26]: naive `last_seen`
stamps are interpreted as UTC. Behavior unchanged - implemented since
83b6f91 (`report._as_utc`, tested in tests/test_report.py); no code change
required.

Proposed spec wording (Input robustness / report):

> A `last_seen` stamp without timezone information is interpreted as UTC,
> never crashes, never shifts stale classification by an unstated offset.

Rationale: mixed-offset or legacy stores would otherwise crash `report` on
the first naive stamp; interpreting naive-as-UTC is deterministic and
conservative. Implemented in shipped behavior since 83b6f91
(`report._as_utc`, tested in tests/test_report.py).
Provenance: agent-b review of 83b6f91 (mail #13) suggested putting the
interpretation on the record.

## D-0004 accuracy-score line inside `report` [CLOSED 2026-08-26 - human mail #54 - condition satisfied @926c5b5]

PROJECT_GOAL.md's report bullet includes an "accuracy score"; spec.md L33
(the frozen table row for `report`) does not. The human's mail #15 ruling
supersedes the frozen row for v1 behavior; see OUTSTANDING below for the
row itself.

RATIFIED IN by the human [mail #15, 2026-08-25], with one condition: when
the holdout is empty or unplayed, the report line must degrade honestly
(e.g. `accuracy: n/a - holdout not yet created`) - never a fabricated
percentage.

IMPLEMENTED in 926c5b5: `report` appends `accuracy: X% (k/N)` by replaying
seed/holdout.jsonl through the same lookup semantics as `qa accuracy`;
a missing or empty holdout degrades to exactly
`accuracy: n/a - holdout not yet created` (exit 0), while a malformed
holdout still raises ValueError -> exit 1 (EmptyHoldout splits honest n/a
from operational failure). Baseline replay unchanged at 100% (4/4).
Condition verified live by agent-b [mail #30]: holdout renamed aside ->
exact n/a line, exit 0, no fabricated percentage; file restored
byte-identical.

RESOLVED 2026-08-26 [mail #41]: the spec.md L33 amendment was approved;
the frozen report row now reads "... stale (>30d since last_seen);
accuracy score". The table matches shipped behavior @926c5b5; nothing
outstanding remains on this decision.

CLOSED 2026-08-26 [human mail #54, relayed verbatim in agent-b TASK
mail #57]: D-0004 is fully resolved - condition satisfied @926c5b5 per
the human ruling. No further action on this decision, ever.

Provenance: goal-vs-spec divergence flagged by agent-a, confirmed firsthand
by agent-b (mails #13/#14); condition text verbatim from mail #15.

## D-0005 import duplicate-signature policy [RATIFIED 2026-08-25 - implemented]

Original proposal: **reject duplicates** outright, import replaces
wholesale, no merge-by-bump.

RATIFIED by the human [mail #15, 2026-08-25] as **reject by default, with
an explicit opt-in merge**:

> On duplicate signature during import, abort that import and name every
> offending line/signature in the error. Provide an explicit `--merge`
> opt-in flag that bumps times_seen instead. Predictability over
> convenience; merging is opt-in.

This supersedes the reject-only wording above (condition text verbatim
from mail #15). Provenance: TASK #14 criterion 4; spec S5 row ("Validate
then atomically replace").

IMPLEMENTED in the S5 slice (qacompanion/transport.py). Implementation
notes binding the shipped behavior: duplicates are detected BOTH within
the import file and against the live store; the default path aborts
naming every offending `line N: signature`. `--merge` folds counts only
(`times_seen` summed onto the live twin; diagnosis, error_excerpt,
confirmed_by, last_seen untouched - corrections travel the teacher loop,
never import), appends unseen signatures with fresh ids in file order,
and refuses a signature matching several live cases (AMBIGUOUS state)
rather than picking a winner. Intra-file duplicates abort in both modes.
Import files must satisfy the full frozen format (`id` included);
signatures pass through verbatim (canonical() stays a record/lookup
gate) so export -> import -> export is byte-stable. Consequence recorded
in SEEDING.md: seed/lore.jsonl (pre-record shape, no id) is not an
import file; lore restores via the record CLI.

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

## Ruling queue status [updated 2026-08-26, per human mails #15 and #41]

Mail #15 ruled on four of the five open items in a single pass:

1. **D-0001** lookup exit-code wording — RATIFIED as worded.
2. **D-0002** `' :: '` separator non-injectivity — RATIFIED as deferred.
3. **D-0003** naive last_seen → UTC fallback — RATIFIED as worded
   [mail #41, 2026-08-26]; behavior unchanged since 83b6f91.
4. **D-0004** accuracy-score line inside `report` — RATIFIED IN with the
   honest-degradation condition; IMPLEMENTED @926c5b5; L33 row amended
   per mail #41 (see D-0004).
5. **D-0005** import duplicate-signature policy — RATIFIED: reject by
   default naming offenders, `--merge` opt-in bumps times_seen;
   implementation queued.

No open rulings remain [queue empty as of mail #41, 2026-08-26].

## S6 live teacher-loop exercise [recorded 2026-08-26]

ROADMAP S6 exit requires exercising one live loop against a real failure
and recording it here. Two live loops now exist:

1. **Case #5** (store-hygiene incident, @e413e7c): diagnosis CONFIRMED by
   the human [mail #41, 2026-08-26]; store `confirmed_by` updated to the
   teacher accordingly - confirmation is not an occurrence, so no
   times_seen bump. The isolation rule stands exactly as diagnosed:
   manual/test invocations MUST set QA_CASES_FILE to a temp copy; live
   cases.jsonl changes only inside a declared cycle; coordinate before
   touching another agent's working tree.
2. **Case #6** (this cycle): the sitrep-reliability failure, observed
   firsthand for the 5th consecutive cycle - sitrep asserted a dirty
   ROADMAP.md plus a failing suite; fresh `git status --porcelain` was
   empty and `python -m unittest` exited 0 (104/104). Recorded via the
   `record` CLI with a proposed diagnosis and REVIEW requested. The loop's
   record/diagnose legs ran against the live store inside this declared
   cycle, exactly as the runbook prescribes.

Teacher-loop runbook landed in README (capture -> record -> REVIEW ->
confirm/correct/create), incorporating the mail #35 riders: holdout path
is seed/holdout.jsonl, never repo root (`QA_HOLDOUT_FILE` override);
accuracy is only meaningful past a handful of holdout entries; drops are
reported as old-vs-new k/N and justified or reverted.

Provenance: ROADMAP S6; IMPLEMENTATION_GUIDE.md slice note S6; riders from
mails #31/#33/#35; phantom-sitrep history in agent-a MEMORY.md.

## Case #6 teacher-review escalation [RESOLVED 2026-08-26 - human mail #54]

A QUESTION was mailed to the human this cycle requesting formal TEACHER
REVIEW of case #6's diagnosis (sitrep-reliability failure). Provenance
admission: earlier REVIEW requests lived only in this document and cycle
summaries - never in a human-addressed mail - so under the escalation
protocol they counted as unanswered; this mail is the first mail-first
leg.

OUTCOME SIGNED 2026-08-26: the human answered [mail #54] - ROADMAP
mystery solved, and the teacher review of case #6's diagnosis is
CONFIRMED (per mail #54, citing the #41-era record, as relayed verbatim
in agent-b's TASK mail #57). The provenance gap is closed. Consequences,
all executed the same cycle:

1. **Auto-bump cap LIFTED**: the hard-stop condition ("resume solely on
   the human's REVIEW/correction or explicit override") is met; bumps
   resume under normal freshness gating. First gated bump applied below.
2. **ROADMAP incident CLOSED** under the case #5 rule (uncoordinated
   tree/restore races; sitrep claims are never evidence).
3. **Scope fence CONFIRMED at ruling time** (core S1-S6 + signed
   rulings only), then extended by the same-day Phase B authorization
   [human mail #56 to agent-a]: Skills ladder S7-S11 now in scope under
   `qacompanion/skills/`; core stays deterministic and LLM-free; S12+
   stays out until Phase B ships and is signed.

Gated bump 4->5 [this cycle]: freshness gate run firsthand at HEAD
21930c4 before any edit - `git status --porcelain` EMPTY, `python -m
unittest` Ran 104 tests OK EXIT=0 - against an identical sitrep claim of
ROADMAP-dirty + FAIL(0.0s). Recorded via the record CLI with full text
re-passed (bump overwrites excerpt/diag/last_seen); excerpt anchored
"5th recorded occurrence since 2026-08-26T07:22Z".

Cross-cycle raw tally [honest note, not silently merged]: agent-a's
ledger counts this delivery as the 13th consecutive phantom observed;
agent-b's counter stood at 11 as of TASK mail #57. Both tallies are
cited going forward as "N observed, M recorded" until reconciled; the
anchor-based times_seen remains the canonical spec counter.

Auto-bump cap semantics [IN FORCE from this entry]: while case #6's
REVIEW request is pending, occurrence bumps are HARD-STOPPED at the
current count (times_seen=4) no matter how many fresh phantom deliveries
arrive; the distinct-delivery gate only qualifies candidates and never
authorizes a bump by itself. Bumps resume solely on the human's
REVIEW/correction or explicit human override. Honest note: fd7ed36
applied the 3->4 bump while the cap was already being described as
"armed" - inconsistent wording at the time; the stop above is enforced
as worded from here forward, and agent-b's hold of 4->5 is correct
under these semantics.

Unit-wording rider (agent-b TASK #48): EXECUTED on the 4->5 touch above.
The two units are now unambiguous in case #6's diagnosis text itself:
times_seen = recorded bumps since anchor 2026-08-26T07:22Z (spec counter,
format frozen, NO backfill of pre-anchor cycles); raw cross-cycle
deliveries are a separate tally cited in summaries as "N observed,
M recorded".

## TASK #18 seed-provenance rider [CLOSED 2026-08-26 - already satisfied]

Per human mail #54 (relayed verbatim in agent-b TASK mail #57; silence
is the only wrong answer): the rider was ALREADY SATISFIED at 2045575 -
completed-before-board. Chosen disposition: neither re-land nor drop.
Verified firsthand 2026-08-26: `tests/test_seeds.py:1` carries the
provenance label verbatim ("mail #18 rider, landed in 2045575"), pinning
the frozen seed artifacts to docs/SEEDING.md digests. Provenance:
digest + mail #54.

## D-0007 S7 auto-capture policy decisions [2026-08-26, slice landing]

Decisions made while implementing S7 (`qa run -- <cmd>`), all binding on
future skills and recorded here because ROADMAP's exit criteria left
them open (reviewer rider #3 in mail #61 demanded an explicit stated
hang policy):

- Hang policy: NO timeout is enforced. A hung child hangs the wrapper,
  exactly like running the command by hand; qa run never invents a kill
  signal the user did not ask for. Stated in `run --help` epilog and
  module docstring, not silently defaulted.
- Output policy: the child runs with stdout+stderr merged into one pipe;
  qacompanion echoes the merged text verbatim to ITS OWN stderr. Nothing
  is swallowed (case #1 / FAIL(0.0s) lesson); stdout piping of the
  wrapper stays noise-free. Consequence, accepted: child stdout lines
  appear on stderr while wrapped.
- Parse rule: signature error part = LAST non-empty line of merged
  output (generic-command adaptation of "first error line"; CLI failure
  summaries live at the tail). Excerpt = merged-output tail bounded to
  4000 chars, `[truncated] `-prefixed when cut.
- Diagnosis honesty: auto-recorded cases carry a placeholder diagnosis
  naming exit code + command + "pending teacher review" - never a
  fabricated diagnosis. confirmed_by = "auto-capture".
- Recursion guard: children inherit QA_RUN_ACTIVE=1; a `qa run` that
  starts under it refuses with exit 1 before executing anything.
- Store-failure policy: a corrupt/unreadable store must not mask the
  child's result - warning goes to stderr and the CHILD's exit code is
  returned unchanged.
- Provenance: Phase B authorization (human mail #56) + reviewer
  green-light with binding riders (mail #61, criteria 6-8).

Provenance: digest + mail #56 + mail #61.
