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
from typing import Any, Dict, List

from .. import ollama_bridge as bridge
from .. import tools as tools_mod
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

    def __init__(self, script):
        self._script = list(script)

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
                last_error = ProviderError(
                    f"gemini request failed: HTTP {exc.code}")
                if exc.code != 503:
                    raise last_error from exc
                time.sleep(5.0 * (attempt + 1))
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
            role = "model" if message.role in ("assistant", "tool")                 else "user"
            contents.append({"role": role, "parts": [{"text": message.content}]})
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
                last_error = ProviderError(
                    f"gemini request failed: HTTP {exc.code}")
                if exc.code != 503:
                    raise last_error from exc
                time.sleep(5.0 * (attempt + 1))
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
                                         or {}))
                 for part in parts if "functionCall" in part]
        text = "".join(str(part.get("text", "")) for part in parts
                       if "text" in part).strip()
        return ModelResponse(
            text=text,
            tool_calls=calls,
            finish_reason="tool_calls" if calls else "stop",
            model=self.model,
        )


def _flatten_messages(messages: List[ModelMessage]) -> str:
    """Flatten a message list into one prompt: system blocks first, then turns."""
    system = [m.content for m in messages if m.role == "system"]
    turns = [f"{m.role}: {m.content}" for m in messages if m.role != "system"]
    return "\n\n".join(system + turns)


def _parse_textual_tool_calls(text: str) -> List[ToolCall]:
    """Normalize textual [TOOL: ...] output into structured ToolCalls.

    Agent-layer format (one call per line, double-quoted string arguments):
        [TOOL: name(key="value", key2="value2")]
    Backward compatible with the S27 brain protocol: a single bare value
    ("[TOOL: case_search(\"x\")]") or one query=/pattern= pair maps to the
    tool's canonical keyword (journal_read -> pattern, else query).
    Documented limits: no quotes or newlines inside argument values.
    """
    calls: List[ToolCall] = []
    for line in text.splitlines():
        match = _TOOL_LINE_RE.search(line.strip())
        if not match:
            continue
        name, argstr = match.group(1), match.group(2).strip()
        args: Dict[str, Any] = {}
        for pair in _ARG_PAIR_RE.finditer(argstr):
            key = pair.group(1) or pair.group(3)
            args[key] = pair.group(2) if pair.group(1) else pair.group(4)
        if not args:
            bare = _BARE_VALUE_RE.match(argstr)
            if bare:
                args["pattern" if name == "journal_read" else "query"] = bare.group(1)
        calls.append(ToolCall(name=name, arguments=args))
    return calls


_TOOL_LINE_RE = re.compile(r"\[\s*TOOL:\s*(\w+)\s*\((.*)\)\s*\]")
_ARG_PAIR_RE = re.compile(r"""(\w+)\s*=\s*"([^"]*)"|(\w+)\s*=\s*'([^']*)'""")
_BARE_VALUE_RE = re.compile(r"""^["']([^"']*)["']$""")


class OllamaProvider(ModelProvider):
    """ModelProvider over the existing S26 Ollama bridge (localhost HTTP)."""

    name = "ollama"

    def __init__(self, model=None, url=None):
        self.model = model
        self.url = url

    def generate(self, request: ModelRequest) -> ModelResponse:
        model = self.model or request.model
        # no availability pre-check: the bridge's ping is itself a full
        # generation (2x cost per turn) and one flaky ping would kill the
        # loop — a dead Ollama surfaces naturally as ProviderError below
        if request.tools:
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
                                       url=self.url, think=think)
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
            text = bridge._ollama_generate(prompt, model=model, url=self.url)
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
