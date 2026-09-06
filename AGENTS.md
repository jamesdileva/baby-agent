# AGENTS.md — baby-agent

Working conventions for any agent (or human) working in this repo.

## Mission

Build and maintain `qacompanion`: a stdlib-only Python CLI that accumulates a
case base of test failures and their diagnoses. The spec of record is
[docs/spec.md](docs/spec.md) — read it fully before the first commit. The spec
is frozen for v1; propose amendments via DECISION-style writeups before
touching it.

## Standing discipline

1. **Slices, not waves.** One committable slice per cycle: implement, test,
   commit, clean tree before responding.
2. **Tests green or it didn't happen.** `python -m unittest` (or the agreed
   runner) exits 0 before every commit. A red suite is never committed.
3. **Honesty over optics.** If accuracy drops or a change regresses something,
   say so in the cycle summary. Hiding regressions is the cardinal sin of a
   QA tool.
4. **Stdlib only.** No third-party dependencies in v1. No network calls.
5. **Spec is law.** Behavior questions resolve to docs/spec.md. Gaps get
   documented as proposed amendments, not silently filled.

## Verification culture

- Every bug fixed gets a regression test named after its failure mode.
- `accuracy` must be re-runnable at any time; a change that lowers holdout
  accuracy must be justified in the commit message or reverted.
- Fixture-based verification is necessary but not sufficient: exercise real
  failure output when touching capture paths.

## Review protocol

- Reviewer verifies firsthand (run the tests, read the diff) before approving.
- Provenance matters: cite the task/mail/issue that authorized a segment.
- Disputes escalate to the human with evidence, not assertion.

## Human escalation protocol

- Any question, ruling request, or blocked decision that needs the human
  MUST be filed as a QUESTION or TASK mail addressed to `human` — AND
  recorded in docs/DECISIONS.md. A question that lives only in a document
  is invisible to the human and counts as unanswered.
- Mail first, document second. The mail pings; the doc preserves.
- When the human replies by mail, sign the outcome into DECISIONS.md the
  same cycle.

### Case confirmation authority

Routine case confirmations may be signed `confirmed_by` firsthand by either
parent when ALL hold: (a) firsthand reproduction evidence is cited,
(b) the diagnosis introduces no spec.md changes,
(c) both agents concur.

New standing rules derived from lessons ALSO do not require human approval —
the parents hold full teaching authority inside this repo. Document every new
rule in DECISIONS.md (audit trail, not permission slip).

Escalate to `human` teacher review ONLY when: the frozen spec
(docs/spec.md) needs amending, agents dispute and cannot resolve a decision
between themselves, or a problem recurs 3+ times despite agreed fixes.
Everything else is yours to decide — that is what being the teachers means.

## Cycle-end ritual (integration with this tool)

Every working cycle in any repo where qacompanion is deployed:

1. If tests failed: `record` each failure, attempt diagnoses, request teacher
   REVIEW of those diagnoses.
2. Run `qa preflight` before claiming anything is "done."
3. If `cases.jsonl` changed: commit it alongside the slice.
4. Report lookup hits in the cycle summary ("recognized: FAIL(0.0s), case #3")
   so the colony sees the tool earning its keep.

## Worklog

Dated history of landed slices, newest first. Standing cycle ritual
(DECISIONS 2026-09-04): **plan + scope → implement → tests green →
commit + push → worklog entry.**

- 2026-09-05 — **S54 Computer Use** —
  `qacompanion/agent/computer.py`: the heavily restricted GUI
  capability behind a THREE-GATE safety model — explicit allow-list
  (default EMPTY: an unconfigured toolkit is a no-op by construction),
  DESTRUCTIVE+requires_confirmation pipeline guarantee (default engine
  demands confirmation for every single GUI action; denied with no
  confirmer — spec overclaimed DENY, corrected), and per-action
  confirmer. Six tools (click/double_click/move/type/press_keys/
  focus_window); screen observation = S44 capture_screen, app
  launching = S45 start_process (documented reuse). FakeComputerProvider
  action log (hermetic); ctypes SendInput Windows adapter (POSIX =
  structured error); max_actions budget (runaway-clicking protection);
  out-of-bounds coordinates are structured errors, never clamped.
  agent_registry → 65 tools (benchmark lean catalog unchanged). Suite
  1384 → 1396 OK. Spec: docs/s54-spec.md.
