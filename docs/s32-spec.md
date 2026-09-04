# S32 — Tool Registry v2: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S32. Builds directly on the S31 contracts (`qacompanion/agent/`). One
slice, purely additive, no CLI changes, stdlib only.

## Overview

A first-class tool platform: any tool can be **registered, validated,
executed, observed, and audited** through one ordered pipeline. The three
existing knowledge tools (`case_search`, `doc_grep`, `journal_read`) are
preserved through the new registry — same handlers, structured arguments,
structured results.

Later sprints plug their subsystems into the pipeline's stages: Workspace
(S33) owns the workspace stage, Permissions (S38) the real policy engine,
Events (S39) the event stream, Execution (S35) real process management.
S32 ships the stages with safe defaults and proves each one's contract.

## Module layout

```text
qacompanion/agent/registry.py     # everything in this sprint
tests/test_agent_registry.py
```

## Registration model

`RegisteredTool` binds an S31 `ToolDefinition` (model-facing contract) to
its runtime metadata and handler:

```text
RegisteredTool
    definition          ToolDefinition (name, description, parameters_schema)
    handler             callable(**validated_arguments) -> str
    output_schema       dict (e.g. {"type": "string"} for knowledge tools)
    category            str (default "general")
    side_effect_level   READ_ONLY | SAFE_WRITE | EXECUTION | DESTRUCTIVE | EXTERNAL
    permission_level    str tag, default "default" (real semantics: S38)
    timeout_seconds     float > 0, default 30.0
    cancellable         bool, default False
    requires_workspace  bool, default False
    requires_confirmation bool, default False (enforcement: S38)
```

`ToolRegistry`: `register` (duplicate names rejected with `RegistryError`),
`get`, `names`, `describe` (JSON-serializable dicts — the audit/describe
surface), `schemas` (list of ToolDefinitions, consumable by any
ModelProvider). Constructor validation raises on bad metadata (non-callable
handler, unknown side_effect_level, non-positive timeout).

## Execution pipeline

`registry.execute(tool_call, policy=None, workspace=None, cancel_event=None,
audit=None) -> ToolResult` — never raises for model-facing outcomes; every
stage failure is a structured `ToolResult(ok=False, error=...)`:

```text
1. lookup        unknown name -> error "unknown tool '...'"
2. validation    strict mini-validator over parameters_schema (below)
3. permission    policy.check(tool_name, arguments) -> ALLOW | DENY | ASK
                 DENY -> "permission denied by policy"
                 ASK  -> "permission ASK requires confirmation flow (S38)"
4. workspace     requires_workspace and no workspace configured ->
                 "workspace required but not configured (S33)"
5. cancellation  cancel_event set -> cancelled=True (checked pre-dispatch)
6. execution     handler(**arguments) under timeout_seconds
                 (concurrent.futures; TimeoutError -> timed_out=True)
                 handler exception -> error "handler failed: ..."
                 non-string return coerced via str() (None -> "")
7. audit         audit(result) invoked for EVERY completed outcome,
                 including denials (exceptions propagate — caller's hook)
```

The mini-validator is documented, stdlib, and deliberately small: object
type, required keys, per-property primitive types (string / number /
integer / boolean / array / object), and rejection of argument keys not in
`properties` (typo protection) unless the schema sets
`additionalProperties: True`. Booleans are never valid integers/numbers.
Validator errors are one string per problem, joined into the result error.

`ToolResult` gains two optional flags — an additive, backward-compatible
extension of the S31 contract: `timed_out: bool = False`,
`cancelled: bool = False` (serialized in to_dict/from_dict).

## Knowledge tools through the registry

`default_knowledge_registry(cases_path=None, digest_path=None, ledger=None)`
registers the three S27 tools wired through `functools.partial` to the
optional store paths: category "knowledge", side_effect_level READ_ONLY,
permission_level "read", timeout 30s, output_schema `{"type": "string"}`.
Behavior is identical to calling `tools.py` handlers directly — the S27
suite remains the owner of their semantics.

## Scope notes (deliberate)

- Permission policy here is a minimal `PermissionPolicy.check` seam with an
  allow-all default; the real policy engine (per-tool/per-workspace/session
  rules, confirmation UX) is S38.
- Cancellation is a cooperative pre-dispatch check; mid-run cancellation of
  real processes arrives with S35.
- The workspace parameter is an opaque placeholder context; S33 replaces it
  with the real `Workspace` boundary.

## Testing strategy (tests/test_agent_registry.py)

- Validator: valid args; missing required; wrong type; bool-as-integer
  rejected; unknown argument key rejected; additionalProperties allowed;
  non-object arguments rejected.
- Registry: register/get/names/describe/schemas; duplicate rejection;
  invalid registrations rejected; describe() is JSON-serializable.
- Pipeline happy path: `case_search` through the registry against a seeded
  temp case file returns ok=True with the diagnosis in output and a
  duration_ms set.
- Every stage's structured failure: unknown tool; malformed arguments;
  permission DENY; permission ASK; workspace required; cancellation;
  timeout (sleeping handler, sub-second); handler exception; non-string
  return coercion.
- Audit: called once per outcome, including denials.
- ToolResult extension: round-trips with the new flags.
- Knowledge factory: three registrations; doc_grep and journal_read
  executed end-to-end against temp fixtures.

Expected suite growth: 891 → ~935 OK.

## Exit criteria (from ROADMAP-agentlite.md §S32)

- Valid calls execute; malformed arguments and unknown tools are rejected
  with structured errors.
- Permission denial, timeout, cancellation, and executor exceptions are all
  proven structured outcomes.
- Existing knowledge tools work through the new registry unchanged.
- Tool results have a consistent, serializable structure.
- Full suite green; clean tree; `qa preflight` pass.
