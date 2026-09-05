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

## Slice 1 — infrastructure fixes (this commit)

- **Configurable bridge timeout**: `OLLAMA_TIMEOUT` env (seconds,
  default 60) replaces the hardcoded 60s in `ollama_bridge._http_post`
  callers — the measured 8B kill at 180s monkey-patch becomes
  configuration.
- **GeminiModelProvider** (agent loop backend, PLAIN mode — the
  no-billing ruling): the loop accepts any provider; the free cloud
  model becomes the escalation/research brain candidate the human
  sketched. Distinct from websearch's GeminiSearchProvider (that one
  searches; this one generates).

## Slice 2 — the bake-off (needs model pulls)

One benchmark run per model; results table committed to
docs/bakeoff-s55.md with honest per-metric comparison. Success bar:
a model that completes the defect-fix benchmark with tests actually
passing in reasonable CPU time — the 1.5B bar is "any honest tool
usage at all".

## Slice 3 — the router (deterministic policy)

```text
ModelRouter(policy) with rules mapping task shape -> provider
    default brain:     bake-off winner (local)
    vision:            qwen2.5vl:3b (local, already pulled) or free Gemini
    stuck/escalation:  free Gemini plain mode (quota-limited helper)
```

Human role sketch to validate: coder for brain, qwen-vl for vision,
Gemini for escalation. The router is deterministic under policy and
mock-tested per the roadmap verification; the S48 benchmark re-runs
under the chosen routing.

## Exit criteria

A committed comparison table; a routing policy wired into the loop;
the dashboard's model field honoring the router. Full suite green;
preflight clean.
