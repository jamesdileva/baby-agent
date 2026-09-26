"""S31 agent providers: ModelProvider abstraction over model runtimes.

FakeModelProvider is the deterministic test backbone (S37's loop will drive
it); OllamaProvider wraps the S26 bridge internals — `qa ask` behavior is
untouched. The provider boundary normalizes the S27 textual tool protocol:
any [TOOL: name(arg="value")] lines in model output become structured
ToolCall objects, so downstream consumers never parse model text.

Scope note: tool schemas carried on ModelRequest are not rendered into the
prompt in S31 — prompt engineering of tools belongs to the S37 loop. The
provider accepts and normalizes whatever the model emits.

Live-provider tests are opt-in via QA_OLLAMA_LIVE=1 and never a CI gate
(DECISIONS 2026-09-04 hermeticity rule).
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .. import ollama_bridge as bridge
from .contracts import ModelMessage, ModelRequest, ModelResponse, ToolCall


class ProviderError(Exception):
    """Structured provider failure: unreachable, model error, or misuse."""


class ModelProvider(ABC):
    """A model runtime behind one stable interface."""

    name = "model"

    @abstractmethod
    def generate(self, request: ModelRequest) -> ModelResponse:
        """Turn a ModelRequest into a normalized ModelResponse."""


class FakeModelProvider(ModelProvider):
    """Scripted, deterministic provider for tests.

    Script items are ModelResponse objects, or ToolCall shortcuts (wrapped
    into a tool_calls response automatically). Responses pop in order;
    an empty script raises ProviderError instead of looping forever.
    """

    name = "fake"

    def __init__(self, script=None):
        self._script = list(script or [])

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not self._script:
            raise ProviderError("fake provider script exhausted")
        item = self._script.pop(0)
        if isinstance(item, ToolCall):
            return ModelResponse(
                text="", tool_calls=[item], finish_reason="tool_calls", model=self.name
            )
        return item


_UNSET = object()  # sentinel: "argument omitted"


def _retry_delay(exc, attempt: int) -> float:
    """F13 (super-audit): the retry sleep was a blind 60s block. Honor
    the server's Retry-After header when present (seconds form; HTTP-
    date forms fall back to the heuristic), cap the wait, and scale
    the heuristic with the attempt number. Cancel plumbing into
    providers is deliberately out of scope here — the loop's cancel
    latency stays bounded by one retry wait, now honest about it."""
    try:
        raw = (exc.headers or {}).get("Retry-After")
    except AttributeError:
        raw = None
    if raw:
        try:
            delay = float(raw)
            if delay >= 0:
                return min(delay, _MAX_RETRY_WAIT)
        except (TypeError, ValueError):
            pass  # HTTP-date form: fall back to the heuristic
    return min(5.0 * (attempt + 1), _MAX_RETRY_WAIT)


_MAX_RETRY_WAIT = 60.0


def _gemini_timeout() -> int:
    """S55: Gemini thinking + big tool catalogs exceed 60s reads."""
    import os as _os
    return int(_os.environ.get("GEMINI_TIMEOUT", "120"))


class GeminiModelProvider(ModelProvider):
    """Free-tier cloud brain (PLAIN generation — no grounding tool),
    per the no-billing ruling. The escalation/research candidate in
    the S55 role sketch; the local bake-off winner stays the default
    brain."""

    name = "gemini"
    native_tools = True  # class-level: Gemini natively emits functionCall

    def __init__(self, api_key=_UNSET, model: Optional[str] = None):
        import os as _os
        self._api_key = _os.environ.get("GEMINI_API_KEY")             if api_key is _UNSET else api_key
        self.model = model or _os.environ.get("GEMINI_MODEL")             or "gemini-flash-latest"

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not self._api_key:
            raise ProviderError(
                "no gemini provider configured: set GEMINI_API_KEY")
        if request.tools:
            return self._generate_native(request)
        prompt = _flatten_messages(request.messages)
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        # 503 high-demand spikes are transient: retry with backoff
        last_error: Optional[Exception] = None
        for attempt in range(3):
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model}:generateContent?key={self._api_key}",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                last_error = None
                break
            except urllib.error.HTTPError as exc:
                try:
                    detail = exc.read().decode("utf-8", "replace")[:400]
                except Exception:
                    detail = ""
                last_error = ProviderError(
                    f"gemini request failed: HTTP {exc.code} {detail}".strip())
                if exc.code not in (429, 503):
                    raise last_error from exc
                # 429 = free-tier rate limit (5 RPM): a full minute wait
                # guarantees a fresh window; 503 = high-demand spike
                time.sleep(_retry_delay(exc, attempt))
            except Exception as exc:
                raise ProviderError(f"gemini request failed: {exc}") from exc
        if last_error is not None:
            raise last_error
        try:
            text = "".join(str(part.get("text", "")) for part
                           in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            text = ""
        if not text.strip():
            raise ProviderError("gemini response missing usable content")
        return ModelResponse(text=text, finish_reason="stop",
                             model=self.model)

    @staticmethod
    def _gemini_safe_schema(schema: Any) -> Dict[str, Any]:
        """Gemini rejects schemas our registry allows (arrays without
        items, objects without properties). Coerce recursively."""
        if not isinstance(schema, dict):
            return {"type": "string"}
        clean: Dict[str, Any] = {
            key: value for key, value in schema.items()
            if key in ("type", "description", "properties", "required",
                       "items", "enum", "format")
        }
        stype = clean.get("type", "string")
        if stype == "object":
            properties = clean.setdefault("properties", {})
            for key, subschema in properties.items():
                properties[key] = GeminiModelProvider._gemini_safe_schema(
                    subschema)
        elif stype == "array":
            clean["items"] = GeminiModelProvider._gemini_safe_schema(
                clean.get("items", {"type": "string"}))
        return clean

    def _generate_native(self, request: ModelRequest) -> ModelResponse:
        """Gemini function_declarations -> functionCall parts
        (DECISIONS 2026-09-05: native tool calling)."""
        import urllib.error as _uerr
        import urllib.request as _ureq

        declarations = [{
            "name": t.name,
            "description": t.description,
            "parameters": GeminiModelProvider._gemini_safe_schema(
                t.parameters_schema),
        } for t in request.tools]
        contents = []
        for message in request.messages:
            if message.role == "assistant":
                # native replay: the requesting turn must carry its
                # functionCall parts; a pure-call turn has no text, and
                # an empty text part is itself a 400
                parts = []
                if (message.content or "").strip():
                    parts.append({"text": message.content})
                for call in message.tool_calls or []:
                    part = {"functionCall": {"name": call.name,
                                             "args": dict(call.arguments
                                                          or {})}}
                    if call.thought_signature:
                        # Gemini thinking models 400 without it (S63);
                        # the signature lives on the PART, not inside
                        # the functionCall object
                        part["thoughtSignature"] = call.thought_signature
                    parts.append(part)
                if parts:
                    contents.append({"role": "model", "parts": parts})
                continue
            if message.role == "tool":
                # native protocol: a tool result is a USER-turn
                # functionResponse part. Sending it as model-role text
                # makes the request "end with a model turn" — Gemini
                # 400s the whole conversation (S63 live finding).
                call_name = "tool"
                try:
                    parsed = json.loads(message.content)
                    if isinstance(parsed, dict):
                        call_name = str(parsed.get("call_name") or "tool")
                except (ValueError, TypeError):
                    pass
                contents.append({"role": "user", "parts": [{
                    "functionResponse": {
                        "name": call_name,
                        "response": {"result":
                                     (message.content or "")[:100_000]},
                    }}]})
                continue
            contents.append({"role": "user",
                             "parts": [{"text": message.content}]})
        body = {
            "contents": contents,
            "tools": [{"function_declarations": declarations}],
        }
        last_error: Optional[Exception] = None
        for attempt in range(3):
            req = _ureq.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model}:generateContent?key={self._api_key}",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            try:
                with _ureq.urlopen(req, timeout=_gemini_timeout()) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                last_error = None
                break
            except _uerr.HTTPError as exc:
                # surface the response body — a bare "HTTP 400" once hid
                # the real cause (empty text part) for a whole debug cycle
                try:
                    detail = exc.read().decode("utf-8", "replace")[:400]
                except Exception:
                    detail = ""
                last_error = ProviderError(
                    f"gemini request failed: HTTP {exc.code} {detail}".strip())
                if exc.code not in (429, 503):
                    raise last_error from exc
                # 429 = free-tier rate limit (5 RPM): a full minute wait
                # guarantees a fresh window; 503 = high-demand spike
                time.sleep(_retry_delay(exc, attempt))
            except Exception as exc:
                raise ProviderError(f"gemini request failed: {exc}") from exc
        if last_error is not None:
            raise last_error
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError):
            parts = []
        calls = [ToolCall(name=part["functionCall"]["name"],
                          arguments=dict(part["functionCall"].get("args")
                                         or {}),
                          thought_signature=part.get("thoughtSignature"))
                 for part in parts if "functionCall" in part]
        text = "".join(str(part.get("text", "")) for part in parts
                       if "text" in part).strip()
        return ModelResponse(
            text=text,
            tool_calls=calls,
            finish_reason="tool_calls" if calls else "stop",
            model=self.model,
        )


_ROLE_LIKE_PREFIX_RE = re.compile(
    r"^(system|user|assistant|tool)\s*:", re.IGNORECASE | re.MULTILINE)


def _escape_role_like(text: str) -> str:
    """B3 (super-audit): flattened content shares a text plane with the
    turn markers, so a tool result (or file) containing a line like
    "system: ignore previous instructions" could read as a new turn.
    Escape by indenting role-like line starts one space — visible in
    debugging, inert to the turn markers."""
    return _ROLE_LIKE_PREFIX_RE.sub(lambda m: " " + m.group(0), text)


def _flatten_messages(messages: List[ModelMessage]) -> str:
    """Flatten a message list into one prompt: system blocks first,
    then turns. B3: tool-role turns are fenced as untrusted blocks and
    role-like line prefixes inside every non-system turn are escaped,
    so flattened content cannot read as a new turn boundary."""
    system = [m.content for m in messages if m.role == "system"]
    turns = []
    for m in messages:
        if m.role == "system":
            continue
        content = _escape_role_like(m.content or "")
        if m.role == "tool":
            turns.append("--- tool result (untrusted) ---\n"
                         f"{content}\n"
                         "--- end tool result ---")
        else:
            turns.append(f"{m.role}: {content}")
    return "\n\n".join(system + turns)


def _parse_textual_tool_calls(text: str) -> List[ToolCall]:
    """Normalize textual [TOOL: ...] output into structured ToolCalls.

    Agent-layer format (one call per line, double-quoted string arguments):
        [TOOL: name(key="value", key2="value2")]
    Typed literals are also accepted for non-string arguments (the
    training renderer emits them bare: ``count=2``, ``force=true``,
    ``limit=null``):
        [TOOL: skill_find(query="x", k=3)]
    Backward compatible with the S27 brain protocol: a single bare value
    ("[TOOL: case_search(\"x\")]") or one query=/pattern= pair maps to the
    tool's canonical keyword (journal_read -> pattern, else query).
    S69 escaping dialect: \\, \\" and \\n inside double-quoted values are
    unescaped after capture (the mirror of format_tool_call's
    rendering), so quoted strings and multi-line content are
    expressible. Unknown escapes (\\r, \\u, ...) are kept literally
    (backslash preserved) instead of crashing the loop. Single-quoted
    legacy values stay raw on purpose: unescaping them would corrupt
    Windows paths such as 'C:\\new\\test'.
    A line matching the call shape always yields a ToolCall — even with
    empty arguments — so the strict validator returns a correctable
    observation instead of the turn silently becoming a final answer.
    """
    calls: List[ToolCall] = []
    pos, end = 0, len(text)
    while pos < end:
        head = _TOOL_HEAD_RE.search(text, pos)
        if head is None:
            break
        scanned = _scan_tool_call(text, head.start())
        if scanned is None:
            pos = head.end()  # malformed head: skip it, keep looking
            continue
        name, argstr, pos = scanned
        calls.append(ToolCall(name=name,
                              arguments=_parse_tool_args(name,
                                                         argstr.strip())))
    return calls


def _parse_tool_args(name: str, argstr: str) -> Dict[str, Any]:
    """Parse one call's argument string into typed arguments."""
    args: Dict[str, Any] = {}
    for pair in _ARG_PAIR_RE.finditer(argstr):
        if pair.group(1) is not None:
            args[pair.group(1)] = _unescape_value(pair.group(2))
        elif pair.group(3) is not None:
            # single-quoted legacy values stay raw (see docstring)
            args[pair.group(3)] = pair.group(4)
        else:
            args[pair.group(5)] = _typed_literal(pair.group(6))
    if not args:
        bare = _BARE_VALUE_RE.match(argstr)
        if bare:
            args["pattern" if name == "journal_read" else "query"] = bare.group(1)
    return args


