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
