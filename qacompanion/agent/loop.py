"""S37 agent loop: the first autonomous model/tool/observation cycle.

The runtime has no hard-coded knowledge of any task — the model (real or
FakeModelProvider) drives, the S32 registry executes, and every observation
feeds back as a structured `tool`-role message. Permission denials, unknown
tools, and timeouts are observations the model adapts to, never exceptions.

Pins (fixtures-first discipline):
- final answer = a response with no tool calls; empty-text responses are
  recorded errors and the loop continues (iteration-bounded);
- the optional verifier callable is the S41 preview: failure enters
  RECOVERING, the failure is fed back, and the loop retries within limits;
- changed-file tracking is metadata-driven (write-level side effect + a
  JSON output carrying a `path` key) — no tool names hard-coded here;
- WAITING_FOR_PERMISSION and PAUSED are reserved (S38/S45) and unreachable;
- termination always ends in a terminal state with a reason string.
"""

import json
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .contracts import ModelMessage, ModelRequest, ToolResult
from .registry import SAFE_WRITE, EXECUTION, DESTRUCTIVE, EXTERNAL, ToolRegistry
from .providers import ModelProvider, ProviderError
from .qa_brain import format_advice
from .session import AgentConfig, AgentSession, AgentState, SessionError
from .workspace import Workspace

WRITE_LEVELS = frozenset({SAFE_WRITE, EXECUTION, DESTRUCTIVE, EXTERNAL})

TERMINATION_COMPLETED = "goal completed"
TERMINATION_MAX_ITERATIONS = "max iterations reached ({0})"
TERMINATION_MAX_RUNTIME = "max runtime exceeded"
TERMINATION_CANCELLED = "cancelled by user"
TERMINATION_PROVIDER_ERROR = "provider error: {0}"
TERMINATION_VERIFICATION_FAILED = "verification failed after {0} attempts"

DEFAULT_SYSTEM_PROMPT = (
    "You are Baby-Agent, an autonomous coding agent working inside a "
    "bounded workspace. Inspect before acting, act through tools, and "
    "verify your work. When the goal is achieved and verified, reply with "
    "a concise final summary and no tool calls."
)

TOOL_PROTOCOL_PROMPT = (
    "\n\n## Tool use\n"
    "To call a tool, output a line exactly in this format:\n"
    '[TOOL: tool_name(argument="value", another="value2")]\n'
    "One call per line; arguments are double-quoted strings (no quotes or "
    "newlines inside a value). After the tool results are returned, keep "
    "working or give your final answer.\n"
    "\n"
    "Example — to create a file, output exactly this shape:\n"
    '[TOOL: write_file(path="notes.txt", content="meeting at noon")]'
)


def build_system_prompt(tools, base: str = DEFAULT_SYSTEM_PROMPT) -> str:
    """Render the tool catalog + textual call protocol into the system
    prompt (the loop owns tool prompt-engineering; providers stay generic).
    Text-protocol models cannot call tools unless the exact syntax is
    taught — found by the live smoke test."""
    lines = [base]
    if tools:
        lines.append("")
        lines.append("Available tools:")
        for tool in tools:
            lines.append(f"- {tool.name}: {tool.description}")
        lines.append(TOOL_PROTOCOL_PROMPT)
    return "\n".join(lines)


def _deadline_exceeded(started_monotonic: float, config: AgentConfig,
                       now: Optional[float] = None) -> bool:
    now = time.monotonic() if now is None else now
    elapsed_seconds = now - started_monotonic
    return elapsed_seconds > config.max_runtime_minutes * 60


def _extract_changed_path(result: ToolResult, registry: ToolRegistry) -> Optional[str]:
    """Metadata-driven changed-file extraction: write-level tool + JSON
    output carrying a `path` key."""
    try:
        tool = registry.get(result.call_name)
    except Exception:
        return None
    if tool.side_effect_level not in WRITE_LEVELS:
        return None
    if not result.ok:
        return None
    try:
        payload = json.loads(result.output)
    except (ValueError, TypeError):
        return None
    if isinstance(payload, dict) and isinstance(payload.get("path"), str):
        return payload["path"]
    return None


