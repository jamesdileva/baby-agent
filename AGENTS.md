# AGENTS.md — baby-agent

Working conventions for any agent (or human) working in this repo.

## Mission

Build and maintain `qacompanion`: a stdlib-only Python CLI that accumulates a
case base of test failures and their diagnoses. The spec of record is
[docs/spec.md](docs/spec.md) — read it fully before the first commit. The spec
is frozen for v1; propose amendments via DECISION-style writeups before
touching it.

## Standing discipline

1. **Slices, not waves.** One committable slice per cycle: implement, test,
   commit, clean tree before responding.
2. **Tests green or it didn't happen.** `python -m unittest` (or the agreed
   runner) exits 0 before every commit. A red suite is never committed.
3. **Honesty over optics.** If accuracy drops or a change regresses something,
   say so in the cycle summary. Hiding regressions is the cardinal sin of a
   QA tool.
4. **Stdlib only.** No third-party dependencies in v1. No network calls.
5. **Spec is law.** Behavior questions resolve to docs/spec.md. Gaps get
   documented as proposed amendments, not silently filled.

## Verification culture

- Every bug fixed gets a regression test named after its failure mode.
- `accuracy` must be re-runnable at any time; a change that lowers holdout
  accuracy must be justified in the commit message or reverted.
- Fixture-based verification is necessary but not sufficient: exercise real
  failure output when touching capture paths.

## Review protocol

- Reviewer verifies firsthand (run the tests, read the diff) before approving.
- Provenance matters: cite the task/mail/issue that authorized a segment.
- Disputes escalate to the human with evidence, not assertion.

## Human escalation protocol

- Any question, ruling request, or blocked decision that needs the human
  MUST be filed as a QUESTION or TASK mail addressed to `human` — AND
  recorded in docs/DECISIONS.md. A question that lives only in a document
  is invisible to the human and counts as unanswered.
- Mail first, document second. The mail pings; the doc preserves.
- When the human replies by mail, sign the outcome into DECISIONS.md the
  same cycle.

### Case confirmation authority

Routine case confirmations may be signed `confirmed_by` firsthand by either
parent when ALL hold: (a) firsthand reproduction evidence is cited,
(b) the diagnosis introduces no spec.md changes,
(c) both agents concur.

New standing rules derived from lessons ALSO do not require human approval —
the parents hold full teaching authority inside this repo. Document every new
rule in DECISIONS.md (audit trail, not permission slip).

Escalate to `human` teacher review ONLY when: the frozen spec
(docs/spec.md) needs amending, agents dispute and cannot resolve a decision
between themselves, or a problem recurs 3+ times despite agreed fixes.
Everything else is yours to decide — that is what being the teachers means.

## Cycle-end ritual (integration with this tool)

Every working cycle in any repo where qacompanion is deployed:

1. If tests failed: `record` each failure, attempt diagnoses, request teacher
   REVIEW of those diagnoses.
2. Run `qa preflight` before claiming anything is "done."
3. If `cases.jsonl` changed: commit it alongside the slice.
4. Report lookup hits in the cycle summary ("recognized: FAIL(0.0s), case #3")
   so the colony sees the tool earning its keep.

## Worklog

Dated history of landed slices, newest first. Standing cycle ritual
(DECISIONS 2026-09-04): **plan + scope → implement → tests green →
commit + push → worklog entry.**

- 2026-09-04 — **S31 Agent Foundation** — `qacompanion/agent/` subpackage
  (contracts.py / providers.py / session.py): ModelProvider abstraction with
  FakeModelProvider (deterministic test backbone) + OllamaProvider (wraps S26
  bridge, normalizes textual [TOOL: ...] output into structured ToolCalls),
  AgentSession state machine (10 states, terminal states final), AgentConfig
  limits, knowledge-tool ToolDefinitions. `qa ask` unchanged. Suite 828 →
  891 OK (hermetic; live Ollama opt-in via QA_OLLAMA_LIVE=1). Spec:
  docs/s31-spec.md. Roadmap: docs/ROADMAP-agentlite.md §S31.
- 2026-09-04 — **Roadmap consolidation + case #10 fix** — Agent-Lite
  roadmap consolidated into docs/ROADMAP-agentlite.md (S31–S65+), DECISIONS
  rulings filed (renumbering, constraints amendment), audit.md superseded;
  fixed pre-existing red test: no-Ollama fallback now surfaces digest
  matches, digest ask test made hermetic (828 OK).
