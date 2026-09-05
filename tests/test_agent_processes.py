"""S45 process & runtime management tests: the roadmap lifecycle chain.

Hermetic: the fixture server is a real ThreadingHTTPServer run via
sys.executable on a port the test reserves (bind-0) then releases.
"""

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from qacompanion.agent import ToolCall, ToolRegistry, Workspace
from qacompanion.agent.fs_tools import agent_registry
from qacompanion.agent.processes import (
    ProcessError,
    ProcessToolkit,
    port_available,
    port_serving,
)

EXE = f'"{sys.executable}"'

SERVER_SCRIPT = """
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
port = int(sys.argv[1])
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"app": "baby-smoke", "path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, fmt, *args):
        print("SERVER-LOG:", fmt % args, flush=True)
print("SERVER-STARTED", flush=True)
ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""

CRASH_SCRIPT = """
import sys
print("about to crash", flush=True)
sys.exit(7)
"""


class ProcessTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.toolkit = ProcessToolkit(self.ws)
        self.reg = ToolRegistry()
        for tool in self.toolkit.tools():
            self.reg.register(tool)
        # reserve a free port, release it, hand it to the fixture server
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        sock.close()
        (self.tmp / "server.py").write_text(SERVER_SCRIPT, encoding="utf-8")
        (self.tmp / "crash.py").write_text(CRASH_SCRIPT, encoding="utf-8")

    def tearDown(self):
        for managed in self.toolkit.manager.list():
            try:
                self.toolkit.manager.stop(managed.handle)
            except Exception:
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, name, confirmer=None, **arguments):
        return self.reg.execute(ToolCall(name=name, arguments=arguments),
                                workspace=self.ws, confirmer=confirmer)

    def payload(self, name, **arguments):
        out = self.call(name, **arguments)
        self.assertTrue(out.ok, f"{name} failed: {out.error}")
        return json.loads(out.output)

    def wait_until(self, condition, timeout=10.0, interval=0.1):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return True
            time.sleep(interval)
        return False


class TestRoadmapChain(ProcessTestBase):
    """start -> wait_for_port -> health_check -> status -> stop -> port free."""

    def test_full_lifecycle_chain(self):
        started = self.payload("start_process",
                               command=f"{EXE} server.py {self.port}")
        handle = started["handle"]
        self.assertTrue(handle.startswith("p"))
        self.assertEqual(started["state"], "running")

        ready = self.payload("wait_for_port", port=self.port,
                             timeout_seconds=10)
        self.assertTrue(ready["ready"])

        health = self.payload("health_check",
                              url=f"http://127.0.0.1:{self.port}/health")
        self.assertTrue(health["ok"])
        self.assertEqual(health["status"], 200)
        self.assertIn("baby-smoke", health["body_prefix"])

        status = self.payload("process_status", handle=handle)
        self.assertEqual(status["state"], "running")
        self.assertGreater(status["uptime_seconds"], 0)
        joined = " ".join(status["recent_output"])
        self.assertTrue(
            self.wait_until(lambda: "SERVER-STARTED" in " ".join(
                self.payload("process_status", handle=handle)
                ["recent_output"])))

        stopped = self.payload("stop_process", handle=handle)
        self.assertEqual(stopped["state"], "stopped")

        exited = self.payload("wait_for_process", handle=handle,
                              timeout_seconds=5)
        self.assertIn(exited["state"], ("stopped", "exited"))

        self.assertTrue(
            self.wait_until(lambda: port_available(self.port)))

    def test_health_check_reflects_server_path(self):
        self.payload("start_process", command=f"{EXE} server.py {self.port}")
        self.payload("wait_for_port", port=self.port, timeout_seconds=10)
        health = self.payload("health_check",
                              url=f"http://127.0.0.1:{self.port}/some/path")
        self.assertIn("/some/path", health["body_prefix"])


class TestRestartAndCrashRecovery(ProcessTestBase):
    def test_crash_detected_then_restart_recovers(self):
        started = self.payload("start_process", command=f"{EXE} crash.py")
        handle = started["handle"]
        exited = self.payload("wait_for_process", handle=handle,
                              timeout_seconds=10)
        self.assertEqual(exited["state"], "exited")
        self.assertEqual(exited["exit_code"], 7)
        status = self.payload("process_status", handle=handle)
        self.assertIn("about to crash", " ".join(status["recent_output"]))

        restarted = self.payload("restart_process", handle=handle)
        self.assertNotEqual(restarted["handle"], handle)
        # a crashed script crashes again: restart still yields a live
        # process handle that then exits with the same code
        reread = self.payload("wait_for_process",
                              handle=restarted["handle"], timeout_seconds=10)
        self.assertEqual(reread["exit_code"], 7)

    def test_server_restart_serves_again(self):
        started = self.payload("start_process",
                               command=f"{EXE} server.py {self.port}")
        self.payload("wait_for_port", port=self.port, timeout_seconds=10)
        self.payload("stop_process", handle=started["handle"])
        self.assertTrue(
            self.wait_until(lambda: port_available(self.port)))

        fresh = self.payload("restart_process", handle=started["handle"])
        ready = self.payload("wait_for_port", port=self.port,
                             timeout_seconds=10)
        self.assertTrue(ready["ready"])
        health = self.payload("health_check",
                              url=f"http://127.0.0.1:{self.port}/")
        self.assertTrue(health["ok"])
        self.payload("stop_process", handle=fresh["handle"])


class TestPortSemantics(ProcessTestBase):
    def test_check_port_free_vs_bound(self):
        self.assertTrue(self.payload("check_port", port=self.port)["available"])
        sock = socket.socket()
        sock.bind(("127.0.0.1", self.port))
        sock.listen(1)
        try:
            self.assertFalse(
                self.payload("check_port", port=self.port)["available"])
        finally:
            sock.close()

    def test_wait_for_port_timeout(self):
        # reserve a port WITHOUT listening: connect refused every poll
        sock = socket.socket()
        sock.bind(("127.0.0.1", self.port))
        try:
            out = self.payload("wait_for_port", port=self.port,
                               timeout_seconds=0.5)
            self.assertFalse(out["ready"])
        finally:
            sock.close()

    def test_port_serving_helper_agrees(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", self.port))
        sock.listen(1)
        try:
            self.assertTrue(port_serving(self.port))
        finally:
            sock.close()


class TestValidationAndGating(ProcessTestBase):
    def test_unknown_handle(self):
        out = self.call("process_status", handle="p999")
        self.assertFalse(out.ok)
        self.assertIn("unknown process handle", out.error)

    def test_empty_command_rejected(self):
        out = self.call("start_process", command="   ")
        self.assertFalse(out.ok)
        self.assertIn("non-empty", out.error)

    def test_stop_unknown_handle(self):
        out = self.call("stop_process", handle="p999")
        self.assertFalse(out.ok)
        self.assertIn("unknown process handle", out.error)

    def test_health_check_localhost_only(self):
        for url in ("https://example.com/", "http://192.168.1.5/",
                    "ftp://127.0.0.1/"):
            out = self.call("health_check", url=url)
            self.assertFalse(out.ok, url)
        out = self.call("health_check", url="http://localhost:1/")
        # the tool ran (ok=True); the HEALTH verdict lives in the payload
        self.assertTrue(out.ok)
        self.assertFalse(json.loads(out.output)["ok"])

    def test_bad_port_rejected(self):
        for port in (0, 70000, "80"):
            out = self.call("check_port", port=port)
            self.assertFalse(out.ok)

    def test_cwd_escape_rejected(self):
        out = self.call("start_process", command=f"{EXE} -c \"print(1)\"",
                        cwd="../elsewhere")
        self.assertFalse(out.ok)
        self.assertIn("rejected by policy", out.error)

    def test_list_processes(self):
        self.payload("start_process", command=f"{EXE} crash.py")
        listing = self.payload("list_processes")
        self.assertGreaterEqual(len(listing["processes"]), 1)


class TestRegistration(ProcessTestBase):
    def test_nine_tools_with_side_effect_matrix(self):
        described = {d["name"]: d for d in self.reg.describe()}
        self.assertEqual(
            set(described),
            {"start_process", "stop_process", "restart_process",
             "list_processes", "process_status", "wait_for_process",
             "check_port", "wait_for_port", "health_check"},
        )
        for name in ("start_process", "stop_process", "restart_process"):
            self.assertEqual(described[name]["side_effect_level"], "EXECUTION")
        for name in ("list_processes", "process_status", "wait_for_process",
                     "check_port", "wait_for_port", "health_check"):
            self.assertEqual(described[name]["side_effect_level"], "READ_ONLY")
        self.assertTrue(all(d["requires_workspace"] for d in described.values()))
        self.assertTrue(all(d["category"] == "processes"
                            for d in described.values()))

    def test_agent_registry_includes_process_tools(self):
        reg = agent_registry(self.ws)
        for name in ("start_process", "wait_for_port", "health_check"):
            self.assertIn(name, reg.names())


if __name__ == "__main__":
    unittest.main()
