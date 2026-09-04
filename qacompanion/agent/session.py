"""S31 agent session: validated state machine with JSONL-ready serialization.

The session is a verified data structure, not an orchestrator — the S37
loop will drive it. State transitions are any-to-any except out of
terminal states (CANCELLED / COMPLETED / FAILED are final). Deserialization
is strict: malformed records raise ValueError per the S1 storage-culture
rule.
"""

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from .contracts import ModelMessage, ToolCall, ToolResult


class SessionError(Exception):
    """Invalid session operation (e.g. transition out of a terminal state)."""


def _utc_now():
    """UTC ISO-8601 stamp with Z suffix (repo convention)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _require(condition, message):
    if not condition:
        raise ValueError(message)


class AgentState(enum.Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    WAITING_FOR_PERMISSION = "WAITING_FOR_PERMISSION"
    VERIFYING = "VERIFYING"
    RECOVERING = "RECOVERING"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


TERMINAL_STATES = frozenset(
    {AgentState.CANCELLED, AgentState.COMPLETED, AgentState.FAILED}
)


@dataclass
class AgentConfig:
    """Runtime limits for a session (enforced by the S37 loop)."""

    max_iterations: int = 25
    command_timeout_seconds: int = 120
    max_runtime_minutes: int = 30

    def __post_init__(self):
        for name in ("max_iterations", "command_timeout_seconds", "max_runtime_minutes"):
            value = getattr(self, name)
            _require(
                isinstance(value, int) and not isinstance(value, bool) and value > 0,
                f"{name} must be a positive integer",
            )

    def to_dict(self):
        return {
            "max_iterations": self.max_iterations,
            "command_timeout_seconds": self.command_timeout_seconds,
            "max_runtime_minutes": self.max_runtime_minutes,
        }

    @classmethod
    def from_dict(cls, data):
        _require(isinstance(data, dict), "config record must be an object")
        return cls(
            max_iterations=data.get("max_iterations", cls().max_iterations),
            command_timeout_seconds=data.get(
                "command_timeout_seconds", cls().command_timeout_seconds
            ),
            max_runtime_minutes=data.get("max_runtime_minutes", cls().max_runtime_minutes),
        )


@dataclass
class AgentSession:
    """One agent engagement: goal, state, and the full trajectory so far."""

    goal: str
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    workspace_root: str = ""
    state: AgentState = AgentState.CREATED
    iterations: int = 0
    messages: List[ModelMessage] = field(default_factory=list)
    tool_calls: List[ToolCall] = field(default_factory=list)
    observations: List[ToolResult] = field(default_factory=list)
    files_changed: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    final_result: Optional[str] = None
    termination_reason: Optional[str] = None

    def __post_init__(self):
        _require(isinstance(self.goal, str) and self.goal.strip(), "goal required")
        _require(isinstance(self.session_id, str) and self.session_id, "session_id required")
        _require(isinstance(self.state, AgentState), "state must be an AgentState")
        _require(isinstance(self.iterations, int), "iterations must be an integer")

    def transition(self, new_state):
        """Move to a new state. Terminal states are final."""
        if not isinstance(new_state, AgentState):
            raise SessionError(f"transition target must be an AgentState, got {new_state!r}")
        if self.state in TERMINAL_STATES:
            raise SessionError(
                f"session is terminal ({self.state.value}); no further transitions"
            )
        self.state = new_state
        self.updated_at = _utc_now()

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "workspace_root": self.workspace_root,
            "state": self.state.value,
            "iterations": self.iterations,
            "messages": [m.to_dict() for m in self.messages],
            "tool_calls": [c.to_dict() for c in self.tool_calls],
            "observations": [o.to_dict() for o in self.observations],
            "files_changed": list(self.files_changed),
            "errors": list(self.errors),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "final_result": self.final_result,
            "termination_reason": self.termination_reason,
        }

    @classmethod
    def from_dict(cls, data):
        _require(isinstance(data, dict), "session record must be an object")
        _require("goal" in data and data["goal"], "session record missing goal")
        state_raw = data.get("state", AgentState.CREATED.value)
        try:
            state = AgentState(state_raw)
        except ValueError as exc:
            raise ValueError(f"unknown session state: {state_raw!r}") from exc
        return cls(
            goal=data["goal"],
            session_id=data.get("session_id") or uuid.uuid4().hex,
            workspace_root=data.get("workspace_root", ""),
            state=state,
            iterations=data.get("iterations", 0),
            messages=[ModelMessage.from_dict(m) for m in data.get("messages", [])],
            tool_calls=[ToolCall.from_dict(c) for c in data.get("tool_calls", [])],
            observations=[ToolResult.from_dict(o) for o in data.get("observations", [])],
            files_changed=list(data.get("files_changed", [])),
            errors=list(data.get("errors", [])),
            created_at=data.get("created_at", _utc_now()),
            updated_at=data.get("updated_at", _utc_now()),
            final_result=data.get("final_result"),
            termination_reason=data.get("termination_reason"),
        )
