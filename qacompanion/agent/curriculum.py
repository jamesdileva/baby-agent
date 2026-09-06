"""S60 synthetic curriculum: generated learning tasks, not random ones.

Tasks are DATA — deterministic templates × category × difficulty level
× seeded variation — with failure injection built into the fixtures:
bug_fix modules CONTAIN the declared defect, feature_add modules are
missing the function tests expect, build_repair modules don't import.
The curriculum states what the agent will hit (known_failure_modes)
and verifies completion the same way every other task does (unittest
via the S57 bridge).

Pins (fixtures-first discipline):
- deterministic: same seed -> byte-identical curriculum; unique task
  ids; repeated normalized goals are detected and skipped (roadmap
  repeated-task reduction);
- difficulty is a VECTOR (reasoning, steps, tools_required) that
  scales with level — subtler defects, more functions;
- MasteryTracker adapts: success streak -> level up, consecutive
  failures -> level down; recommend() picks the least-covered skill;
- tasks bridge to S57 via as_eval_task() — the curriculum never
  re-implements verification.
"""

import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .evaluation import EvalTask

CATEGORIES = ("bug_fix", "feature_add", "testing", "refactor",
              "build_repair", "dependency", "regression", "docs")
LEVELS = (1, 2, 3, 4, 5, 6, 7, 8)
SKILLS = ("python", "testing", "debugging", "refactoring", "dependencies",
          "documentation", "regression")

DEFAULT_LEVEL_RANGE = (1, 4)


class CurriculumError(ValueError):
    """Invalid curriculum configuration or task."""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _test_footer(module: str, cases: str) -> str:
    return textwrap.dedent(f"""\
        import unittest

        from {module} import {cases}

        """)  # caller appends test class + main


def _bug_fix_fixture(variant: int, level: int):
    """Module contains a deliberate defect; tests fail until fixed."""
    variants = [
        # (module_name, function, correct_body, defective_body, test_case)
        ("math_ops", "add",
         "    return a + b", "    return a - b",
         'self.assertEqual(add(2, 3), 5)'),
        ("string_ops", "join_words",
         '    return " ".join(words)', '    return "".join(words)',
         'self.assertEqual(join_words(["a", "b"]), "a b")'),
        ("list_ops", "last_item",
         "    return items[-1]", "    return items[0]",
         'self.assertEqual(last_item([1, 2, 3]), 3)'),
        ("math_ops", "clamp",
         "    return max(low, min(high, value))",
         "    return min(low, max(high, value))",
         'self.assertEqual(clamp(15, 0, 10), 10)'),
        ("string_ops", "count_vowels",
         "    return sum(1 for ch in text if ch.lower() in \"aeiou\")",
         "    return sum(1 for ch in text if ch.lower() not in \"aeiou\")",
         'self.assertEqual(count_vowels("hello"), 2)'),
    ]
    module, func, good, bad, test = variants[variant % len(variants)]
    # level scales subtlety: higher levels append a decoy correct
    # function so the fix requires reading, not pattern-matching
    decoy = ("\n\ndef helper_ok(x):\n    return x\n"
             if level >= 3 else "")
    module_code = (f"def {func}(a, b=1, items=None, text='', value=0, "
                   f"low=0, high=100):\n{bad}\n{decoy}")
    # rewrite with explicit signatures for clarity per variant
    signatures = {
        "add": "def add(a, b):\n{bad}",
        "join_words": "def join_words(words):\n{bad}",
        "last_item": "def last_item(items):\n{bad}",
        "clamp": "def clamp(value, low, high):\n{bad}",
        "count_vowels": "def count_vowels(text):\n{bad}",
    }
    module_code = signatures[func].format(bad=bad) + decoy
    test_code = (
        f"import unittest\n\nfrom {module} import {func}\n\n\n"
        f"class Test{func.capitalize()}(unittest.TestCase):\n"
        f"    def test_{func}(self):\n        {test}\n\n\n"
        f"if __name__ == \"__main__\":\n    unittest.main()\n")
    failure = f"{func} is implemented incorrectly (defect by design)"
    skills = ["python", "debugging"]
    goal = (f"The test suite in this project fails because {func} is "
            f"implemented incorrectly. Find the bug, fix it, and run "
            f"the tests to verify they pass.")
    return module_code, test_code, goal, failure, skills, module, func


