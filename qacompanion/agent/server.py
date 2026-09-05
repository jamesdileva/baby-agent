"""S52 desktop UI backend: the runtime's local API layer.

A localhost-only HTTP server (stdlib ThreadingHTTPServer) exposing the
agent runtime to the dashboard: REST for control + Server-Sent Events
for the S39 event stream. The UI subscribes; it never polls internal
state.

Security posture (spec s52):
- binds 127.0.0.1 only — the runtime is never network-exposed;
- single-user local assumption, no auth on loopback;
- sessions run through the same S37 loop / S38 engine policy as every
  other path — the UI adds convenience, not authority.

Verification honesty: user sessions default to NO verification gate (a
completed session is recorded as unverified/partial per S50 — the UI
shows it). A `verify_command` on session start builds a real S41 gate
(expect_exit 0) for projects that have one.

Provider selection: an injectable factory (tests pass a
FakeModelProvider factory); the default builds an OllamaProvider with
the requested model.
"""

import json
import queue
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .benchmark import coding_registry
from .events import EventStream
from .experience import ExperienceStore, MemoryLayer
from .loop import AgentLoop
from .session_learning import record_session
from .verification import VerificationPlan, VerificationStep, plan_verifier
from .workspace import Workspace


def default_provider_factory(model: Optional[str] = None):
    """Default model backend: local Ollama."""
    from .providers import OllamaProvider

    return OllamaProvider(model=model)


@dataclass
class ManagedSession:
    """One server-run agent session plus its observability plumbing."""

    session_id: str
    goal: str
    workspace_root: str
    model: Optional[str]
    events: EventStream
    cancel_event: threading.Event
    session: Any = None
    report: Any = None
    error: Optional[str] = None
    done: bool = False
    thread: Optional[threading.Thread] = None
    subscribers: List[Any] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        session = self.session
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "workspace": self.workspace_root,
            "model": self.model,
            "state": session.state.value if session else "STARTING",
            "iterations": session.iterations if session else 0,
            "files_changed": list(session.files_changed) if session else [],
            "verification_results": (
                list(session.verification_results) if session else []),
            "termination_reason": session.termination_reason if session
            else None,
            "done": self.done,
            "error": self.error,
        }


def _verify_plan(verify_command: str) -> VerificationPlan:
    return VerificationPlan(name="user-verification", steps=[
        VerificationStep(name="verify", category="RUNTIME",
                         command=verify_command),
    ])


class AgentServerApp:
    """Application state + operations behind the HTTP surface."""

    def __init__(self,
                 provider_factory: Optional[Callable[..., Any]] = None,
                 experience_store: Optional[ExperienceStore] = None):
        self.provider_factory = provider_factory or default_provider_factory
        self.experience_store = experience_store
        self.sessions: Dict[str, ManagedSession] = {}
        self._lock = threading.Lock()

    def start_session(self, goal: str, workspace: str = "",
                      model: Optional[str] = None,
                      verify_command: Optional[str] = None) -> str:
        if not goal.strip():
            raise ValueError("goal must be a non-empty string")
        root = Path(workspace) if workspace else Path(
            tempfile.mkdtemp(prefix="agent-session-"))
        root.mkdir(parents=True, exist_ok=True)  # new projects welcome
        ws = Workspace(root)
        session_id = uuid.uuid4().hex
        events = EventStream()
        cancel_event = threading.Event()
        managed = ManagedSession(
            session_id=session_id, goal=goal,
            workspace_root=str(ws.root), model=model,
            events=events, cancel_event=cancel_event,
        )
        with self._lock:
            self.sessions[session_id] = managed

        store = self.experience_store
        verifier = plan_verifier(_verify_plan(verify_command), ws) \
            if verify_command else None
        # the server's session id IS the agent session's id: the UI holds
        # this id for events and state, so they must be one and the same
        from .session import AgentSession
        pre_session = AgentSession(goal=goal, session_id=session_id,
                                   workspace_root=str(ws.root))

        def run():
            try:
                provider = self.provider_factory(model)
                registry = coding_registry(ws, experience_store=store)
                loop = AgentLoop(provider, registry, ws, verifier=verifier,
                                 cancel_event=cancel_event, events=events)
                session = loop.run(goal, session=pre_session)
                managed.session = session
                if store is not None:
                    record_session(session, store, model=model)
            except Exception as exc:  # operational failure: visible, honest
                managed.error = f"{type(exc).__name__}: {exc}"
            finally:
                managed.done = True

        managed.thread = threading.Thread(target=run, daemon=True)
        managed.thread.start()
        return session_id

    def stop_session(self, session_id: str) -> bool:
        managed = self.sessions.get(session_id)
        if managed is None:
            return False
        managed.cancel_event.set()
        return True

    def subscribe(self, session_id: str) -> Optional["queue.Queue"]:
        managed = self.sessions.get(session_id)
        if managed is None:
            return None
        event_queue: "queue.Queue" = queue.Queue()
        with self._lock:
            # replay history first, then attach live — a subscriber that
            # arrives late still sees session_started
            for event in managed.events.events:
                event_queue.put(event)
            managed.events.subscribe(lambda event: event_queue.put(event))
            managed.subscribers.append(event_queue)
        return event_queue


