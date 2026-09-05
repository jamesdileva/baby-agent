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
