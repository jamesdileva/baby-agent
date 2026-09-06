"""S59 apprenticeship lab tests: teacher demonstration, student retry,
verification + curation gates. All hermetic via fake providers."""

import shutil
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import FakeModelProvider, ModelResponse, ToolCall
from qacompanion.agent.apprenticeship import (
    ApprenticeshipLab,
    Lesson,
    ScriptedTeacherProvider,
)
from qacompanion.agent.evaluation import default_tasks
from qacompanion.agent.experience import ExperienceStore

LESSONS = {
    "defect-fix-calculator": ("calculator.py",
                              "    return a - b", "    return a + b"),
    "defect-fix-strings": ("string_utils.py",
                           "    return text\n\n\ndef shout",
                           "    return text[::-1]\n\n\ndef shout"),
    "defect-fix-json": ("config_parser.py",
                        "    return data.get(key)",
                        '    return data.get("settings", {}).get(key)'),
}


def _lesson_for(task_name):
    path, old, new = LESSONS[task_name]
    return Lesson(
        explanation=f"The defect is in {path}: replace the broken "
                    f"expression with the correct one.",
        actions=[{"tool": "edit_file",
                  "arguments": {"path": path, "old_string": old,
                                "new_string": new}}],
    )


class LabBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = ExperienceStore(self.tmp / "experience.jsonl")
        self.lab = ApprenticeshipLab(store=self.store)
        self.tasks = {t.name: t for t in default_tasks()}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class AttemptFactory:
    """Provider factory where attempt N is scripted: attempt 1 fails,
    later attempts apply the lesson (or claim fine if learn=False)."""

    def __init__(self, task_name, learn=True):
        path, old, new = LESSONS[task_name]
        self.attempt = 0
        self._edit = ToolCall(name="edit_file", arguments={
            "path": path, "old_string": old, "new_string": new})
        self.learn = learn

    def __call__(self, model=None):
        attempt = self.attempt
        self.attempt += 1
        if attempt == 0 or not self.learn:
            return FakeModelProvider([
                ModelResponse(text="looks fine to me",
                              finish_reason="stop")])
        return FakeModelProvider([
            self._edit,
            ModelResponse(text="applied the lesson", finish_reason="stop"),
        ])


class TestApprenticeshipFlow(LabBase):
    def test_full_cycle_accepted(self):
        task = self.tasks["defect-fix-calculator"]
        teacher = ScriptedTeacherProvider(_lesson_for(task.name))
        factory = AttemptFactory(task.name, learn=True)

        record = self.lab.run_session(task, factory, teacher)

        self.assertEqual(record.status, "accepted")
        self.assertTrue(record.verified)
        self.assertIsNotNone(record.student_first_report)
        self.assertIsNotNone(record.student_retry_report)
        self.assertTrue(record.lessons_extracted)
        experiences = self.store.load()
        self.assertTrue(any(e.tags and "apprenticeship" in e.tags
                            for e in experiences))

    def test_teacher_without_actions_rejected(self):
        task = self.tasks["defect-fix-json"]
        teacher = ScriptedTeacherProvider(Lesson(explanation="no idea"))
        factory = AttemptFactory(task.name, learn=True)
        record = self.lab.run_session(task, factory, teacher)
        self.assertEqual(record.status, "rejected")
        self.assertIn("teacher_failed", record.reject_reason)

    def test_student_never_learns_rejected(self):
        task = self.tasks["defect-fix-strings"]
        teacher = ScriptedTeacherProvider(_lesson_for(task.name))
        factory = AttemptFactory(task.name, learn=False)
        record = self.lab.run_session(task, factory, teacher)
        self.assertEqual(record.status, "rejected")
        self.assertIn("verification_failed", record.reject_reason)
        self.assertFalse(record.verified)
        self.assertEqual(self.store.load(), [])  # nothing stored

    def test_teacher_lesson_is_structured(self):
        lesson = _lesson_for("defect-fix-json")
        self.assertEqual(lesson.actions[0]["tool"], "edit_file")
        self.assertIn("settings", lesson.actions[0]["arguments"]["new_string"])
        round_trip = Lesson.from_dict(lesson.to_dict())
        self.assertEqual(round_trip.explanation, lesson.explanation)


class TestLabReport(LabBase):
    def test_counts_by_teacher(self):
        from qacompanion.agent.apprenticeship import LabReport

        task = self.tasks["defect-fix-json"]
        report = LabReport()
        teacher = ScriptedTeacherProvider(_lesson_for(task.name))
        good = self.lab.run_session(
            task, AttemptFactory(task.name, learn=True),
            teacher)
        report.add(good)
        bad_teacher = ScriptedTeacherProvider(Lesson(explanation="no"))
        bad = self.lab.run_session(
            task, AttemptFactory(task.name, learn=True),
            bad_teacher)
        report.add(bad)

        self.assertEqual(report.sessions, 2)
        self.assertEqual(report.accepted, 1)
        self.assertEqual(report.rejected, 1)
        self.assertEqual(report.by_teacher["scripted"]["accepted"], 1)
        self.assertEqual(report.by_teacher["scripted"]["sessions"], 2)


if __name__ == "__main__":
    unittest.main()
