"""S60 synthetic curriculum tests: determinism, dedupe, coverage,
mastery adaptation, S57 bridge. All hermetic."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent.curriculum import (
    CurriculumError,
    CurriculumTask,
    MasteryTracker,
    SyntheticCurriculum,
    _normalize,
)
from qacompanion.agent.evaluation import run_evaluation


class TestTaskSchema(unittest.TestCase):
    def test_validation(self):
        base = dict(task_id="C-0001", category="bug_fix", level=2,
                    difficulty={"reasoning": 1, "steps": 3,
                                "tools_required": 3},
                    goal="fix it", files={"m.py": "x = 1"},
                    verify_command="python -m unittest",
                    skills=["python"], known_failure_modes=[],
                    seed=1)
        CurriculumTask(**base)  # valid
        for key, bad_value in (("category", "quantum"), ("level", 9),
                               ("level", 0)):
            with self.assertRaises(CurriculumError):
                CurriculumTask(**{**base, key: bad_value})
        with self.assertRaises(CurriculumError):
            CurriculumTask(**{**base, "goal": ""})
        with self.assertRaises(CurriculumError):
            CurriculumTask(**{**base, "files": {}})

    def test_to_dict_round_trip_keys(self):
        base = dict(task_id="C-0001", category="bug_fix", level=2,
                    difficulty={"reasoning": 1}, goal="g",
                    files={"m.py": "x"}, verify_command="v",
                    skills=["python"], known_failure_modes=["f"], seed=3)
        task = CurriculumTask(**base)
        data = task.to_dict()
        for key in base:
            self.assertIn(key, data)

    def test_write_fixtures(self):
        task = CurriculumTask(
            task_id="C-0002", category="docs", level=1,
            difficulty={"reasoning": 1}, goal="add docstrings",
            files={"docs_mod.py": "def a():\n    pass\n"},
            verify_command="true", skills=["python"],
            known_failure_modes=[], seed=1)
        tmp = Path(tempfile.mkdtemp())
        try:
            task.write_fixtures(tmp)
            self.assertTrue((tmp / "docs_mod.py").exists())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestGenerator(unittest.TestCase):
    def test_deterministic_same_seed(self):
        a = SyntheticCurriculum(seed=11).generate(8)
        b = SyntheticCurriculum(seed=11).generate(8)
        self.assertEqual(
            [(t.category, t.level, t.goal) for t in a],
            [(t.category, t.level, t.goal) for t in b])

    def test_unique_ids(self):
        tasks = SyntheticCurriculum(seed=1).generate(10)
        ids = [t.task_id for t in tasks]
        self.assertEqual(len(ids), len(set(ids)))

    def test_dedupe_repeated_goals(self):
        # a tiny category set with low variation would produce repeated
        # goals; the generator must skip them
        curriculum = SyntheticCurriculum(seed=1,
                                         categories=("bug_fix",))
        tasks = curriculum.generate(4)
        goals = [_normalize(t.goal) for t in tasks]
        self.assertEqual(len(goals), len(set(goals)))

    def test_level_range_respected(self):
        tasks = SyntheticCurriculum(seed=5, level_range=(2, 3)).generate(8)
        for task in tasks:
            self.assertIn(task.level, (2, 3))

    def test_category_filter(self):
        tasks = SyntheticCurriculum(seed=2,
                                    categories=("bug_fix",)).generate(3)
        self.assertTrue(all(t.category == "bug_fix" for t in tasks))

    def test_coverage_counts(self):
        curriculum = SyntheticCurriculum(seed=3)
        curriculum.generate(12)
        coverage = curriculum.coverage()
        self.assertIn("python", coverage)
        self.assertGreater(coverage["python"], 0)

    def test_invalid_config(self):
        with self.assertRaises(CurriculumError):
            SyntheticCurriculum(categories=())
        with self.assertRaises(CurriculumError):
            SyntheticCurriculum(level_range=(5, 2))
        with self.assertRaises(CurriculumError):
            SyntheticCurriculum(categories=("quantum",))


class TestBugFixDefectInjected(unittest.TestCase):
    def test_defect_present_and_tests_fail(self):
        """Failure injection by construction: the bug_fix fixture's
        tests genuinely fail pre-fix (run once via subprocess)."""
        curriculum = SyntheticCurriculum(seed=9, categories=("bug_fix",))
        task = curriculum.generate(1)[0]
        tmp = Path(tempfile.mkdtemp())
        try:
            task.write_fixtures(tmp)
            proc = subprocess.run(
                [sys.executable, "-m", "unittest"],
                cwd=str(tmp), capture_output=True, text=True,
                timeout=60)
            self.assertNotEqual(proc.returncode, 0,
                                "defect fixture must fail pre-fix")
            self.assertTrue(task.known_failure_modes,
                            "declared failure modes required")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestMasteryTracker(unittest.TestCase):
    def test_level_up_on_streak(self):
        tracker = MasteryTracker(level_up_streak=3)
        for _ in range(3):
            tracker.record("python", True)
        self.assertEqual(tracker.working_level("python"), 2)

    def test_level_down_on_failures(self):
        tracker = MasteryTracker(level_down_failures=2)
        tracker.record("python", False)
        tracker.record("python", False)
        self.assertEqual(tracker.working_level("python"), 1)

    def test_mixed_streak_holds_level(self):
        tracker = MasteryTracker(level_up_streak=3, level_down_failures=2)
        for outcome in (True, False, True):
            tracker.record("python", outcome)
        self.assertEqual(tracker.working_level("python"), 1)

    def test_recommend_least_attempted(self):
        tracker = MasteryTracker()
        tracker.record("python", True)
        skill, level = tracker.recommend(("python", "testing"))
        self.assertEqual(skill, "testing")


class TestS57Bridge(unittest.TestCase):
    def test_as_eval_task_runs_through_harness(self):
        # pick a seeded bug_fix task whose defect is the known add-variant
        task = None
        for seed in range(30):
            candidate = SyntheticCurriculum(
                seed=seed, categories=("bug_fix",)).generate(1)[0]
            if candidate.known_failure_modes[0].startswith("add"):
                task = candidate
                break
        self.assertIsNotNone(task, "no add-variant found in seed range")
        eval_task = task.as_eval_task()
        self.assertEqual(eval_task.goal, task.goal)

        # scripted provider: fix the add defect, run tests, finish
        module_name = next(name for name in task.files
                           if not name.startswith("test_"))
        from qacompanion.agent import FakeModelProvider, ModelResponse, \
            ToolCall
        provider = FakeModelProvider([
            ToolCall(name="edit_file", arguments={
                "path": module_name,
                "old_string": "    return a - b",
                "new_string": "    return a + b"}),
            ToolCall(name="run_tests", arguments={
                "command": f'"{sys.executable}" -m unittest'}),
            ModelResponse(text="fixed", finish_reason="stop"),
        ])

        import tempfile
        tmp = Path(tempfile.mkdtemp())
        try:
            report = run_evaluation(
                models={"fake": lambda model=None: provider},
                tasks=[eval_task],
                run_id="curr-bridge")
            agg = report.aggregates()["fake"]
            self.assertEqual(agg["success_rate"], 1.0)
            self.assertEqual(agg["tasks"], 1)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
