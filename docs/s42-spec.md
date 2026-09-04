# S42 — Web Research: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S42. Builds on S31–S41. One slice, stdlib only, no CLI changes.

## Overview

Internet research capability through a provider abstraction. Web research
is a tool capability, not a property of one model — search results are
EVIDENCE with retained provenance, never truth.

## Provider choice (human discussion, recorded)

Human direction: Google — ideally "Google Search with AI mode" (Gemini
answering through Google Search). That is exactly the Gemini API's
**grounding with Google Search**: one AI Studio API key (free tier) gives
search-grounded answers with citation metadata. No key is required for
this sprint — everything ships hermetic; the live provider activates when
`GEMINI_API_KEY` is present in the environment.

## Module layout

```text
qacompanion/agent/websearch.py    # provider abstraction + tool
tests/test_agent_websearch.py
```

## Providers

```text
WebSearchProvider (ABC)
    .name -> str
    .search(query, max_sources=5) -> SearchResult

SearchResult (dataclass, to_dict/from_dict)
    query, sources: [{title, url, snippet}], provider, timestamp
    answered: str|None   (grounded-model answer text, when the provider
                          supplies one — the "AI mode" part)

FakeWebSearchProvider      scripted, deterministic (the test backbone)
GeminiSearchProvider       Google AI Studio / v1beta generateContent with
                           the google_search grounding tool; parses
                           candidates[0].content.parts text +
                           groundingMetadata.groundingChunks[].web
                           {uri, title} into sources. Model configurable
                           (GEMINI_MODEL env, default gemini-2.0-flash).
                           Defensive parsing: shape drift becomes
                           structured WebSearchError, never a crash.
```

Provider selection for the tool: explicit injection (tests) →
`GEMINI_API_KEY` env present → GeminiSearchProvider → none: the tool
returns a structured error naming the fix ("set GEMINI_API_KEY"). The
stdlib urllib POST carries the key; the key is never logged or echoed.

## The tool

`web_search` (category "research", **EXTERNAL** side effect — the first
EXTERNAL tool; the S38 engine's default posture EXTERNAL→ASK is the
constraints amendment made real: no network without permission).

```text
web_search {query, max_sources?} -> SearchResult JSON
```

Evidence principle: sources stay attached (url, title, snippet, provider,
timestamp); the caller (loop) injects the result into context; provenance
survives into session records.

## Safety

- No network in tests, ever: the fake provider covers the suite; Gemini
  unit tests mock urllib. A live smoke can run manually once a key exists
  (same status as the Ollama live test — opt-in, never a CI gate).
- Default permission posture is ASK (EXTERNAL) → no confirmer = denial.
  Autonomous web access requires an explicit policy + confirmer, exactly
  like commits.

## Testing strategy (tests/test_agent_websearch.py)

- SearchResult round trips; provider interface conformance.
- Fake provider: scripted sources, answer text, max_sources honored.
- Gemini provider (urllib mocked): parses grounded answer + grounding
  chunks into sources; HTTP error / malformed JSON / shape drift →
  structured WebSearchError; missing key → structured error before any
  request; key never appears in error strings.
- Tool: registration (EXTERNAL, requires_workspace False? — no; research
  is workspace-independent: requires_workspace stays False), through-
  registry run with fake provider, no-provider structured error.
- Policy e2e: default EXTERNAL→ASK denial without confirmer; approved
  with confirmer.
- agent_registry includes web_search.

Expected suite growth: 1161 → ~1180 OK.

## Exit criteria (from ROADMAP-agentlite.md §S42)

Controlled research tasks: request emitted, sources captured, citations
attached to findings, results injectable into context, web failures
degrade gracefully — all proven hermetically. Full suite green; preflight
clean.
