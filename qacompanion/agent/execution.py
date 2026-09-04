"""S35 terminal & execution: structured commands inside the workspace.

Commands run through subprocess with real timeouts that kill the whole
process tree (POSIX killpg / Windows taskkill /T) — a grandchild holding
the stdout pipe must not outlive the kill. Semantics pin (spec s35):

- ok = "the pipeline ran the command": exit 0 / non-zero / timed-out all
  return ok=True with the full CommandResult JSON (exit_code, timed_out,
  stdout, stderr carry the story — the model needs the evidence);
- operational failures (escape, bad cwd, spawn error, pre-dispatch
  cancellation) are ok=False structured errors;
- two timeout layers: inner per-command timeout (default 120s, cap 600s)
  kills the tree; the S32 registry handler timeout (660s) is a backstop;
- shell=True: the agent runs command lines; injection is the permission
  layer's concern (S38 seam demonstrated in tests);
- environment inherited with optional set_env merged (never logged);
- mid-run cancellation is S45 — S35 has the S32 pre-dispatch check only.
"""

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .registry import EXECUTION, RegisteredTool, ToolDefinition, ToolOperationError, ToolRegistry
from .workspace import PathError, Workspace

DEFAULT_COMMAND_TIMEOUT = 120.0
MAX_COMMAND_TIMEOUT = 600.0
MAX_OUTPUT_BYTES = 64 * 1024
REGISTERED_TOOL_TIMEOUT = MAX_COMMAND_TIMEOUT + 60.0
KILL_REAP_GRACE = 2.0


class CommandError(ToolOperationError):
    """Operational failure before/around command execution."""


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


@dataclass
class CommandResult:
    """The structured outcome of one command execution."""

    command: str
    cwd: str
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    timed_out: bool = False
    cancelled: bool = False
    started_at: str = ""
    finished_at: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    pid: Optional[int] = None

    def to_dict(self):
        return {
            "command": self.command,
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
            "cancelled": self.cancelled,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "pid": self.pid,
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("command result record must be an object")
        return cls(
            command=data.get("command", ""),
            cwd=data.get("cwd", "."),
            exit_code=data.get("exit_code"),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            duration_ms=data.get("duration_ms", 0),
            timed_out=bool(data.get("timed_out", False)),
            cancelled=bool(data.get("cancelled", False)),
            started_at=data.get("started_at", ""),
            finished_at=data.get("finished_at", ""),
            stdout_truncated=bool(data.get("stdout_truncated", False)),
            stderr_truncated=bool(data.get("stderr_truncated", False)),
            pid=data.get("pid"),
        )


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the process and its children (tree), best effort."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=5,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        return
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def _cap(text: str) -> tuple:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return text, False
    cut = encoded[:MAX_OUTPUT_BYTES].decode("utf-8", errors="ignore")
    return cut, True


def execute_command(
    workspace: Workspace,
    command: str,
    cwd: str = ".",
    timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT,
    set_env: Optional[Dict[str, str]] = None,
    cancel_event=None,
) -> CommandResult:
    """Run a command line inside the workspace; never raises for run outcomes."""
    if not isinstance(command, str) or not command.strip():
        raise CommandError("command must be a non-empty string")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) \
            or timeout_seconds <= 0:
        raise CommandError("timeout_seconds must be a positive number")
    effective_timeout = min(float(timeout_seconds), MAX_COMMAND_TIMEOUT)
    if cancel_event is not None and cancel_event.is_set():
        now = _utc_stamp()
        return CommandResult(
            command=command, cwd=cwd, cancelled=True,
            started_at=now, finished_at=now,
        )

    try:
        cwd_abs = workspace.resolve(cwd)
    except PathError as exc:
        raise CommandError(str(exc)) from exc
    if not cwd_abs.is_dir():
        raise CommandError(f"cwd is not a directory: {cwd}")

    env = None
    if set_env:
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in set_env.items()})

    popen_kwargs = {}
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True
    else:
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    started_at = _utc_stamp()
    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=str(cwd_abs),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **popen_kwargs,
        )
    except OSError as exc:
        raise CommandError(f"failed to start command: {exc}") from exc

    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=effective_timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=KILL_REAP_GRACE)
        except Exception:
            stdout, stderr = "", ""
    finished_at = _utc_stamp()
    duration_ms = int((time.monotonic() - started) * 1000)

    stdout, stdout_truncated = _cap(stdout or "")
    stderr, stderr_truncated = _cap(stderr or "")
    return CommandResult(
        command=command,
        cwd=workspace.relative(cwd_abs),
        exit_code=proc.returncode,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        timed_out=timed_out,
        cancelled=False,
        started_at=started_at,
        finished_at=finished_at,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        pid=proc.pid,
    )


