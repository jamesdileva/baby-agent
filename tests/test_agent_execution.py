"""S35 terminal & execution tests: structured commands inside the boundary.

Hermetic: every command uses sys.executable (no npm/cargo/network); complex
scenarios (tree kill, large output, child spawn) run script files written
into the temp workspace instead of fragile shell quoting.
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from qacompanion.agent import ToolCall, ToolRegistry, Workspace
from qacompanion.agent.execution import (
    MAX_OUTPUT_BYTES,
    CommandResult,
    ExecutionToolkit,
    detect_command,
    execute_command,
)
from qacompanion.agent.fs_tools import agent_registry

EXE = f'"{sys.executable}"'


class ExecTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.toolkit = ExecutionToolkit(self.ws)
        self.reg = ToolRegistry()
        for tool in self.toolkit.tools():
            self.reg.register(tool)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, name, **arguments):
        return self.reg.execute(ToolCall(name=name, arguments=arguments),
                                workspace=self.ws)

    def result(self, name, **arguments):
        out = self.call(name, **arguments)
        self.assertTrue(out.ok, f"{name} failed: {out.error}")
        return CommandResult.from_dict(json.loads(out.output))


class TestRunCommandCore(ExecTestBase):
    def test_success(self):
        r = self.result("run_command", command=f'{EXE} -c "print(\'hello\')"')
        self.assertEqual(r.exit_code, 0)
        self.assertEqual(r.stdout, "hello\n")
        self.assertEqual(r.stderr, "")
        self.assertFalse(r.timed_out)
        self.assertFalse(r.cancelled)
        self.assertIsInstance(r.pid, int)
        self.assertTrue(r.started_at.endswith("Z"))
        self.assertTrue(r.finished_at.endswith("Z"))
        self.assertGreaterEqual(r.duration_ms, 0)

    def test_nonzero_exit_keeps_output(self):
        r = self.result("run_command",
                        command=f'{EXE} -c "print(\'out line\'); '
                                f"import sys; print('err line', file=sys.stderr); "
                                f'sys.exit(3)"')
        self.assertEqual(r.exit_code, 3)
        self.assertIn("out line", r.stdout)
        self.assertIn("err line", r.stderr)
        self.assertFalse(r.timed_out)

    def test_stderr_only_failure(self):
        r = self.result("run_command",
                        command=f'{EXE} -c "import sys; '
                                f"print('boom', file=sys.stderr); sys.exit(1)\"")
        self.assertEqual(r.exit_code, 1)
        self.assertIn("boom", r.stderr)

    def test_large_output_truncated(self):
        script = self.tmp / "big.py"
        script.write_text("print('x' * 200000)\n", encoding="utf-8")
        r = self.result("run_command", command=f"{EXE} big.py")
        self.assertEqual(r.exit_code, 0)
        self.assertTrue(r.stdout_truncated)
        self.assertLessEqual(len(r.stdout.encode("utf-8")), MAX_OUTPUT_BYTES)

    def test_timeout_kills_command(self):
        r = self.result("run_command",
                        command=f'{EXE} -c "import time; time.sleep(5)"',
                        timeout_seconds=0.5)
        self.assertTrue(r.timed_out)
        self.assertLess(r.duration_ms, 4000)

    def test_timeout_kills_whole_tree(self):
        # parent spawns a sleeping child holding the stdout pipe; a
        # single-process kill would block ~5s on the pipe
        script = self.tmp / "spawn_sleep.py"
        script.write_text(
            "import subprocess, sys\n"
            "subprocess.run([sys.executable, '-c', 'import time; time.sleep(5)'])\n"
            "print('parent done')\n",
            encoding="utf-8",
        )
        r = self.result("run_command", command=f"{EXE} spawn_sleep.py",
                        timeout_seconds=0.5)
        self.assertTrue(r.timed_out)
        self.assertLess(r.duration_ms, 4000)

    def test_child_spawn_normal_completion(self):
        script = self.tmp / "spawn_ok.py"
        script.write_text(
            "import subprocess, sys\n"
            "subprocess.run([sys.executable, '-c', \"print('child says hi')\"])\n"
            "print('parent says hi')\n",
            encoding="utf-8",
        )
        r = self.result("run_command", command=f"{EXE} spawn_ok.py")
        self.assertEqual(r.exit_code, 0)
        self.assertIn("child says hi", r.stdout)
        self.assertIn("parent says hi", r.stdout)

    def test_cwd_recorded_and_observed(self):
        (self.tmp / "sub").mkdir()
        r = self.result("run_command",
                        command=f'{EXE} -c "import os; print(os.path.basename(os.getcwd()))"',
                        cwd="sub")
        self.assertEqual(r.cwd, "sub")
        self.assertIn("sub", r.stdout)

    def test_cwd_escape_operational_error(self):
        out = self.call("run_command", command=f'{EXE} -c "print(1)"', cwd="../")
        self.assertFalse(out.ok)
        self.assertIn("rejected by policy", out.error)

    def test_missing_cwd_operational_error(self):
        out = self.call("run_command", command=f'{EXE} -c "print(1)"', cwd="ghost")
        self.assertFalse(out.ok)
        self.assertIn("not a directory", out.error)

    def test_set_env_merged(self):
        r = self.result("run_command",
                        command=f'{EXE} -c "import os; print(os.environ.get(\'BABY_TEST_VAR\'))"',
                        set_env={"BABY_TEST_VAR": "42"})
        self.assertIn("42", r.stdout)

    def test_empty_command_rejected(self):
        out = self.call("run_command", command="   ")
        self.assertFalse(out.ok)
        self.assertIn("non-empty", out.error)

    def test_cancellation_before_dispatch(self):
        event = threading.Event()
        event.set()
        out = self.reg.execute(
            ToolCall(name="run_command",
                     arguments={"command": f'{EXE} -c "print(1)"'}),
            workspace=self.ws, cancel_event=event,
        )
        # cancelled at the S32 gate, before the handler: structured denial
        # on the ToolResult itself, no JSON payload
        self.assertFalse(out.ok)
        self.assertTrue(out.cancelled)
        self.assertEqual(out.output, "")

    def test_command_result_round_trip(self):
        r = CommandResult(command="x", cwd=".", exit_code=2, stdout="o", stderr="e",
                          duration_ms=5, timed_out=False, cancelled=False,
                          started_at="2026-09-04T00:00:00Z",
                          finished_at="2026-09-04T00:00:01Z")
        restored = CommandResult.from_dict(json.loads(json.dumps(r.to_dict())))
        self.assertEqual(restored, r)

    def test_command_result_malformed(self):
        with self.assertRaises(ValueError):
            CommandResult.from_dict(["not", "an", "object"])


class TestDetectionAndWrappers(ExecTestBase):
    def test_detection_table(self):
        (self.tmp / "requirements.txt").write_text("", encoding="utf-8")
        self.assertEqual(detect_command("run_tests", self.ws), "python -m unittest")
        self.assertIsNone(detect_command("run_lint", self.ws))

    def test_no_detection_is_structured_error(self):
        out = self.call("run_lint")  # empty workspace: nothing detected
        self.assertFalse(out.ok)
        self.assertIn("pass command explicitly", out.error)

    def test_explicit_command_on_wrapper(self):
        r = self.result("run_tests", command=f'{EXE} -c "print(\'suite ran\')"')
        self.assertEqual(r.exit_code, 0)
        self.assertIn("suite ran", r.stdout)

    def test_python_tests_detected_in_python_project(self):
        (self.tmp / "pyproject.toml").write_text("", encoding="utf-8")
        self.assertEqual(detect_command("run_tests", self.ws), "python -m unittest")


class TestRegistrationAndPolicy(ExecTestBase):
    def test_five_tools_registered(self):
        self.assertEqual(
            self.reg.names(),
            ["run_build", "run_command", "run_lint", "run_tests", "run_typecheck"],
        )
        described = {d["name"]: d for d in self.reg.describe()}
        self.assertTrue(all(d["category"] == "execution" for d in described.values()))
        self.assertTrue(all(d["side_effect_level"] == "EXECUTION"
                            for d in described.values()))
        self.assertTrue(all(d["requires_workspace"] for d in described.values()))
        self.assertTrue(all(d["cancellable"] for d in described.values()))

    def test_agent_registry_grew_to_fifteen(self):
        reg = agent_registry(self.ws)
        self.assertEqual(len(reg.names()), 15)
        self.assertIn("run_command", reg.names())
        self.assertIn("write_file", reg.names())

    def test_permission_policy_can_deny_command_prefixes(self):
        class NoDelete:
            def check(self, tool_name, arguments):
                cmd = str(arguments.get("command", "")).lower()
                if cmd.startswith("del") or cmd.startswith("rm"):
                    return "DENY"
                return "ALLOW"

        out = self.reg.execute(
            ToolCall(name="run_command", arguments={"command": "del everything"}),
            workspace=self.ws, policy=NoDelete(),
        )
        self.assertFalse(out.ok)
        self.assertIn("permission denied", out.error)


if __name__ == "__main__":
    unittest.main()
