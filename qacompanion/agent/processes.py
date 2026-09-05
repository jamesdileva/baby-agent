"""S45 process & runtime management: lifecycle for the apps the agent builds.

ProcessManager runs long-lived processes (dev servers, watchers) with
daemon reader threads feeding bounded log rings — a chatty server must
never block on a full pipe, so communicate() semantics deliberately do
NOT apply here. Stopping reuses the S35 tree-kill (POSIX killpg / Windows
taskkill /T) so grandchildren die with the server.

Port semantics are pinned and opposite in direction:
- check_port    = BIND test    -> "is this port free?"
- wait_for_port = CONNECT poll -> "is my app serving yet?"

health_check is localhost-only by construction (host allowlist), a GET
that never leaves the machine — READ_ONLY, and the dev loop never nags
for confirmation. Remote fetches are open_url's job.

Pins (fixtures-first discipline):
- every failure is a structured ProcessError (ToolOperationError);
- crash detection is honest reading: status `exited` + exit_code —
  recovery is the agent calling restart_process (no auto-supervision
  daemon in S45);
- handles are manager-local ("p1", "p2", ...), never PIDs.
"""

import json
import os
import socket
import subprocess
import threading
import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .execution import EXECUTION, kill_process_tree
from .registry import READ_ONLY, RegisteredTool, ToolDefinition, ToolOperationError, ToolRegistry
from .workspace import PathError, Workspace

LOG_RING_LINES = 500
STATUS_OUTPUT_LINES = 30
PORT_POLL_INTERVAL = 0.1
DEFAULT_WAIT_TIMEOUT = 30.0
LOCAL_HOSTS = ("localhost", "127.0.0.1")


class ProcessError(ToolOperationError):
    """Structured process-management failure."""


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def port_available(port: int) -> bool:
    """BIND test: True when nothing is listening on 127.0.0.1:port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def port_serving(port: int) -> bool:
    """CONNECT test: True when something accepts on 127.0.0.1:port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        return sock.connect_ex(("127.0.0.1", port)) == 0
    finally:
        sock.close()


def wait_for_port_serving(port: int, timeout_seconds: float
                          ) -> Tuple[bool, int]:
    started = time.monotonic()
    deadline = started + timeout_seconds
    while time.monotonic() < deadline:
        if port_serving(port):
            return True, int((time.monotonic() - started) * 1000)
        time.sleep(PORT_POLL_INTERVAL)
    return False, int((time.monotonic() - started) * 1000)


@dataclass
class ManagedProcess:
    handle: str
    command: str
    cwd: str
    started_monotonic: float
    started_at: str
    proc: Any = None  # subprocess.Popen
    logs: deque = field(default_factory=lambda: deque(maxlen=LOG_RING_LINES))
    state: str = "running"  # running | exited | stopped
    exit_code: Optional[int] = None

    def refresh(self) -> None:
        if self.state == "running" and self.proc is not None:
            code = self.proc.poll()
            if code is not None:
                self.state = "exited"
                self.exit_code = code


