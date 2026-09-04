"""S32 tool registry v2: register, validate, execute, observe, audit.

One ordered pipeline turns a model-declared ToolCall into a structured
ToolResult; every stage failure is a structured denial, never an exception
to the model loop:

    lookup -> validation -> permission -> workspace -> cancellation
    -> execution (timeout) -> audit

Stage subsystems land in their own sprints: Workspace (S33) owns stage 4,
Permissions (S38) the real policy engine behind stage 3, Events (S39) the
event stream behind the audit hook, Execution (S35) real process timeout /
cancellation behind stage 6. The three S27 knowledge tools ship through
default_knowledge_registry() with identical semantics to tools.py.

Pins (fixtures-first discipline):
- execute() never raises for model-facing outcomes; programming errors
  (duplicate registration, bad metadata) raise RegistryError;
- argument validation is strict: required keys enforced, unknown keys
  rejected unless the schema sets additionalProperties: True, booleans
  never count as integers/numbers;
- permission ASK is a structured denial until S38 provides a confirmation
  flow;
- audit callbacks fire for EVERY completed outcome, denials included.
"""

import concurrent.futures
import functools
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .contracts import ToolCall, ToolDefinition, ToolResult
from .permissions import PermissionDecision


class RegistryError(Exception):
    """Programming error in registry use (duplicate name, bad metadata)."""


class ToolOperationError(Exception):
    """An expected tool failure (S34 seam): str(exc) becomes the structured
    ToolResult error, without the 'handler failed' repr prefix reserved for
    unexpected exceptions."""


READ_ONLY = "READ_ONLY"
SAFE_WRITE = "SAFE_WRITE"
EXECUTION = "EXECUTION"
DESTRUCTIVE = "DESTRUCTIVE"
EXTERNAL = "EXTERNAL"
VALID_SIDE_EFFECT_LEVELS = frozenset(
    {READ_ONLY, SAFE_WRITE, EXECUTION, DESTRUCTIVE, EXTERNAL}
)

PRIMITIVE_TYPES = {
    "string": str,
    "array": list,
    "object": dict,
}


@dataclass
class RegisteredTool:
    """A tool's full contract: definition + runtime metadata + handler."""

    definition: ToolDefinition
    handler: Callable[..., str]
    output_schema: Dict[str, Any] = field(default_factory=lambda: {"type": "string"})
    category: str = "general"
    side_effect_level: str = READ_ONLY
    permission_level: str = "default"
    timeout_seconds: float = 30.0
    cancellable: bool = False
    requires_workspace: bool = False
    requires_confirmation: bool = False

    def __post_init__(self):
        if not isinstance(self.definition, ToolDefinition):
            raise RegistryError("definition must be a ToolDefinition")
        if not callable(self.handler):
            raise RegistryError("handler must be callable")
        if not isinstance(self.output_schema, dict):
            raise RegistryError("output_schema must be a dict")
        if self.side_effect_level not in VALID_SIDE_EFFECT_LEVELS:
            raise RegistryError(
                f"unknown side_effect_level: {self.side_effect_level!r}"
            )
        if isinstance(self.timeout_seconds, bool) or not isinstance(
            self.timeout_seconds, (int, float)
        ) or self.timeout_seconds <= 0:
            raise RegistryError("timeout_seconds must be a positive number")

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.definition.name,
            "description": self.definition.description,
            "parameters_schema": self.definition.parameters_schema,
            "output_schema": self.output_schema,
            "category": self.category,
            "side_effect_level": self.side_effect_level,
            "permission_level": self.permission_level,
            "timeout_seconds": self.timeout_seconds,
            "cancellable": self.cancellable,
            "requires_workspace": self.requires_workspace,
            "requires_confirmation": self.requires_confirmation,
        }


class PermissionPolicy:
    """Minimal internal permission seam (the canonical engine lives in
    qacompanion.agent.permissions since S38).

    check() returns ALLOW, DENY, or ASK. The default implementation allows
    everything; conservative deployments override it.
    """

    def check(self, tool_name: str, arguments: Dict[str, Any],
              tool: Any = None) -> str:
        return "ALLOW"


