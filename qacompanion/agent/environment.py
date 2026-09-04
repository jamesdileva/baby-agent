"""S40 environment intelligence: know the machine before blaming the code.

One tool, get_environment_summary, with section filters (the roadmap's
seven granular tools map to sections — one prompt surface, same
capability). Every collector degrades to "unknown"/null on failure; no
collector can crash the summary. Environment-variable METADATA only:
names and set-ness, never values — no exceptions.

Pins (fixtures-first discipline):
- binaries are probed only after shutil.which finds them (2 s timeout);
- GPU is reported only with evidence (nvidia-smi present);
- version comparison is honest-simple: leading numeric tuple prefix.
"""

import ctypes
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from typing import Any, Dict, List, Optional

from .registry import READ_ONLY, RegisteredTool, ToolDefinition, ToolOperationError, ToolRegistry
from .workspace import Workspace

PROBE_TIMEOUT = 2.0
SECTIONS = ("os", "cpu", "memory", "gpu", "runtimes", "package_managers",
            "disk", "variables")

RUNTIME_BINARIES = ("node", "npm", "pnpm", "yarn", "git", "java", "rustc", "go")
PACKAGE_MANAGERS = ("pip", "uv", "poetry", "npm", "pnpm", "yarn", "cargo", "go")
WATCHED_VARIABLES = (
    "PATH", "HOME", "USERPROFILE", "VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME",
    "OLLAMA_MODEL", "OLLAMA_URL", "JAVA_HOME", "NODE_ENV", "GIT_DIR",
    "HTTP_PROXY", "HTTPS_PROXY",
)


def _probe_version(binary: str) -> Optional[str]:
    """--version probe for a binary known to exist. None on any failure."""
    exe = shutil.which(binary)
    if exe is None:
        return None
    try:
        proc = subprocess.run(
            [exe, "--version"], capture_output=True, timeout=PROBE_TIMEOUT,
            text=True, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (proc.stdout or proc.stderr or "").strip()
    return output.splitlines()[0][:120] if output else None


def _memory_windows() -> Optional[Dict[str, int]]:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return {"total_bytes": stat.ullTotalPhys,
                    "available_bytes": stat.ullAvailPhys}
    except Exception:
        pass
    return None


def _memory_linux() -> Optional[Dict[str, int]]:
    try:
        with open("/proc/meminfo", "r", encoding="ascii") as fh:
            info = {}
            for line in fh:
                key, _, rest = line.partition(":")
                parts = rest.split()
                if parts:
                    info[key.strip()] = int(parts[0]) * 1024
        if "MemTotal" in info:
            return {"total_bytes": info["MemTotal"],
                    "available_bytes": info.get("MemAvailable")}
    except (OSError, ValueError):
        pass
    return None


def collect_os() -> Dict[str, Any]:
    return {"os": {
        "system": platform.system() or None,
        "release": platform.release() or None,
        "version": platform.version() or None,
        "machine": platform.machine() or None,
        "hostname": socket.gethostname(),
        "python": sys.version.split()[0],
    }}


def collect_cpu() -> Dict[str, Any]:
    return {"cpu": {
        "count": os.cpu_count(),
        "processor": platform.processor() or None,
    }}


def collect_memory() -> Dict[str, Any]:
    if os.name == "nt":
        info = _memory_windows()
    else:
        info = _memory_linux()
    return {"memory": info or "unknown"}


def collect_gpu() -> Dict[str, Any]:
    if shutil.which("nvidia-smi") is None:
        return {"gpu": None}
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, timeout=PROBE_TIMEOUT,
            text=True, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"gpu": None}
    names = [line.strip() for line in (proc.stdout or "").splitlines()
             if line.strip()]
    return {"gpu": names[0] if names else None}


def collect_runtimes() -> Dict[str, Any]:
    runtimes = {"python": ".".join(str(p) for p in sys.version_info[:3])}
    for binary in RUNTIME_BINARIES:
        runtimes[binary] = _probe_version(binary)
    return {"runtimes": runtimes}


