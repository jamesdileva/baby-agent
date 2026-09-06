# S55 Bake-off Results — defect-fix benchmark (2026-09-05)

Instrument: the S48 harness (identical fixture, goal, verifier gate;
metrics recorded per run). Machine: CPU-only, 17 GB RAM.
OLLAMA_TIMEOUT=180–300 for the slow runs; OLLAMA_THINK=false for qwen3.

| model | result | turns | tool calls | commands run | tool failures | verifications failed | duration | verdict |
|---|---|---|---|---|---|---|---|---|
| qwen2.5-coder:1.5b | FAIL | 11 | 3 | 0 | 1 | 0 | 85s | faked evidence (log files); never ran tests |
| llama3.1:8b | FAIL | 3 | 6 | 1 | 5 | 0 | 397s | too slow on CPU; tool-call format errors |
| qwen2.5-coder:3b | FAIL | 25 | 107 | 30 | 69 | 17 | 366s | best protocol driver; looped without fixing |
| qwen3:4b (think on) | FAIL | 1 | 0 | 0 | 0 | 0 | 180s | first turn exceeded 180s: <think> blocks |
| qwen3:4b (think off) | FAIL | 5 | 5 | 3 | 3 | 0 | 472s | used tools, then per-turn timeouts |
| gemini-flash-latest | FAIL | 5 | 0 | 0 | 0 | 4 | 50s | 503 high-demand (free tier) |
| gemini-3.1-flash-lite | FAIL | 25 | 0 | 0 | 0 | 24 | 311s | never emitted a tool call; claimed done 24x |

## The finding that matters

**The gap is the protocol, not the brains.** Every tested model — local
and cloud, 1.5B to 8B — failed to drive the taught textual
`[TOOL: name(arg="value")]` protocol reliably to completion. The
pattern differs by model (faking evidence, looping, ignoring the
protocol) but the failure class is identical: a bespoke text protocol
requires a precision that even strong instruction-followers don't
consistently deliver.

**Consequence for the roadmap:** routing cannot fix this. The unlock is
**native tool-calling adapters** — Ollama's structured tool API and
Gemini's native function calling both exist and both are stronger than
prompt-taught textual protocols. The textual protocol remains as the
1.5B-era compatibility shim it always was.

## Follow-ups filed

1. Native tool-calling adapters (Ollama + Gemini) — the real unlock;
   textual protocol stays as fallback.
2. ModelRouter (slice 3): deterministic role routing (brain / vision /
   escalation) once adapters land — the human's role sketch stands:
   local coder brain, qwen2.5vl vision, free-Gemini escalation.
3. qwen3:4b remains the most promising LOCAL candidate (used tools,
   ran commands, honest failures) once native tool calling removes the
   protocol burden — and its thinking mode is switchable via
   OLLAMA_THINK=false (added this sprint).
4. Gemini 503 retry-with-backoff added this sprint; free tier remains
   demand-gated in evening windows.


## Native tool-calling retest (slice 4, same day)

DECISIONS 2026-09-05 landed native adapters (Ollama /api/chat with
tools; Gemini function_declarations). Retest results:

| model | mode | result | verdict |
|---|---|---|---|
| qwen2.5-coder:3b | native | FAIL — 0 tool calls in 25 iterations | qwen2.5-coder models do not support Ollama native tools (template lacks tool support); params silently ignored |
| qwen3:4b (think off, num_ctx 8192) | native | FAIL — 0 tool calls, 300s turn timeout at 22 min | schemas + prompt overwhelm CPU 4B; latency disqualifies on this box |
| gemini-3.1-flash-lite | NATIVE | **PASS — success in 6 iterations, 144s, unit-tests=pass, 0 failures, 0 interventions** | **first honest benchmark pass in project history** |

Also fixed en route: Gemini-safe schema coercion (arrays need items,
objects need properties — the registry's minimal schemas 400'd),
GEMINI_TIMEOUT env (thinking + big catalogs exceed 60s reads), 503
retry-with-backoff.

## Updated conclusion

The S48 goal is closed by the free cloud brain: with native function
calling, the harness + loop + tools + verifier chain passes end-to-end
autonomously. The local models' gap is real but now precisely bounded:
protocol handling (solved by native adapters) and CPU latency (not
solvable in software). The human's role sketch is validated and
 sharpened:

```text
brain (real tasks):    gemini-3.1-flash-lite (free, native tools)  144s PASS
brain (free-local):    qwen3:4b / qwen2.5-coder:3b — honest attempts,
                       not yet benchmark-competent on CPU
vision:                qwen2.5vl:3b (local) or Gemini multimodal
escalation/stuck:      the same Gemini brain IS the escalation tier
```

Follow-up: qwen3:4b native worth revisiting on GPU hardware; qwen3
tool-call parsing (0 calls in 6 native iterations) may also improve
with a smaller per-family tool catalog.


## Slice-5 head-to-head (lean 12-tool catalog, best config per model)

Slice 5 changes: native-only prompting (no textual/native conflict),
lean 12-tool catalog, num_ctx 8192.

| model | mode | result | turns | tool calls | tool failures | duration | verdict |
|---|---|---|---|---|---|---|---|
| qwen3:4b | native + lean | FAIL — turn timeout at 300s | 1 | 0 | 0 | 300s | even lean, 8192-ctx prefill + catalog is minutes/turn on CPU |
| qwen2.5-coder:3b | textual + lean | FAIL — 24 rejections | 7 | 8 | 6 | 590s | timeout mid-run; protocol OK, solving absent |
| phi4-mini | native + lean | FAIL — 24 rejections | 25 | 0 | 0 | 363s | emits SCHEMA as arguments (echoes the JSON spec, not values) |
| granite3.3:2b | native + lean | FAIL — 14 rejections | 25 | 8 | 7 | 1224s | calls tools but wrong ones/args; 20 min wall |

## Final S55 conclusion

All four local candidates fail the benchmark with every configuration
tried (textual, native, lean, full catalog, think on/off, num_ctx
2048/8192). The isolated probes prove the plumbing is correct — models
that support Ollama native tools DO emit valid calls — but completing
a multi-step defect-fix task requires sustained multi-turn reasoning
that no 2–4B model on this CPU delivers within practical latency.
phi4-mini additionally exposes a real adapter finding: it echoes the
parameter SCHEMA as arguments (a model/template quirk the harness
honestly recorded).

The passing brain remains **gemini-3.1-flash-lite via native function
calling** (144s, verified). Local candidates are revisited on GPU
hardware or with a distill baby-agent:ep1 (S63+), whose training data
(S50 corpus + S55 trajectories) specifically teaches the tool protocol
that general small models struggle with.
