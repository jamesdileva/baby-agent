# S38 — Permission & Safety: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S38. Builds on S31–S37. One slice, stdlib only, no CLI changes.

## Overview

The real permission engine: model-generated actions are untrusted
automation. Every tool call passes through validation → permission →
workspace policy → executor (S32 pipeline, unchanged order); S38 gives the
permission stage a rule engine, a confirmation flow, an audit trail — and
unlocks the git write verbs deferred in S36.

## Module layout

```text
qacompanion/agent/permissions.py    # PermissionPolicy (engine), PermissionDecision
qacompanion/agent/registry.py       # seam evolution: 3-arg check + confirmer param
qacompanion/agent/git_tools.py      # + git_add, git_commit (write verbs unlocked)
qacompanion/agent/loop.py           # + confirmer passthrough
tests/test_agent_permissions.py
```

## PermissionDecision + PermissionPolicy (engine)

```text
PermissionDecision (frozen)
    mode     ALLOW | ASK | DENY
    rule     which rule decided ("explicit:git_commit", "level:DESTRUCTIVE",
             "confirmation-required", "fallback", "confirmer-approved", ...)
    reason   human-readable detail

PermissionPolicy(rules=[], level_defaults=DEFAULT_LEVEL_DEFAULTS,
                 default_mode="ALLOW", name="policy")
    .decide(tool_name, arguments, tool=None) -> PermissionDecision
    .check(tool_name, arguments, tool=None) -> str      # S32 compat seam
    .decisions                                          # audit trail (list)
```

Resolution order — first match wins:

```text
1. explicit rules        PermissionRule(tool_glob, mode, reason,
                         args_contains=None)  — fnmatch on tool name;
                         args_contains={arg: substring} must all match
                         (e.g. run_command + command containing "npm install")
2. tool declaration      tool.requires_confirmation -> ASK
3. side-effect defaults  DEFAULT_LEVEL_DEFAULTS: READ_ONLY->ALLOW,
                         SAFE_WRITE->ALLOW, EXECUTION->ALLOW,
                         DESTRUCTIVE->DENY, EXTERNAL->ASK
4. fallback              default_mode (configurable; "DENY" = paranoid mode)
```

Every decision is appended to the policy's audit trail (tool, mode, rule,
reason, timestamp). The engine never executes anything and never touches
the filesystem — it only decides and records.

## Confirmation flow (the ASK story)

The S32 registry gains an additive `confirmer=None` parameter:

```text
policy says ASK
    -> confirmer is None   -> structured denial: "permission ASK requires
                              confirmation but no confirmer is available"
    -> confirmer(call, decision) truthy  -> proceed; audit records
                              "confirmer-approved"
    -> falsy               -> denial: "denied by confirmation"
```

The confirmer is a callable seam exactly like S37's verifier: scripted in
tests; a CLI prompt or UI dialog arrives with S52. `AgentLoop` gains a
`confirmer=` passthrough; the default (None) keeps today's safe behavior
(ASK = denial).

**Seam evolution (deliberate, our own code):** the S32 `check` seam becomes
`check(tool_name, arguments, tool=None)` so the engine can read
`side_effect_level` / `requires_confirmation`. The four test-local policies
in our suites are updated for the third parameter. Registry's internal
`ALLOW_ALL_POLICY` stays minimal; the engine lives in permissions.py and is
exported as the canonical `PermissionPolicy`.

## Git write verbs (deferred in S36, unlocked here)

- **git_add** `{path?}` (default ".") — SAFE_WRITE, no confirmation
  (staging is reversible); path resolved through PathPolicy; returns
  staged path + rc.
- **git_commit** `{message}` — SAFE_WRITE with `requires_confirmation=True`
  (the S36 posture: commits are ASK); runs `git commit -m <message>` with
  the repo's own identity (absent identity = structured git error); maps
  "nothing to commit" to an honest `{committed: false}` result; on success
  returns `{committed: true, hash, branch, message}`.

`agent_registry()` grows to 21 tools.

## Testing strategy

- Engine: rule resolution (exact, glob, first-match, args_contains),
  level defaults incl. DESTRUCTIVE→DENY and EXTERNAL→ASK on synthetic
  tools, requires_confirmation→ASK, fallback + DENY-by-default mode,
  decision audit trail, check() compat.
- Registry: ASK + confirmer approves/denies; ASK without confirmer;
  ALLOW path unaffected; audit contains confirmer outcomes.
- Loop: confirmer passthrough — scripted model calls git_commit;
  approved run commits; denied run comes back as a structured observation
  the model adapts to.
- Git verbs (real temp repos): add stages a modification; commit creates
  a commit (hash + clean tree); nothing-to-commit honest result; missing
  identity → structured git error; escape path → structured error.
- Existing suites updated for the 3-arg seam and registry count 19 → 21.

Expected suite growth: 1080 → ~1120 OK.

## Exit criteria (from ROADMAP-agentlite.md §S38)

Every tool call demonstrably passes validation → permission → workspace →
executor; ALLOW/ASK/DENY each tested; confirmation works (approve + deny +
absent); decisions are audited; destructive defaults are safe. Full suite
green; preflight clean.