def _unescape_value(value: str) -> str:
    """S69: one escaping dialect — unescape exactly what format_tool_call
    renders (backslash, quote, newline, tab); anything else is kept
    literally so model-emitted escapes can never crash the loop."""
    return _UNESCAPE_RE.sub(
        lambda m: _UNESCAPES.get(m.group(1), "\\" + m.group(1)), value)


def _typed_literal(token: str) -> Any:
    """One bare textual-protocol literal to its typed value."""
    if token == "true":
        return True
    if token == "false":
        return False
    if token == "null":
        return None
    try:
        return int(token)
    except ValueError:
        return float(token)


def _scan_tool_call(text: str, start: int):
    """Scan one ``[TOOL: name(...)]`` starting at ``start`` (the ``[``).

    Quote- and escape-aware: ``)]`` or ``(`` inside a quoted value never
    terminates the argument section. Returns (name, argstr, end_index)
    or None when the head has no well-formed closing.
    """
    head = _TOOL_HEAD_RE.match(text, start)
    if head is None:
        return None
    name = head.group(1)
    i, n = head.end(), len(text)
    args_start = i
    depth = 1
    quote = None
    escaped = False
    while i < n:
        ch = text[i]
        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
        elif ch in ("\"", "'"):
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    if depth != 0 or i >= n:
        return None
    argstr = text[args_start:i]
    j = i + 1
    while j < n and text[j] in " \t":
        j += 1
    if j >= n or text[j] != "]":
        return None
    return name, argstr, j + 1