def _feature_add_fixture(variant: int, level: int):
    variants = [
        ("stats_ops", "average",
         "def average(values):\n    "
         "return sum(values) / len(values) if values else 0",
         'self.assertEqual(average([2, 4, 6]), 4)'),
        ("text_ops", "capitalize_words",
         "def capitalize_words(text):\n    "
         "return \" \".join(w.capitalize() for w in text.split())",
         'self.assertEqual(capitalize_words("a b"), "A B")'),
        ("math_ops", "is_even",
         "def is_even(n):\n    return n % 2 == 0",
         'self.assertTrue(is_even(4))'),
    ]
    module, func, impl, test = variants[variant % len(variants)]
    module_code = (f"# {func} is not implemented yet — that is the "
                   f"task.\n\n\n")
    test_code = (
        f"import unittest\n\nfrom {module} import {func}\n\n\n"
        f"class Test{func.capitalize()}(unittest.TestCase):\n"
        f"    def test_{func}(self):\n        {test}\n\n\n"
        f"if __name__ == \"__main__\":\n    unittest.main()\n")
    goal = (f"The module {module} is missing the {func} function that "
            f"its tests expect. Implement it and run the tests to "
            f"verify they pass.")
    failure = f"{func} does not exist yet (feature by design)"
    return module_code, test_code, goal, failure, ["python", "testing"], \
        module, func


def _testing_fixture(variant: int, level: int):
    module, func = ("calc_ops", "multiply"), "multiply"
    module_code = "def multiply(a, b):\n    return a * b\n"
    test_code = ("# The multiply function is implemented and correct — "
                 "but has no tests.\n# Write a unittest test class that "
                 "verifies it.\n")
    goal = ("The module calc_ops has no tests. Write a unittest test "
            "file that verifies multiply works, and run it to confirm "
            "your tests pass.")
    return module_code, test_code, goal, None, ["python", "testing"], \
        "test_calc_ops", func


def _refactor_fixture(variant: int, level: int):
    module_code = ("def process(items):\n"
                   "    result = []\n"
                   "    for item in items:\n"
                   "        if item % 2 == 0:\n"
                   "            result.append(item * 2)\n"
                   "    return result\n")
    test_code = (
        "import unittest\n\nfrom process_mod import process\n\n\n"
        "class TestProcess(unittest.TestCase):\n"
        "    def test_process(self):\n"
        "        self.assertEqual(process([1, 2, 3, 4]), [2, 4, 6, 8])\n\n\n"
        "if __name__ == \"__main__\":\n    unittest.main()\n")
    goal = ("Refactor the processing code to use a list comprehension. "
            "The tests must still pass when you are done.")
    return module_code, test_code, goal, None, ["python", "refactoring"], \
        "process_mod", "process"


def _build_repair_fixture(variant: int, level: int):
    broken = ("def total(values):\n    return sum(values\n"
              "def double(x):\n    return x * 2\n")
    test_code = (
        "import unittest\n\nfrom broken_mod import total, double\n\n\n"
        "class TestBroken(unittest.TestCase):\n"
        "    def test_total(self):\n"
        "        self.assertEqual(total([1, 2]), 3)\n"
        "    def test_double(self):\n"
        "        self.assertEqual(double(2), 4)\n\n\n"
        "if __name__ == \"__main__\":\n    unittest.main()\n")
    goal = ("The module in this project has a syntax error and cannot "
            "even be imported. Repair it and run the tests to verify.")
    return broken, test_code, goal, "syntax error in module", \
        ["python", "debugging"], "broken_mod", "total"


