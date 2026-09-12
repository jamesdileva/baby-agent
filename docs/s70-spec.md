# S70 — Dashboard Operations (buttons for the loop)

Status: scoped 2026-09-12. The S68 loop commands (`qa gemini-drip`,
`qa verdict`) become buttons on the dashboard — deliberate,
human-initiated actions, never auto-fired (the S38 philosophy: opening
a page is looking, not doing; each click spends real quota or CPU and
gets pressed on purpose).

## Implement

### Server (`server.py`)

- `AgentServerApp` gains a **job model** mirroring the session pattern:
  `start_job(kind, runner)` → job id + background thread; jobs carry
  `{id, kind, status: running|done|failed, started_at, finished_at,
  summary}`. Failures land in the job's summary — visible, honest.
- **POST /api/drip** — one real benchmark pass on the free-tier brain
  (`GeminiModelProvider`), recorded into the experience store; ~7-9
  requests of the 20/day budget. Provider errors (quota) surface in
  the job summary, exit status honest.
- **POST /api/verdict** `{models: "a,b", tasks: N}` — the S68
  `run_verdict` (textual contract, recorded, protocol metrics) with
  OllamaProviders mapped from the model list.
- **GET /api/jobs** — the job list (newest first) for the UI panel.
- Runners are injectable callables on the app (default to the real
  implementations) so tests inject fakes — the established server-test
  pattern.

### UI (`app/`)

- An **Operations panel**: "Run drip" button; a models input + "Run
  verdict" button; the jobs list (kind, status, summary) polling
  /api/jobs on a 3-second interval. Same visual language as the
  sessions panel.

### Safety posture

- Buttons only. No auto-fire on page load, no timers. Localhost-only
  binding unchanged; every job is a deliberate click.
- Drip/verdict jobs record into the same experience store as the CLI —
  one loop, two surfaces.

## Verification

- Endpoint tests with injected fake runners: job lifecycle (running →
  done with summary; failed with the error), job list shape, POST
  validation (verdict requires models).
- `npm run build` stays the UI gate; the Python suite never depends on
  node.
