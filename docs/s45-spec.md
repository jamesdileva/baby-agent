# S45 — Process & Runtime Management: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S45. Builds on S31–S44. One slice, stdlib only, no CLI changes.

## Overview

Move beyond one-shot commands: the agent can start a dev server, wait
until it is actually serving, health-check it, read its logs, stop it,
restart it, and detect/recover from crashes — the lifecycle of the
applications it creates. The roadmap end-goal chain
(`start → wait_for_port → health_check → capture_screen`) becomes fully
mechanical (S44 already provides the last step).

## Module layout

```text
qacompanion/agent/processes.py     # ProcessManager + the nine tools
qacompanion/agent/execution.py     # _kill_tree promoted to public
                                   # kill_process_tree (reused here)
tests/test_agent_processes.py
```

## ProcessManager

```text
ProcessManager
    .start(command, cwd, set_env) -> handle "p<N>"
    .stop(handle)                 tree-kill (kill_process_tree), state "stopped"
    .restart(handle)              stop + start same command, NEW handle
    .status(handle)               state: running | exited | stopped
                                  exit_code, uptime_seconds, recent_output
    .list() / .wait(handle, timeout)
    .logs                         bounded ring buffer (500 lines) per process,
                                  fed by daemon reader threads (a dev
                                  server's output must never block on a
                                  full pipe — communicate() semantics do
                                  not apply to long-running processes)
```

States: `running` (poll() is None), `exited` (exit_code recorded — crash
detection is just reading it), `stopped` (killed by the agent). No
auto-restart daemon in S45 — recovery means the agent observes the crash
via `process_status` and calls `restart_process`; auto-supervision is a
documented future item.

## The nine tools (all requires_workspace=True, category "processes")

```text
start_process   {command, cwd?, set_env?}   EXECUTION  (shell=True at the
                                            workspace-resolved cwd)
stop_process    {handle}                    EXECUTION
restart_process {handle}                    EXECUTION
list_processes  {}                          READ_ONLY
process_status  {handle}                    READ_ONLY
wait_for_process{handle, timeout_seconds?}  READ_ONLY
check_port      {port}                      READ_ONLY
wait_for_port   {port, timeout_seconds?}    READ_ONLY
health_check    {url}                       READ_ONLY
```

**The port semantics split (pinned):** `check_port` is a BIND test —
"is this port free?" (`wait_for_port`'s opposite). `wait_for_port` is a
CONNECT poll against 127.0.0.1 — "is my app serving yet?" (ready-state
detection, 0.1 s interval).

**health_check is localhost-only by construction** (host must be
127.0.0.1/localhost) — an HTTP GET that never leaves the machine, so it
is READ_ONLY rather than EXTERNAL, and the dev-loop never nags for
confirmation. Anything remote is `open_url`'s job.

## Testing strategy (tests/test_agent_processes.py)

All hermetic via sys.executable; the fixture is a real tiny HTTP server
script (ThreadingHTTPServer on a port the test reserves with bind-0 then
releases):

- **The roadmap chain**: start_process(server) → wait_for_port (ready
  within timeout) → health_check (200 + expected body) → process_status
  (running, logs contain the startup line) → stop_process →
  wait_for_process (exited) → check_port (available again).
- Restart: stop + restart under a new handle; the new process serves.
- Crash recovery: a script exiting nonzero → status `exited` with
  exit_code → restart_process recovers.
- wait_for_process on a script that exits (exit code captured).
- check_port / wait_for_port: free vs bound port; timeout → ready False.
- Logs: recent_output reflects server output (poll-waited).
- Validation: unknown handle, empty command, non-localhost health_check
  rejected.
- Registration: nine tools, side-effect matrix, agent_registry 32 → 41
  (exact count asserted once, in the combines-all test).

Expected suite growth: 1222 → ~1250 OK.

## Exit criteria (from ROADMAP-agentlite.md §S45)

Test server: start, wait, detect ready state, health check, stop,
restart, recovery from a crashed process — all through registry tools.
Full suite green; preflight clean.