ALLOW_ALL_POLICY = PermissionPolicy()


def validate_tool_arguments(
    definition: ToolDefinition, arguments: Any
) -> List[str]:
    """Strict mini-validator. Returns one error string per problem.

    Supported schema subset: {"type": "object", "properties": {name:
    {"type": primitive}}, "required": [names], "additionalProperties": bool}.
    Booleans are never integers/numbers.
    """
    errors: List[str] = []
    if not isinstance(arguments, dict):
        return [f"arguments must be an object, got {type(arguments).__name__}"]
    schema = definition.parameters_schema or {}
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    for key in required:
        if key not in arguments:
            errors.append(f"missing required argument: {key}")
    allowed_extra = bool(schema.get("additionalProperties", False))
    for key, value in arguments.items():
        if key not in properties:
            if not allowed_extra:
                errors.append(f"unknown argument: {key}")
            continue
        expected = properties[key].get("type")
        if expected == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(f"argument {key} must be an integer")
        elif expected == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"argument {key} must be a number")
        elif expected == "boolean":
            if not isinstance(value, bool):
                errors.append(f"argument {key} must be a boolean")
        elif expected in PRIMITIVE_TYPES:
            if not isinstance(value, PRIMITIVE_TYPES[expected]):
                errors.append(f"argument {key} must be a {expected}")
        elif expected is not None:
            errors.append(f"argument {key} has unsupported schema type: {expected!r}")
    return errors


@dataclass
class _Outcome:
    """Internal pipeline result before conversion to ToolResult."""

    ok: bool
    output: str = ""
    error: Optional[str] = None
    timed_out: bool = False
    cancelled: bool = False


def _as_decision(tool_name: str, mode_or_decision, rule: str = "policy",
                 reason: str = "") -> PermissionDecision:
    """Normalize a policy's return value into a PermissionDecision."""
    if isinstance(mode_or_decision, PermissionDecision):
        return mode_or_decision
    return PermissionDecision(
        tool_name=tool_name, mode=mode_or_decision, rule=rule, reason=reason,
    )


