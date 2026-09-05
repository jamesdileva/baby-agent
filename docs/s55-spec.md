# S55 — Model Routing & Bake-Off: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S55 (including the 2026-09-05 agenda notes). Builds on S31–S52. Slices
within the sprint; each lands green.

## The measured problem (S48 live data)

```text
qwen2.5-coder:1.5b   ~5s/turn, but UNRELIABLE: never ran tests,
                     faked evidence, 7 premature-done claims
llama3.1:8b          ~130s/turn on CPU: 5 tool-call errors, per-request
                     timeouts even at 180s
```

The loop needs a brain between those: strong enough to follow the
textual tool protocol honestly, small enough for CPU latency.

## Research findings (2026-09-05, cited in the worklog)

- **Qwen3-4B** — community + benchmark favorite in the 3–4B class
  ("unusually strong tool-calling priors", best small base model in
  Distill Labs' 12-model benchmark). Primary candidate.
  Integration note: Qwen3 emits <think> blocks by default — the loop
  tolerates them (tool-line parser is line-based) but `/no_think` in
  the system prompt keeps latency down; bake-off measures both.
- **Phi-4-mini (3.8B)** — Microsoft's edge model, documented Ollama
  function calling. Second candidate.
- **qwen2.5-coder:3b** — same family as our default; measures whether
  the coder fine-tune or the newer generation matters more.
- Excluded: 30B-class MoE (machine has 17 GB RAM), 7–8B (measured too
  slow on CPU).

**Bake-off field**: existing controls qwen2.5-coder:1.5b +
llama3.1:8b, challengers qwen3:4b + qwen2.5-coder:3b. Instrument: the
S48 defect-fix benchmark, one run per model, same fixture, metrics
from the harness (success, iterations, tool_calls, commands_run,
tool_failures, duration, termination_reason).

## Slice 1 — infrastructure fixes (landed)

- **Configurable bridge timeout**: `OLLAMA_TIMEOUT` env (seconds,
  call-time resolution) replaces the hardcoded 60s.
- **GeminiModelProvider** (agent loop backend, PLAIN mode — the
  no-billing ruling).

## Slice 2 — the bake-off (landed; results in docs/bakeoff-s55.md)

Seven models, zero passes. The finding that reframes the roadmap:
**the gap is the taught textual protocol, not the brains** — models
fake evidence, loop, or ignore the protocol entirely.

## Slice 4 — native tool-calling adapters (the unlock)

The bake-off's conclusion made primary. Decision (DECISIONS
2026-09-05): **native tool calling becomes the primary contract when a
request declares tools; the textual protocol demotes to the
compatibility shim for tool-less requests and the 1.5B-era fallback.**

- **OllamaProvider**: when `request.tools` is non-empty, call
  `/api/chat` with `tools: [{type: "function", function: {name,
  description, parameters}}]` built from the ToolDefinitions; map
  `message.tool_calls[].function` → structured ToolCalls. Empty tools
  → the legacy `/api/generate` textual path, unchanged. OLLAMA_THINK
  applies to both endpoints.
- **GeminiModelProvider**: when `request.tools` is non-empty, send
  `tools: [{function_declarations: [...]}]`; map `functionCall` parts
  → ToolCalls. Text-only requests keep the plain path.
- Tool results feed back through the existing tool-role messages
  (S37); no loop changes needed.
- The 503 retry/backoff and OLLAMA_TIMEOUT apply to both adapters.

## Slice 3 — the router (after the retest)

```text
ModelRouter(policy) with rules mapping task shape -> provider
    default brain:     retest winner (local, native tools)
    vision:            qwen2.5vl:3b (local, already pulled) or free Gemini
    stuck/escalation:  free Gemini plain mode (quota-limited helper)
```

Human role sketch to validate: coder for brain, qwen-vl for vision,
Gemini for escalation. The router is deterministic under policy and
mock-tested per the roadmap verification; the S48 benchmark re-runs
under the chosen routing.

## Exit criteria

Native adapters landed with hermetic tests; **the bake-off table
re-run on native tool calling** (docs/bakeoff-s55.md updated with a
native section); a model that honestly passes the defect-fix benchmark
would close the S48 goal. Full suite green; preflight clean.


## Slice 5 — native-only prompting + lean catalog + head-to-head

The bake-off's diagnosis (catalog weight + prompt conflict) becomes
engineering:

1. **Native-only prompting**: `build_system_prompt(..., native_tools)`
   — when the provider is native-capable (`provider.native_tools`),
   the textual `[TOOL: ...]` protocol is NOT taught; the catalog is
   listed, the native tools are attached, done. Textual providers keep
   the protocol teaching. Providers declare capability:
   `OllamaProvider(native_tools=True)`, `GeminiModelProvider
   .native_tools = True`; unknown providers default False (textual).
2. **Lean catalog**: the loop accepts `tool_catalog` (a name filter) —
   the model sees only those ToolDefinitions in request.tools AND the
   system-prompt listing; the registry still holds everything (the
   harness can execute tools the model wasn't offered). The benchmark
   offers the LEAN_CODING_TOOLS set (7 filesystem + 5 execution = 12
   tools) instead of all 22 — halving catalog weight for CPU models.

## Head-to-head (four local models, best config each)

```text
qwen3:4b            native + native-prompt + lean catalog
qwen2.5-coder:3b    TEXTUAL (no Ollama native tool support) + lean
phi4-mini (3.8B)    native + native-prompt + lean (edge-focused = fast CPU)
granite3.3:2b       native attempt; fallback textual if 0 calls
```

Success bar: honest tool usage + the defect fixed + unit-tests pass.
Everything is recorded either way.
