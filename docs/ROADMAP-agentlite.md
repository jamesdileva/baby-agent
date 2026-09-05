# Roadmap — Agent-Lite Track (S31 → S65+)

**Status:** canonical planning document for the Agent-Lite track.
**Provenance:** consolidated from `audit.md` (repository audit + first sprint
set), `audit2.md` (expanded/re-scoped sprint catalog S31–S60), and
`sprints51-60(before model training).md` (Apprenticeship layer). Those three
documents are superseded by this one; `audit.md` is retained as the historical
audit of record with a pointer here.

**Numbering ruling** (filed in DECISIONS.md): the sprint numbers S31 and S32
that originally belonged to the v5 fine-tune track in
[ROADMAP.md](ROADMAP.md) (`baby-agent:ep1`, generational loop) remain
**skip-and-logged** (GPU prerequisite, DECISIONS 2026-08). They are re-realized
in this track as **S63** (training data) and **S64** (Ep1). Every S-number
below refers to THIS document, not to ROADMAP.md's v5 track.

**Where we stand:** S1–S30 complete (827 tests OK). The v5 track is paused.
This track is the continuation: give the QA/learning brain the ability to act.

---

# Part 1 — Repository audit (condensed)

## 1.1 What already exists (strong)

```text
█████████░  Memory / Cases            (JSONL store, signatures, lookup)
█████████░  Failure intelligence      (flaky, regression, environment, preflight)
████████░░  Documentation / RAG       (digest, ask-with-citations)
████████░░  Learning pipeline         (candidate detection, adjudication, weak subjects)
███████░░░  Ollama integration        (S26 bridge, RAG answers)
█████████░  Testing                   (827 tests, fixture discipline)
███████░░░  Continuous observation    (S29 resident digest daemon)
████████░░  Skills infrastructure     (declarative packs + guarded modules)
████████░░  Research tools            (case_search, doc_grep, journal_read)
████████░░  Escalation                (S28 handshake, distillation into cases)
████████░░  Training-data export      (S30 export-training, holdout frozen)
```

## 1.2 What is missing

The repository is a strong **memory + learning + QA brain** with a local
model attached. It can answer, classify, and remember. It cannot *do*.

Missing layer — the Agent Runtime:

```text
ModelProvider abstraction   structured tool calling   Workspace boundary
Filesystem tools            Terminal tools            Git tools
Agent loop                  Session state             Permission policy
Event stream                Verification engine       Environment awareness
Web research / retrieval    Vision                    Process management
Experience memory           Skills 2.0                Evaluation harness
Desktop UI                  Apprenticeship pipeline   Training pipeline 2.0
```

## 1.3 Verdict: evolve, do not restart

The existing qacompanion becomes the agent's long-term memory and diagnostic
intelligence. A new runtime gives the model the ability to inspect, modify,
execute, test, and learn from real projects. The existing QA subsystem is the
agent's first brain subsystem; the runtime is its ability to act.

```text
                   MODEL
                     |
                 AGENT LOOP
                     |
              +------+------+
              |             |
              v             v
          ACTIONS        KNOWLEDGE
     Files/Shell/Git   Cases/Docs/Journal
              |             |
              +------+------+
                     |
                   RESULT
             success | failure
                     v
          QA Intelligence (signature -> case lookup -> diagnosis)
                     |
                  FIX -> VERIFY -> LEARN
```

## 1.4 What "Agent-Lite" means here

A lightweight LLM-powered autonomous agent that receives a goal, inspects a
bounded workspace, uses structured tools, observes results, modifies the
workspace, runs verification, recovers from failures, and persists useful
lessons. The minimum loop:

```text
GOAL -> CONTEXT -> MODEL -> TOOL CALL -> EXECUTION -> OBSERVATION
     -> MODEL -> ... -> VERIFICATION -> (failure -> diagnose -> fix) -> COMPLETE -> LEARN
```

The key distinction: Baby-Agent must **do things**, not merely explain how a
human should do them.

## 1.5 Target architecture

```text
                    BABY-AGENT
      +------------------+------------------+
      |                  |                  |
  PERCEPTION          REASONING          MEMORY
  filesystem          ModelProvider      cases
  terminal            ContextBuilder     docs
  runtime             planner            journal
  environment         agent loop         skills
  web                 router             experience
  vision              recovery           trajectories
  browser
      |                  |                  |
      +------------------+------------------+
                        |
                      TOOLS  (registry: schema, permission, timeout, audit)
                        |
                   VERIFICATION  (build / tests / lint / types / runtime / visual / goal)
                        |
                     LEARNING -> EXPERIENCE -> EVALUATION -> TRAINING DATA
                        |
                 Baby-Agent Ep1 -> Generations
```

Provider independence is a first-class requirement:

```text
ModelProvider
    +-- FakeModelProvider   (deterministic, tests)
    +-- OllamaProvider      (local, S26 bridge behind it)
    +-- OpenAIProvider      (future)
    +-- GeminiProvider      (future)
```

## 1.6 UI direction

GUI-first, terminal-capable. Ollama is the model runtime, not the UI. The UI
belongs to Baby-Agent (Electron + React + TypeScript over a local Python
runtime — S52). The terminal remains for debugging, developers, and recovery.
Normal workflow: select workspace → type goal → watch the agent inspect,
edit, run, diagnose, fix, and verify. The user is the goal setter and
supervisor, not the terminal operator.

## 1.7 Migration strategy

Do not rewrite. Incremental extraction, every sprint leaves the repo usable:

```text
qacompanion (as-is) -> wrap existing tools -> ModelProvider -> Tool Registry v2
-> Workspace -> Filesystem -> Execution -> AgentSession -> AgentLoop
-> Verification -> Perception -> Apprenticeship -> Desktop UI
```

---

# Part 2 — Constraints and discipline

Carried over unchanged from AGENTS.md: one committable slice per cycle;
tests green before every commit; honesty over optics (regressions are
reported, never hidden); provenance for every decision; review protocol and
human-escalation protocol apply.

**Constraint amendment (filed in DECISIONS.md):**

