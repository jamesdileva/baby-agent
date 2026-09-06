# S56 — Context Optimization: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S56. Builds on S31–S55. One slice, stdlib only, no CLI changes.

## Overview

Keep the agent effective as projects grow: never drown the model. The
loop currently replays the ENTIRE message history every turn — fine at
10 turns, fatal at 100 with full command outputs. S56 builds the
prioritized, budgeted context assembly and wires it into the loop
additively.

**Integration shape (additive):** `AgentLoop(context_builder=None)` —
when present, the loop calls it instead of replaying
`session.messages` wholesale. Absent → today's behavior, unchanged
(all existing tests keep passing unmodified).

## Module layout

```text
qacompanion/agent/context.py     # budget, reducers, builder, retriever
qacompanion/agent/loop.py        # + context_builder param (additive)
tests/test_agent_context.py
```

## Components

- **ContextBudget**: char-based budget with accounting; over-budget
  content is dropped lowest-priority-first, never partially cut
  mid-message (a truncated JSON observation is worse than a summarized
  one).
- **ObservationReducer / ToolResultSummarizer**: command-shaped results
  (embedded CommandResult JSON) reduce to exit_code + stdout head/tail
  (first 5 + last 10 lines) + stderr head; file reads reduce to head
  lines; anything older than the last K turns reduces to a one-line
  digest. The LATEST tool result is always kept verbatim (the model is
  about to reason over it).
- **MemoryRetriever**: wraps the S47 MemoryLayer — at run start, the
  goal is the query; top hits inject as a prioritized memory block
  (source-labeled). Deterministic keyword scoring, no embeddings.
- **ContextBuilder**: assembles the request message list under budget:
  system prompt (with catalog), goal, memory block, verification
  status, then history newest-first with reductions, lowest-priority
  dropped first. Priority order (spec §S56): goal > current failure >
  recent tool results > files changed > verification status > older
  history.

## The five questions a context must answer (the verification)

After assembly, a probe API (`ContextBuilder.debug_report()`) returns
what survived: goal present, latest tool result verbatim, budget used,
items dropped. The roadmap's verification — large synthetic session
stays within budget while retaining what the task needs — is asserted
on exactly those facts.

## Testing strategy (tests/test_agent_context.py)

- Budget: accounting, over-budget drop order, never-split guarantee.
- Reducers: command-output head/tail, dedupe of repeated outputs,
  latest-verbatim guarantee, old-turn one-line digests.
- Builder: prioritized assembly on a synthetic 100-turn session —
  goal survives, latest observation survives verbatim, budget held,
  dropped count reported.
- MemoryRetriever: injection from the S47 store, source labels, empty
  store degrades silently.
- Loop integration: context_builder wired; with a fake provider the
  request the model receives is under budget while retaining the
  latest tool result; without it, behavior is byte-identical to
  before (all existing loop tests unmodified).

Expected suite growth: 1396 → ~1415 OK.

## Exit criteria (from ROADMAP-agentlite.md §S56)

Large synthetic session: context within budget while retaining goal +
latest evidence. Loop integration additive. Full suite green;
preflight clean.