class ProcessManager:
    """Owns the agent's long-lived processes (handles are manager-local)."""

    def __init__(self):
        self._processes: Dict[str, ManagedProcess] = {}
        self._counter = 0

    def _next_handle(self) -> str:
        self._counter += 1
        return f"p{self._counter}"

    def start(self, command: str, cwd: str,
              set_env: Optional[Dict[str, str]] = None) -> ManagedProcess:
        env = None
        if set_env:
            env = dict(os.environ)
            env.update({str(k): str(v) for k, v in set_env.items()})

        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # one merged stream: server logs
            text=True,
            encoding="utf-8",
            errors="replace",
            **({} if os.name == "nt" else {"start_new_session": True}),
        )
        handle = self._next_handle()
        managed = ManagedProcess(
            handle=handle, command=command, cwd=cwd,
            started_monotonic=time.monotonic(), started_at=_utc_stamp(),
            proc=proc,
        )
        self._processes[handle] = managed

        def reader(managed=managed):
            try:
                for line in iter(managed.proc.stdout.readline, ""):
                    if line.strip():
                        managed.logs.append(line.rstrip("\n"))
            except Exception:
                pass  # process died or stream closed: status reflects it

        threading.Thread(target=reader, daemon=True).start()
        return managed

    def get(self, handle: str) -> ManagedProcess:
        managed = self._processes.get(handle)
        if managed is None:
            raise ProcessError(f"unknown process handle: {handle!r}")
        managed.refresh()
        return managed

    def stop(self, handle: str) -> ManagedProcess:
        managed = self.get(handle)
        if managed.state == "running":
            kill_process_tree(managed.proc)
            managed.proc.wait(timeout=10)
            managed.state = "stopped"
            managed.exit_code = managed.proc.returncode
        return managed

    def restart(self, handle: str, cwd_override: Optional[str] = None,
                ) -> ManagedProcess:
        old = self.get(handle)
        command, cwd = old.command, cwd_override or old.cwd
        set_env = None  # restarts reuse the environment as-started
        self.stop(handle)
        return self.start(command, cwd, set_env)

    def list(self) -> List[ManagedProcess]:
        for managed in self._processes.values():
            managed.refresh()
        return list(self._processes.values())

    def wait(self, handle: str, timeout_seconds: float) -> ManagedProcess:
        managed = self.get(handle)
        if managed.state == "running" and managed.proc is not None:
            try:
                code = managed.proc.wait(timeout=timeout_seconds)
                managed.state = "exited"
                managed.exit_code = code
            except subprocess.TimeoutExpired:
                pass  # still running: honest status
        return managed


def _recent_logs(managed: ManagedProcess) -> List[str]:
    return list(managed.logs)[-STATUS_OUTPUT_LINES:]