def _dependency_fixture(variant: int, level: int):
    main_code = ("from helpers import format_money\n\n\ndef bill(amount):"
                 "\n    return format_money(amount)\n")
    test_code = (
        "import unittest\n\nfrom billing import bill\n\n\n"
        "class TestBill(unittest.TestCase):\n"
        "    def test_bill(self):\n"
        "        self.assertEqual(bill(5), \"$5.00\")\n\n\n"
        "if __name__ == \"__main__\":\n    unittest.main()\n")
    goal = ("The billing module imports a helpers module that doesn't "
            "exist. Create it so the import works and the tests pass.")
    failure = "helpers module does not exist (dependency by design)"
    return main_code, test_code, goal, failure, \
        ["python", "dependencies"], "billing", "bill"


def _regression_fixture(variant: int, level: int):
    module_code = ("def sort_words(words):\n    "
                   "return sorted(words, key=str.lower)\n")
    test_code = ("# Regression: sort_words used to be case-sensitive and "
                 "broke on\n# mixed-case input. It is fixed now — add a "
                 "unittest test file that\n# pins the correct behavior "
                 "so it cannot regress silently.\n")
    goal = ("sort_words was fixed after a case-sensitivity bug. Add a "
            "unittest test file that pins the correct behavior, and run "
            "it to confirm your tests pass.")
    return module_code, test_code, goal, None, \
        ["python", "regression", "testing"], "sort_mod", "sort_words"


def _docs_fixture(variant: int, level: int):
    module_code = ("def greet(name):\n    return f\"Hello, {name}!\"\n\n\n"
                   "def farewell(name):\n    return f\"Bye, {name}.\"\n")
    goal = ("Both functions in this module are undocumented. Add a "
            "docstring to each one describing its behavior.")
    return module_code, None, goal, None, ["python", "documentation"], \
        "docs_mod", "greet"


_BUILDERS = {
    "bug_fix": _bug_fix_fixture,
    "feature_add": _feature_add_fixture,
    "testing": _testing_fixture,
    "refactor": _refactor_fixture,
    "build_repair": _build_repair_fixture,
    "dependency": _dependency_fixture,
    "regression": _regression_fixture,
    "docs": _docs_fixture,
}


@dataclass
class CurriculumTask:
    """One generated learning task (DATA — feeds the S57 harness)."""

    task_id: str
    category: str
    level: int
    difficulty: Dict[str, int]
    goal: str
    files: Dict[str, str]
    verify_command: str
    skills: List[str]
    known_failure_modes: List[str]
    seed: int

    def __post_init__(self):
        if self.category not in CATEGORIES:
            raise CurriculumError(f"unknown category: {self.category!r}")
        if self.level not in LEVELS:
            raise CurriculumError(f"level must be 1..8: {self.level!r}")
        if not self.goal.strip():
            raise CurriculumError("goal required")
        if not self.files:
            raise CurriculumError("task requires fixture files")

    def write_fixtures(self, root: Path) -> None:
        for name, content in self.files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def as_eval_task(self) -> EvalTask:
        return EvalTask(name=f"curr-{self.task_id}", goal=self.goal,
                        files=dict(self.files),
                        verify_command=self.verify_command)

    def to_dict(self):
        data = {key: getattr(self, key) for key in (
            "task_id", "category", "level", "difficulty", "goal",
            "verify_command", "skills", "known_failure_modes", "seed")}
        data["files"] = dict(self.files)
        return data


