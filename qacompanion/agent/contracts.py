"""S31 agent contracts: structured model/tool/session representations.

The Agent-Lite runtime speaks in structured objects, never parsed model
text: ModelProvider returns ModelResponse carrying ToolCall objects; tool
capabilities are ToolDefinition instances. Serialization is plain dicts
(callers own JSON encoding) with strict validation on the way in —
malformed records raise ValueError, per the S1 storage-culture rule.

Pins (fixtures-first discipline):
- message roles: system, user, assistant, tool (ValueError otherwise);
- finish reasons: stop, tool_calls, error;
- ToolCall / ToolDefinition are frozen (attribute assignment blocked);
- knowledge tools (case_search, doc_grep, journal_read) carry schemas
  matching their tools.py argument shapes (query / pattern strings);
- timestamps, where present, are UTC ISO-8601 with Z suffix (repo
  convention, see session.py).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

VALID_ROLES = ("system", "user", "assistant", "tool")
FINISH_REASONS = ("stop", "tool_calls", "error")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class ModelMessage:
    """One conversation turn."""

    role: str
    content: str

    def __post_init__(self):
        _require(self.role in VALID_ROLES, f"invalid message role: {self.role!r}")
        _require(isinstance(self.content, str), "message content must be a string")

    def to_dict(self):
        return {"role": self.role, "content": self.content}

    @classmethod
    def from_dict(cls, data):
        _require(isinstance(data, dict), "message record must be an object")
        _require("role" in data and "content" in data, "message missing role/content")
        return cls(role=data["role"], content=data["content"])


@dataclass
class ModelRequest:
    """What the runtime asks of a provider."""

    messages: List[ModelMessage] = field(default_factory=list)
    tools: List["ToolDefinition"] = field(default_factory=list)
    model: Optional[str] = None
    temperature: Optional[float] = None

    def __post_init__(self):
        _require(
            all(isinstance(m, ModelMessage) for m in self.messages),
            "request messages must be ModelMessage instances",
        )
        _require(
            all(isinstance(t, ToolDefinition) for t in self.tools),
            "request tools must be ToolDefinition instances",
        )

    def to_dict(self):
        return {
            "messages": [m.to_dict() for m in self.messages],
            "tools": [t.to_dict() for t in self.tools],
            "model": self.model,
            "temperature": self.temperature,
        }

    @classmethod
    def from_dict(cls, data):
        _require(isinstance(data, dict), "request record must be an object")
        messages = [ModelMessage.from_dict(m) for m in data.get("messages", [])]
        tools = [ToolDefinition.from_dict(t) for t in data.get("tools", [])]
        return cls(
            messages=messages,
            tools=tools,
            model=data.get("model"),
            temperature=data.get("temperature"),
        )


@dataclass
class ModelResponse:
    """Normalized provider output: text, structured tool calls, metadata."""

    text: str = ""
    tool_calls: List["ToolCall"] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Optional[Dict[str, Any]] = None
    model: Optional[str] = None

    def __post_init__(self):
        _require(
            self.finish_reason in FINISH_REASONS,
            f"invalid finish_reason: {self.finish_reason!r}",
        )
        _require(
            all(isinstance(c, ToolCall) for c in self.tool_calls),
            "response tool_calls must be ToolCall instances",
        )

    def has_tool_calls(self):
        return bool(self.tool_calls)

    def to_dict(self):
        return {
            "text": self.text,
            "tool_calls": [c.to_dict() for c in self.tool_calls],
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, data):
        _require(isinstance(data, dict), "response record must be an object")
        return cls(
            text=data.get("text", ""),
            tool_calls=[ToolCall.from_dict(c) for c in data.get("tool_calls", [])],
            finish_reason=data.get("finish_reason", "stop"),
            usage=data.get("usage"),
            model=data.get("model"),
        )


@dataclass(frozen=True)
class ToolDefinition:
    """A tool's contract: name, description, JSON-schema-style parameters."""

    name: str
    description: str
    parameters_schema: Dict[str, Any]

    def __post_init__(self):
        _require(isinstance(self.name, str) and self.name.strip(), "tool name required")
        _require(isinstance(self.description, str), "tool description must be a string")
        _require(isinstance(self.parameters_schema, dict), "parameters_schema must be a dict")

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters_schema": self.parameters_schema,
        }

    @classmethod
    def from_dict(cls, data):
        _require(isinstance(data, dict), "tool definition must be an object")
        _require(
            "name" in data and "description" in data and "parameters_schema" in data,
            "tool definition missing name/description/parameters_schema",
        )
        return cls(
            name=data["name"],
            description=data["description"],
            parameters_schema=data["parameters_schema"],
        )


@dataclass(frozen=True)
class ToolCall:
    """A requested tool invocation: name + structured arguments."""

    name: str
    arguments: Dict[str, Any]
    call_id: Optional[str] = None

    def __post_init__(self):
        _require(isinstance(self.name, str) and self.name.strip(), "tool call name required")
        _require(isinstance(self.arguments, dict), "tool call arguments must be a dict")

    def to_dict(self):
        return {
            "name": self.name,
            "arguments": self.arguments,
            "call_id": self.call_id,
        }

    @classmethod
    def from_dict(cls, data):
        _require(isinstance(data, dict), "tool call must be an object")
        _require("name" in data and "arguments" in data, "tool call missing name/arguments")
        return cls(
            name=data["name"],
            arguments=data["arguments"],
            call_id=data.get("call_id"),
        )


@dataclass
class ToolResult:
    """The recorded outcome of one tool invocation (S32 adds the executor
    pipeline; timed_out/cancelled are the S32 structured outcome flags)."""

    call_name: str
    ok: bool
    output: str
    call_id: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    timed_out: bool = False
    cancelled: bool = False

    def __post_init__(self):
        _require(isinstance(self.call_name, str) and self.call_name.strip(), "call_name required")
        _require(isinstance(self.output, str), "tool result output must be a string")

    def to_dict(self):
        return {
            "call_name": self.call_name,
            "ok": self.ok,
            "output": self.output,
            "call_id": self.call_id,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
            "cancelled": self.cancelled,
        }

    @classmethod
    def from_dict(cls, data):
        _require(isinstance(data, dict), "tool result must be an object")
        _require(
            "call_name" in data and "ok" in data and "output" in data,
            "tool result missing call_name/ok/output",
        )
        return cls(
            call_name=data["call_name"],
            ok=bool(data["ok"]),
            output=data["output"],
            call_id=data.get("call_id"),
            error=data.get("error"),
            duration_ms=data.get("duration_ms"),
            timed_out=bool(data.get("timed_out", False)),
            cancelled=bool(data.get("cancelled", False)),
        )


def knowledge_tool_definitions():
    """ToolDefinitions for the three S27 knowledge tools.

    Schemas mirror the tools.py argument shapes so the model-facing
    contract and the dispatch contract cannot drift apart silently.
    """
    def _string_arg(name, description):
        return {
            "type": "object",
            "properties": {name: {"type": "string", "description": description}},
            "required": [name],
        }

    return [
        ToolDefinition(
            name="case_search",
            description="Search past failure cases by keyword.",
            parameters_schema=_string_arg("query", "search keywords"),
        ),
        ToolDefinition(
            name="doc_grep",
            description="Search digested documentation by keyword.",
            parameters_schema=_string_arg("query", "search keywords"),
        ),
        ToolDefinition(
            name="journal_read",
            description="Search the journal ledger by pattern.",
            parameters_schema=_string_arg("pattern", "search pattern"),
        ),
    ]
