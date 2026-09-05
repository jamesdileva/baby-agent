# S49 — QA Brain Integration: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S49. Builds on S31–S48. One slice, stdlib only, no CLI changes.

## Overview

The architecture payoff: when a command fails, the agent's accumulated
QA intelligence is supplied to the model AUTOMATICALLY — before its
next action. Failure path: `CommandResult → failure signature → case
lookup → known: historical diagnosis injected; unknown: memory fallback
(experiences/docs/journal via S47's MemoryLayer) or honest silence`.

**Recording stays out of scope (deliberate):** the repo's rule is no
case auto-creation without confirmation (case-#10 lore) — S49 is a
read-only brain. Writing new cases from agent sessions belongs to S50.

## Module layout

```text
qacompanion/agent/qa_brain.py     # QABrain + signature derivation
qacompanion/agent/loop.py         # additive qa_brain param + injection
tests/test_agent_qa_brain.py
```

## QABrain

```text
derive_signature(call_name, output_text) -> canonical signature
    (signatures.normalize + canonical; test_name = tool call name,
     first_error_line = first non-empty line of error+output)

QABrain(cases_path=None, memory_layer=None)
    .advise(result: ToolResult) -> dict | None
        only for failed results; layered lookup:
        1. exact case-signature match (lookup.select)
        2. keyword case match   (bridge._match_cases, error-line terms)
        3. memory fallback      (MemoryLayer.search, source-labeled)
        4. nothing found        -> None (honest silence)
    advice dict: {source: "case"|"memory", case_id?, signature?,
                  diagnosis, times_seen?, score?}
```

A corrupt/missing case store degrades to the memory layer; a failing
memory layer degrades to silence — the loop must never crash on advice.

## Loop wiring (additive)

`AgentLoop(qa_brain=None)`: after a FAILED tool result's observation
message, the brain advises; a match appends one `system`-role message
carrying `{"qa_memory": advice}` so the model sees the historical
diagnosis before its next turn, and a `memory_advice` event is emitted
(S39 vocabulary, additive). No match → no message. Recording cases is
NOT done here (S50).

## Testing strategy (tests/test_agent_qa_brain.py)

- derive_signature: stable/normalized (paths, case, whitespace).
- advise layers with real fixtures: seeded case (CaseStore) matched
  exactly; keyword match on a differently-phrased case; memory fallback
  (experience fixture); total miss → None; corrupt store → memory
  fallback still works.
- Loop integration (hermetic, sys.executable): seed a case for a
  ZeroDivisionError command; scripted model runs the failing command →
  the NEXT provider request contains a qa_memory message with the
  historical diagnosis; a no-match run injects nothing; successful
  commands never trigger advice.

Expected suite growth: 1293 → ~1305 OK.

## Exit criteria (from ROADMAP-agentlite.md §S49)

Seed a known case, reproduce the failure, and the historical resolution
is supplied to the model before its next action. Full suite green;
preflight clean.
