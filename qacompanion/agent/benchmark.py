"""S48 first autonomous coding task: the defect-fix benchmark.

A repeatable harness: write a tiny project with one intentional defect
into a temp workspace, hand the natural-language goal to the S37 loop
with the coding-relevant tool families, and only accept COMPLETED when
an S41 verification plan proves the tests pass. Metrics come from the
session and the S39 event stream — the harness observes what the runtime
already narrates; nothing is estimated.

Pins (fixtures-first discipline):
- intervention_count is 0 by construction: the human never touches the
  workspace during a run; autonomous means no manual commands;
- the suite is hermetic (FakeModelProvider + sys.executable); the live
  model run is a manual smoke, never a CI gate (DECISIONS 2026-09-04);
- success is NEVER self-reported by the model — only the verification
  plan's result counts.
"""

import json
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from .events import EventStream
from .execution import ExecutionToolkit
from .fs_tools import FilesystemToolkit
from .codeintel import CodeIntelToolkit
from .experience import ExperienceStore, MemoryToolkit
from .loop import AgentLoop
from .registry import ToolRegistry
from .verification import VerificationPlan, VerificationStep, plan_verifier
from .workspace import Workspace

CALCULATOR_DEFECT = '''def add(a, b):
    return a - b


def multiply(a, b):
    return a * b
'''

TEST_FILE = '''import unittest

from calculator import add, multiply


class TestCalculator(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)

    def test_multiply(self):
        self.assertEqual(multiply(2, 3), 6)


if __name__ == "__main__":
    unittest.main()
'''

README = '''# Calculator

Tiny demo project. `add(a, b)` must return the sum of a and b;
`multiply(a, b)` the product.
'''

BENCHMARK_GOAL = ("The tests in this project are failing. Find the bug, "
                  "fix it, and run the tests to verify they pass.")

PYTHON = f'"{sys.executable}"'


def _verification_plan() -> VerificationPlan:
    return VerificationPlan(name="benchmark-tests-pass", steps=[
        VerificationStep(name="unit-tests", category="TEST",
                         command=f"{PYTHON} -m unittest -v",
                         must_contain="OK"),
    ])


@dataclass
class BenchmarkReport:
    """Honest metrics for one autonomous run."""

    task: str
    goal: str
    model: str
    success: bool
    termination_reason: str
    iterations: int
    duration_seconds: float
    files_changed: list
    tool_calls: int
    commands_run: int
    tool_failures: int
    recovery_count: int
    verification_results: list
    intervention_count: int = 0

    def to_dict(self):
        return {
            "task": self.task,
            "goal": self.goal,
            "model": self.model,
            "success": self.success,
            "termination_reason": self.termination_reason,
            "iterations": self.iterations,
            "duration_seconds": self.duration_seconds,
            "files_changed": list(self.files_changed),
            "tool_calls": self.tool_calls,
            "commands_run": self.commands_run,
            "tool_failures": self.tool_failures,
            "recovery_count": self.recovery_count,
            "verification_results": list(self.verification_results),
            "intervention_count": self.intervention_count,
        }


def create_fixture(workspace: Workspace) -> None:
    """Write the deterministic defect fixture (idempotent)."""
    (workspace.root / "calculator.py").write_text(CALCULATOR_DEFECT,
                                                  encoding="utf-8")
    (workspace.root / "test_calculator.py").write_text(TEST_FILE,
                                                       encoding="utf-8")
    (workspace.root / "README.md").write_text(README, encoding="utf-8")


def _coding_registry(workspace: Workspace,
                     experience_store: Optional[ExperienceStore] = None
                     ) -> ToolRegistry:
    """The benchmark's tool set: coding families only, hermetic by
    construction (no web, no vision — nothing here needs network)."""
    registry = ToolRegistry()
    for tool in FilesystemToolkit(workspace).tools():
        registry.register(tool)
    for tool in ExecutionToolkit(workspace).tools():
        registry.register(tool)
    for tool in CodeIntelToolkit(workspace).tools():
        registry.register(tool)
    for tool in MemoryToolkit(experience_store).tools():
        registry.register(tool)
    return registry


def run_benchmark(provider, config=None, workspace_root=None,
                  experience_store: Optional[ExperienceStore] = None,
                  events: Optional[EventStream] = None,
                  quiet: bool = True) -> BenchmarkReport:
    """Run one autonomous defect-fix attempt and return honest metrics."""
    root = Path(workspace_root or tempfile.mkdtemp(prefix="benchmark-"))
    workspace = Workspace(root)
    create_fixture(workspace)

    registry = _coding_registry(workspace, experience_store)
    verifier = plan_verifier(_verification_plan(), workspace)
    events = events or EventStream()

    started = time.monotonic()
    loop = AgentLoop(provider, registry, workspace, config=config,
                     verifier=verifier, events=events)
    session = loop.run(BENCHMARK_GOAL)
    duration = time.monotonic() - started

    types = events.types()
    report = BenchmarkReport(
        task="defect-fix-calculator",
        goal=BENCHMARK_GOAL,
        model=getattr(provider, "model", None) or provider.name,
        success=session.state.value == "COMPLETED",
        termination_reason=session.termination_reason or "",
        iterations=session.iterations,
        duration_seconds=round(duration, 2),
        files_changed=list(session.files_changed),
        tool_calls=len(session.tool_calls),
        commands_run=sum(1 for call in session.tool_calls
                         if call.name in ("run_command", "run_tests",
                                          "run_build", "run_lint",
                                          "run_typecheck")),
        tool_failures=sum(1 for e in types if e == "tool_failed"),
        recovery_count=sum(1 for e in types if e == "recovery_started"),
        verification_results=list(session.verification_results),
    )
    return report