class ToolRegistry:
    """Registry + executor for agent tools."""

    def __init__(self):
        self._tools: Dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        name = tool.definition.name
        if name in self._tools:
            raise RegistryError(f"tool already registered: {name!r}")
        self._tools[name] = tool

    def get(self, name: str) -> RegisteredTool:
        if name not in self._tools:
            raise RegistryError(f"unknown tool: {name!r}")
        return self._tools[name]

    def names(self) -> List[str]:
        return sorted(self._tools)

    def schemas(self) -> List[ToolDefinition]:
        return [self._tools[name].definition for name in sorted(self._tools)]

    def describe(self) -> List[Dict[str, Any]]:
        return [self._tools[name].describe() for name in sorted(self._tools)]

    def execute(
        self,
        tool_call: ToolCall,
        policy: Optional[PermissionPolicy] = None,
        workspace: Optional[Any] = None,
        cancel_event: Optional[threading.Event] = None,
        audit: Optional[Callable[[ToolResult], None]] = None,
        confirmer: Optional[Callable[[ToolCall, Any], bool]] = None,
    ) -> ToolResult:
        """Run the full pipeline. Never raises for model-facing outcomes.

        confirmer (S38): when the policy says ASK, confirmer(tool_call,
        decision) truthy approves the call, falsy denies it; absent
        confirmer keeps the S32 safe default (ASK = structured denial).
        """
        started = time.monotonic()
        outcome = self._run_pipeline(tool_call, policy, workspace, cancel_event,
                                     confirmer)
        duration_ms = int((time.monotonic() - started) * 1000)
        result = ToolResult(
            call_name=tool_call.name,
            ok=outcome.ok,
            output=outcome.output,
            call_id=tool_call.call_id,
            error=outcome.error,
            duration_ms=duration_ms,
            timed_out=outcome.timed_out,
            cancelled=outcome.cancelled,
        )
        if audit is not None:
            audit(result)
        return result

    def _run_pipeline(
        self,
        tool_call: ToolCall,
        policy: Optional[PermissionPolicy],
        workspace: Optional[Any],
        cancel_event: Optional[threading.Event],
        confirmer: Optional[Callable[[ToolCall, Any], bool]] = None,
    ) -> _Outcome:
        tool = self._tools.get(tool_call.name)
        if tool is None:
            return _Outcome(ok=False, error=f"unknown tool {tool_call.name!r}")

        validation_errors = validate_tool_arguments(
            tool.definition, tool_call.arguments
        )
        if validation_errors:
            return _Outcome(
                ok=False,
                error="invalid arguments: " + "; ".join(validation_errors),
            )

        raw_decision = (policy or ALLOW_ALL_POLICY).check(
            tool_call.name, tool_call.arguments, tool
        )
        # normalize: policies return mode strings; the confirmer always
        # receives a full PermissionDecision
        decision = _as_decision(tool_call.name, raw_decision)
        # pipeline guarantee: a tool's own requires_confirmation declaration
        # forces ASK even when the policy would allow (S36 posture: commits
        # are never autonomous, whatever the policy says)
        if decision.mode == "ALLOW" and tool.requires_confirmation:
            decision = _as_decision(tool_call.name, "ASK",
                                    rule="confirmation-required",
                                    reason=f"{tool_call.name} declares "
                                           f"requires_confirmation")
        if decision.mode == "DENY":
            return _Outcome(ok=False, error="permission denied by policy")
        if decision.mode == "ASK":
            if confirmer is None:
                return _Outcome(
                    ok=False,
                    error="permission ASK requires confirmation "
                          "but no confirmer is available",
                )
            try:
                approved = confirmer(tool_call, decision)
            except Exception as exc:
                return _Outcome(ok=False, error=f"confirmer crashed: {exc!r}")
            if not approved:
                return _Outcome(ok=False, error="denied by confirmation")
            # approved: fall through to workspace / cancellation / execution

        if tool.requires_workspace and workspace is None:
            return _Outcome(
                ok=False,
                error="workspace required but not configured (S33)",
            )

        if cancel_event is not None and cancel_event.is_set():
            return _Outcome(ok=False, error="cancelled before execution", cancelled=True)

        return self._execute_handler(tool, tool_call.arguments)

    def _execute_handler(self, tool: RegisteredTool, arguments: Dict[str, Any]) -> _Outcome:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(tool.handler, **arguments)
            try:
                output = future.result(timeout=tool.timeout_seconds)
            except concurrent.futures.TimeoutError:
                return _Outcome(
                    ok=False,
                    error=f"timed out after {tool.timeout_seconds}s",
                    timed_out=True,
                )
            except ToolOperationError as exc:
                return _Outcome(ok=False, error=str(exc))
            except Exception as exc:
                return _Outcome(ok=False, error=f"handler failed: {exc!r}")
        if output is None:
            output = ""
        elif not isinstance(output, str):
            output = str(output)
        return _Outcome(ok=True, output=output)


def default_knowledge_registry(
    cases_path=None, digest_path=None, ledger=None
) -> ToolRegistry:
    """Registry preloaded with the three S27 knowledge tools.

    Handlers are the unchanged tools.py functions with the optional store
    paths bound; semantics stay owned by the S27 suite.
    """
    from .. import tools as tools_mod

    registry = ToolRegistry()

    def _knowledge(name, description, arg_name, handler):
        return RegisteredTool(
            definition=ToolDefinition(
                name=name,
                description=description,
                parameters_schema={
                    "type": "object",
                    "properties": {arg_name: {"type": "string"}},
                    "required": [arg_name],
                },
            ),
            handler=handler,
            category="knowledge",
            side_effect_level=READ_ONLY,
            permission_level="read",
        )

    registry.register(_knowledge(
        "case_search", "Search past failure cases by keyword.", "query",
        functools.partial(tools_mod.case_search, cases_path=cases_path),
    ))
    registry.register(_knowledge(
        "doc_grep", "Search digested documentation by keyword.", "query",
        functools.partial(tools_mod.doc_grep, digest_path=digest_path),
    ))
    registry.register(_knowledge(
        "journal_read", "Search the journal ledger by pattern.", "pattern",
        functools.partial(tools_mod.journal_read, ledger=ledger),
    ))
    return registry