1. The qacompanion **core engine remains stdlib-only, deterministic, and
   LLM-free** (D1 stands). The brain stays an optional layer.
2. The **agent runtime layer** (everything in this document) begins stdlib-only
   (S31–S39 are pure stdlib Python). Third-party dependencies are permitted
   only where a sprint explicitly names them, only behind a provider
   abstraction, and never inside the `qacompanion` package: Ollama over
   localhost HTTP (S26 precedent), cloud model/web/vision providers (S42+,
   policy-gated, default DENY), Electron/React/Vite (S52 UI), Playwright
   (S53 browser). Live-provider tests are always separate suites; the core
   runtime must be fully testable with fakes, offline.
3. **No network calls** from the agent runtime except through the explicitly
   permission-gated tools built for that purpose (S42/S43), default DENY.
4. Sprint-number precedent: the fine-tune sprints deferred for lack of GPU are
   re-realized as S63/S64; nothing in this document requires a GPU.

---

# Part 3 — Sprint catalog

Format per sprint: Objective / Implement / End goal / Verification.
Status: S31 is **next**; all others proposed until their slice commits.

| Sprint | Name | Status |
|---|---|---|
| S31 | Agent Foundation | **next** |
| S32 | Tool Registry v2 | proposed |
| S33 | Workspace Abstraction | proposed |
| S34 | Filesystem Tools | proposed |
| S35 | Terminal & Execution | proposed |
| S36 | Git Intelligence | proposed |
| S37 | Agent Loop | proposed |
| S38 | Permission & Safety | proposed |
| S39 | Event Stream & Observability | proposed |
| S40 | Environment Intelligence | proposed |
| S41 | Verification Engine | proposed |
| S42 | Web Research | proposed |
| S43 | URL Context & Retrieval | proposed |
| S44 | Vision / Screenshot Analysis | proposed |
| S45 | Process & Runtime Management | proposed |
| S46 | Static Code Intelligence | proposed |
| S47 | Experience Memory | proposed |
| S48 | First Autonomous Coding Task | proposed |
| S49 | QA Brain Integration | proposed |
| S50 | Learning From Agent Sessions | proposed |
| S51 | Skills 2.0 | proposed |
| S52 | Desktop UI | proposed |
| S53 | Browser Abstraction | proposed |
| S54 | Computer Use | proposed |
| S55 | Model Routing | proposed |
| S56 | Context Optimization | proposed |
| S57 | Agent Evaluation Harness | proposed |
| S58 | Failure Recovery & Escalation 2.0 | proposed |
| S59 | Agent Apprenticeship Lab | proposed |
| S60 | Synthetic Curriculum | proposed |
| S61 | Multi-Agent Teacher Sessions | proposed |
| S62 | Trajectory Curation | proposed |
| S63 | Training Dataset Pipeline 2.0 | proposed |
| S64 | Baby-Agent Ep1 | proposed |
| S65+ | Generational Agents | long-term |

---

## S31 — Agent Foundation

**Objective.** Create the core runtime contracts without attempting full
autonomy. The rest of Baby-Agent talks to a model through one stable interface
instead of depending directly on Ollama or any vendor SDK.

**Implement.**

```text
ModelProvider   ModelRequest   ModelResponse   ModelMessage
ToolDefinition  ToolCall       ToolResult
AgentSession    AgentState     AgentConfig
FakeModelProvider  OllamaProvider (wraps the S26 bridge)
```

Provider interface supports: text input, structured tool definitions,
tool-call responses, model metadata, token usage when available, structured
errors, cancellation. Streaming and multimodal are optional extensions, not
day-one requirements. Future providers (OpenAI, Gemini) plug into the same
interface.

**End goal.** Model access and tool-call representation become structured
internal objects; the textual tool syntax remains only as a compatibility
shim.

**Verification.**

- Fake provider returns deterministic responses; used by the whole test suite.
- Ollama provider performs a basic request (live test kept separate).
- Provider failures become structured errors.
- Agent sessions enter/leave valid states; sessions serialize.
- Tool calls are represented without textual parsing.
- Existing QA modules and `qa ask` behavior unchanged; full suite green.

---

## S32 — Tool Registry v2

**Objective.** Turn the existing tool system into a first-class agent tool
platform: any tool can be safely registered, validated, executed, observed,
and audited.

**Implement.** Every tool carries: `name`, `description`, `input_schema`,
`output_schema`, `handler`, `category`, `permission_level`,
`side_effect_level` (READ_ONLY / SAFE_WRITE / EXECUTION / DESTRUCTIVE /
EXTERNAL), `timeout`, `cancellable`, `requires_workspace`,
`requires_confirmation`.

Execution pipeline:

```text
model tool call -> schema validation -> permission check -> workspace policy
-> timeout/cancellation -> executor -> structured ToolResult -> event stream
```

Preserve the existing knowledge tools: `case_search`, `doc_grep`,
`journal_read`.

**End goal.** Predictable execution contract for every tool.

**Verification.** Tests cover valid calls, malformed arguments, unknown
tools, permission denial, timeout, cancellation, executor exceptions, and
structured result serialization.

---

## S33 — Workspace Abstraction

**Objective.** Give the agent a formal concept of the project it operates on —
an explicit boundary for every future filesystem/terminal action.

**Implement.** `Workspace`, `WorkspaceManager`, `PathPolicy`,
`ProjectMetadata`, `WorkspaceConfig`. Workspace knows: root, current
directory, allowed paths, excluded paths, git root, project type, detected
languages, package managers, entrypoints.

Path policy must reject: `..` traversal, absolute-path escape, symlink
escape, unapproved directories, protected system locations.

**End goal.** The agent operates inside an explicit project boundary.

**Verification.** Valid access passes; parent traversal, absolute escape,
symlink escape, and excluded-directory access are all rejected — tested with
malicious/pathological paths, including Windows-specific cases.

---

## S34 — Filesystem Tools

**Objective.** The model can inspect and modify projects without the user
copying code into the conversation.

**Implement.** `list_directory`, `read_file`, `write_file`, `edit_file`,
`search_code`, `file_exists`, `file_metadata`. Considerations: UTF-8
handling, binary-file detection, maximum read size, line-oriented editing,
atomic writes, backup/rollback support, file hashes, changed-file tracking,
excluded directories, generated-file awareness.

