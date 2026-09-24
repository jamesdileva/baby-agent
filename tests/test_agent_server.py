"""S52 server tests: REST + SSE over 127.0.0.1, hermetic (fake provider).

Real HTTP over the loopback interface; the fake provider makes sessions
complete deterministically.
"""

import json
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

from qacompanion.agent import FakeModelProvider, ModelResponse, ToolCall
from qacompanion.agent.experience import ExperienceStore
from qacompanion.agent.server import AgentServer, AgentServerApp

PY = f'"{sys.executable}"'


def _fake_factory(fix_script=None):
    """Provider factory: each session gets a fresh scripted provider."""
    def factory(model=None):
        script = fix_script if fix_script is not None else [
            ToolCall(name="write_file", arguments={
                "path": "hello.txt", "content": "built by the agent"}),
            ModelResponse(text="created hello.txt", finish_reason="stop"),
        ]
        return FakeModelProvider([item for item in script])
    return factory


class ServerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = ExperienceStore(self.tmp / "experience.jsonl")
        self.app = AgentServerApp(provider_factory=_fake_factory(),
                                  experience_store=self.store)
        self.server = AgentServer(self.app)
        self.server.serve()

    def tearDown(self):
        self.server.shutdown()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self, path):
        with urllib.request.urlopen(self.server.url + path, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post(self, path, payload):
        request = urllib.request.Request(
            self.server.url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def read_events(self, session_id, timeout=10.0):
        """Consume the SSE stream until it ends (session terminal)."""
        events = []
        with urllib.request.urlopen(
                f"{self.server.url}/api/events?session_id={session_id}",
                timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if line.startswith("data: "):
                    events.append(json.loads(line[len("data: "):]))
        return events


class TestRestSurface(ServerBase):
    def test_health(self):
        self.assertEqual(self.get("/api/health")["status"], "ok")

    def test_loopback_only(self):
        with self.assertRaises(ValueError):
            AgentServer(self.app, host="0.0.0.0")

    def test_session_lifecycle(self):
        workspace = str(self.tmp / "project")
        out = self.post("/api/session/start", {
            "goal": "create hello.txt",
            "workspace": workspace,
        })
        session_id = out["session_id"]

        # eventually done (background thread)
        import time
        deadline = time.monotonic() + 10
        summary = {}
        while time.monotonic() < deadline:
            summary = self.get(f"/api/session/{session_id}")
            if summary["done"]:
                break
            time.sleep(0.05)
        self.assertTrue(summary["done"])
        self.assertEqual(summary["state"], "COMPLETED")
        self.assertIn("hello.txt", summary["files_changed"])

        sessions = self.get("/api/sessions")["sessions"]
        self.assertEqual(sessions[0]["session_id"], session_id)

    def test_start_requires_goal(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/session/start", {"goal": ""})
        self.assertEqual(ctx.exception.code, 400)

    def test_unknown_session_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/session/ghost")
        self.assertEqual(ctx.exception.code, 404)

    def test_dashboard_assets_served(self):
        dist = Path(__file__).resolve().parents[1] / "app" / "dist"
        if not (dist / "index.html").exists():
            self.skipTest("dashboard not built (npm build is the UI "
                          "gate; CI does not build it)")
        # / serves the built shell; JS assets serve as real JS (the
        # walkthrough caught the index-for-everything bug)
        with urllib.request.urlopen(self.server.url + "/", timeout=5) as resp:
            body = resp.read().decode("utf-8")
        self.assertIn("<div id=\"root\">", body)
        asset_line = next(line for line in body.splitlines()
                          if "/assets/" in line and ".js" in line)
        asset_path = asset_line.split('src="')[1].split('"')[0]
        request = urllib.request.Request(self.server.url + asset_path)
        with urllib.request.urlopen(request, timeout=5) as resp:
            self.assertEqual(resp.headers["Content-Type"],
                             "text/javascript; charset=utf-8")

    def test_skills_and_memory_endpoints(self):
        skills = self.get("/api/skills")["skills"]
        self.assertTrue(any(s["name"] == "resume_interrupted_task"
                            for s in skills))
        memory = self.get("/api/memory?query=websocket")
        self.assertIn("results", memory)


class TestSSEStream(ServerBase):
    def test_events_stream_until_terminal(self):
        session_id = self.post("/api/session/start", {
            "goal": "create hello.txt",
            "workspace": str(self.tmp / "ws"),
        })["session_id"]
        events = self.read_events(session_id)
        types = [e["event_type"] for e in events]
        self.assertEqual(types[0], "session_started")
        self.assertIn("tool_completed", types)
        self.assertEqual(types[-1], "session_completed")
        self.assertTrue(all(e["session_id"] == session_id for e in events))

    def test_stop_endpoint_cancels(self):
        # a scripted provider that never finishes: cancel mid-flight
        app = AgentServerApp(provider_factory=lambda model=None: (
            _NeverDoneProvider()), experience_store=self.store)
        server = AgentServer(app)
        server.serve()
        try:
            session_id = json.loads(urllib.request.urlopen(
                urllib.request.Request(
                    server.url + "/api/session/start",
                    data=json.dumps({"goal": "endless"}).encode(),
                    headers={"Content-Type": "application/json"}),
                timeout=5).read().decode())["session_id"]
            self.post.__func__ # plain request below
            request = urllib.request.Request(
                f"{server.url}/api/session/{session_id}/stop", data=b"{}",
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=5) as resp:
                self.assertTrue(json.loads(
                    resp.read().decode())["stopped"])
        finally:
            server.shutdown()

    def test_experience_recorded_for_server_sessions(self):
        session_id = self.post("/api/session/start", {
            "goal": "create hello.txt",
            "workspace": str(self.tmp / "ws2"),
        })["session_id"]
        import time
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.get(f"/api/session/{session_id}")["done"]:
                break
            time.sleep(0.05)
        experiences = self.store.load()
        self.assertEqual(len(experiences), 1)
        self.assertEqual(experiences[0].goal, "create hello.txt")


class _NeverDoneProvider(FakeModelProvider):
    """A provider whose sessions never end (for the stop endpoint)."""

    def __init__(self):
        super().__init__([])
        self._count = 0

    def generate(self, request):
        self._count += 1
        return ModelResponse(text=f"still working ({self._count})",
                             finish_reason="stop")


class TestOperations(ServerBase):
    """S70: the loop's buttons — drip + verdict as deliberate jobs."""

    def setUp(self):
        super().setUp()
        self.app.drip_runner = lambda: ("SUCCESS | goal completed"
                                        " | iters=6 | calls=5")
        self.app.verdict_runner = lambda models, tasks: (
            f"generation verdict: {','.join(models)}"
            f" ({tasks} tasks)")

    def _await_done(self):
        import time
        jobs = self.get("/api/jobs")["jobs"]
        for _ in range(50):
            if jobs[0]["status"] != "running":
                break
            time.sleep(0.1)
            jobs = self.get("/api/jobs")["jobs"]
        return jobs

    def test_drip_job_lifecycle(self):
        response = self.post("/api/drip", {})
        self.assertIn("job_id", response)
        jobs = self._await_done()
        self.assertEqual("done", jobs[0]["status"])
        self.assertEqual("drip", jobs[0]["kind"])
        self.assertIn("SUCCESS", jobs[0]["summary"])
        self.assertTrue(jobs[0]["finished_at"])

    def test_verdict_job_carries_models(self):
        self.post("/api/verdict",
                  {"models": "baby-agent:ep4-q4,baby-agent:ep3-q4",
                   "tasks": 3})
        jobs = self._await_done()
        self.assertEqual("done", jobs[0]["status"])
        self.assertIn("baby-agent:ep4-q4,baby-agent:ep3-q4",
                      jobs[0]["summary"])
        self.assertIn("3 tasks", jobs[0]["summary"])

    def test_verdict_requires_models(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/verdict", {"models": ""})
        self.assertEqual(400, ctx.exception.code)

    def test_jobs_newest_first_and_kinds(self):
        self.post("/api/drip", {})
        self.post("/api/verdict", {"models": "m1"})
        jobs = self._await_done()
        self.assertEqual(2, len(jobs))
        self.assertEqual({"drip", "verdict"},
                         {job["kind"] for job in jobs})
        self.assertGreaterEqual(jobs[0]["started_at"],
                                jobs[1]["started_at"])


if __name__ == "__main__":
    unittest.main()
