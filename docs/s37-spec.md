# S37 — Agent Loop: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S37. Builds on S31–S36. One slice, stdlib only, no CLI changes.

## Overview

The first actual autonomous reasoning loop:

```text
GOAL -> CONTEXT -> MODEL -> TOOL CALL -> VALIDATE/EXECUTE (S32 pipeline)
     -> OBSERVATION -> MODEL -> ... -> VERIFY -> (FAIL -> RECOVER -> VERIFY)
     -> COMPLETE
```

The runtime has **no hard-coded knowledge of any task** — everything
task-specific comes from the model (real or the deterministic
FakeModelProvider) and the tool registry built in S31–S36.

## Module layout

```text
qacompanion/agent/loop.py          # AgentLoop + prompt builder
qacompanion/agent/session.py       # + verification_results field (additive)
tests/test_agent_loop.py
```

## Loop semantics (pinned)

- **Context**: `[system, user(goal)]` then the full accumulated history.
  The system prompt renders the registry's tool names + descriptions
  (S31 providers do not prompt-engineer tools; the loop owns it).
- **Tool turn**: every response tool call goes through the S32 pipeline
  (`registry.execute(...)` with workspace, permission policy,
  cancel_event). Each call and result is appended to the session
  (`tool_calls` / `observations`); each result is fed back to the model as
  a `tool`-role message containing the structured JSON of the ToolResult —
  **permission denials, unknown tools, and timeouts are observations, not
  exceptions**: the model sees the denial and adapts.
- **Final answer**: a response with no tool calls is the final answer.
  Empty-text responses (no calls, no text) are recorded as errors and the
  loop continues (bounded by the iteration limit).
- **Verification**: after a final answer the session enters VERIFYING and
  the optional `verifier` callable runs (signature `verify(session) ->
  (ok, detail)`; default None = accept). Failure enters RECOVERING, the
  verification failure is fed back as a user message, and the loop
  continues — the minimal FAIL → DIAGNOSE → FIX → VERIFY cycle. The real
  verification engine is S41; this seam is its preview.
- **Changed-file tracking** is metadata-driven: a ToolResult whose output
  parses as JSON containing a `path` key, emitted by a tool whose
  registered `side_effect_level` is a write level, appends the path to
  `session.files_changed` (no tool-name hard-coding in the loop).
- **Limits** (from AgentConfig): max_iterations → FAILED
  "max iterations reached (N)"; max_runtime_minutes → FAILED "max runtime
  exceeded". Exhaustion while verification keeps failing → FAILED
  "verification failed after N attempts".
- **Cancellation**: checked before each iteration and before each tool
  execution → CANCELLED, "cancelled by user".
- **Provider errors** (including FakeModelProvider script exhaustion) →
  FAILED "provider error: ...".
- Terminal states are final (S31 rule); WAITING_FOR_PERMISSION and PAUSED
  are reserved for S38/S45 and unreachable in S37.
- `session.verification_results` (new additive field) records every verify
  attempt `{ok, detail, at}`.

Termination reasons (constants): `goal completed`, `max iterations reached
(N)`, `max runtime exceeded`, `cancelled by user`, `provider error: ...`,
`verification failed after N attempts`.

## API

```text
AgentLoop(provider, registry, workspace, config=None, policy=None,
          cancel_event=None, verifier=None)
    .run(goal, session=None) -> AgentSession   # terminal state guaranteed
build_system_prompt(tools) -> str
```

## Testing strategy (tests/test_agent_loop.py)

All deterministic — FakeModelProvider scripts and test-local providers;
real workspace + FilesystemToolkit + ExecutionToolkit tools; hermetic
commands via sys.executable.

- **Roadmap verification sequence**: fake-model script write_file (with a
  deliberate error) → run_command (python executes it, fails) → read_file
  (the error) → edit_file (fix) → run_command (passes) → final answer —
  completes with state COMPLETED, calls/observations recorded,
  files_changed populated, final_result set.
- **Feedback proof**: a recording provider asserts the second request's
  messages contain the first tool's structured JSON result (path + sha256)
  — tool output provably fed back into the next model iteration.
- Iteration limit: always-calling provider → FAILED at exactly
  max_iterations.
- Verification: pass path (VERIFYING state observed by the verifier);
  fail-then-recover path (RECOVERING traversed, verification_results has
  one failure then one success, ends COMPLETED); exhaustion → "verification
  failed after N attempts".
- Cancellation via a tripwire tool that sets the cancel_event mid-run.
- Provider error → FAILED with reason; empty response → continues.
- Denial feedback: deny-all policy → model observes the structured denial,
  loop completes normally.
- Unknown tool → structured "unknown tool" observation, loop continues.
- Runtime deadline unit check; system prompt renders tool catalog.
- Session.verification_results round-trips (additive field).

Expected suite growth: 1062 → ~1100 OK.

## Exit criteria (from ROADMAP-agentlite.md §S37)

A deterministic fake model autonomously performs a multi-step coding task
with no hard-coded knowledge in the runtime; tool output provably feeds
back into the next model iteration; limits, cancellation, and failure
handling all terminate with reasons. Full suite green; preflight clean.