**End goal.** Structured, safe file operations inside the workspace.

**Verification.** A fake agent can list → read → create → edit → search →
inspect inside a test workspace, receives useful structured errors, and never
escapes the workspace.

---

## S35 — Terminal & Execution

**Objective.** Structured command execution: the agent can build and test the
project without the user operating a terminal.

**Implement.** `run_command`, `run_tests`, `run_build`, `run_lint`,
`run_typecheck` (initially explicit commands; project detection later).

```text
CommandResult: command, cwd, stdout, stderr, exit_code, duration,
               timed_out, cancelled, started_at, finished_at
```

Execution supports: timeout, cancellation, output limits, environment
isolation, working directory, process-tree tracking, non-zero-exit handling,
command allow/deny policy.

**Verification.** Controlled commands that succeed, fail, time out, produce
stderr, produce large output, spawn children, and get cancelled — all return
structured results; nothing executes outside workspace policy without
permission.

---

## S36 — Git Intelligence

**Objective.** Source-control awareness before autonomous changes.

**Implement.** Initially `git_status`, `git_diff`, `git_log`, `git_branch`.
Later (policy-gated): `git_add`, `git_commit`, `git_checkout`, `git_restore`,
`git_stash`. No autonomous commits without policy controls.

**End goal.** Before and after work, the agent answers: What changed? What
was already changed? What did I change? What remains?

**Verification.** Temporary git repository: status/diff parsing, branch
detection, clean/dirty detection, changed-file tracking, clean failure
handling; commits require confirmation.

---

## S37 — Agent Loop

**Objective.** The first actual autonomous reasoning loop.

**Implement.**

```text
GOAL -> CONTEXT -> MODEL -> TOOL CALL -> VALIDATE -> EXECUTE -> OBSERVATION
     -> MODEL -> ... -> VERIFY -> (FAIL -> DIAGNOSE -> FIX -> VERIFY) -> COMPLETE
```

Session tracks: session_id, goal, workspace, state, iteration, messages,
tool_calls, observations, changed_files, failures, verification_results,
start/end time, termination_reason. States: CREATED, PLANNING, RUNNING,
WAITING_FOR_PERMISSION, VERIFYING, RECOVERING, PAUSED, CANCELLED, COMPLETED,
FAILED. Includes iteration limits, final-answer detection, failure handling,
cancellation.

**End goal.** A deterministic fake model autonomously performs a multi-step
coding task.

**Verification.** Fake-model script (`list_directory → read_file →
write_file → run_build → read_error → edit_file → run_build → final`)
executes with no hard-coded knowledge of the test task; a test proves tool
output is fed back into the next model iteration.

---

## S38 — Permission & Safety

**Objective.** Treat model-generated actions as untrusted automation.

**Implement.** `PermissionPolicy`, `PermissionDecision`; modes ALLOW / ASK /
DENY. Example posture:

```text
read_file, search_code, write_file, run_tests -> ALLOW
npm install, network request, git commit, delete file -> ASK (policy-dependent)
format disk, credential access, system directory -> DENY
```

Supports per-tool, per-workspace, and session permissions; user confirmation;
audit logging; destructive-operation detection.

**End goal.** Autonomous without unrestricted authority.

**Verification.** Every tool call demonstrably passes validation →
permission → workspace policy → executor; each mode tested; user cancellation
works.

---

## S39 — Event Stream & Observability

**Objective.** Make the runtime observable by the UI and by future
debugging/evaluation systems without coupling them to internal state.

**Implement.** Events (non-exhaustive): session_started, session_state_changed,
model_started, model_response, tool_requested, tool_started, tool_completed,
tool_failed, file_changed, command_started, command_output, command_completed,
permission_requested/granted/denied, verification_started/completed,
failure_detected, recovery_started, session_paused/cancelled/completed.
Envelope: `event_id`, `session_id`, `timestamp`, `event_type`, `payload`.

**End goal.** The UI subscribes to the event stream; it never polls internals.

**Verification.** A test session emits the expected complete event sequence.

---

## S40 — Environment Intelligence

**Objective.** Understand the machine; distinguish "the code is wrong" from
"the environment cannot run this project."

**Implement.** Tools: `get_environment_summary`, `get_os`, `get_cpu`,
`get_memory`, `get_gpu`, `get_runtime_versions`, `get_package_manager`.
Collect OS/arch, Python, Node, npm/pnpm/yarn, Git, Java, Rust, Go, GPU, RAM,
disk, available ports, environment-variable **metadata**. Never expose
secrets.

**Verification.** A deliberately incompatible project yields an environment
mismatch report before the agent blindly retries fixes.

---

## S41 — Verification Engine

**Objective.** Verification becomes a first-class subsystem, not just another
command. "I changed the code" ≠ "I proved the requested behavior works."

**Implement.** `VerificationPlan`, `VerificationStep`, `VerificationResult`,
`VerificationReport`. Categories: BUILD, TEST, LINT, TYPECHECK, RUNTIME,
HEALTHCHECK, VISUAL, REGRESSION, GOAL. A plan may chain: install deps →
typecheck → build → launch → health check → tests → inspect UI → compare
expected result.

**Verification.** Benchmark projects where build passes but tests fail, tests
pass but runtime fails, runtime works but UI is wrong, and code works but the
goal is incomplete — the engine distinguishes all four.

---

## S42 — Web Research

**Objective.** Internet research capability through a provider abstraction.
Web research is a tool capability, not a property of one model.

**Implement.** `WebSearchProvider` (initial: Gemini/Google Search grounding),
tool `web_search`. Input: query, purpose, freshness, max_sources. Output
`SearchResult`: query, sources, titles, urls, snippets, citations, provider,
timestamp.

**Principle.** Search results are evidence: collect sources → inspect the
relevant source → reason → record provenance (url, title, retrieval time,
provider, excerpt, decision made) → apply. Failures must not crash the agent.

**Verification.** Controlled research tasks: request emitted, sources
captured, citations stay attached, results injected into context, web
failures degrade gracefully. (Policy-gated network tool; default DENY — see
Part 2.)