# --- default command detection (small table; grows later) -----------------

DETECTED_COMMANDS = {
    "run_tests": {
        "python": "python -m unittest",
        "node": "npm test",
        "rust": "cargo test",
        "go": "go test ./...",
    },
    "run_build": {
        "node": "npm run build",
        "rust": "cargo build",
        "go": "go build ./...",
    },
    "run_lint": {
        "node": "npm run lint",
    },
    "run_typecheck": {
        "node": "npm run typecheck",
    },
}


def detect_command(tool_name: str, workspace: Workspace) -> Optional[str]:
    # live re-detect (one scandir): files written after Workspace
    # construction must be visible to detection
    from .workspace import ProjectMetadata

    project_type = ProjectMetadata.detect(workspace.root).project_type
    return DETECTED_COMMANDS.get(tool_name, {}).get(project_type)


class ExecutionToolkit:
    """Binds the five execution tools to one workspace."""

    def __init__(self, workspace: Workspace):
        self.workspace = workspace

    def _run(self, tool_name: str, command: Optional[str], cwd: str,
             timeout_seconds: float, set_env: Optional[Dict[str, str]]) -> str:
        if not command:
            detected = detect_command(tool_name, self.workspace)
            if not detected:
                raise CommandError(
                    f"no {tool_name} command detected for project type "
                    f"{self.workspace.metadata.project_type!r} — pass command explicitly"
                )
            command = detected
        result = execute_command(
            self.workspace,
            command=command,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            set_env=set_env,
        )
        return json.dumps(result.to_dict(), ensure_ascii=False)

    def run_command(self, command: str, cwd: str = ".",
                    timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT,
                    set_env: Optional[Dict[str, str]] = None) -> str:
        return self._run("run_command", command, cwd, timeout_seconds, set_env)

    def run_tests(self, command: Optional[str] = None, cwd: str = ".",
                  timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT,
                  set_env: Optional[Dict[str, str]] = None) -> str:
        return self._run("run_tests", command, cwd, timeout_seconds, set_env)

    def run_build(self, command: Optional[str] = None, cwd: str = ".",
                  timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT,
                  set_env: Optional[Dict[str, str]] = None) -> str:
        return self._run("run_build", command, cwd, timeout_seconds, set_env)

    def run_lint(self, command: Optional[str] = None, cwd: str = ".",
                 timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT,
                 set_env: Optional[Dict[str, str]] = None) -> str:
        return self._run("run_lint", command, cwd, timeout_seconds, set_env)

    def run_typecheck(self, command: Optional[str] = None, cwd: str = ".",
                      timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT,
                      set_env: Optional[Dict[str, str]] = None) -> str:
        return self._run("run_typecheck", command, cwd, timeout_seconds, set_env)

    def tools(self):
        def _tool(name, description, schema, handler):
            return RegisteredTool(
                definition=ToolDefinition(
                    name=name, description=description, parameters_schema=schema
                ),
                handler=handler,
                category="execution",
                side_effect_level=EXECUTION,
                timeout_seconds=REGISTERED_TOOL_TIMEOUT,
                requires_workspace=True,
                cancellable=True,
            )

        command_schema = {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {"type": "string"},
                "timeout_seconds": {"type": "number"},
                "set_env": {"type": "object"},
            },
            "required": [],
        }
        explicit_schema = {
            "type": "object",
            "properties": dict(command_schema["properties"]),
            "required": [],
        }

        return [
            _tool("run_command", "Run a command line in the workspace.",
                  {**command_schema, "required": ["command"]}, self.run_command),
            _tool("run_tests", "Run the project's tests (detected or explicit).",
                  explicit_schema, self.run_tests),
            _tool("run_build", "Build the project (detected or explicit).",
                  explicit_schema, self.run_build),
            _tool("run_lint", "Lint the project (detected or explicit).",
                  explicit_schema, self.run_lint),
            _tool("run_typecheck", "Typecheck the project (detected or explicit).",
                  explicit_schema, self.run_typecheck),
        ]


def update_agent_registry(registry: ToolRegistry, workspace: Workspace) -> None:
    """Register the execution tools into an existing registry."""
    for tool in ExecutionToolkit(workspace).tools():
        registry.register(tool)