- 2026-09-05 — **S53 Browser Abstraction** —
  `qacompanion/agent/browser.py`: BrowserProvider ABC + two adapters —
  FakeBrowserProvider (in-memory page model: registered pages,
  selector-addressable elements, history, click/type/select mutation,
  REAL PNG screenshots via the S44 codec with per-page colors so
  compare_images can verify) and PlaywrightBrowserProvider (sync
  Playwright behind an import guard — activates with `pip install
  playwright && playwright install chromium`, structured error naming
  the fix before that; no binaries download as a side effect). Eight
  EXTERNAL tools (browser_open/back/click/type/scroll/select/
  screenshot/extract — default ASK posture; screenshot is the only
  workspace writer); browser_download covered by S43
  download_artifact (documented deviation). Playwright method mapping
  proven with a mocked module both absent and present.
  agent_registry → 59 tools (benchmark lean catalog unchanged — the
  benchmark doesn't browse). Suite 1363 → 1384 OK. Spec:
  docs/s53-spec.md.
- 2026-09-05 — **S55 slice 5 (native-only prompting + lean catalog +
  head-to-head)** — The bake-off diagnosis became engineering:
  build_system_prompt(native_tools=...) — providers declare capability
  (OllamaProvider(native_tools=...), Gemini class attr; unknown
  providers default textual); the textual protocol is taught ONLY to
  shim models (the conflict is ours, not the models'). Loop gained
  tool_catalog (model-facing subset; registry keeps everything —
  harness can execute tools the model wasn't offered). Benchmark
  offers LEAN_MODEL_CATALOG (12 of 22). Pulled phi4-mini +
  granite3.3:2b; four-way head-to-head, every config tried: ALL FOUR
  FAIL (qwen3:4b turn-timeout at 300s even lean; 3b timeout mid-run
  after 8 honest calls; phi4-mini 0 calls — echoes the SCHEMA as
  arguments, adapter finding recorded; granite 8 calls/7 failures,
  20 min wall). Isolated probes prove plumbing correct — the gap is
  sustained multi-turn reasoning on 2–4B CPU, not plumbing. Passing
  brain remains gemini-3.1-flash-lite native (144s, verified). Local
  revisit: GPU or baby-agent:ep1 distill (S63+, training data teaches
  the protocol general small models lack). Suite 1363 OK. Slice-5
  section: docs/bakeoff-s55.md.
- 2026-09-05 — **S55 slice 3 (ModelRouter) + tool-call diagnosis** —
  Diagnosis of the native-retest zero-tool-call mystery: qwen3:4b emits
  CORRECT native tool calls in an isolated 2-tool probe (10–15s, both
  think modes — Ollama and the model are fine); with the benchmark's
  20-tool catalog it needs 177–300+s/turn on CPU, and the textual
  protocol teaching in the system prompt conflicts with native calling
  (0 native calls when both present). Filed as catalog-weight +
  prompt-conflict engineering (native-only prompting, hierarchical tool
  selection — follow-ups). **ModelRouter landed**:
  deterministic role routing under policy (ordered ModelRoute rules,
  first-match, trigger-driven escalation on failure_count>=2/stuck,
  unknown roles fall back to brain, explain() for dashboards);
  default_router() encodes the human role sketch — local qwen3:4b
  brain, free-Gemini escalation tier only when GEMINI_API_KEY present,
  qwen2.5-coder:3b as the cheap local route. Route is pure policy —
  never calls a model. Suite 1354 → 1363 OK.
- 2026-09-05 — **S55 slice 4 + PASS (native tool-calling adapters)** —
  DECISIONS 2026-09-05: native tool calling is the primary provider
  contract when tools are declared; textual protocol demotes to shim.
  OllamaProvider: /api/chat with structured tools (tools declared ->
  native; absent -> /api/generate textual). GeminiModelProvider:
  function_declarations -> functionCall parts + Gemini-safe schema
  coercion (registry arrays/objects 400'd without items/properties) +
  GEMINI_TIMEOUT env + 503 retry-with-backoff + OLLAMA_NUM_CTX env
  (bridge never set a context window — 23 tool schemas overflowed the
  ~2048 default). **THE BENCHMARK PASSED**: gemini-3.1-flash-lite via
  native function calling completed the defect-fix benchmark
  autonomously — 6 iterations, 144s, calculator.py fixed,
  unit-tests=pass verified, 0 tool failures, 0 interventions. First
  honest pass in project history; the S48 goal condition is closed.
  Native retest of locals: qwen2.5-coder:3b has NO Ollama native tool
  support (0 calls in 25 iterations); qwen3:4b native + num_ctx still
  timeout-prone on CPU (0 calls in 6 iterations, 22 min) — revisit on
  GPU. Bake-off table updated (docs/bakeoff-s55.md). Role sketch
  validated: gemini-3.1-flash-lite = brain for real tasks; local
  qwen models = cheap/routine + vision; loop accepts any provider.
  Suite 1349 → 1354 OK.
- 2026-09-05 — **S55 slice 2 (bake-off)** — Seven-model defect-fix
  bake-off complete (docs/bakeoff-s55.md): every brain failed —
  1.5b faked evidence, 8b too slow, qwen2.5-coder:3b drove 107 tool
  calls but looped without fixing (verifier refused 17x), qwen3:4b
  timed out (think blocks; OLLAMA_THINK=false flag added to the
  bridge), cloud Gemini 503-throttled and lite never emitted a tool
  call. **The finding that reframes the roadmap: the gap is the taught
  textual tool protocol, not the brains** — native tool-calling
  adapters (Ollama structured tools, Gemini function calling) filed as
  the real unlock; textual protocol demoted to compatibility shim.
  Also added: Gemini 503 retry-with-backoff (free tier demand spikes).
  Suite 1349 OK. Follow-ups: native adapters, then ModelRouter (slice
  3) per the human role sketch.
- 2026-09-05 — **S55 slice 1 (model routing & bake-off)** — Research
  (cited in docs/s55-spec.md): Qwen3-4B is the 3–4B class favorite
  ("unusually strong tool-calling priors" — ertas.ai; best small base
  model — distillabs.ai; runs on CPU ~1.5s/turn — r/LocalLLaMA),
  Phi-4-mini the alternative; 30B MoE excluded (17 GB RAM). Spec:
  docs/s55-spec.md — bake-off via the S48 harness (controls 1.5b + 8b,
  challengers qwen3:4b + qwen2.5-coder:3b), role sketch to validate
  (local coder brain / qwen2.5vl vision / free-Gemini escalation).
  Slice 1 landed: **OLLAMA_TIMEOUT** call-time configurable bridge
  timeout (the 8B 180s monkey-patch becomes configuration; reload-free
  env resolution after importlib.reload poisoned cross-module refs) +
  **GeminiModelProvider** (agent loop backend, PLAIN generation per the
  no-billing ruling — distinct from GeminiSearchProvider; the
  escalation/research candidate in the role sketch). Model pulls
  (qwen3:4b, qwen2.5-coder:3b) kicked off in background; bake-off run +
  router are slices 2/3. Suite 1342 → 1349 OK. Spec: docs/s55-spec.md.
- 2026-09-05 — **S52 close-out + live walkthrough** — `qa serve` CLI
  wired (localhost dashboard server, Ctrl+C clean shutdown); Electron
  deferral recorded in ROADMAP §S52. Live browser walkthrough caught a
  real bug: static asset requests were served index.html (module never
  loaded) — fixed with traversal-proof static serving from app/dist
  (content types, SPA fallback). End-to-end from the dashboard UI:
  Start agent -> live SSE feed (21 events) -> session completed;
  qwen2.5-coder:1.5b again tried faking evidence (writing logs.txt) and
  the no-clobber guard refused it twice in the UI context. Honest
  limitation visible: dashboard sessions without verify_command
  complete unverified (S50 records them partial). Suite 1341 → 1342 OK.
- 2026-09-05 — **S52 Desktop UI (API-first; Electron deferred)** —
  `qacompanion/agent/server.py`: the runtime's local API layer in
  STDLIB (ThreadingHTTPServer) — REST (health, session
  start/stop/detail/list, skills, memory, environment) + SSE streaming
  of the S39 event stream with replay-then-live subscribe. Security
  posture: binds 127.0.0.1 only; sessions run the same S37 loop / S38
  engine policy (the UI adds convenience, not authority); unverified
  completions recorded honestly as partial (opt-in verify_command
  builds a real S41 gate). **Server session id IS the agent session
  id** (pre-built AgentSession passed into loop.run) — found via a
  cross-session event-id mismatch. `app/`: Vite+React+TS dashboard
  (goal input, live event feed, session list/summary, stop); npm build
  green; the server serves app/dist at / — open
  http://127.0.0.1:8765/ and watch the agent work. **Electron shell
  deferred** to a packaging follow-up: the browser is the desktop shell
  for now; the API contract is unchanged when it lands. node is NOT a
  Python-suite dependency (npm build is the UI gate). Suite 1332 →
  1341 OK. Spec: docs/s52-spec.md.
- 2026-09-05 — **S51 Skills 2.0** —
  `qacompanion/agent/skills.py`: Skill schema (the exact S51 fields the
  S50 resume seed already follows: name/goal/description/required_tools/
  preconditions/procedure/verification/failure_modes/examples/confidence,
  strict validation, identifier-like names because they map to files) +
  SkillLibrary over skills/agent (TOLERANT loading: one malformed file
  recorded in .errors and skipped — a library must not die on one bad
  entry, unlike strict single-file stores) + deterministic keyword
  retrieval (S47 pattern). Two brain-level tools: skill_find (READ_ONLY
  — surfaces goal/preconditions/procedure/verification for the MODEL to
  follow with its ordinary tools; nothing executes procedures
  programmatically) and skill_teach (SAFE_WRITE — validated, atomic).
  **The S50→S51 loop is closed**: the resume seed
  (resume_interrupted_task.json) loads and is findable. Clarification
  from the human, folded into the miner (S50 follow-up commit): bare
  continuation pings ("continue") are boilerplate by exact match, but a
  SUBSTANTIAL goal-less session (>=100 parts) is now mined with an
  honest placeholder goal + goal-less tag — mid-session continues never
  affected anything (the miner always took the first non-boilerplate
  user text as the goal). agent_registry → 51 tools (exact count once,
  in the combines-all test). Suite 1318 → 1332 OK. Spec:
  docs/s51-spec.md.
- 2026-09-05 — **S50 Learning From Agent Sessions** —
  `qacompanion/agent/session_learning.py`: mechanical outcome
  classification (COMPLETED+first-verify-ok = success, later-verify =
  recovered, FAILED = failed, CANCELLED/unverified = partial —
  human_corrected/unsafe stay unimplemented until intervention tracking
  exists), session_to_experience capture (qa_memory advice harvested
  into diagnosis, actions, tags incl. "unverified"), record_session;
  rule-based Curator delivering the human-directed backlog (greeting
  pings removed, ×321 resume pattern PROMOTED to skill seed
  skills/agent/resume_interrupted_task.json — S51-schema DATA, nothing
  loads it until S51 — and removed from the episodic store); miner
  error→patch enrichment (substantive error lines preferred over bare
  traceback headers, resolution claimed only when a patch follows the
  error); benchmark harness records sessions as experiences (loop stays
  pure). **Live corpus final state: 1,170 sessions → 95 curated
  experiences** (1,062 sessions skipped as boilerplate/trivial — the
  continuation template is now boilerplate at the source, so curator
  and miner no longer fight; the 2 enriched pairs sitting under resume
  goals were traded away deliberately — S62's deeper extraction recovers
  them from the DB). Suite 1306 → 1318 OK. Spec: docs/s50-spec.md.
- 2026-09-05 — **S49 QA Brain Integration** —
  `qacompanion/agent/qa_brain.py`: the architecture payoff — when a tool
  fails, the colony's accumulated QA intelligence is injected into the
  loop AUTOMATICALLY before the model's next action. QABrain: failure
  signature via S2 normalize+canonical -> layered lookup (exact case
  signature via lookup.select -> keyword match via bridge._match_cases
  with punctuation-free end-weighted query terms -> S47 MemoryLayer
  fallback) -> advice {source, case_id, diagnosis, times_seen} appended
  as a system-role message + memory_advice event. **The brain owns
  failure semantics**: failed ToolResults AND the S35 convention
  (run_command ok=True with embedded CommandResult nonzero exit) — the
  loop just asks. Honest silence on no match; degraded stores never
  crash the loop. Read-only brain: no case auto-creation (case-#10
  lore); writing cases is S50's job. Hermeticity lesson repeated twice
  this sprint: MemoryLayer defaults to the repo's REAL cases.jsonl when
  cases_path=None — tests must inject isolated paths. Loop wiring via
  additive AgentLoop(qa_brain=None); agent_registry unchanged (49 — the
  brain is loop-level, not a tool). Suite 1293 → 1306 OK. Spec:
  docs/s49-spec.md.
- 2026-09-05 — **S48 First Autonomous Coding Task** —
  `qacompanion/agent/benchmark.py`: the defect-fix benchmark harness —
  deterministic fixture (calculator.py with one intentional defect +
  failing unittest), natural-language goal (no file names), the S37 loop
  with coding-family tools only (fs/execution/verification/code/memory —
  hermetic by construction), and the S41 plan-verifier gate: COMPLETED
  only when the tests genuinely pass. BenchmarkReport records honest
  metrics from the session + S39 events (files_changed, commands_run,
  tool_failures, recovery_count, verification results,
  intervention_count=0 by construction). **S41 amendment** (found by the
  benchmark): must_contain/must_not_contain now check COMBINED
  stdout+stderr — unittest reports on stderr and stdout-only checks
  missed it. Hermetic success path green (scripted
  inspect→fail→fix→pass→final with full metrics). **Live runs — honest
  failures**: qwen2.5-coder:1.5b never ran a test (0 commands), faked
  evidence via log files, 7 premature-done claims all rejected by the
  verifier, ended on an Ollama timeout; llama3.1:8b made 5 tool-call
  errors and timed out per-request even at 180s (8B on CPU too slow for
  the loop). The harness recorded both runs completely — capability, not
  harness, is the gap (S55: routing to a stronger model; loop accepts
  any provider; free Gemini plain-mode is a candidate adapter). Bridge
  60s HTTP timeout is a hard cap worth making configurable (S55 note).
  **Curation backlog (human-directed, for S50/S56/S62 wherever it fits
  best)**: curation pass over the 99 mined experiences; merge the
  x321 resume pattern ("response interrupted, continue") into a skill;
  drop greeting pings ("hello" x7); deeper marathon-session extraction
  (diagnosis/resolution from surfhop/sentinel/dinner-menu-generator).
  Suite 1288 → 1293 OK. Spec: docs/s48-spec.md.
- 2026-09-05 — **S47.1 opencode Session Mining** — human-directed: "can
  baby-agent learn from my already-made projects?" Located the corpus:
  `~/.local/share/opencode/opencode.db` (8 GB SQLite, SST opencode;
  1,170 sessions / 42.5k messages / 171.7k parts across 21 projects,
  2026-07-30 → now). `qacompanion/agent/opencode_mine.py`: READ-ONLY
  miner (mode=ro) → one Experience per session (goal = first
  non-boilerplate user text part, ordered tool names as actions capped
  at 50, volume counts in context, opencode session id as provenance,
  ProjectMetadata from the project directory when it exists). Curation
  learned the hard way: first import's top "experiences" were antfarm's
  injected kickoff preamble ("SITUATION REPORT…") reinforced x127 —
  fixed with boilerplate detection, word-boundary goal truncation, and
  skipping goal-less sessions. Two measured session shapes drive the
  design: marathon projects (surfhop: 2 sessions / 1,694 messages;
  dinner-menu-generator: 1 session / 2,483) vs turn-spawn antfarm (385
  tiny sessions). **Clean import: 1,170 sessions → 99 experiences (330
  reinforcements, 741 skipped, 0 errors, 19.5s)**; top pattern =
  "response interrupted, continue" x321 (the colony's resume loop).
  experience.jsonl gitignored (runtime artifact, stays local). Suite
  1277 → 1288 OK. Spec: docs/s47-spec.md (S47.1 section).
- 2026-09-04 — **S47 Experience Memory** —
  `qacompanion/agent/experience.py`: Experience record (goal/outcome/
  context/actions/failure/diagnosis/resolution/verification/confidence/
  tags/project metadata, strict validation, JSONL-ready) +
  ExperienceStore (experience.jsonl, QA_EXPERIENCE_FILE override, atomic
  writes, BOM/CRLF tolerance, **recurrence reinforcement**: a repeated
  normalized goal bumps times_seen instead of duplicating) + MemoryLayer
  (unified read over cases/digest/journal/experiences, merged, scored,
  source-labeled; missing stores degrade to empty) + three brain-level
  tools (experience_record SAFE_WRITE, experience_search /
  memory_search READ_ONLY). Retrieval is deterministic keyword scoring
  with times_seen/confidence boosts — semantic upgrade documented for
  S56. agent_registry → 49 tools (exact count asserted once; family
  tests membership-only). Suite 1258 → 1277 OK. Spec: docs/s47-spec.md.
- 2026-09-04 — **S46 Static Code Intelligence** —
  `qacompanion/agent/codeintel.py`: CodeIndex over the workspace with
  three precision-labeled language tiers — Python via real stdlib AST
  (functions/methods with qualified names, classes, module-level
  variables, precise ast.Name/Attribute references, imports, syntax-error
  diagnostics), JavaScript/TypeScript via a documented regex scanner
  (heuristic), generic keyword fallback (labeled); mtime+size caching so
  the index stays correct while the agent edits; walk through PathPolicy
  (exclusions/binaries/caps enforced). Five READ_ONLY tools: code_symbols
  (search + exact definition lookup), code_references, code_imports,
  code_importers (dotted-suffix match), code_diagnostics.
  agent_registry → 46 tools. Two findings fixed honestly: (a) the AST
  visitor initially double-visited every node (unconditional recurse
  after the special-case branches) producing phantom unqualified
  definitions — restructured with an explicit else; variable
  definition-sites are the ONLY is_definition references (a function's
  own name is not a Name node — documented in code and tests); (b) the
  human's GEMINI_API_KEY (setx) leaked into the test process and the
  missing-key tests silently found it — one test even made a REAL
  network call. Fixed properly: provider constructors now take a
  sentinel (explicit api_key=None = definitely no key; omitted = env
  fallback), and toolkit tests resolve providers only inside their
  popped-env contexts. Suite 1238 → 1258 OK. Spec: docs/s46-spec.md.
  NOTE for S55: human has qwen2.5vl:3b pulled locally — candidate local
  vision fallback alongside free-tier Gemini vision.
- 2026-09-04 — **S45 Process & Runtime Management** —
  `qacompanion/agent/processes.py`: ProcessManager owning long-lived
  processes with daemon reader threads feeding bounded log rings (server
  output must never block on a full pipe) and S35 tree-kill (promoted to
  public kill_process_tree) for stops. Nine tools: start/stop/restart
  (EXECUTION), list/status/wait_for_process, check_port / wait_for_port
  (semantic split pinned: bind test = free, connect poll = serving),
  health_check (localhost-only by construction — READ_ONLY, remote is
  open_url's job). Crash detection = honest status reading; recovery =
  the agent calling restart (no auto-supervision daemon in S45). The
  roadmap chain (start server -> wait_for_port -> health_check -> stop ->
  restart -> crash recovery) is proven end-to-end against a real
  ThreadingHTTPServer fixture. agent_registry → 41 tools.
  Suite 1222 → 1238 OK. Spec: docs/s45-spec.md.
- 2026-09-04 — **S44 Vision / Screenshot Analysis** —
  `qacompanion/agent/vision.py`: minimal stdlib PNG codec (encode/decode,
  8-bit RGB filter 0); ctypes GDI acquisition (capture_screen /
  capture_window / capture_region — Windows, POSIX structured error);
  VisionProvider (Fake + Gemini multimodal PLAIN request per the no-
  billing ruling); inspect_image (EXTERNAL — the image leaves the
  machine) + compare_images (READ_ONLY local pixel diff, threshold-based);
  honest side-effect matrix across the five tools. agent_registry → 32
  tools. **Live smoke**: captured the real 1920x1080 screen through GDI,
  encoded via our PNG codec, and gemini-3.1-flash-lite (free) described
  it — recognizing the baby-agent terminal itself. flash-latest/3-flash-
  preview were 503 high-demand; lite is the pinned default.
  Suite 1198 → 1222 OK. Spec: docs/s44-spec.md.
- 2026-09-04 — **S42.1 plain-mode search fallback (human ruling: no
  billing)** — GeminiSearchProvider falls back from grounding-429 to
  plain model knowledge, marked grounded=false / provider gemini:plain /
  no sources; live smoke: web_search through the gated registry path
  (ASK -> confirmer) answered free. The answer itself demonstrated the
  tradeoff (stale version info — extract_page is the recency escape
  hatch). HTTPError bodies now surfaced in errors.
- 2026-09-04 — **S43 URL Context & Retrieval** —
  `qacompanion/agent/webfetch.py`: URL safety policy checked before any
  request (scheme http/https, ports 80/443, EVERY resolved IP must be
  public — loopback/RFC1918/link-local/metadata endpoints unreachable;
  DNS-rebinding residual risk documented); open_url (HTML→text via stdlib
  parser, title/links/20k-char cap), extract_page (query-relevant
  passages), download_artifact (≤10 MB strict cap, atomic, PathPolicy-
  bound, sha256). All EXTERNAL (S38 ASK posture), urllib always mocked in
  tests. agent_registry → 27 tools. Suite 1179 → 1197 OK.
  Spec: docs/s43-spec.md.
- 2026-09-04 — **S42 Web Research** — `qacompanion/agent/websearch.py`:
  WebSearchProvider abstraction; FakeWebSearchProvider (hermetic backbone)
  + GeminiSearchProvider (Google AI Studio generateContent with
  google_search grounding — the human-directed "Google Search with AI"
  provider; activates on GEMINI_API_KEY, defensive parsing, key never
  logged). web_search tool = first EXTERNAL-side-effect tool.
  **Registry default policy is now the S38 engine** (was minimal
  allow-all): EXTERNAL→ASK and DESTRUCTIVE→DENY are the default posture,
  not an opt-in. Suite 1161 → 1179 OK. Spec: docs/s42-spec.md.
- 2026-09-04 — **S41 Verification Engine** —
  `qacompanion/agent/verification.py`: data-driven VerificationPlan /
  VerificationStep / VerificationResult / VerificationReport; sequential
  command steps (BUILD/TEST/LINT/TYPECHECK/RUNTIME/HEALTHCHECK) at the
  workspace root through the S35 executor (timeout, tree-kill, output
  caps inherited); stop-on-first-failure with honest skipped steps (ok=
  None); must_contain / must_not_contain / expect_exit; optional steps.
  `run_verification` registry tool (the model verifies its own work,
  EXECUTION-gated); `plan_verifier` adapts a plan into the S37 loop
  verifier — fail → recover → pass proven end-to-end. GOAL predicates
  stay the S37 seam; REGRESSION is a TEST rerun; VISUAL waits for S44.
  agent_registry → 23 tools (exact-count assertion now lives in ONE test;
  per-family tests assert membership — ends the per-sprint count churn).
  Suite 1143 → 1161 OK. Spec: docs/s41-spec.md.
- 2026-09-04 — **S40 Environment Intelligence** —
  `qacompanion/agent/environment.py`: `get_environment_summary` with
  section filters (os/cpu/memory/gpu/runtimes/package_managers/disk/
  variables) — the roadmap's seven granular tools mapped to sections
  (one prompt surface, S37 lesson). Mismatch check (`requires: {tool:
  min_version}` → satisfied/mismatches) so the agent sees "node >= 20
  unavailable" before retrying unfixable code. Variable metadata is
  names+set-ness only — values never surface (tested). Every collector
  degrades to unknown/null; binaries probed only after shutil.which.
  Suite 1125 → 1143 OK. Spec: docs/s40-spec.md.
- 2026-09-04 — **S39 Event Stream & Observability** —
  `qacompanion/agent/events.py`: Event envelope (seq, uuid, session, Z-stamp,
  type, payload) + EventStream (sync callback subscribers, bounded replay
  history, raising subscribers recorded and never breaking a run). Loop is
  the primary emitter (session_started/state_changed/model_started/
  model_response/tool_requested/completed+failed/file_changed/
  verification_started+completed/recovery_started/failure_detected/
  session_completed+cancelled+failed); registry emits permission_requested/
  granted/denied at the decision point via additive execute() params and
  prefers the engine's decide() so events carry the real rule. Roadmap
  verification: exact ordered event sequence asserted for a scripted run.
  Suite 1109 → 1125 OK. Spec: docs/s39-spec.md.
- 2026-09-04 — **S38 Permission & Safety** — `qacompanion/agent/permissions.py`:
  PermissionPolicy engine (explicit rules w/ args_contains > tool-declared
  requires_confirmation > side-effect-level defaults (DESTRUCTIVE→DENY,
  EXTERNAL→ASK) > fallback w/ DENY-by-default mode) + PermissionDecision
  audit trail; registry confirmer seam (ASK → approvable/deniable, absent =
  safe denial) with decisions normalized to PermissionDecision; loop
  confirmer passthrough; **pipeline guarantee**: a tool's own
  requires_confirmation forces ASK regardless of policy. Git write verbs
  unlocked (S36 deferral resolved): git_add (SAFE_WRITE) + git_commit
  (ASK-gated; nothing-to-commit is an honest no-op — and git prints that
  on stdout, not stderr). agent_registry → 21 tools. Suite 1080 → 1109 OK.
  Spec: docs/s38-spec.md.
- 2026-09-04 — **Live Ollama validation (manual smoke, not committed as
  tests)** — qwen2.5-coder:1.5b re-pulled; the S37 loop ran LIVE end-to-end
  (goal → taught textual tool call → S32 pipeline → atomic write → verifier
  passed → COMPLETED, 2 iterations; hello.txt + files_changed recorded).
  `qa ask` brain restored (grounded, 12 sources). Three fixes landed from
  live findings: S37.1 loop prompt now teaches the textual tool protocol +
  agent-layer parser upgraded to multi-arg `[TOOL: name(k="v", k2="v2")]`
  (S27's single-arg parser couldn't express path/content); S37.2 few-shot
  example added (1.5B model invented its own syntax without one);
  S37.3 redundant availability ping removed from OllamaProvider.generate
  (2x cost/turn, one flaky ping killed the loop). Suite 1076 → 1080 OK.
  Commits 8552b6a, 74bde10, f8299b9.
- 2026-09-04 — **S37 Agent Loop** — `qacompanion/agent/loop.py`: the first
  autonomous reasoning cycle, task-agnostic — goal → model → S32 tool
  pipeline → observation fed back as structured `tool` messages (denials,
  unknown tools, timeouts are observations, never exceptions) → final
  answer. Pluggable verifier (S41 preview): failure enters RECOVERING and
  retries within limits; session gains verification_results (additive).
  Iteration/runtime limits, cancellation, provider errors — every exit a
  terminal state with a reason. Metadata-driven changed-file tracking
  (write-level side effect + JSON path key). The roadmap verification
  sequence (write buggy file → run fails → read error → edit fix → run
  passes → final) passes via FakeModelProvider; feedback provably reaches
  the next model iteration. Suite 1062 → 1076 OK. Spec: docs/s37-spec.md.
- 2026-09-04 — **S36 Git Intelligence** — `qacompanion/agent/git_tools.py`:
  git_status/diff/log/branch over argv-list git (no shell), paths resolved
  through PathPolicy, porcelain v1 parsing (renames with orig_path, C-quoted
  paths incl. UTF-8 octal unquoting, ahead/behind, detached HEAD), \\x1f
  log separators, clean failures (non-repo, missing binary). Write verbs
  (git_add/commit) deliberately deferred to S38 pending confirmation
  enforcement — no autonomous commits. agent_registry → 19 tools.
  Suite 1039 → 1062 OK. Spec: docs/s36-spec.md.
- 2026-09-04 — **S35 Terminal & Execution** — `qacompanion/agent/execution.py`:
  CommandResult (exit_code, capped stdout/stderr with truncation flags,
  duration, Z-stamps, pid, JSONL round-trip); five tools (run_command,
  run_tests, run_build, run_lint, run_typecheck) with metadata-based
  detection table + explicit-command override; tree-kill timeouts (POSIX
  killpg / Windows taskkill /T) proven by a grandchild-holding-stdout test;
  ok="pipeline ran the command" so evidence survives for diagnosis;
  cwd/env/cancellation operational errors structured; agent_registry →
  15 tools. Suite 1017 → 1039 OK. Spec: docs/s35-spec.md.
- 2026-09-04 — **S34 Filesystem Tools** — `qacompanion/agent/fs_tools.py`:
  seven tools (list_directory, read_file, write_file, edit_file, search_code,
  file_exists, file_metadata) bound to the S33 Workspace via
  FilesystemToolkit, all resolving through PathPolicy — boundary escapes and
  excluded paths return structured errors through the S32 pipeline. Atomic
  no-clobber writes (temp + os.replace), unique-match edits, byte-faithful
  reads (BOM stripped for the model, preserved by edit), binary/generated
  awareness in search, ChangeLedger with sha256s per mutation, registry
  ToolOperationError seam for clean structured failures. `agent_registry()`
  = knowledge + filesystem tools. Suite 979 → 1017 OK. Spec: docs/s34-spec.md.
- 2026-09-04 — **S33 Workspace Abstraction** — `qacompanion/agent/workspace.py`:
  PathPolicy layered containment (strict ".." ban, symlink-following resolve,
  normcase containment vs root + allowed paths, exclusion prefixes,
  protected system locations — Windows `C:\Windows`-class and POSIX `/etc`-class),
  Workspace (root/cwd/git_root/metadata/config), WorkspaceManager (normcase
  cache + active), ProjectMetadata (languages/package-managers-from-lockfiles/
  entrypoints/project_type). Integrates S32's `requires_workspace` gate.
  Suite 932 → 979 OK (symlink tests skip honestly without OS symlink
  privilege). Spec: docs/s33-spec.md.
- 2026-09-04 — **S32 Tool Registry v2** — `qacompanion/agent/registry.py`:
  RegisteredTool metadata (side_effect_level, timeout, cancellable,
  requires_workspace/confirmation), ordered execution pipeline (lookup →
  strict mini-validation → permission seam → workspace gate → cancellation →
  timeout execution → audit hook), every stage failure a structured
  ToolResult; ToolResult gains timed_out/cancelled flags (additive);
  default_knowledge_registry() serves case_search/doc_grep/journal_read
  unchanged. Suite 891 → 932 OK. Spec: docs/s32-spec.md.
- 2026-09-04 — housekeeping — removed docs/DRAFT_decisions-fhm.md (human-
  directed: belongs to another project, not this repo's decision log).
- 2026-09-04 — **S31 Agent Foundation** — `qacompanion/agent/` subpackage
  (contracts.py / providers.py / session.py): ModelProvider abstraction with
  FakeModelProvider (deterministic test backbone) + OllamaProvider (wraps S26
  bridge, normalizes textual [TOOL: ...] output into structured ToolCalls),
  AgentSession state machine (10 states, terminal states final), AgentConfig
  limits, knowledge-tool ToolDefinitions. `qa ask` unchanged. Suite 828 →
  891 OK (hermetic; live Ollama opt-in via QA_OLLAMA_LIVE=1). Spec:
  docs/s31-spec.md. Roadmap: docs/ROADMAP-agentlite.md §S31.
- 2026-09-04 — **Roadmap consolidation + case #10 fix** — Agent-Lite
  roadmap consolidated into docs/ROADMAP-agentlite.md (S31–S65+), DECISIONS
  rulings filed (renumbering, constraints amendment), audit.md superseded;
  fixed pre-existing red test: no-Ollama fallback now surfaces digest
  matches, digest ask test made hermetic (828 OK).