---

## S43 — URL Context & Retrieval

**Objective.** Inspect specific pages after discovering them: search →
official docs → extract relevant section → apply knowledge.

**Implement.** `open_url`, `extract_page`, `download_artifact`. Support HTML,
documentation pages, public text, selected PDFs/artifacts, source metadata,
retrieval limits.

**Verification.** Agent searches an API, opens the official documentation,
extracts the relevant section, and uses it to make an implementation decision.

---

## S44 — Vision / Screenshot Analysis

**Objective.** Visual perception. Architecture rule: vision capability ≠
screen acquisition. Acquisition tools capture; a VisionProvider interprets;
the agent model decides; action tools act.

**Implement.** Tools: `capture_screen`, `capture_window`, `capture_region`,
`inspect_image`, `compare_images`. `VisionProvider` adapters (Gemini
multimodal, OpenAI multimodal, local vision model). A screenshot becomes an
ordinary `ImageObservation` the model can reason over.

**End goal.** launch app → screenshot → inspect → detect broken layout → edit
CSS → relaunch → compare → verify improvement.

**Verification.** Benchmark with an intentionally broken UI: capture,
identify, modify, relaunch, compare, verify improvement.

---

## S45 — Process & Runtime Management

**Objective.** Move beyond one-shot commands; manage the lifecycle of
applications the agent creates.

**Implement.** `start_process`, `stop_process`, `restart_process`,
`list_processes`, `process_status`, `wait_for_process`, `check_port`,
`wait_for_port`, `health_check`.

**End goal.** `npm run dev` → wait_for_port → health_check → capture_screen.

**Verification.** Test server: start, wait, ready detection, health check,
stop, restart, recovery from a crashed process.

---

## S46 — Static Code Intelligence

**Objective.** Code understanding beyond raw text search.

**Implement.** `CodeIndex` with Python AST, a TypeScript/JavaScript parser, a
generic text fallback, and future LSP integration. Capabilities: symbol
search, definition lookup, reference lookup, imports/exports, dependency
graph, diagnostics.

**End goal.** Answer "where is this defined / who calls it / what imports
this" without reading the whole repository.

**Verification.** Multi-module project yields correct symbol/reference
discovery.

---

## S47 — Experience Memory

**Objective.** Expand the QA memory into general agent experience; the case
base becomes one specialized source inside a broader memory layer.

**Implement.** `Experience` record: goal, context, actions, observations,
failure, diagnosis, resolution, verification, outcome, confidence, timestamp,
project metadata. Stores: working, episodic, semantic, failure, skill,
environment, documentation memory (see Part 6).

**End goal.** Baby-Agent improves at recurring problems without retraining.

**Verification.** Teach a successful recovery procedure; run a similar task;
the experience is retrieved and influences the plan.

---

## S48 — First Autonomous Coding Task

**Objective.** Prove the entire core stack before adding more intelligence.

**Benchmark.** Bounded workspace + natural-language goal + intentional
defect. The agent must: inspect → plan → read → edit → build → observe
failure → diagnose → fix → verify → report. **No manual command execution.**

**Verification.** The benchmark records files changed, commands executed,
failures, recovery, verification, final result, and human-intervention count.

---

## S49 — QA Brain Integration

**Objective.** Connect the Agent Runtime to the existing QA intelligence —
the architecture payoff of the whole track.

**Failure path.**

```text
CommandResult -> Failure Detection -> Failure Signature -> Case Lookup
    -> known:    historical diagnosis supplied to the model
    -> unknown:  research / reason
```

The existing systems contribute: known failure signatures, previous fixes,
confidence, environment clues, regression information, weak-subject
information.

**Verification.** Seed a known case, reproduce the failure, confirm the
historical resolution is supplied to the model before its next action.

---

## S50 — Learning From Agent Sessions

**Objective.** Record useful autonomous trajectories as experience data.

**Implement.** Capture: goal, context, plan, tool calls/results, files
changed, failures, diagnoses, fixes, verification, outcome, human
interventions. Classify: successful / failed / recovered / human-corrected /
partially successful / unsafe / inefficient.