def make_handler(app: AgentServerApp):
    """Build a request handler class bound to one app instance."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # silence per-request noise
            pass

        def _json(self, payload, status=200):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self):
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _serve_dist(self, path: str):
            """Serve the built dashboard. / -> index.html; asset paths
            resolve INSIDE app/dist only (traversal-proof)."""
            dist = Path(__file__).resolve().parents[2] / "app" / "dist"
            index = dist / "index.html"
            if not index.exists():
                self._json({"error": "dashboard not built (npm run "
                                     "build in app/)"}, 404)
                return
            if path == "/" or path == "/index.html":
                target, content_type = index, "text/html; charset=utf-8"
            else:
                candidate = (dist / path.lstrip("/")).resolve()
                try:
                    candidate.relative_to(dist.resolve())
                except ValueError:
                    self._json({"error": "forbidden path"}, 403)
                    return
                if not candidate.is_file():
                    # SPA fallback: unknown paths render the app shell
                    target, content_type = index, "text/html; charset=utf-8"
                else:
                    target = candidate
                    suffix = candidate.suffix.lower()
                    content_type = {
                        ".js": "text/javascript; charset=utf-8",
                        ".css": "text/css; charset=utf-8",
                        ".html": "text/html; charset=utf-8",
                        ".svg": "image/svg+xml",
                        ".png": "image/png",
                        ".ico": "image/x-icon",
                    }.get(suffix, "application/octet-stream")
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path, _, query = self.path.partition("?")
            params = dict(pair.split("=", 1) for pair in query.split("&")
                          if "=" in pair)
            if path == "/" or not path.startswith("/api/"):
                self._serve_dist(path)
                return
            if path == "/api/health":
                self._json({"status": "ok", "api": "baby-agent/v1"})
            elif path == "/api/sessions":
                with app._lock:
                    sessions = [m.summary() for m in app.sessions.values()]
                self._json({"sessions": sessions})
            elif path.startswith("/api/session/"):
                session_id = path[len("/api/session/"):]
                managed = app.sessions.get(session_id)
                if managed is None:
                    self._json({"error": "unknown session"}, 404)
                else:
                    self._json(managed.summary())
            elif path == "/api/events":
                self._stream_events(params.get("session_id"))
            elif path == "/api/skills":
                from .skills import SkillLibrary
                self._json({"skills": [s.to_dict() for s in
                                       SkillLibrary().list_skills()]})
            elif path == "/api/memory":
                query_text = params.get("query", "")
                layer = MemoryLayer(
                    experience_store=app.experience_store or
                    ExperienceStore())
                results = layer.search(query_text, k_per_source=3)
                self._json({"query": query_text, "results": results})
            elif path == "/api/environment":
                from .environment import collect_os, collect_runtimes
                self._json({**collect_os(), **collect_runtimes()})
            else:
                self._json({"error": f"unknown path {path}"}, 404)

        def _stream_events(self, session_id):
            if not session_id or session_id not in app.sessions:
                self._json({"error": "unknown session"}, 404)
                return
            event_queue = app.subscribe(session_id)
            managed = app.sessions[session_id]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    try:
                        event = event_queue.get(timeout=1.0)
                    except queue.Empty:
                        if managed.done:
                            break
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                        continue
                    payload = json.dumps(event.to_dict(),
                                         ensure_ascii=False)
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
            except (OSError, ConnectionAbortedError):
                pass  # client disconnected
            finally:
                if event_queue in managed.subscribers:
                    managed.subscribers.remove(event_queue)

        def do_POST(self):
            if self.path == "/api/session/start":
                try:
                    body = self._read_json()
                    session_id = app.start_session(
                        goal=body.get("goal", ""),
                        workspace=body.get("workspace", ""),
                        model=body.get("model"),
                        verify_command=body.get("verify_command"))
                    self._json({"session_id": session_id})
                except Exception as exc:
                    # value/workspace errors are client-visible; anything
                    # else still surfaces as a structured 400, never a
                    # dropped connection
                    self._json({"error": f"{type(exc).__name__}: {exc}"}, 400)
            elif self.path.startswith("/api/session/") \
                    and self.path.endswith("/stop"):
                session_id = self.path[len("/api/session/"):-len("/stop")]
                stopped = app.stop_session(session_id)
                self._json({"stopped": bool(stopped)},
                           200 if stopped else 404)
            else:
                self._json({"error": f"unknown path {self.path}"}, 404)

    return Handler


class AgentServer:
    """The bound, serving handle. Call .serve() to run in a thread."""

    def __init__(self, app: AgentServerApp, host: str = "127.0.0.1",
                 port: int = 0):
        if host != "127.0.0.1":
            raise ValueError("the agent server binds 127.0.0.1 only")
        self.app = app
        self.httpd = ThreadingHTTPServer((host, port), make_handler(app))
        self.port = self.httpd.server_address[1]
        self.host = host

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def serve(self, daemon: bool = True) -> threading.Thread:
        thread = threading.Thread(target=self.httpd.serve_forever,
                                  daemon=daemon)
        thread.start()
        return thread

    def shutdown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
