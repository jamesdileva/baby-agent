"""S41 verification engine tests: plan model, runner, tool, loop adapter.

Hermetic: all step commands use sys.executable against temp workspaces.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import (
    AgentConfig,
    AgentLoop,
    AgentState,
    FakeModelProvider,
    ModelResponse,
    ToolCall,
    ToolRegistry,
    Workspace,
)
from qacompanion.agent.fs_tools import FilesystemToolkit, agent_registry
from qacompanion.agent.verification import (
    VerificationPlan,
    VerificationStep,
    VerificationToolkit,
    plan_verifier,
)

EXE = f'"{sys.executable}"'


def _plan(steps, name="verify", **kwargs):
    return VerificationPlan(name=name, steps=[
        VerificationStep(name=n, **spec) for n, spec in steps
    ], **kwargs)


def _step(name, command, **kwargs):
    spec = {"command": command, "category": "RUNTIME", **kwargs}
    return (name, spec)


class TestPlanModel(unittest.TestCase):
    def test_from_dict_round_trip(self):
        data = {
            "name": "build-and-test",
            "steps": [
                {"name": "build", "category": "BUILD", "command": "make build"},
                {"name": "test", "category": "TEST", "command": "make test",
                 "must_contain": "OK", "optional": False},
            ],
            "stop_on_first_failure": False,
        }
        plan = VerificationPlan.from_dict(data)
        self.assertEqual(plan.name, "build-and-test")
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].category, "BUILD")
        self.assertFalse(plan.stop_on_first_failure)
        self.assertEqual(plan.to_dict()["steps"][1]["must_contain"], "OK")

    def test_validation_rejections(self):
        with self.assertRaises(ValueError):
            VerificationPlan.from_dict(["not", "an", "object"])
        with self.assertRaises(ValueError):
            VerificationPlan.from_dict({"name": "x", "steps": []})
        with self.assertRaises(ValueError):
            VerificationStep(name="s", category="VIBES", command="x")
        with self.assertRaises(ValueError):
            VerificationStep(name="s", category="BUILD", command="  ")
        with self.assertRaises(ValueError):
            VerificationStep(name=" ", category="BUILD", command="x")
        with self.assertRaises(ValueError):
            VerificationStep(name="s", category="BUILD", command="x",
                             expect_exit=True)


class TestPlanRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_all_pass(self):
        plan = _plan([
            _step("write", f'{EXE} -c "from pathlib import Path; Path(\'a.txt\').write_text(\'hi\')"'),
            _step("check", f'{EXE} -c "from pathlib import Path; assert Path(\'a.txt\').exists()"',
                  category="TEST", must_contain=""),
        ])
        report = plan.run(self.ws)
        self.assertTrue(report.ok)
        self.assertTrue(all(step.ok for step in report.steps))
        self.assertGreater(report.steps[0].duration_ms, 0)

    def test_failure_skips_rest(self):
        plan = _plan([
            _step("failing", f'{EXE} -c "import sys; sys.exit(3)"',
                  category="BUILD"),
            _step("never", f'{EXE} -c "print(1)"', category="TEST"),
        ])
        report = plan.run(self.ws)
        self.assertFalse(report.ok)
        self.assertFalse(report.steps[0].ok)
        self.assertEqual(report.steps[0].exit_code, 3)
        self.assertIsNone(report.steps[1].ok)  # skipped

    def test_continue_when_stop_on_first_failure_false(self):
        plan = _plan([
            _step("one", f'{EXE} -c "import sys; sys.exit(1)"'),
            _step("two", f'{EXE} -c "print(2)"'),
        ], stop_on_first_failure=False)
        report = plan.run(self.ws)
        self.assertFalse(report.ok)
        self.assertFalse(report.steps[0].ok)
        self.assertTrue(report.steps[1].ok)

    def test_must_contain_satisfied_and_violated(self):
        plan = _plan([
            _step("ok", f'{EXE} -c "print(\'all good\')"', must_contain="all good"),
            _step("bad", f'{EXE} -c "print(\'wrong text\')"', must_contain="wanted"),
        ])
        report = plan.run(self.ws)
        self.assertTrue(report.steps[0].ok)
        self.assertFalse(report.steps[1].ok)

    def test_must_not_contain_violation(self):
        plan = _plan([
            _step("quiet", f'{EXE} -c "print(\'clean output\')"',
                  must_not_contain="ERROR"),
            _step("loud", f'{EXE} -c "print(\'ERROR spam\')"',
                  must_not_contain="ERROR"),
        ])
        report = plan.run(self.ws)
        self.assertTrue(report.steps[0].ok)
        self.assertFalse(report.steps[1].ok)

    def test_optional_failure_does_not_fail_plan(self):
        plan = _plan([
            _step("critical", f'{EXE} -c "print(1)"'),
            _step("nice-to-have", f'{EXE} -c "import sys; sys.exit(1)"',
                  optional=True),
        ])
        report = plan.run(self.ws)
        self.assertTrue(report.ok)
        self.assertFalse(report.steps[1].ok)

    def test_expect_exit_nonzero(self):
        # a step that EXPECTS failure (e.g. asserting a bug reproduces)
        plan = _plan([
            _step("expects-crash", f'{EXE} -c "import sys; sys.exit(2)"',
                  expect_exit=2),
        ])
        self.assertTrue(plan.run(self.ws).ok)

    def test_report_serializable(self):
        plan = _plan([_step("s", f'{EXE} -c "print(1)"')])
        line = json.dumps(plan.run(self.ws).to_dict())
        self.assertIn('"ok": true', line)


class TestRunVerificationTool(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.reg = ToolRegistry()
        for tool in VerificationToolkit(self.ws).tools():
            self.reg.register(tool)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_registration_metadata(self):
        described = self.reg.describe()[0]
        self.assertEqual(described["name"], "run_verification")
        self.assertEqual(described["side_effect_level"], "EXECUTION")
        self.assertTrue(described["requires_workspace"])

    def test_plan_execution_through_registry(self):
        (self.tmp / "data.txt").write_text("payload-42", encoding="utf-8")
        plan = {
            "name": "check-payload",
            "steps": [
                {"name": "payload-present", "category": "TEST",
                 "command": f'{EXE} -c "from pathlib import Path; '
                            f'assert \'payload-42\' in Path(\'data.txt\').read_text()"',
                 "must_contain": ""},
            ],
        }
        result = self.reg.execute(ToolCall(name="run_verification",
                                           arguments={"plan": plan}),
                                  workspace=self.ws)
        self.assertTrue(result.ok, result.error)
        report = json.loads(result.output)
        self.assertTrue(report["ok"])
        self.assertEqual(report["steps"][0]["name"], "payload-present")

    def test_invalid_plan_structured_error(self):
        result = self.reg.execute(
            ToolCall(name="run_verification", arguments={"plan": {"steps": []}}),
            workspace=self.ws)
        self.assertFalse(result.ok)
        self.assertIn("invalid verification plan", result.error)

    def test_step_failure_in_report_not_exception(self):
        plan = {"name": "p", "steps": [
            {"name": "fails", "category": "BUILD",
             "command": f'{EXE} -c "import sys; sys.exit(1)"'}]}
        result = self.reg.execute(ToolCall(name="run_verification",
                                           arguments={"plan": plan}),
                                  workspace=self.ws)
        self.assertTrue(result.ok)  # the tool ran; the PLAN failed
        report = json.loads(result.output)
        self.assertFalse(report["ok"])


class TestLoopIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.reg = ToolRegistry()
        for tool in FilesystemToolkit(self.ws).tools():
            self.reg.register(tool)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _goal_verifier(self):
        plan = _plan([
            _step("file-exists", f'{EXE} -c "from pathlib import Path; '
                                 f'assert Path(\'hello.txt\').exists()"',
                  category="HEALTHCHECK"),
        ])
        return plan_verifier(plan, self.ws)

    def test_passing_plan_completes(self):
        (self.tmp / "hello.txt").write_text("x", encoding="utf-8")
        provider = FakeModelProvider([
            ModelResponse(text="the file is in place", finish_reason="stop"),
        ])
        loop = AgentLoop(provider, self.reg, self.ws,
                         verifier=self._goal_verifier())
        session = loop.run("make hello.txt")
        self.assertEqual(session.state, AgentState.COMPLETED)
        self.assertTrue(session.verification_results[0]["ok"])

    def test_failing_plan_exhausts(self):
        provider = FakeModelProvider([
            ModelResponse(text="I claim success", finish_reason="stop"),
        ])
        loop = AgentLoop(provider, self.reg, self.ws,
                         config=AgentConfig(max_iterations=1),
                         verifier=self._goal_verifier())
        session = loop.run("make hello.txt")
        self.assertEqual(session.state, AgentState.FAILED)
        self.assertIn("verification failed", session.termination_reason)

    def test_recovery_then_pass(self):
        provider = FakeModelProvider([
            ModelResponse(text="I claim success", finish_reason="stop"),
            ToolCall(name="write_file", arguments={"path": "hello.txt",
                                                   "content": "x"}),
            ModelResponse(text="now it exists", finish_reason="stop"),
        ])
        loop = AgentLoop(provider, self.reg, self.ws,
                         verifier=self._goal_verifier())
        session = loop.run("make hello.txt")
        self.assertEqual(session.state, AgentState.COMPLETED)
        self.assertEqual([r["ok"] for r in session.verification_results],
                         [False, True])


class TestAgentRegistryGrowth(unittest.TestCase):
    def test_registry_includes_verification_tool(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            reg = agent_registry(Workspace(tmp))
            self.assertIn("run_verification", reg.names())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
