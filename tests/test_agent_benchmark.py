"""S48 benchmark tests: hermetic autonomous defect-fix runs.

FakeModelProvider scripts the model; every command is sys.executable;
no network anywhere.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import (
    AgentConfig,
    FakeModelProvider,
    ModelResponse,
    ToolCall,
    Workspace,
)
from qacompanion.agent.benchmark import (
    BENCHMARK_GOAL,
    create_fixture,
    run_benchmark,
)

PY = f'"{sys.executable}"'


def _success_script():
    """inspect -> run tests (fail) -> fix -> run tests (pass) -> final."""
    return [
        ToolCall(name="read_file", arguments={"path": "calculator.py"}),
        ToolCall(name="run_tests", arguments={"command": f"{PY} -m unittest"}),
        ToolCall(name="edit_file", arguments={
            "path": "calculator.py",
            "old_string": "    return a - b",
            "new_string": "    return a + b",
        }),
        ToolCall(name="run_tests", arguments={"command": f"{PY} -m unittest"}),
        ModelResponse(text="The add() function subtracted instead of "
                           "adding. Fixed and verified: 2 tests pass.",
                      finish_reason="stop"),
    ]


class TestBenchmarkSuccess(unittest.TestCase):
    def test_autonomous_defect_fix(self):
        report = run_benchmark(FakeModelProvider(_success_script()))
        self.assertTrue(report.success, report.termination_reason)
        self.assertEqual(report.termination_reason, "goal completed")
        self.assertEqual(report.intervention_count, 0)
        self.assertIn("calculator.py", report.files_changed)
        self.assertEqual(report.tool_failures, 0)
        self.assertGreaterEqual(report.commands_run, 2)
        self.assertTrue(all(v["ok"] for v in report.verification_results))
        serialized = json.dumps(report.to_dict())
        self.assertIn('"success": true', serialized)


class TestBenchmarkFailure(unittest.TestCase):
    def test_model_that_never_fixes_fails_honestly(self):
        provider = FakeModelProvider([
            ModelResponse(text="I looked at it, seems fine!",
                          finish_reason="stop"),
            ModelResponse(text="Still looks fine to me!",
                          finish_reason="stop"),
        ])
        report = run_benchmark(provider, config=AgentConfig(max_iterations=2))
        self.assertFalse(report.success)
        self.assertIn("verification failed", report.termination_reason)
        self.assertEqual(report.recovery_count, 1)


class TestRecoveryAccounting(unittest.TestCase):
    def test_failed_then_recovered_run_counts_recovery(self):
        # premature "Done!" -> verifier fails -> RECOVERING -> the model
        # fixes the defect -> verifier passes
        provider = FakeModelProvider([
            ModelResponse(text="Done!", finish_reason="stop"),
            ToolCall(name="edit_file", arguments={
                "path": "calculator.py",
                "old_string": "    return a - b",
                "new_string": "    return a + b",
            }),
            ModelResponse(text="Now the tests pass.", finish_reason="stop"),
        ])
        report = run_benchmark(provider)
        self.assertTrue(report.success)
        self.assertEqual(report.recovery_count, 1)
        outcomes = [v["ok"] for v in report.verification_results]
        self.assertEqual(outcomes, [False, True])


class TestFixture(unittest.TestCase):
    def test_defect_present_before_run(self):
        root = Path(tempfile.mkdtemp(prefix="fixture-"))
        workspace = Workspace(root)
        create_fixture(workspace)
        content = (root / "calculator.py").read_text(encoding="utf-8")
        self.assertIn("a - b", content)  # the defect
        tests = (root / "test_calculator.py").read_text(encoding="utf-8")
        self.assertIn("assertEqual(add(2, 3), 5)", tests)

    def test_goal_is_natural_language(self):
        # the model must find the code; the goal never names files
        self.assertNotIn("calculator.py", BENCHMARK_GOAL)


if __name__ == "__main__":
    unittest.main()