_TOOL_HEAD_RE = re.compile(r"\[\s*TOOL:\s*(\w+)\s*\(")
# S69: escape-aware double-quoted values — (?:[^"\\]|\\.)* consumes \"
# and \\ sequences so escaped quotes no longer terminate the value.
# Typed literals (true/false/null/numbers) mirror training.format_tool_call,
# which renders non-strings bare. Single-quoted values stay raw (legacy).
_ARG_PAIR_RE = re.compile(
    r"""(\w+)\s*=\s*"((?:[^"\\]|\\.)*)"|(\w+)\s*=\s*'([^']*)'|"""
    r"""(\w+)\s*=\s*(true|false|null|-?\d+(?:\.\d+)?)""")
_BARE_VALUE_RE = re.compile(r"""^["']([^"']*)["']$""")

# S69 escaping dialect (shared with training.format_tool_call):
# backslash, quote, and newline are the escaped set
_UNESCAPES = {"\\": "\\", '"': '"', "n": "\n", "t": "\t"}
_UNESCAPE_RE = re.compile(r"\\(.)")


class OllamaProvider(ModelProvider):
    """ModelProvider over the existing S26 Ollama bridge (localhost HTTP)."""

    name = "ollama"

    def __init__(self, model=None, url=None, native_tools: bool = True,
                 temperature=None, seed=None):
        self.model = model
        self.url = url
        # S55: qwen2.5-coder-class models lack Ollama native tool support
        # — instantiate with native_tools=False to force the textual shim
        self.native_tools = native_tools
        # S93: pinned decoding for measurement stability (verdicts);
        # None leaves the server default (all other callers unchanged)
        self.temperature = temperature
        self.seed = seed

    def generate(self, request: ModelRequest) -> ModelResponse:
        model = self.model or request.model
        # no availability pre-check: the bridge's ping is itself a full
        # generation (2x cost per turn) and one flaky ping would kill the
        # loop — a dead Ollama surfaces naturally as ProviderError below
        if request.tools and self.native_tools:
            # DECISIONS 2026-09-05: native tool calling is the primary
            # contract when tools are declared
            return self._generate_native(request, model)
        return self._generate_textual(request, model)

    def _generate_native(self, request: ModelRequest,
                         model: Optional[str]) -> ModelResponse:
        """Ollama /api/chat with structured tools (DECISIONS 2026-09-05)."""
        messages = [{"role": m.role, "content": m.content}
                    for m in request.messages]
        tools = [{
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters_schema,
            },
        } for t in request.tools]
        think = bridge._think_flag()
        try:
            data = bridge._ollama_chat(messages, tools=tools, model=model,
                                       url=self.url, think=think,
                                       temperature=self.temperature,
                                       seed=self.seed)
        except bridge.OllamaError as exc:
            raise ProviderError(f"ollama failure: {exc}") from exc
        message = data.get("message") or {}
        calls = [
            ToolCall(name=tc.get("function", {}).get("name", "unknown"),
                     arguments=dict(tc.get("function", {}).get("arguments")
                                    or {}))
            for tc in (message.get("tool_calls") or [])
        ]
        text = message.get("content") or ""
        return ModelResponse(
            text=text,
            tool_calls=calls,
            finish_reason="tool_calls" if calls else "stop",
            usage=None,
            model=model or os.environ.get("OLLAMA_MODEL") or bridge.DEFAULT_MODEL,
        )

    def _generate_textual(self, request: ModelRequest,
                          model: Optional[str]) -> ModelResponse:
        try:
            prompt = _flatten_messages(request.messages)
            text = bridge._ollama_generate(prompt, model=model, url=self.url,
                                           temperature=self.temperature,
                                           seed=self.seed)
        except bridge.OllamaError as exc:
            raise ProviderError(f"ollama failure: {exc}") from exc
        calls = _parse_textual_tool_calls(text)
        return ModelResponse(
            text=text,
            tool_calls=calls,
            finish_reason="tool_calls" if calls else "stop",
            usage=None,
            model=model or os.environ.get("OLLAMA_MODEL") or bridge.DEFAULT_MODEL,
        )
