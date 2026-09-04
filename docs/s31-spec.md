# S31 — Agent Foundation: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S31. One slice: implement, tests green, commit, clean tree. Purely additive —
no existing module's behavior changes and no CLI surface is added.

## Overview

Introduce the core runtime contracts of the Agent-Lite track: a
provider-agnostic model interface, structured tool-call representations, and
a serializable agent session. After S31, nothing in the codebase talks to
Ollama through ad-hoc function calls in new code — the bridge stays as-is for
`qa ask`, and new consumers go through `ModelProvider`.

Non-goals (later sprints): tool registry/executor (S32), workspace (S33),
agent loop (S37), permissions (S38), events (S39). No GPU, no network beyond
the existing localhost Ollama calls, stdlib only.

## Module layout

New subpackage (growth path: S32 registry.py, S33 workspace.py, S37 loop.py,
S38 permissions.py, S39 events.py all land here):

```text
qacompanion/agent/
    __init__.py      # public re-exports only
    contracts.py     # dataclasses: ModelMessage, ModelRequest, ModelResponse,
                     # ToolDefinition, ToolCall, ToolResult + enums
    providers.py     # ModelProvider (ABC), FakeModelProvider, OllamaProvider,
                     # ProviderError
    session.py       # AgentState (enum), AgentConfig, AgentSession
tests/test_agent_core.py
```

## Contracts (contracts.py)

All stdlib `dataclass`; JSON-serialization via `to_dict()`/`from_dict()`
(plain dicts, no JSON strings inside — callers own encoding). Timestamps are
naive UTC ISO-8601 stamps per the D-0003 convention.

```text
ModelMessage(role, content)          role in {"system","user","assistant","tool"}
ModelRequest(messages, tools=None, model=None, temperature=None)
ModelResponse(text, tool_calls, finish_reason, usage, model)
    finish_reason in {"stop","tool_calls","error"}
    usage: {"prompt_tokens": int|None, "completion_tokens": int|None}
ToolDefinition(name, description, parameters_schema)   # JSON-schema-style dict
ToolCall(name, arguments, call_id=None)                # frozen (immutable)
ToolResult(call_name, call_id, ok, output, error=None, duration_ms=None)
```

`ToolCall` is immutable; `ToolResult` records outcomes (execution itself
arrives with the S32 executor — S31 only represents).

Helper: `knowledge_tool_definitions()` returning `ToolDefinition` instances
for the three existing tools (`case_search`, `doc_grep`, `journal_read`)
with schemas matching their S27 argument shapes — proving existing tools are
describable without the textual protocol.

## Providers (providers.py)

```text
ModelProvider (ABC)
    name -> str                      # "fake", "ollama", ...
    generate(request: ModelRequest) -> ModelResponse
```

- **FakeModelProvider**: constructed with a scripted list of responses
  (ModelResponse or ToolCall shortcuts); `generate()` pops in order;
  deterministic; raises `ProviderError("script exhausted")` when empty. This
  is the test backbone for S37's loop.
- **OllamaProvider**: wraps the existing S26 bridge internals
  (`_is_ollama_available`, `_ollama_generate`) — `qa ask` behavior is
  untouched. `generate()` flattens messages into a prompt (system first,
  then turns), calls the bridge, and normalizes the S27 textual tool
  protocol: any `[TOOL: name(args)]` lines in the model output are parsed
  via `tools.parse_tool_calls` into structured `ToolCall` objects, so
  downstream consumers never parse text. Unavailable/failed bridge calls
  raise `ProviderError` (structured error; never a bare exception).

Provider conformance is a shared test: both providers satisfy the same
interface contract suite (Ollama's via mocks).

## Session (session.py)

```text
AgentState (enum)
    CREATED, PLANNING, RUNNING, WAITING_FOR_PERMISSION, VERIFYING,
    RECOVERING, PAUSED, CANCELLED, COMPLETED, FAILED

AgentConfig
    max_iterations=25, command_timeout_seconds=120, max_runtime_minutes=30

AgentSession
    session_id (uuid4 hex), goal, workspace_root, state, iterations,
    messages[], tool_calls[], observations[], files_changed[], errors[],
    created_at, updated_at, final_result, termination_reason
    transition(new_state)   # any->any except out of terminal states
                            # (COMPLETED/CANCELLED/FAILED are final)
    to_dict() / from_dict() # JSONL-ready round-trip
```

No loop and no orchestration in S31 — the session is a verified data
structure with validated transitions that S37 will drive.

## CLI impact

None. No new subcommands, no changed output. `qa ask` is preserved exactly.

## Testing strategy (tests/test_agent_core.py)

- Contracts: construction, defaults, immutability of ToolCall, dict
  round-trips (including non-ASCII), enum membership.
- Session: valid transitions, terminal-state rejection, round-trip
  serialization, uuid uniqueness, timestamp conventions.
- Fake provider: scripted sequence in order, shortcut ToolCall form,
  exhaustion raises ProviderError.
- Ollama provider (all mocked, hermetic — DECISIONS 2026-09-04 rule):
  available path returns ModelResponse; textual `[TOOL: ...]` output becomes
  structured ToolCalls; bridge failure → ProviderError; unavailable →
  ProviderError. Bridge itself is NOT re-tested here (S26/S27 suites own it).
- Knowledge tool definitions: names/schemas match S27 argument shapes.
- One **opt-in** live test `test_ollama_live` guarded by env var
  `QA_OLLAMA_LIVE=1` (skipped by default, never a CI gate).

Expected suite growth: 828 → ~870 OK.

## Exit criteria (from ROADMAP-agentlite.md §S31)

- Fake provider deterministic; whole suite hermetic and green.
- Ollama reachable through `OllamaProvider` (live opt-in or manual).
- Provider failures are structured `ProviderError`s.
- Sessions transition validly and serialize.
- Tool calls represented without textual parsing downstream.
- `qa ask` behavior unchanged; full suite green; clean tree.