def collect_package_managers() -> Dict[str, Any]:
    return {"package_managers": {
        name: shutil.which(name) is not None for name in PACKAGE_MANAGERS
    }}


def collect_disk(workspace: Workspace) -> Dict[str, Any]:
    try:
        usage = shutil.disk_usage(str(workspace.root))
        return {"disk": {"total_bytes": usage.total, "free_bytes": usage.free,
                         "used_bytes": usage.used}}
    except OSError:
        return {"disk": "unknown"}


def collect_variables() -> Dict[str, Any]:
    # names + set-ness ONLY — values never leave the environment
    return {"variables": [
        {"name": name, "set": name in os.environ}
        for name in WATCHED_VARIABLES
    ]}


def probe_ports(ports: List[int]) -> Dict[str, Any]:
    results = []
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", port))
            available = True
        except OSError:
            available = False
        finally:
            sock.close()
        results.append({"port": port, "available": available})
    return {"ports": results}


def _version_tuple(version: str) -> Optional[tuple]:
    match = re.search(r"\d+(\.\d+)*", version or "")
    if not match:
        return None
    return tuple(int(part) for part in match.group(0).split("."))


def find_mismatches(requires: Dict[str, str]) -> List[Dict[str, Any]]:
    """Compare required minimum versions against probed runtimes."""
    mismatches = []
    probeable = set(RUNTIME_BINARIES) | {"python"}
    for tool, required in requires.items():
        if tool == "python":
            found_version = ".".join(str(p) for p in sys.version_info[:3])
        elif tool in probeable:
            found_version = _probe_version(tool)
        else:
            found_version = None
        required_tuple = _version_tuple(required)
        found_tuple = _version_tuple(found_version) if found_version else None
        if found_tuple is None:
            mismatches.append({"tool": tool, "required": required,
                               "found": found_version})
        elif required_tuple is not None and found_tuple < required_tuple:
            mismatches.append({"tool": tool, "required": required,
                               "found": found_version})
    return mismatches


class EnvironmentToolkit:
    """Binds get_environment_summary to one workspace."""

    def __init__(self, workspace: Workspace):
        self.workspace = workspace

    def get_environment_summary(self, section: Optional[str] = None,
                                requires: Optional[Dict[str, str]] = None,
                                check_ports: Optional[List[int]] = None) -> str:
        sections = {
            "os": lambda: collect_os(),
            "cpu": lambda: collect_cpu(),
            "memory": lambda: collect_memory(),
            "gpu": lambda: collect_gpu(),
            "runtimes": lambda: collect_runtimes(),
            "package_managers": lambda: collect_package_managers(),
            "disk": lambda: collect_disk(self.workspace),
            "variables": lambda: collect_variables(),
        }
        if section is not None and section not in sections:
            raise ToolOperationError(
                f"unknown section: {section!r} (known: {', '.join(sections)})"
            )
        payload: Dict[str, Any] = {}
        if section is not None:
            payload.update(sections[section]())
        else:
            for collector in sections.values():
                payload.update(collector())
        if requires:
            mismatches = find_mismatches(requires)
            payload["requires"] = dict(requires)
            payload["mismatches"] = mismatches
            payload["satisfied"] = not mismatches
        if check_ports:
            payload.update(probe_ports(check_ports))
        return json.dumps(payload, ensure_ascii=False)

    def tools(self) -> List[RegisteredTool]:
        return [RegisteredTool(
            definition=ToolDefinition(
                name="get_environment_summary",
                description="Machine/workspace environment: os, cpu, memory, "
                            "gpu, runtimes, package managers, disk, "
                            "variables (names only). Optional version "
                            "mismatch check.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "section": {"type": "string"},
                        "requires": {"type": "object"},
                        "check_ports": {"type": "array"},
                    },
                    "required": [],
                },
            ),
            handler=self.get_environment_summary,
            category="environment",
            side_effect_level=READ_ONLY,
            requires_workspace=True,
        )]


def update_agent_registry(registry: ToolRegistry, workspace: Workspace) -> None:
    """Register the environment tools into an existing registry."""
    for tool in EnvironmentToolkit(workspace).tools():
        registry.register(tool)
