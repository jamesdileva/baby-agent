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

import os
import re
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