**Notes (2026-09-05, human-directed curation backlog — mined corpus from
S47.1 lives in experience.jsonl: 1,170 sessions → 99 experiences).**
This sprint owns: (1) a curation pass over the 99 mined experiences
(drop greeting pings like "hello" ×7, drop/merge low-value patterns);
(2) merge the ×321 resume pattern ("Your previous response was
interrupted. Continue where you left off") into a proper SKILL
(resume_interrupted_task) rather than an experience; (3) deeper
marathon-session extraction — diagnosis/resolution mining from the
big-content projects (surfhop: 2 sessions/1,694 msgs,
dinner-menu-generator: 1/2,483, sentinel: 50k parts) where outcome and
fix work is inferable from edit/patch parts. See also S62 for the full
curation machinery.

**Verification.** Run a task with an unknown failure, recover, verify a new
experience/case exists with signature, diagnosis, resolution, verification,
timestamp.

---

## S51 — Skills 2.0

**Objective.** Reusable procedures on top of primitive tools — data/procedure
driven, not giant hard-coded functions.

**Implement.** Skill fields: name, goal, description, required_tools,
preconditions, procedure, verification, failure_modes, examples, confidence.
Target families (grown over time): project inspection/setup; app creation
(create_react_app, create_fastapi_app); debugging (build failure, test
failure, typescript, python, runtime, with screenshot); research (unknown
API, dependency, documentation, web issue); UI (inspect, fix layout);
verification (verify_application, run_regression); release (prepare_release,
create_git_checkpoint); runtime (start_and_verify_application,
recover_failed_process, analyze_runtime_logs, analyze_dependency_conflict);
environment (diagnose_environment).

**Verification.** Teach/retrieve a skill; the agent follows its procedure and
performs its verification step.

---

## S52 — Desktop UI

**Objective.** Replace the manual CLI workflow with a polished application.

**Status (2026-09-05).** Delivered API-first: `qa serve` boots the
localhost REST+SSE server (stdlib) and serves the built Vite+React+TS
dashboard from app/dist. **Deferred to an S52 packaging follow-up:**
the Electron shell (window chrome, tray, packaging/installers) — the
browser is the desktop shell until then; the API contract is unchanged
when it lands.

**Stack.** Electron + React + TypeScript + Vite; Python runtime behind
FastAPI or local IPC; SQLite storage (existing JSONL stores remain behind
repositories during migration).

**Screens.** Dashboard, New Task, Active Session, Projects, History, Memory,
Skills, Settings.

New Task: workspace picker, goal input, model choice (Local / Gemini /
OpenAI / Auto), permission preset (Safe / Balanced / Autonomous), start.

Active Session shows: goal, status, current step, activity summary, tool
calls, files changed, command output, errors, build/test status,
verification, current model, elapsed time, pause/stop. **Do not expose
private chain-of-thought — show concise action/status summaries.**

Project View: git status, recent sessions, known issues, environment,
verification history.

**Verification.** Open → select workspace → enter goal → start → watch live
→ pause/stop → review changed files → see build/test/verification results →
read the final summary.

---

## S53 — Browser Abstraction

**Objective.** A controlled browser interface for the agent's web
applications and documentation.

**Implement.** `BrowserProvider` (initial: Playwright). Tools:
browser_open/back/click/type/scroll/select/screenshot/extract/download. Use
cases: test web apps, inspect docs, interact with dev servers, verify forms,
reproduce UI bugs, collect screenshots.

**Verification.** Small web app: launch → open browser → navigate → interact
→ screenshot → verify.

---

## S54 — Computer Use

**Objective.** General GUI interaction — only after screenshots, browser
automation, and permissions are reliable, and heavily restricted. Not needed
for ordinary coding tasks.

**Implement.** `ComputerUseTool` → Permission Layer → OS Automation Adapter.
Capabilities: mouse, click, keyboard, window selection, screen observation,
application launching.

**Verification.** Sandboxed GUI benchmark with an explicit allow-list of
actions.

---

## S55 — Model Routing

**Objective.** Balance speed, cost, privacy, and capability across providers.

**Routing example.**

```text
small/local model  -> classification, simple edits, routine retrieval
strong model       -> planning, difficult debugging
coding model       -> implementation
vision model       -> screenshots
research model     -> current web research
escalation model   -> stuck situations
```

Router inputs: task type, difficulty, context size, latency budget, privacy,
cost, availability, failure count.

**Notes (2026-09-05, from S48 live benchmark data — no worklog dig needed).**

Measured on the S48 defect-fix benchmark (CPU-only machine, no GPU):

```text
qwen2.5-coder:1.5b   fast (~5s/turn) but UNRELIABLE: 0 test runs,
                     7 premature-done claims (all rejected by the
                     verifier), faked evidence via log files
llama3.1:8b          too slow on CPU: 5 tool-call errors, per-request
                     timeouts even at 180s, 397s for 3 iterations
```

Sprint agenda (human + agents):
1. **Bake-off candidates between 1.5B and 8B** — human suggestion:
   qwen2.5-coder:3b / 5b class. Research current options, run the S48
   benchmark as the bake-off harness (it already produces comparable
   metrics per model).
2. **Make the bridge HTTP timeout configurable** (currently hardcoded
   60s in ollama_bridge._http_post) — a hard cap slow models always
   hit; smoke runs had to monkey-patch it.
3. **Role sketch (human direction, to validate with the bake-off)**:
   local qwen2.5-coder variant as the BRAIN (coder), qwen2.5vl:3b
   (already pulled) as VISION, free-tier Gemini as
   RESEARCH/ESCALATION helper when baby-agent gets stuck — Gemini is
   quota-limited so it stays the on-demand helper, not the default.
4. **GeminiModelProvider adapter** (plain mode, no grounding — works
   free per the no-billing ruling) so the loop/benchmark can run on a
   cloud model; ModelProvider already accepts any backend.
5. Benchmark categories beyond defect-fix come after the bake-off picks
   the brain.

**Verification.** Mock multiple providers; routing is deterministic under
policy.

---

## S56 — Context Optimization

**Objective.** Keep the agent effective as projects grow; never drown the
model.

**Implement.** `ContextBuilder`, `ContextBudget`, `ContextPriority`,
`ObservationReducer`, `FileSummary`, `ToolResultSummarizer`,
`MemoryRetriever`. Prioritize: current failure, current files, relevant code,
recent tool results, verification status, relevant memory/docs, goal. Never
send: whole repository, whole terminal history, irrelevant docs, duplicate
tool results.

**Verification.** Large synthetic repository: context stays within a
configured budget while retaining what the task needs.

---

## S57 — Agent Evaluation Harness

**Objective.** Repeatable benchmarks so improvement is measurable, not
anecdotal.

**Metrics.** Task success, goal completion, iterations, tool calls, time,
token usage, failures, recovery rate, unnecessary actions, human
interventions, verification quality, regressions. Track: base model, agent
version, tool/skill/memory version, workspace, task, result.

**Verification.** Two versions, identical benchmarks, comparable reports.

---

## S58 — Failure Recovery & Escalation 2.0

**Objective.** Explicit recovery behavior instead of indefinite looping.
Failure becomes a controlled state machine.

**Implement.** Strategies: retry, re-read, search code/memory/web, inspect
environment/logs, alternate implementation, rollback, ask user, escalate
model, terminate. Triggers: repeated same failure, no progress, verification
regression, permission issue, environment mismatch, tool failure, context
overflow, model uncertainty, iteration/runtime limits.

```text
FAILURE -> CLASSIFY
    known        -> memory
    environment  -> diagnose environment
    dependency   -> web / docs
    code         -> inspect / edit
    runtime      -> logs / process
    visual       -> screenshot
    unknown      -> escalate
```

**Verification.** Several failure categories; the correct recovery strategy
is selected each time.

---

## S59 — Agent Apprenticeship Lab

**Objective.** A dedicated learning environment where Baby-Agent observes,
interacts with, and learns from stronger external agents/models — the bridge
between a working Agent-Lite and a future trained generation. The purpose is
NOT initially to train weights; it is to expose Baby-Agent to large numbers
of high-quality, **verified** software-development examples.

**Implement.**

```text
TeacherProvider
    +-- Gemini   +-- OpenCode-compatible agents
    +-- Ollama/local models   +-- OpenAI   +-- future providers
```

Session types: **discussion** (teacher proposes, Baby-Agent questions,
teacher explains, student summarizes the lesson), **demonstration** (teacher
solves a task; full trajectory recorded), **critique** (teacher reviews
Baby-Agent's proposal; revision; verification), **debugging** (both agents
get the same broken project), **architecture review** (multiple teachers
compare designs).

Session contract records: session_id, teacher_provider/model, student_model,
task_id, goal, difficulty, conversation, tool_calls, observations, decisions,
corrections, verification, outcome, lessons, skills_identified,
trajectory_quality, timestamp. Lifecycle: CREATED → TASK_ASSIGNED →
TEACHER_SESSION → OBSERVATION → CRITIQUE → VERIFICATION → CURATION →
ACCEPT/REJECT → EXPERIENCE.

**Principles.**

- Teacher said it ≠ correct. Every claim is verified or marked uncertain.
- Teacher sessions involving executable code run in isolated environments.
- Never learn: credentials, secrets, unsafe commands, destructive
  procedures, unverified claims, provider-specific hallucinations, malicious
  instructions. Teacher output is untrusted knowledge until verified and
  curated into trusted experience.
- Diversity over volume: 1,000 nearly identical sessions are worth less than
  a smaller collection covering many different problems. Recent code-agent
  research finds trajectory diversity can matter more than trajectory count.
- Scale strategy: 10 → 50 → 100 → 250 → 500 → 1,000 sessions, evaluating
  after each stage (new skills? new failures? more diverse strategies?). If
  coverage stalls, change the curriculum — do not simply generate more.
  Treat 1,000 as the first meaningful experiment, with the machinery designed
  to scale to 10,000+ later.
- Teacher cost tiers: cheap/local teachers for simple tasks, generation,
  critique, summarization; strong teachers for complex architecture,
  difficult debugging, long-horizon coding, adjudication. A teacher router
  maps task difficulty → cheap / capable / strong / multiple teachers.

**Verification.** A teacher can be assigned a structured task and complete a
session; Baby-Agent observes; the full interaction (tool calls, observations)
is recorded and replayable; a verifier determines whether the solution
actually worked; lessons are extracted; accepted lessons enter memory;
high-quality trajectories are exportable for later training.

---

## S60 — Synthetic Curriculum

**Objective.** Systematically generate software-development learning tasks
instead of relying on random conversations — answering "what should
Baby-Agent learn?" before "how do we train it?".

**Implement.**

- Curriculum hierarchy: L1 basic concepts → L2 simple implementation → L3
  debugging → L4 multi-step implementation → L5 architecture → L6 complex
  debugging → L7 multi-system applications → L8 long-horizon autonomous
  development.
- Task categories: project creation, features, bug fixing, refactoring,
  testing, build repair, dependencies, API integration, database, UI
  dev/debug, performance, security, environment diagnosis, documentation,
  research, architecture, git, runtime debugging, regression, release prep.
- Difficulty is a vector, not a number: task_complexity, codebase_size,
  files/components/deps/tools/steps, failure_probability, context_size,
  debugging_depth, verification_depth, research/visual/runtime requirements.
- Generated tasks carry: goal, environment, initial repository, constraints,
  expected behavior, known failure modes, verification plan, difficulty,
  required skills.
- **Failure injection**: tasks intentionally contain missing/wrong deps,
  bad imports, type mismatches, exceptions, broken SQL, invalid API calls,
  port conflicts, failing tests, broken CSS/layout, crashes, bad config —
  so the agent learns failure → investigation → diagnosis → correction →
  verification, not just problem → perfect answer.
- Disposable synthetic environments: `training/workspaces/session-NNNNN/`.
- Adaptive: track mastery/failure/recovery/verification rates; increase
  difficulty on success, generate intermediate tasks on struggle.
- Coverage matrix (skills × tasks) prevents dataset bias; repeated tasks are
  detected and reduced.

**Verification.** Generates valid tasks with explicit success criteria and
assigned difficulty; tasks can be grouped by skill, contain intentional
failures, run in isolated workspaces, and be verified; difficulty adapts to
performance; coverage is tracked; duplicates shrink.

---

## S61 — Multi-Agent Teacher Sessions

**Objective.** Structured multi-teacher discussions, debates, reviews, and
collaborative problem solving — to generate higher-quality learning examples,
not a permanent swarm.

**Implement.** Roles (configurable): architect, coder, debugger, reviewer,
security/performance reviewers, UI designer, researcher, tester, verifier,
project manager. Modes: independent solutions then compare; critique chain;
debate with judge; specialist review panels; teacher-vs-teacher debugging of
the same broken project with a verifier picking the best diagnosis.

Session contract: participants, roles, provider/model, messages, proposals,
critiques, votes, verification, final_solution, disagreements,
resolved_disagreements, trajectory_quality.

**Principles.** Consensus ≠ correctness — multi-agent agreement still passes
through verification. Deliberately vary model, provider, temperature, prompt
style, role, architecture preference, strategy, difficulty; avoid one teacher
/ one style / one pattern repeated thousands of times. Capture not just the
correct answer but the alternatives, why they were rejected, tradeoffs,
mistakes, criticism, correction — these are the most valuable training
examples. The system must degrade gracefully to a single teacher.

**Verification.** Independent teachers solve the same task; solutions are
compared; teachers critique one another; disagreements are recorded; a
verifier judges claims; incorrect consensus can be rejected; final
trajectories preserve alternatives and corrections; diversity is measurable;
demonstrably different strategies emerge.

---

## S62 — Trajectory Curation

**Objective.** The gate between "something happened" and "Baby-Agent should
learn this." Not every session enters the dataset.

**Note (2026-09-05).** The near-term curation backlog for the mined
opencode corpus is tracked in S50 (this sprint supplies the full
machinery it will eventually use).

**Pipeline.**

```text
RAW SESSION -> normalize -> validate -> execute/reproduce -> verify
-> score -> critique -> deduplicate -> extract lessons
-> ACCEPT / REVIEW / REJECT
```

**Quality score** (0–1 per dimension): correctness, completeness,
verification, tool_use, efficiency, clarity, robustness, recovery, diversity,
relevance — combined into an overall score.

**Hard rejections:** incorrect final result, unverified claims, unsafe
behavior, fabricated tool results, hallucinated APIs, nonexistent files,
unreproducible actions, broken final project, credential exposure, unbounded
destructive behavior.

**Soft penalties:** unnecessary tool calls, repeated actions, excessive
context, poor planning, avoidable failures, redundant explanations,
unnecessary dependency additions, unnecessary architectural complexity.

**Preserve useful failures.** Classify SUCCESS / FAILED / RECOVERED /
HUMAN_CORRECTED / UNSAFE / INVALID. A recovered trajectory (wrong decision →
failure → diagnosis → correction → verification) teaches recovery, which is
more valuable than perfection. Where possible, distinguish useful decisions
from incorrect ones so later training avoids teaching bad behavior.

**Lesson extraction.** One trajectory can yield: memory entry, failure case,
skill candidate, training example, benchmark item.

**Deduplication & diversity.** Similarity across goal, tool sequence, files
changed, solution structure, failure type, reasoning pattern. Maximize useful
coverage × quality × diversity — not raw sample count.

**Human review.** Low-confidence/high-value trajectories route to optional
human approval, showing goal, environment, actions, results, failures, fixes,
verification, final state, score.

**Dataset separation (permanent rule).**

```text
EXPERIENCE DATA  = everything that happened
CURATED DATA     = useful, verified experiences
TRAINING DATA    = the explicitly accepted subset, formatted for training
```

**Verification.** Raw sessions normalize; trajectories replay; tool calls
validate; results verify; incorrect trajectories are rejected; failed-but-
useful recoveries survive; scores/duplicates/diversity work; lessons extract;
curated trajectories export (`trajectory.jsonl`, `lessons.jsonl`,
`skills.jsonl`, `failures.jsonl`, `preferences.jsonl`, `benchmarks.jsonl`);
the training set contains only accepted examples; **the curation pipeline is
testable without live LLMs**.

---

## S63 — Training Dataset Pipeline 2.0

**Objective.** Only after the runtime generates meaningful, curated
trajectories: build the training corpus.

**Implement.** Structured trajectory export: goal, context, plan, action,
observation, …, verification, outcome — with enough metadata to reproduce the
task. Trajectory classes: successful / failed / recovered / human-corrected /
unsafe / inefficient. Source: S62's CURATED dataset — never raw experience.

**End goal.** High-quality data for fine-tuning, preference optimization,
tool-use training, failure-recovery training, evaluation, and skill
discovery.

**Verification.** A completed coding session exports as a valid structured
training record.

---

## S64 — Baby-Agent Ep1

**Objective.** Resurrect the generations idea (originally ROADMAP.md S31/S32,
skip-and-logged for GPU) only now that data quality and an evaluation harness
exist.

**Process.**

```text
real agent sessions (S48–S50) + apprenticeship corpus (S59–S62)
-> curate -> training dataset -> fine-tune / adapt
-> baby-agent:ep1 -> benchmark -> improvement? (yes/no)
```

**Honesty rule.** Do not assume a trained model is better. Evaluate coding
success, tool selection, planning, recovery, iterations, memory usage,
verification, latency, model size. Compare Ep1 against the base model on the
same benchmark suite; report regressions honestly. A generation that forgets
old lessons is documented, not shipped silently.

**Verification.** Measurable improvement over the base model on the same
benchmark, or the attempt is recorded as failed.

---

## S65+ — Generational Agents

Long-term: Ep1 → experience → evaluate → improve → Ep2 → …

Targeted improvements per generation: planning, tool selection, iteration
count, debugging, memory retrieval, skill reuse, verification, latency, model
size, local inference, multimodal reasoning. **Every generation is
benchmarked** — never assumed better.

---

# Part 4 — Dependency order

```text
S30 COMPLETE (QA brain, training-data export)
    |
    v
S31 Agent Foundation
    |
S32 Tool Registry v2
    |
S33 Workspace
    |
S34 Filesystem
    |
S35 Execution
    |
S36 Git
    |
S37 Agent Loop
    |
S38 Permissions
    |
S39 Events
    |
    +---------------------+
    |                     |
    v                     v
S40 Environment      S41 Verification
    |                     |
    +----------+----------+
               |
               v
S42 Web Research
               |
S43 URL Retrieval
               |
S44 Vision
               |
S45 Process Management
               |
S46 Code Intelligence
               |
S47 Experience Memory
               |
S48 First Autonomous Coding Task
               |
S49 QA Brain Integration
               |
S50 Session Learning
               |
S51 Skills 2.0
               |
S52 Desktop UI
               |
S53 Browser
               |
S54 Computer Use
               |
S55 Model Routing
               |
S56 Context Optimization
               |
S57 Evaluation Harness
               |
S58 Recovery & Escalation 2.0
               |
S59 Apprenticeship Lab
               |
S60 Synthetic Curriculum
               |
S61 Multi-Agent Teacher Sessions
               |
S62 Trajectory Curation
               |
S63 Training Dataset 2.0
               |
S64 Baby-Agent Ep1
               |
S65+ Generations
```

Some sprints parallelize once their interfaces exist (S40/S41; the UI and
browser tracks are independent of the apprenticeship track), but the chain
above is the safest implementation order. The apprenticeship layer (S59–S62)
sits immediately before training (S63/S64) per its founding rationale: answer
"what should Baby-Agent learn?" before "how do we train it?".

---

# Part 5 — Inventories

## Tool inventory (eventual; availability is policy- and task-dependent)

```text
Knowledge:    case_search, doc_grep, journal_read, memory_search
Workspace:    list_directory, read_file, write_file, edit_file, search_code,
              file_exists, file_metadata
Execution:    run_command, run_tests, run_build, run_lint, run_typecheck
Git:          git_status, git_diff, git_log, git_branch, git_add, git_commit,
              git_restore
Environment:  get_environment_summary, get_os, get_cpu, get_memory, get_gpu,
              get_runtime_versions, get_package_manager
Runtime:      start/stop/restart_process, list_processes, process_status,
              wait_for_process, check_port, wait_for_port, health_check
Web:          web_search, open_url, extract_page, download_artifact
Vision:       capture_screen, capture_window, capture_region, inspect_image,
              compare_images
Browser:      browser_open/back/click/type/scroll/select/screenshot/
              extract/download
Verification: run_verification
```

Day-one toolbox (S31–S36) is deliberately small: the existing knowledge tools
plus workspace/execution/git reads. That is enough for a capable coding agent.

## Skill inventory

See S51. Grown incrementally; skills are data/procedure driven.

---

# Part 6 — Architecture principles

**The five fundamental abilities.** PERCEIVE (project, environment, web,
runtime, visuals), REASON (goals, plans, diagnosis, action choice), ACT
(files, commands, processes, systems), VERIFY (prove the requested result
works), LEARN (remember procedures, failures, corrections, outcomes). The
model supplies much of the reasoning; Baby-Agent supplies the complete system
around the model.

**User supervises, agent operates.** The user provides goals and approvals;
the agent reasons, acts, observes, verifies, learns. The user never manually
shuttles information between terminal, editor, browser, LLM, error output,
and documentation — Baby-Agent is that orchestration layer.

**Tools are the agent's hands.** The model never directly controls the OS.
Every action flows: MODEL → structured tool call → REGISTRY → VALIDATION →
PERMISSION → WORKSPACE/SYSTEM POLICY → EXECUTOR → OBSERVATION → MODEL. This
yields safety, testability, provider independence, observability, and
auditability.

**Vision is perception, not UI automation.** Separate acquisition (capture
tools) from interpretation (vision model) from decision (agent model) from
action (filesystem/browser/computer-use tools). Vision providers are
swappable.

**Web search is research, not truth.** Search results are evidence with
retained provenance (url, title, time, provider, excerpt, decision made).

**Verification is separate from reasoning.** The model may decide *what*
should be verified; the verification system decides whether the evidence
supports completion. MODEL: "it works" is never proof.

**Memory is not just chat history.** Planned stores: working (current task),
episodic (previous sessions), semantic (durable knowledge), failure (known
errors/fixes — the existing case base), skill (reusable procedures),
environment (machine/project constraints), documentation (retrieved
knowledge).

**The agent must know when it is stuck.** Every session has max_iterations,
max_runtime, max_same_failure, max_tool_failures, max_retries,
context_budget. Progress is measurable (new files, target file changed,
failure changed, verification score improved, test count improved, goal
checklist advanced). On stall: retry → alternate strategy → research →
escalate → ask user → stop.

**What NOT to build early.** Multi-agent swarms (beyond S61's bounded teacher
sessions), self-rewriting runtime, autonomous GitHub publishing, unrestricted
computer control, unrestricted credentials/network, custom foundation-model
training (before S63), large vector-database infrastructure, distributed
clusters, cloud orchestration. First prove: one agent, one workspace, one
model, a small safe tool set, a reliable observe → act → verify loop.

---

# Part 7 — Security, testing, evaluation

## Security model

The agent is untrusted automation even when local. Minimum safeguards:
workspace sandbox, path-traversal prevention, symlink policy, command
timeout, process cancellation, iteration and runtime limits, permission
policy, audit log, destructive-operation confirmation, credential isolation,
network policy, tool-result limits. The model never gains implicit authority
by producing a valid-looking tool call.

## Testing strategy

- **Unit:** tool schemas, path validation, workspace, permissions,
  providers, registry, agent state, verification, memory, routing, context
  budgeting.
- **Integration:** model→tool→result, workspace→filesystem, agent→command
  execution, QA→failure lookup, agent→memory, web→context, vision→
  observation, process→health check.
- **End-to-end:** deterministic fake models script full trajectories. The
  core runtime must never require Ollama, cloud providers, internet, GPU, or
  a real browser to test.
- **Live-provider tests** are separate integration/evaluation suites,
  never CI gates.

## Evaluation philosophy

Benchmarks over vibes. Categories: new project creation, feature addition,
bug fixing, build repair, test repair, dependency migration, API integration,
UI repair, runtime debugging, environment diagnosis, documentation research,
regression prevention. A benchmark result records task, agent version, model,
workspace, success, iterations, tool calls, time, tokens, failures, recovery,
human interventions, verification quality. The goal is to move from "I think
it got smarter" to "v0.8 solved 72% of the benchmark, up from 61%, with 18%
fewer tool calls."

---

# Part 8 — Definitions of done

## Agent-Lite complete

Not "an LLM can call tools." Given a bounded workspace and a natural-language
goal, Baby-Agent can: understand the goal; inspect the project and
environment; form a useful plan; read/search files; create/edit files; run
project commands; observe results; detect failures; search accumulated
knowledge; research unknowns when necessary; diagnose/fix; manage the
application when required; verify builds/tests/runtime; inspect visually when
appropriate; repeat within limits; recover from common failures; report what
it did; persist useful experiences; and let the user observe, pause, approve,
or stop it throughout.

## Baby-Agent beyond Agent-Lite

```text
Agent-Lite + persistent learning + skills + evaluation + trajectory
collection + multimodal perception + model routing + self-improvement
= Baby-Agent
```

Long-term vision: a small autonomous software agent that grows through
experience rather than merely becoming a larger chatbot — a persistent,
multimodal, tool-using agent runtime with experiential memory, verification,
failure recovery, and self-improvement.

## First major target

> "I can open Baby-Agent, point it at a project, type what I want built, and
> watch it inspect, edit, run, diagnose, fix, and verify the project without
> me manually copying commands or code between the terminal and an LLM."

## One-sentence definition

Baby-Agent is a local-first autonomous software-development system that can
perceive a project and its environment, reason through a goal, use tools to
change and operate the project, verify the result, recover from failures,
remember what it learned, and progressively improve through experience.
