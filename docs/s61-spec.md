# S61 — Multi-Agent Teacher Sessions: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S61. Builds on S31–S60 (TeacherProvider ABC from S59). One slice,
stdlib only, no CLI changes.

## Overview

Structured multi-teacher sessions — debates, independent solutions,
critique chains — to generate higher-quality learning examples. The
goal is NOT a permanent swarm: sessions are bounded, roles are
configurable, consensus is verified, and diversity is deliberately
varied.

**Core principle (spec-pinned): consensus ≠ correctness.** Three
teachers agreeing can still be wrong — every claimed outcome passes
the S41 verification gate, and DISAGREEMENTS are recorded as
first-class data (they're the most valuable training examples).

## Module layout

```text
qacompanion/agent/multi_agent.py    # roles, debate modes, session runner
tests/test_agent_multi_agent.py
```

## Session shapes

```text
independent    N teachers solve the same task; verifier picks/validates
debate         teacher A proposes -> teacher B critiques -> A revises
critique_chain sequential review by successive roles
specialist     primary agent + role reviewers (security, performance,
               testing) -> final revision
```

## Teacher roles (configurable per session)

```text
architect, coder, debugger, reviewer, security_reviewer,
performance_reviewer, ui_designer, researcher, tester, verifier,
project_manager
```

## Session contract

```text
session_id, task_name, mode (independent | debate | critique_chain |
specialist), participants [{name, provider, role}], teacher messages
per participant, proposals, critiques, votes, verified outcome
(S41 gate), disagreements [{between, positions}], final_solution,
trajectory_quality, consensus_reached (bool — recorded, NOT equated
with correct), started_at
```

## Diversity tracking (per session + aggregate)

model/provider/temperature/role variation is RECORDED per participant;
the session report aggregates how many distinct models, roles, and
approaches participated — the measurable form of "avoid 1 teacher, 1
style, 1 architecture repeated thousands of times".

## Verification

- The session's final solution runs through the S41 gate — consensus
  never substitutes for evidence.
- Independent mode: each teacher's solution is verified separately;
  results compared; agreements AND disagreements recorded.
- Debate/critique: the revised solution is verified.

## Implementation (honest scope)

Teachers are wrapped `TeacherProvider` instances (S59 ABC); the
multi-agent runner orchestrates them in the four session shapes and
records the full contract. Deterministic scripted providers cover the
suite hermetically; real multi-teacher runs compose the S59 lab for
the curation pipeline (S62).

## Testing strategy (tests/test_agent_multi_agent.py)

- Session contract completeness per mode; participants recorded with
  roles; disagreements captured when teachers diverge; votes tallied.
- Independent mode: distinct solutions compared; verifier adjudicates;
  consensus recorded but NOT equated with verified (a unanimous-wrong
  scripted panel must still FAIL the gate — the core principle).
- Debate mode: proposal → critique → revision flow recorded.
- Diversity report: distinct models/roles counted.
- Registry unchanged (orchestration is harness-level).

Expected suite growth: 1461 → ~1475 OK.

## Exit criteria (from ROADMAP-agentlite.md §S61)

Multiple independent teachers solve the same task; disagreements are
recorded; a verifier can determine which claims are correct; incorrect
consensus can be rejected; diversity is measurable. Full suite green;
preflight clean.
