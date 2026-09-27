"""S52 server tests: REST + SSE over 127.0.0.1, hermetic (fake provider).

Real HTTP over the loopback interface; the fake provider makes sessions
complete deterministically.
"""

import json
import os
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from qacompanion.agent import FakeModelProvider, ModelResponse, ToolCall
from qacompanion.agent.experience import ExperienceStore
from qacompanion.agent.server import AgentServer, AgentServerApp

PY = f'"{sys.executable}"'


def _fake_factory(fix_script=None):
    """Provider factory: each session gets a fresh scripted provider."""
    def factory(model=None, provider=None):
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
        app = AgentServerApp(provider_factory=lambda model=None,
                                                              provider=None: (
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
        self.app.verdict_runner = lambda models, tasks, temperature=None, \
            seed=None: (
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


class TestS96DashboardSurface(ServerBase):
    """S96: model chooser data, per-session provider, folder picker,
    verdict decoding flags — all hermetic."""

    def test_models_lists_ollama_names(self):
        import subprocess
        from unittest.mock import patch
        blob = ("NAME\tID\tSIZE\n"
                "baby-agent:ep11-q4\tce5a\t4.7 GB\n"
                "qwen3.5:9b\t6488\t6.6 GB\n")
        fake = subprocess.CompletedProcess(args=["ollama", "list"],
                                           returncode=0, stdout=blob,
                                           stderr="")
        with patch("subprocess.run", return_value=fake):
            out = self.get("/api/models")
        self.assertEqual(out["models"],
                         ["baby-agent:ep11-q4", "qwen3.5:9b"])

    def test_models_missing_ollama_is_structured(self):
        from unittest.mock import patch
        import urllib.error
        with patch("subprocess.run",
                   side_effect=FileNotFoundError("nope")):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.get("/api/models")
            self.assertEqual(503, ctx.exception.code)

    def test_session_accepts_provider_and_model(self):
        import json
        import urllib.request
        seen = {}
        def factory(model=None, provider=None):
            seen["model"] = model
            seen["provider"] = provider
            return _fake_factory()()
        app = AgentServerApp(provider_factory=factory,
                             experience_store=self.store)
        server = AgentServer(app)
        server.serve()
        try:
            request = urllib.request.Request(
                server.url + "/api/session/start",
                data=json.dumps({
                    "goal": "create hello.txt",
                    "workspace": str(self.tmp / "ws3"),
                    "model": "baby-agent:ep11-q4",
                    "provider": "ollama",
                }).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request,
                                        timeout=5) as resp:
                out = json.loads(resp.read().decode())
            self.assertIn("session_id", out)
            import time
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                with urllib.request.urlopen(
                        server.url + "/api/session/"
                        + out["session_id"],
                        timeout=5) as resp:
                    if json.loads(resp.read().decode())["done"]:
                        break
                time.sleep(0.05)
        finally:
            server.shutdown()
        self.assertEqual(seen["model"], "baby-agent:ep11-q4")
        self.assertEqual(seen["provider"], "ollama")

    def test_unknown_provider_is_structured_error(self):
        from qacompanion.agent.server import default_provider_factory
        with self.assertRaises(ValueError):
            default_provider_factory("m", "gpt-5")

    def test_browse_lists_subdirectories(self):
        (self.tmp / "proj-a").mkdir()
        (self.tmp / "proj-b").mkdir()
        (self.tmp / "file.txt").write_text("x", encoding="utf-8")
        out = self.get("/api/browse?path=" + str(self.tmp).replace(
            "\\", "/"))
        self.assertIn("proj-a", out["directories"])
        self.assertIn("proj-b", out["directories"])
        self.assertNotIn("file.txt", out["directories"])
        self.assertIn("parent", out)

    def test_browse_missing_is_404(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/browse?path=" + str(self.tmp / "nope"))
        self.assertEqual(404, ctx.exception.code)

    def test_browse_decodes_percent_encoded_paths(self):
        # S96.1: browsers encode Windows paths (C%3A%5C…); the raw
        # form matched nothing and Up navigation 404'd
        import urllib.parse
        (self.tmp / "proj-a").mkdir()
        encoded = urllib.parse.quote(str(self.tmp / "proj-a"), safe="")
        out = self.get("/api/browse?path=" + encoded)
        self.assertIn("directories", out)

    def test_dashboard_registry_grows_eyes(self):
        # S97: interactive sessions offer the vision tools (benchmarks
        # keep the lean hermetic catalog — asserted by their own pins)
        from qacompanion.agent.server import dashboard_registry
        from qacompanion.agent.workspace import Workspace
        reg = dashboard_registry(Workspace(self.tmp), self.store)
        for name in ("capture_screen", "capture_window", "capture_region",
                     "inspect_image", "compare_images",
                     "detect_blank_screen"):
            self.assertIn(name, reg.names())

    def test_repeating_failure_terminates_honestly(self):        # S98: the S58 no-progress machinery is wired in — an
        # identical failing call terminates with a stated reason
        # instead of burning max_iterations on repeats. The failure
        # is a validation error (NOT an environment marker — those
        # route to ENVIRONMENT_CHECK by S58 design, observed live
        # looping there; separate follow-up, not this slice).
        from qacompanion.agent import ModelResponse, ToolCall
        from qacompanion.agent.providers import ModelProvider

        class _Looper(ModelProvider):
            name = "looper"

            def generate(self, request):
                return ModelResponse(
                    text="", tool_calls=[ToolCall(
                        name="read_file", arguments={})],
                    finish_reason="tool_calls")

        app = AgentServerApp(
            provider_factory=lambda model=None, provider=None: _Looper(),
            experience_store=self.store)
        session_id = app.start_session(
            goal="read the ghost file", workspace=str(self.tmp / "ws9"))
        import time
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if app.sessions[session_id].done:
                break
            time.sleep(0.05)
        summary = app.sessions[session_id].summary()
        self.assertTrue(summary["done"])
        self.assertEqual(summary["state"], "FAILED")
        self.assertLess(summary["iterations"], 25)
        self.assertIn("human decision",
                      summary["termination_reason"])

    def test_verdict_carries_decoding_flags(self):
        seen = {}
        self.app.verdict_runner = lambda models, tasks, temperature=None, \
            seed=None: (seen.update(temperature=temperature, seed=seed)
                        or "done")
        self.post("/api/verdict", {"models": "m1", "temperature": 0,
                                   "seed": 42})
        import time
        for _ in range(50):
            jobs = self.get("/api/jobs")["jobs"]
            if jobs[0]["status"] != "running":
                break
            time.sleep(0.1)
        self.assertEqual(seen["temperature"], 0)
        self.assertEqual(seen["seed"], 42)


class TestSessionConfirmations(ServerBase):
    """S99: EXTERNAL approvals resolve through the dashboard."""

    def _inspect_session(self, timeout_patch=None):
        from qacompanion.agent import FakeModelProvider, ModelResponse, ToolCall
        from qacompanion.agent.vision import encode_png
        ws = self.tmp / "shot-ws"
        ws.mkdir(exist_ok=True)
        (ws / "shot.png").write_bytes(encode_png(2, 1, [
            b"\xff\xff\xff\xff\xff\xff"]))
        script = [ToolCall(name="inspect_image",
                           arguments={"path": "shot.png"}),
                  ModelResponse(text="described", finish_reason="stop")]
        app = AgentServerApp(
            provider_factory=lambda model=None, provider=None: (
                FakeModelProvider([i for i in script])),
            experience_store=self.store)
        # patches stay live for the whole session: the toolkit
        # resolves the provider and the confirmer reads the timeout
        # inside the session thread, not at construction
        stoppers = []
        env = patch.dict(os.environ, {}, clear=False)
        env.start()
        stoppers.append(env.stop)
        os.environ.pop("GEMINI_API_KEY", None)
        if timeout_patch is not None:
            patcher = patch(
                "qacompanion.agent.server.CONFIRM_TIMEOUT_SECONDS",
                timeout_patch)
            patcher.start()
            stoppers.append(patcher.stop)
        sid = app.start_session(
            goal="describe the screenshot",
            workspace=str(ws), model="m")
        return app, sid, stoppers

    def _await_pending(self, app, sid):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            pending = app.sessions[sid].summary()["pending_confirmation"]
            if pending is not None:
                return pending
            if app.sessions[sid].done:
                return None
            time.sleep(0.05)
        return app.sessions[sid].summary()["pending_confirmation"]

    def _await_done(self, app, sid):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if app.sessions[sid].done:
                break
            time.sleep(0.05)

    def test_approve_reaches_tool(self):
        app, sid, stoppers = self._inspect_session()
        try:
            pending = self._await_pending(app, sid)
            self.assertIsNotNone(pending)
            self.assertEqual(pending["tool"], "inspect_image")
            self.assertTrue(app.confirm_session(sid, True))
            self._await_done(app, sid)
            summary = app.sessions[sid].summary()
            self.assertTrue(summary["done"])
            self.assertIsNone(summary["pending_confirmation"])
        finally:
            app.sessions[sid].cancel_event.set()
            for stop in stoppers:
                stop()

    def test_deny_blocks_tool(self):
        app, sid, stoppers = self._inspect_session()
        try:
            self.assertIsNotNone(self._await_pending(app, sid))
            self.assertTrue(app.confirm_session(sid, False))
            self._await_done(app, sid)
            recs = [r for r in self.store.load()
                    if "screenshot" in r.goal]
            self.assertTrue(recs)
            steps = recs[-1].context.get("tool_calls") or []
            denied = [s for s in steps
                      if s.get("tool") == "inspect_image"
                      and not s.get("ok")]
            self.assertTrue(denied)
        finally:
            app.sessions[sid].cancel_event.set()
            for stop in stoppers:
                stop()

    def test_timeout_denies_safely(self):
        app, sid, stoppers = self._inspect_session(timeout_patch=0.05)
        try:
            self._await_done(app, sid)
            summary = app.sessions[sid].summary()
            self.assertTrue(summary["done"])
            self.assertIsNone(summary["pending_confirmation"])
        finally:
            app.sessions[sid].cancel_event.set()
            for stop in stoppers:
                stop()

    def test_confirm_unknown_session_404(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/session/ghost/confirm", {"approved": True})
        self.assertEqual(404, ctx.exception.code)

    def test_confirm_without_pending_409(self):
        import urllib.error
        session_id = self.post("/api/session/start", {
            "goal": "create hello.txt",
            "workspace": str(self.tmp / "ws10"),
        })["session_id"]
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post(f"/api/session/{session_id}/confirm",
                      {"approved": True})
        self.assertEqual(409, ctx.exception.code)


if __name__ == "__main__":
    unittest.main()
