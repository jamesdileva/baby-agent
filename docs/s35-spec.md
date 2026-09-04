# S35 — Terminal & Execution: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S35. Builds on S31–S34. One slice, purely additive, stdlib only.

## Overview

Structured command execution: the agent builds and tests projects without
the user operating a terminal. Commands run inside the workspace boundary,
under real timeouts that kill the whole process tree, returning a
`CommandResult` whose stdout/stderr survive for diagnosis.

## Module layout

```text
qacompanion/agent/execution.py      # CommandResult, executor, ExecutionToolkit
tests/test_agent_execution.py
```

## CommandResult

```text
command, cwd (posix-rel), exit_code, stdout, stderr,
duration_ms, timed_out, cancelled,
started_at, finished_at (UTC Z stamps),
stdout_truncated, stderr_truncated, pid
```

`to_dict`/`from_dict` (JSONL-ready — S50 trajectory capture consumes these).
Output caps: MAX_OUTPUT_BYTES = 64 KB per stream (excess dropped, truncated
flag set).

## Execution semantics (pinned)

- **ok = "the pipeline ran the command"**, not "the command succeeded".
  Every completed run — exit 0, non-zero, or timed-out — returns
  `ok=True` with the full CommandResult JSON as output; `exit_code`,
  `timed_out`, `cancelled` fields carry the story. Rationale: the model
  needs stdout/stderr to diagnose; masking them as ok=False/error would
  hide the evidence. Only *operational* failures are `ok=False`:
  escape attempts, missing/invalid cwd, spawn errors, pre-dispatch
  cancellation.
- **Two timeout layers**: inner per-command `timeout_seconds` (arg,
  default 120, capped at MAX_COMMAND_TIMEOUT = 600) kills the process tree
  and returns partial output with `timed_out: true`; the S32 registry
  handler timeout (set to 660) remains a backstop.
- **Process-tree kill**: POSIX — `start_new_session=True` + `killpg`;
  Windows — `CREATE_NEW_PROCESS_GROUP` + `taskkill /F /T`. Without this,
  a grandchild holding the stdout pipe would outlive the kill.
- **Shell**: `shell=True` (the agent runs command *lines*); injection is
  the permission layer's concern (S38), demonstrated via the existing
  PermissionPolicy seam inspecting `arguments["command"]`.
- **Environment**: inherited, with an optional `set_env` dict merged in
  (never logged).
- **cwd**: optional relative directory resolved through PathPolicy.
- **Mid-run cancellation** stays out of S35 (pre-dispatch check via the
  S32 cancel_event only); real process lifecycle management is S45.

## The five tools (ExecutionToolkit)

All: category "execution", side_effect EXECUTION, requires_workspace=True,
cancellable, registered timeout 660s.

- **run_command** `{command, cwd?, timeout_seconds?, set_env?}` — the core.
- **run_tests / run_build / run_lint / run_typecheck** `{command?, cwd?, ...}` —
  policy-named entry points. With an explicit `command` they behave exactly
  like run_command. Without one, they try metadata-based detection from the
  S33 ProjectMetadata (`python -m unittest` / `npm test` / `cargo test` /
  `go test ./...`, `npm run build`, etc. — small table, grows later); no
  detection → structured error naming the fix ("pass command explicitly").

`agent_registry()` grows to 15 tools (3 knowledge + 7 filesystem + 5
execution).

## Testing strategy (tests/test_agent_execution.py)

All hermetic via `sys.executable` — no reliance on npm/cargo/network; test
scripts are written into the temp workspace (child spawning, large output,
sleep) instead of fragile shell quoting.

- Success: exit 0, stdout captured, stamps/duration/pid present.
- Non-zero exit: exit_code 3 with stdout AND stderr captured, ok=True.
- stderr-only failure output captured.
- Large output: 200 KB → truncated flags, capped length.
- Timeout: 5 s command, 0.5 s timeout → timed_out, duration < 4 s.
- **Tree kill**: parent spawns a sleeping child holding stdout; 0.5 s
  timeout → duration < 4 s (a single-process kill would block ~5 s).
- Child spawn (normal completion): parent + child output both captured.
- cwd: recorded posix-rel; command observes the directory; escape and
  missing cwd are structured operational errors.
- set_env merged into environment.
- Cancellation: pre-set cancel_event → ok=False, cancelled, command never
  ran (probe file absent).
- Detection table: unit-tested per project_type; no-detection → structured
  error; explicit command on a wrapper executes like run_command.
- CommandResult round-trip; registry gate; permission policy denying a
  command prefix via the S32 seam.
- Registration: five tools, EXECUTION level; agent_registry = 15.

Expected suite growth: 1017 → ~1060 OK.

## Exit criteria (from ROADMAP-agentlite.md §S35)

Controlled commands that succeed, fail, time out, produce stderr, produce
large output, spawn children, and are cancelled — all return structured
results; nothing executes outside workspace policy without permission.
Full suite green; preflight clean.