class SyntheticCurriculum:
    """Deterministic task generator with coverage + dedupe."""

    def __init__(self, seed: int = 42,
                 categories: Tuple[str, ...] = CATEGORIES,
                 level_range: Tuple[int, int] = DEFAULT_LEVEL_RANGE):
        if not categories:
            raise CurriculumError("at least one category required")
        for cat in categories:
            if cat not in CATEGORIES:
                raise CurriculumError(f"unknown category: {cat!r}")
        lo, hi = level_range
        if lo < 1 or hi > 8 or lo > hi:
            raise CurriculumError(
                f"level_range must be within 1..8: {level_range!r}")
        self.seed = seed
        self.categories = tuple(categories)
        self.level_range = (lo, hi)
        self._rng = random.Random(seed)
        self._tasks: List[CurriculumTask] = []
        self._goals: set = set()
        self._counter = 0

    def generate(self, count: int, level: Optional[int] = None
                 ) -> List[CurriculumTask]:
        """Generate up to count tasks; repeated normalized goals are
        skipped (roadmap repeated-task reduction)."""
        if count < 1:
            raise CurriculumError("count must be >= 1")
        generated: List[CurriculumTask] = []
        attempts = 0
        while len(generated) < count and attempts < count * 20:
            attempts += 1
            variant = self._rng.randrange(1000)
            category = self.categories[
                (self._counter + variant) % len(self.categories)]
            lo, hi = self.level_range
            level = level if level is not None else self._rng.randint(lo, hi)
            self._counter += 1
            task = self._build(category, level, variant)
            goal_key = _normalize(task.goal)
            if goal_key in self._goals:
                continue  # repeated goal: skip (roadmap dedupe rule)
            self._goals.add(goal_key)
            self._tasks.append(task)
            generated.append(task)
        return generated

    def _build(self, category: str, level: int,
               variant: int) -> CurriculumTask:
        builder = _BUILDERS[category]
        module_code, test_code, goal, failure, skills, mod, func = \
            builder(variant, level)
        files = {f"{mod}.py": module_code}
        if test_code:
            files[f"test_{mod}.py"] = test_code
        import sys as _sys
        python = f'"{_sys.executable}"'
        verify = f"{python} -m unittest" if category != "docs" else \
            (f'{python} -c "import docs_mod as d; assert '
             f'd.greet.__doc__ and d.farewell.__doc__"')
        difficulty = {
            "reasoning": min(5, 1 + level // 2),
            "steps": min(10, 2 + level),
            "tools_required": 3,
        }
        task_id = f"C-{self._counter:04d}"
        known = [failure] if failure else []
        if category == "docs":
            known = ["missing docstrings are the task"]
        return CurriculumTask(
            task_id=task_id, category=category, level=level,
            difficulty=difficulty, goal=goal, files=files,
            verify_command=verify, skills=list(skills),
            known_failure_modes=known,
            seed=self.seed + self._counter)

    def coverage(self) -> Dict[str, int]:
        """The coverage matrix: skill -> task count (dataset-bias check)."""
        coverage: Dict[str, int] = {}
        for task in self._tasks:
            for skill in task.skills:
                coverage[skill] = coverage.get(skill, 0) + 1
        return coverage

    def tasks(self) -> List[CurriculumTask]:
        return list(self._tasks)


class MasteryTracker:
    """Per-skill outcome tracking with adaptive working level."""

    def __init__(self, level_up_streak: int = 3,
                 level_down_failures: int = 2,
                 min_level: int = 1, max_level: int = 8):
        if level_up_streak < 1 or level_down_failures < 1:
            raise CurriculumError("streak thresholds must be >= 1")
        self.level_up_streak = level_up_streak
        self.level_down_failures = level_down_failures
        self.min_level = min_level
        self.max_level = max_level
        self._levels: Dict[str, int] = {}
        self._streaks: Dict[str, List[bool]] = {}

    def record(self, skill: str, success: bool) -> None:
        streaks = self._streaks.setdefault(skill, [])
        streaks.append(bool(success))

    def working_level(self, skill: str) -> int:
        level = self._levels.get(skill, self.min_level)
        streaks = self._streaks.get(skill, [])
        recent = streaks[-(self.level_up_streak + self.level_down_failures):]
        if len(recent) >= self.level_up_streak and all(recent[
                -self.level_up_streak:]):
            level = min(level + 1, self.max_level)
        elif (len(recent) >= self.level_down_failures
                and not any(recent[-self.level_down_failures:])):
            level = max(level - 1, self.min_level)
        self._levels[skill] = level
        return level

    def recommend(self, skills: Tuple[str, ...] = SKILLS
                  ) -> Tuple[str, int]:
        """Least-attempted skill, at its adaptive working level."""
        least = min(skills, key=lambda s: len(self._streaks.get(s, [])))
        return least, self.working_level(least)

