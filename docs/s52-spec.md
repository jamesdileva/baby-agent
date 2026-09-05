# S52 — Desktop UI: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S52. Builds on S31–S51. One slice.

## Stack decision (documented deviation)

The roadmap names Electron + React + TypeScript + Vite over a Python
local API. This sprint delivers the **API-first core + the browser UI**:

1. `qacompanion/agent/server.py` — the local API layer in **stdlib**
   (`ThreadingHTTPServer`): REST + Server-Sent Events over the S39
   event stream. This is the "FastAPI or local IPC" contract, without a
   dependency.
2. `app/` — a **Vite + React + TypeScript** dashboard consuming that API
   (goal input → start → live event feed → report).
3. **The Electron shell is deferred** to a packaging follow-up: the
   browser IS the desktop shell for now (the dashboard is a normal web
   app pointed at the localhost API). Deferral noted in the roadmap;
   nothing in the API contract changes when the shell lands.

Rationale: the API contract is the durable, testable part (full Python
test coverage, hermetic); Electron packaging is heavy binary
downloading with no suite-testable path. UI-first in the browser keeps
every discipline intact while delivering the S52 user journey today.

## Security posture

- The server binds **127.0.0.1 only** — the runtime is never exposed to
  the network (consistent with health_check's localhost rule).
- Single-user local assumption documented; no auth on loopback.
- The UI's start-session endpoint runs the S37 loop with the S38 engine
  policy — the same permission gates as every other path; the UI adds
  convenience, not authority.

## The API (v1)

```text
GET  /api/health                     -> {status, version}
POST /api/session/start              {goal, workspace, model?} -> {session_id}
GET  /api/sessions                   -> [{session_id, goal, state, ...}]
GET  /api/session/{id}               -> full session state + report when done
POST /api/session/{id}/stop          -> cancels via the S38-gated cancel path
GET  /api/events?session_id={id}     -> text/event-stream (S39 events)
GET  /api/skills                     -> skill library listing
GET  /api/memory?query=...           -> MemoryLayer unified search
GET  /api/environment                -> environment summary
```

- Sessions run in background threads on a coding registry (the S48
  coding families + skills) inside a temp or user-specified workspace;
  `intervention_count` semantics preserved (the UI can only stop, never
  steer mid-run — the S52 spec's pause/stop controls map to the S38
  cancel path).
- SSE: per-session subscriber queue; stream ends when the session is
  terminal and the queue is drained. Heartbeats keep connections warm.
- Provider selection: default OllamaProvider(model from request);
  injectable factory for tests (FakeModelProvider).

## The dashboard (app/)

Vite + React + TypeScript, no component library, hand-rolled styles:

- Goal input + workspace path + model field + Start/Stop.
- Live event feed (SSE): state changes, tool calls, file changes,
  verification attempts, advice — the S39 narration.
- Session summary (report metrics) when terminal.
- Sessions list from the server.

Verification on the UI side: `npm run build` (tsc + vite build) must
pass; the Python suite stays the primary gate (node is not a CI
dependency).

## Testing strategy (tests/test_agent_server.py)

All hermetic — FakeModelProvider factory, port 0, real HTTP over
127.0.0.1 via urllib:

- health; session start (background run completes with the fake
  provider); sessions list; session detail with report; stop endpoint.
- SSE: subscribe and receive session_started + completion events;
  stream terminates on session end.
- Security: server binds loopback (construct with host=127.0.0.1; the
  test asserts the socket is loopback-bound).
- experience recording still happens (S50) for server-run sessions.

Expected suite growth: 1332 → ~1345 OK.

## Exit criteria (from ROADMAP-agentlite.md §S52)

User can open the dashboard, enter a goal, start the agent, watch live
activity, stop it, and read the summary — without the terminal (proven
by the API tests + built dashboard; the live browser walkthrough is a
manual smoke). Electron shell deferred with the contract unchanged.
Full suite green; preflight clean.