class AgentLoop:
    """Drives goal -> model -> tool -> observation -> ... -> verify -> done."""

    def __init__(
        self,
        provider: ModelProvider,
        registry: ToolRegistry,
        workspace: Workspace,
        config: Optional[AgentConfig] = None,
        policy: Optional[Any] = None,
        cancel_event=None,
        verifier: Optional[Callable[[AgentSession], Tuple[bool, str]]] = None,
        confirmer: Optional[Callable[[Any, Any], bool]] = None,
        events=None,
        qa_brain=None,
    ):
        self.provider = provider
        self.registry = registry
        self.workspace = workspace
        self.config = config or AgentConfig()
        self.policy = policy
        self.cancel_event = cancel_event
        self.verifier = verifier
        self.confirmer = confirmer
        self.events = events
        self.qa_brain = qa_brain

    # -- helpers ----------------------------------------------------------

    def _cancelled(self) -> bool:
        return self.cancel_event is not None and self.cancel_event.is_set()

    def _emit(self, event_type: str, session: AgentSession, **payload) -> None:
        if self.events is not None:
            self.events.emit(event_type, session.session_id, payload)

    def _set_state(self, session: AgentSession, state: AgentState) -> None:
        previous = session.state
        session.transition(state)
        self._emit("session_state_changed", session,
                   **{"from": previous.value, "to": state.value})

    def _finish(self, session: AgentSession, state: AgentState, reason: str) -> AgentSession:
        try:
            self._set_state(session, state)
        except SessionError:
            pass  # already terminal
        session.termination_reason = reason
        terminal_event = {
            AgentState.COMPLETED: "session_completed",
            AgentState.CANCELLED: "session_cancelled",
            AgentState.FAILED: "session_failed",
        }.get(state)
        if terminal_event:
            self._emit(terminal_event, session, termination_reason=reason)
        return session

    def _record_failure(self, session: AgentSession, message: str) -> None:
        session.errors.append(message)
        self._emit("failure_detected", session, message=message)

    # -- main loop --------------------------------------------------------

    def run(self, goal: str, session: Optional[AgentSession] = None) -> AgentSession:
        session = session or AgentSession(
            goal=goal, workspace_root=str(self.workspace.root)
        )
        self._emit("session_started", session, goal=goal,
                   workspace_root=session.workspace_root)
        self._set_state(session, AgentState.PLANNING)
        messages: List[ModelMessage] = [
            ModelMessage(role="system",
                         content=build_system_prompt(self.registry.schemas())),
            ModelMessage(role="user", content=goal),
        ]
        session.messages.extend(messages)

        started = time.monotonic()
        self._set_state(session, AgentState.RUNNING)

        while True:
            if self._cancelled():
                return self._finish(session, AgentState.CANCELLED,
                                    TERMINATION_CANCELLED)
            if session.iterations >= self.config.max_iterations:
                return self._finish(session, AgentState.FAILED,
                                    TERMINATION_MAX_ITERATIONS.format(
                                        self.config.max_iterations))
            if _deadline_exceeded(started, self.config):
                return self._finish(session, AgentState.FAILED,
                                    TERMINATION_MAX_RUNTIME)

            session.iterations += 1
            self._emit("model_started", session, iteration=session.iterations)
            try:
                response = self.provider.generate(
                    ModelRequest(messages=list(session.messages),
                                 tools=self.registry.schemas())
                )
            except ProviderError as exc:
                self._record_failure(session, str(exc))
                return self._finish(session, AgentState.FAILED,
                                    TERMINATION_PROVIDER_ERROR.format(exc))

            self._emit("model_response", session,
                       iteration=session.iterations,
                       finish_reason=response.finish_reason,
                       has_tool_calls=response.has_tool_calls(),
                       tool_call_names=[c.name for c in response.tool_calls])

            if response.finish_reason == "error":
                self._record_failure(session, response.text or "model error")
                return self._finish(session, AgentState.FAILED,
                                    TERMINATION_PROVIDER_ERROR.format(
                                        response.text or "model error"))

            if not response.has_tool_calls():
                if not response.text.strip():
                    self._record_failure(session, "empty model response")
                    continue
                # final answer -> verify
                self._set_state(session, AgentState.VERIFYING)
                if self.verifier is not None:
                    attempt = len(session.verification_results) + 1
                    self._emit("verification_started", session, attempt=attempt)
                    ok, detail = self._verify(session)
                    session.verification_results.append({
                        "ok": ok, "detail": detail,
                        "at": session.updated_at,
                    })
                    self._emit("verification_completed", session,
                               attempt=attempt, ok=ok, detail=detail)
                    if ok:
                        session.final_result = response.text
                        return self._finish(session, AgentState.COMPLETED,
                                            TERMINATION_COMPLETED)
                    attempts = len(session.verification_results)
                    if session.iterations >= self.config.max_iterations:
                        return self._finish(
                            session, AgentState.FAILED,
                            TERMINATION_VERIFICATION_FAILED.format(attempts),
                        )
                    self._set_state(session, AgentState.RECOVERING)
                    self._emit("recovery_started", session, attempt=attempt)
                    session.messages.append(
                        ModelMessage(role="assistant", content=response.text))
                    session.messages.append(ModelMessage(
                        role="user",
                        content=f"Verification failed: {detail}. "
                                "Diagnose, fix, and try again.",
                    ))
                    self._set_state(session, AgentState.RUNNING)
                    continue
                session.final_result = response.text
                return self._finish(session, AgentState.COMPLETED,
                                    TERMINATION_COMPLETED)

            # tool turn
            session.messages.append(ModelMessage(
                role="assistant", content=response.text))
            for call in response.tool_calls:
                if self._cancelled():
                    return self._finish(session, AgentState.CANCELLED,
                                        TERMINATION_CANCELLED)
                self._emit("tool_requested", session, tool=call.name,
                           arguments=dict(call.arguments))
                try:
                    result = self.registry.execute(
                        call,
                        policy=self.policy,
                        workspace=self.workspace,
                        cancel_event=self.cancel_event,
                        confirmer=self.confirmer,
                        event_stream=self.events,
                        session_id=session.session_id,
                    )
                except Exception as exc:  # pipeline crash: feed back, continue
                    self._record_failure(
                        session, f"tool execution crashed: {exc!r}")
                    result = ToolResult(
                        call_name=call.name, ok=False, output="",
                        error=f"tool execution crashed: {exc}",
                    )
                session.tool_calls.append(call)
                session.observations.append(result)
                changed = _extract_changed_path(result, self.registry)
                if changed and changed not in session.files_changed:
                    session.files_changed.append(changed)
                if not result.ok:
                    self._record_failure(
                        session, f"tool {call.name!r} failed: {result.error}")
                    self._emit("tool_failed", session, tool=call.name,
                               error=result.error,
                               duration_ms=result.duration_ms)
                else:
                    self._emit("tool_completed", session, tool=call.name,
                               duration_ms=result.duration_ms,
                               changed_path=changed)
                if changed:
                    self._emit("file_changed", session, path=changed)
                session.messages.append(ModelMessage(
                    role="tool",
                    content=json.dumps(result.to_dict(), ensure_ascii=False),
                ))
                if self.qa_brain is not None:
                    # S49: the QA brain's advice reaches the model BEFORE
                    # its next action. The brain owns failure semantics
                    # (failed results AND the S35 embedded-CommandResult
                    # convention) — the loop only asks. Recording cases
                    # is S50's job.
                    advice = self.qa_brain.advise(result)
                    if advice:
                        session.messages.append(ModelMessage(
                            role="system",
                            content=format_advice(advice)))
                        self._emit("memory_advice", session,
                                   source=advice.get("source"),
                                   call=call.name)

    def _verify(self, session: AgentSession) -> Tuple[bool, str]:
        try:
            ok, detail = self.verifier(session)
            return bool(ok), str(detail)
        except Exception as exc:
            return False, f"verifier crashed: {exc!r}"
