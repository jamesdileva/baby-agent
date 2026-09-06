"""S57 evaluation harness tests: fixtures, runner, aggregation,
persistence, compare. All hermetic via FakeModelProvider."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qacompanion.agent import FakeModelProvider, ModelResponse, ToolCall
from qacompanion.agent.benchmark import BENCHMARK_GOAL
from qacompanion.agent.evaluation import (
    EvalError,
    EvalReport,
    compare,
    default_tasks,
    run_evaluation,
)
from qacompanion.agent.experience import ExperienceStore

PY = f'"{sys.executable}"'


def _fix_script(edit_old, edit_new, test_command):
    """inspect -> run tests (fail) -> fix -> run tests (pass) -> final."""
    return [
        ToolCall(name="edit_file", arguments={
            "path": None,  # patched per task below
            "old_string": edit_old,
            "new_string": edit_new}),
        ToolCall(name="run_tests", arguments={"command": test_command}),
        ModelResponse(text="fixed", finish_reason="stop"),
    ]


FIXES = (
    ("calculator.py", "    return a - b", "    return a + b"),
    ("string_utils.py", "    return text\n\n\ndef shout",
     "    return text[::-1]\n\n\ndef shout"),
    ("config_parser.py", "    return data.get(key)",
     '    return data.get("settings", {}).get(key)'),
)


class _ScriptedFactory:
    """Provider factory: turn 1 attempts ALL three known fixes (the two
    inapplicable ones fail harmlessly on files that don't exist); after
    any tool result the model answers final. Succeed=False leaves the
    defects in place (honest-failure control)."""

    def __init__(self, succeed=True):
        self.succeed = succeed

    def __call__(self, model=None):
        from qacompanion.agent import ModelResponse, ToolCall

        succeed = self.succeed  # closure capture (nested class scope)

        class _AutoFix(FakeModelProvider):
            def __init__(self):
                super().__init__([])  # stateless: synthesizes per turn

            def generate(self, request):
                has_tool_result = any(m.role == "tool"
                                      for m in request.messages)
                if has_tool_result:
                    return ModelResponse(text="fixed",
                                         finish_reason="stop")
                calls = [ToolCall(name="edit_file", arguments={
                    "path": path,
                    "old_string": old,
                    "new_string": new if succeed else old,
                }) for path, old, new in FIXES]
                return ModelResponse(text="", tool_calls=calls,
                                     finish_reason="tool_calls")

        return _AutoFix()


class EvalBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = ExperienceStore(self.tmp / "e.jsonl")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestFixtures(EvalBase):
    def test_three_deterministic_tasks(self):
        tasks = default_tasks()
        self.assertEqual([t.name for t in tasks],
                         ["defect-fix-calculator", "defect-fix-strings",
                          "defect-fix-json"])
        for task in tasks:
            self.assertNotIn(".py", task.goal)  # goals name no files
            root = self.tmp / task.name
            task.write_fixture(root)
            for name in task.files:
                self.assertTrue((root / name).exists())

    def test_calculator_defect_present(self):
        task = default_tasks()[0]
        root = self.tmp / "calc"
        task.write_fixture(root)
        self.assertIn("a - b", (root / "calculator.py").read_text(
            encoding="utf-8"))


class TestRunner(EvalBase):
    def test_all_pass_run(self):
        report = run_evaluation(
            models={"test-model": _ScriptedFactory(succeed=True)},
            store=self.store, run_id="run-all-pass")
        agg = report.aggregates()["test-model"]
        self.assertEqual(agg["tasks"], 3)
        self.assertEqual(agg["success_rate"], 1.0)
        self.assertEqual(agg["total_interventions"], 0)

    def test_failing_model_reported_honestly(self):
        # a provider that never edits anything: all tasks fail
        def never_fix(model=None):
            return FakeModelProvider([
                ModelResponse(text="looks fine to me",
                              finish_reason="stop")])
        report = run_evaluation(models={"lazy": never_fix},
                                store=self.store, run_id="run-lazy")
        agg = report.aggregates()["lazy"]
        self.assertEqual(agg["success_rate"], 0.0)
        self.assertEqual(agg["successes"], 0)

    def test_experience_recorded_per_run(self):
        store = ExperienceStore(self.tmp / "exp.jsonl")
        run_evaluation(models={"m": _ScriptedFactory(succeed=True)},
                       tasks=[default_tasks()[0]],
                       store=store, run_id="exp-run")
        self.assertEqual(len(store.load()), 1)


class TestPersistence(EvalBase):
    def test_save_load_round_trip(self):
        report = run_evaluation(
            models={"m": _ScriptedFactory(succeed=True)},
            tasks=[default_tasks()[0]], run_id="persist-me")
        path = self.tmp / "run.json"
        report.save(path)
        loaded = EvalReport.load(path)
        self.assertEqual(loaded.run_id, "persist-me")
        self.assertEqual(loaded.results, report.results)

    def test_corrupt_run_structured_error(self):
        bad = self.tmp / "bad.json"
        bad.write_text("{nope", encoding="utf-8")
        with self.assertRaises(EvalError):
            EvalReport.load(bad)

    def test_save_goes_to_eval_dir(self):
        import os
        with patch.dict(os.environ, {"QA_EVAL_DIR": str(self.tmp / "runs")}):
            report = run_evaluation(
                models={"m": _ScriptedFactory(succeed=True)},
                tasks=[default_tasks()[0]], run_id="dir-check")
            path = report.save()
            self.assertTrue(path.exists())
            self.assertIn("runs", str(path))


class TestCompare(EvalBase):
    def _report(self, run_id, calc_success, strings_success):
        report = EvalReport(run_id=run_id, started_at="2026-09-05T00:00:00Z",
                            models=["m", "other"])
        report.results = {
            "m": {
                "defect-fix-calculator": {
                    "success": calc_success, "iterations": 5,
                    "duration_seconds": 100.0},
                "defect-fix-strings": {
                    "success": strings_success, "iterations": 3,
                    "duration_seconds": 50.0},
            },
            "other": {
                "defect-fix-calculator": {
                    "success": True, "iterations": 2,
                    "duration_seconds": 40.0},
            },
        }
        return report

    def test_regression_flagged(self):
        result = compare(self._report("old", True, True),
                         self._report("new", False, True))
        self.assertEqual(len(result["regressions"]), 1)
        self.assertEqual(result["regressions"][0]["task"],
                         "defect-fix-calculator")
        self.assertEqual(result["deltas"]["m"]["success_rate"], -0.5)

    def test_improvement_flagged(self):
        result = compare(self._report("old", False, False),
                         self._report("new", True, False))
        self.assertEqual(len(result["improvements"]), 1)
        self.assertEqual(result["improvements"][0]["task"],
                         "defect-fix-calculator")
        self.assertEqual(result["regressions"], [])

    def test_new_task_in_new_run_ignored(self):
        # a model gains a task the old run didn't have: not a regression
        result = compare(self._report("old", True, True),
                         self._report("new", True, True))
        self.assertEqual(result["regressions"], [])
        self.assertEqual(result["improvements"], [])


if __name__ == "__main__":
    unittest.main()