class ProcessToolkit:
    """Binds the nine process tools to one workspace + manager."""

    def __init__(self, workspace: Workspace,
                 manager: Optional[ProcessManager] = None):
        self.workspace = workspace
        self.manager = manager or ProcessManager()

    def _resolve_cwd(self, cwd: str) -> str:
        try:
            return str(self.workspace.resolve(cwd or "."))
        except PathError as exc:
            raise ProcessError(str(exc)) from exc

    def start_process(self, command: str, cwd: str = ".",
                      set_env: Optional[Dict[str, str]] = None) -> str:
        if not isinstance(command, str) or not command.strip():
            raise ProcessError("command must be a non-empty string")
        managed = self.manager.start(
            command, cwd=self._resolve_cwd(cwd), set_env=set_env)
        return json.dumps({
            "handle": managed.handle,
            "command": managed.command,
            "cwd": managed.cwd,
            "pid": managed.proc.pid,
            "state": managed.state,
        }, ensure_ascii=False)

    def stop_process(self, handle: str) -> str:
        managed = self.manager.stop(handle)
        return json.dumps({
            "handle": managed.handle, "state": managed.state,
            "exit_code": managed.exit_code,
        }, ensure_ascii=False)

    def restart_process(self, handle: str) -> str:
        fresh = self.manager.restart(handle)
        return json.dumps({
            "handle": fresh.handle,
            "restarted_from": handle,
            "command": fresh.command,
            "pid": fresh.proc.pid,
            "state": fresh.state,
        }, ensure_ascii=False)

    def list_processes(self) -> str:
        return json.dumps({"processes": [
            {"handle": m.handle, "command": m.command, "state": m.state,
             "exit_code": m.exit_code}
            for m in self.manager.list()
        ]}, ensure_ascii=False)

    def process_status(self, handle: str) -> str:
        m = self.manager.get(handle)
        return json.dumps({
            "handle": m.handle,
            "command": m.command,
            "state": m.state,
            "exit_code": m.exit_code,
            "uptime_seconds": round(time.monotonic() - m.started_monotonic, 1),
            "started_at": m.started_at,
            "recent_output": _recent_logs(m),
        }, ensure_ascii=False)

    def wait_for_process(self, handle: str,
                         timeout_seconds: float = DEFAULT_WAIT_TIMEOUT) -> str:
        m = self.manager.wait(handle, timeout_seconds)
        return json.dumps({
            "handle": m.handle, "state": m.state, "exit_code": m.exit_code,
        }, ensure_ascii=False)

    def check_port(self, port: int) -> str:
        _require_port(port)
        return json.dumps({"port": port,
                           "available": port_available(port)})

    def wait_for_port(self, port: int,
                      timeout_seconds: float = DEFAULT_WAIT_TIMEOUT) -> str:
        _require_port(port)
        ready, waited_ms = wait_for_port_serving(port, timeout_seconds)
        return json.dumps({"port": port, "ready": ready,
                           "waited_ms": waited_ms})

    def health_check(self, url: str) -> str:
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http",):
            raise ProcessError("health_check scheme must be http")
        if (parsed.hostname or "").lower() not in LOCAL_HOSTS:
            raise ProcessError(
                "health_check is localhost-only — use open_url for remote"
            )
        port = parsed.port or 80
        started = time.monotonic()
        try:
            with urllib.request.urlopen(url, timeout=5.0) as resp:
                status = resp.status
                body = resp.read(500).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = ""
        except (urllib.error.URLError, OSError) as exc:
            return json.dumps({"url": url, "ok": False,
                               "error": str(exc)[:200],
                               "response_ms": int(
                                   (time.monotonic() - started) * 1000)})
        return json.dumps({
            "url": url, "ok": status == 200, "status": status,
            "body_prefix": body[:200],
            "response_ms": int((time.monotonic() - started) * 1000),
        }, ensure_ascii=False)

    def tools(self) -> List[RegisteredTool]:
        def _tool(name, description, schema, handler, side_effect):
            return RegisteredTool(
                definition=ToolDefinition(
                    name=name, description=description,
                    parameters_schema=schema),
                handler=handler,
                category="processes",
                side_effect_level=side_effect,
                requires_workspace=True,
            )

        return [
            _tool("start_process", "Start a long-lived process (dev server, "
                  "watcher); returns a handle.",
                  {"type": "object",
                   "properties": {"command": {"type": "string"},
                                  "cwd": {"type": "string"},
                                  "set_env": {"type": "object"}},
                   "required": ["command"]},
                  self.start_process, EXECUTION),
            _tool("stop_process", "Stop a managed process (tree-kill).",
                  {"type": "object",
                   "properties": {"handle": {"type": "string"}},
                   "required": ["handle"]},
                  self.stop_process, EXECUTION),
            _tool("restart_process", "Stop and start the same command under "
                  "a new handle.",
                  {"type": "object",
                   "properties": {"handle": {"type": "string"}},
                   "required": ["handle"]},
                  self.restart_process, EXECUTION),
            _tool("list_processes", "All managed processes and their states.",
                  {"type": "object", "properties": {}, "required": []},
                  self.list_processes, READ_ONLY),
            _tool("process_status", "State, uptime, and recent output of "
                  "one managed process.",
                  {"type": "object",
                   "properties": {"handle": {"type": "string"}},
                   "required": ["handle"]},
                  self.process_status, READ_ONLY),
            _tool("wait_for_process", "Wait for a managed process to exit.",
                  {"type": "object",
                   "properties": {"handle": {"type": "string"},
                                  "timeout_seconds": {"type": "number"}},
                   "required": ["handle"]},
                  self.wait_for_process, READ_ONLY),
            _tool("check_port", "Is this localhost port free? (bind test)",
                  {"type": "object",
                   "properties": {"port": {"type": "integer"}},
                   "required": ["port"]},
                  self.check_port, READ_ONLY),
            _tool("wait_for_port", "Wait until something accepts on this "
                  "localhost port (ready-state detection).",
                  {"type": "object",
                   "properties": {"port": {"type": "integer"},
                                  "timeout_seconds": {"type": "number"}},
                   "required": ["port"]},
                  self.wait_for_port, READ_ONLY),
            _tool("health_check", "HTTP GET a localhost URL (dev servers "
                  "only) and report status/body.",
                  {"type": "object",
                   "properties": {"url": {"type": "string"}},
                   "required": ["url"]},
                  self.health_check, READ_ONLY),
        ]


def _require_port(port: int) -> None:
    if isinstance(port, bool) or not isinstance(port, int) \
            or not (0 < port < 65536):
        raise ProcessError("port must be an integer in (0, 65536)")


def update_agent_registry(registry: ToolRegistry, workspace: Workspace) -> None:
    """Register the process tools into an existing registry."""
    for tool in ProcessToolkit(workspace).tools():
        registry.register(tool)
