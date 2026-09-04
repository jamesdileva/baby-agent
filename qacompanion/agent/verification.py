"""S41 verification engine: prove the requested behavior, don't claim it.

A VerificationPlan is a named sequence of command steps (BUILD, TEST,
LINT, TYPECHECK, RUNTIME, HEALTHCHECK) run sequentially at the workspace
root through the S35 execution machinery — timeout, tree-kill, output
caps and Z-stamps all apply. A failed non-optional step skips the rest
(stop_on_first_failure); skipped steps record ok=None. GOAL predicates
remain the S37 verifier seam; `plan_verifier` adapts a plan into that
seam. REGRESSION is a TEST plan rerun; VISUAL waits for S44.

Pins (fixtures-first discipline):
- steps run at the WORKSPACE ROOT only — no per-step cwd (the root is the
  S33-resolved boundary; per-step cwd can come later with a policy
  resolve);
- the model can request verification itself via the run_verification
  tool — same S38-gated EXECUTION pipeline as run_command, no new
  escalation;
- reports are JSON-ready dicts, honest about every step.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .execution import DEFAULT_COMMAND_TIMEOUT, execute_command
from .registry import EXECUTION, RegisteredTool, ToolDefinition, ToolOperationError, ToolRegistry
from .workspace import Workspace

BUILD = "BUILD"
TEST = "TEST"
LINT = "LINT"
TYPECHECK = "TYPECHECK"
RUNTIME = "RUNTIME"
HEALTHCHECK = "HEALTHCHECK"
STEP_CATEGORIES = (BUILD, TEST, LINT, TYPECHECK, RUNTIME, HEALTHCHECK)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


@dataclass
class VerificationStep:
    """One verification command and what 'passing' means for it."""

    name: str
    category: str
    command: str
    expect_exit: int = 0
    must_contain: Optional[str] = None
    must_not_contain: Optional[str] = None
    optional: bool = False

    def __post_init__(self):
        _require(isinstance(self.name, str) and self.name.strip(),
                 "step name required")
        _require(self.category in STEP_CATEGORIES,
                 f"unknown step category: {self.category!r} "
                 f"(known: {', '.join(STEP_CATEGORIES)})")
        _require(isinstance(self.command, str) and self.command.strip(),
                 f"step {self.name!r}: command required")
        _require(isinstance(self.expect_exit, int)
                 and not isinstance(self.expect_exit, bool),
                 f"step {self.name!r}: expect_exit must be an integer")

    def to_dict(self):
        return {
            "name": self.name,
            "category": self.category,
            "command": self.command,
            "expect_exit": self.expect_exit,
            "must_contain": self.must_contain,
            "must_not_contain": self.must_not_contain,
            "optional": self.optional,
        }

    @classmethod
    def from_dict(cls, data):
        _require(isinstance(data, dict), "step record must be an object")
        _require("name" in data and "category" in data and "command" in data,
                 "step record missing name/category/command")
        return cls(
            name=data["name"],
            category=data["category"],
            command=data["command"],
            expect_exit=data.get("expect_exit", 0),
            must_contain=data.get("must_contain"),
            must_not_contain=data.get("must_not_contain"),
            optional=bool(data.get("optional", False)),
        )


@dataclass
class VerificationResult:
    """The outcome of one step: ok=True passed, False failed, None skipped."""

    name: str
    category: str
    ok: Optional[bool]
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0

    def to_dict(self):
        return {
            "name": self.name,
            "category": self.category,
            "ok": self.ok,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
        }


@dataclass
class VerificationReport:
    """Aggregated plan outcome: ok means every non-optional step passed."""

    plan_name: str
    ok: bool
    steps: List[VerificationResult] = field(default_factory=list)

    def to_dict(self):
        return {
            "plan": self.plan_name,
            "ok": self.ok,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass
class VerificationPlan:
    """A named, data-driven sequence of verification steps."""

    name: str
    steps: List[VerificationStep]
    stop_on_first_failure: bool = True

    def __post_init__(self):
        _require(isinstance(self.name, str) and self.name.strip(),
                 "plan name required")
        _require(isinstance(self.steps, list) and self.steps,
                 "plan requires at least one step")
        _require(all(isinstance(s, VerificationStep) for s in self.steps),
                 "plan steps must be VerificationStep instances")

    def to_dict(self):
        return {
            "name": self.name,
            "steps": [step.to_dict() for step in self.steps],
            "stop_on_first_failure": self.stop_on_first_failure,
        }

    @classmethod
    def from_dict(cls, data):
        _require(isinstance(data, dict), "plan record must be an object")
        _require("name" in data, "plan record missing name")
        _require(isinstance(data.get("steps"), list) and data["steps"],
                 "plan record requires a non-empty steps list")
        return cls(
            name=data["name"],
            steps=[VerificationStep.from_dict(step) for step in data["steps"]],
            stop_on_first_failure=bool(data.get("stop_on_first_failure", True)),
        )

    def run(self, workspace: Workspace,
            timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT) -> VerificationReport:
        """Run steps sequentially at the workspace root."""
        results: List[VerificationResult] = []
        plan_ok = True
        aborted = False
        for step in self.steps:
            if aborted:
                results.append(VerificationResult(
                    name=step.name, category=step.category, ok=None))
                continue
            command = execute_command(
                workspace, command=step.command, cwd=".",
                timeout_seconds=timeout_seconds,
            )
            if command.timed_out or command.cancelled:
                step_ok = False
            else:
                step_ok = command.exit_code == step.expect_exit
                if step_ok and step.must_contain is not None:
                    step_ok = step.must_contain in (command.stdout or "")
                if step_ok and step.must_not_contain is not None:
                    combined = (command.stdout or "") + (command.stderr or "")
                    step_ok = step.must_not_contain not in combined
            results.append(VerificationResult(
                name=step.name, category=step.category, ok=step_ok,
                exit_code=command.exit_code, stdout=command.stdout,
                stderr=command.stderr, duration_ms=command.duration_ms,
            ))
            if not step_ok:
                if step.optional:
                    continue
                plan_ok = False
                if self.stop_on_first_failure:
                    aborted = True
        return VerificationReport(plan_name=self.name, ok=plan_ok, steps=results)


def plan_verifier(plan: VerificationPlan, workspace: Workspace,
                  timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT
                  ) -> Callable[[Any], Tuple[bool, str]]:
    """Adapt a plan into the S37 loop verifier seam."""
    def verify(session) -> Tuple[bool, str]:
        report = plan.run(workspace, timeout_seconds=timeout_seconds)
        detail = f"plan {plan.name!r}: " + ", ".join(
            f"{step.name}={'pass' if step.ok else ('skipped' if step.ok is None else 'FAIL')}"
            for step in report.steps
        )
        return report.ok, detail
    return verify


def run_plan_tool(workspace: Workspace, plan: Dict[str, Any],
                  timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT) -> str:
    """Handler for the run_verification registry tool."""
    try:
        parsed = VerificationPlan.from_dict(plan)
    except ValueError as exc:
        raise ToolOperationError(f"invalid verification plan: {exc}") from exc
    report = parsed.run(workspace, timeout_seconds=timeout_seconds)
    return json.dumps(report.to_dict(), ensure_ascii=False)


class VerificationToolkit:
    """Binds run_verification to one workspace."""

    def __init__(self, workspace: Workspace):
        self.workspace = workspace

    def tools(self) -> List[RegisteredTool]:
        return [RegisteredTool(
            definition=ToolDefinition(
                name="run_verification",
                description="Run a named verification plan (sequential "
                            "command steps: BUILD/TEST/LINT/TYPECHECK/"
                            "RUNTIME/HEALTHCHECK) and return the report.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "plan": {
                            "type": "object",
                            "description": "plan record: {name, steps: "
                                           "[{name, category, command, ...}]}",
                        },
                        "timeout_seconds": {"type": "number"},
                    },
                    "required": ["plan"],
                },
            ),
            handler=lambda **kw: run_plan_tool(
                self.workspace, kw.get("plan") or {},
                timeout_seconds=kw.get("timeout_seconds",
                                       DEFAULT_COMMAND_TIMEOUT),
            ),
            category="verification",
            side_effect_level=EXECUTION,
            requires_workspace=True,
        )]


def update_agent_registry(registry: ToolRegistry, workspace: Workspace) -> None:
    """Register the verification tools into an existing registry."""
    for tool in VerificationToolkit(workspace).tools():
        registry.register(tool)
