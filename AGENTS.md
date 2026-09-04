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
