"""S57 agent evaluation harness: improvement becomes measurable.

Runs the S48 defect-fix benchmark across a SUITE of deterministic
tasks and a set of models, aggregates per-model metrics, persists run
records as JSON, and compares two runs — flagging regressions (any
model x task whose success flipped True->False) as loudly as
improvements.

Pins (fixtures-first discipline):
- three deterministic fixtures, each with one intentional defect and
  its own S41 verification plan; hermetic (FakeModelProvider covers
  the suite);
- run records persist atomically under QA_EVAL_DIR (default eval-runs/,
  gitignored runtime artifacts);
- compare() is symmetric and honest: regressions AND improvements are
  both reported, never averaged away.
"""

import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .benchmark import run_benchmark
from .events import EventStream
from .experience import ExperienceStore


class EvalError(Exception):
    """Structured evaluation failure (bad config, corrupt run file)."""


def _utc_stamp() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def eval_dir() -> Path:
    return Path(os.environ.get("QA_EVAL_DIR", "eval-runs"))


# --- fixtures ---------------------------------------------------------------

STRING_DEFECT = '''def reverse(text):
    return text


def shout(text):
    return text.upper() + "!"
'''

STRING_TESTS = '''import unittest

from string_utils import reverse, shout


class TestStringUtils(unittest.TestCase):
    def test_reverse(self):
        self.assertEqual(reverse("abc"), "cba")

    def test_shout(self):
        self.assertEqual(shout("hey"), "HEY!")


if __name__ == "__main__":
    unittest.main()
'''

JSON_DEFECT = '''import json


def parse_config(raw):
    data = json.loads(raw)
    return data.get("name", "")


def deep_lookup(data, key):
    return data.get(key)
'''

JSON_TESTS = '''import unittest

from config_parser import parse_config, deep_lookup


class TestConfigParser(unittest.TestCase):
    def test_parse_name(self):
        self.assertEqual(parse_config('{"name": "svc"}'), "svc")

    def test_deep_lookup(self):
        self.assertEqual(deep_lookup({"settings": {"x": 1}}, "x"), 1)


if __name__ == "__main__":
    unittest.main()
'''

# deep_lookup must reach the nested "settings" key — the defect
JSON_DEFECT_FIXED_HINT = {"settings": {"x": 1}}


@dataclass
class EvalTask:
    """One deterministic defect-fix task."""

    name: str
    goal: str
    files: Dict[str, str]
    verify_command: str

    def write_fixture(self, root: Path) -> None:
        for name, content in self.files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")


def default_tasks() -> List[EvalTask]:
    import sys
    python = f'"{sys.executable}"'
    return [
        EvalTask(
            name="defect-fix-calculator",
            goal="The tests in this project are failing. Find the bug, "
                 "fix it, and run the tests to verify they pass.",
            files={
                "calculator.py": "def add(a, b):\n    return a - b\n\n\n"
                                 "def multiply(a, b):\n    return a * b\n",
                "test_calculator.py":
                    "import unittest\n\nfrom calculator import add, "
                    "multiply\n\n\nclass TestCalculator(unittest.TestCase):"
                    "\n    def test_add(self):\n        "
                    "self.assertEqual(add(2, 3), 5)\n\n    def "
                    "test_multiply(self):\n        "
                    "self.assertEqual(multiply(2, 3), 6)\n\n\nif __name__"
                    " == \"__main__\":\n    unittest.main()\n",
                "README.md": "add() must return the SUM; multiply() the "
                             "product.",
            },
            verify_command=f"{python} -m unittest",
        ),
        EvalTask(
            name="defect-fix-strings",
            goal="The test suite in this project is failing. Find the "
                 "bug, fix it, and run the tests to verify they pass.",
            files={
                "string_utils.py": STRING_DEFECT,
                "test_string_utils.py": STRING_TESTS,
            },
            verify_command=f"{python} -m unittest",
        ),
        EvalTask(
            name="defect-fix-json",
            goal="A test in this project fails. The lookup function is "
                 "supposed to read nested values. Find the bug, fix it, "
                 "and run the tests to verify they pass.",
            files={
                "config_parser.py": JSON_DEFECT,
                "test_config_parser.py": JSON_TESTS,
            },
            verify_command=f"{python} -m unittest",
        ),
    ]


# --- runner + report ---------------------------------------------------------

@dataclass
class EvalReport:
    run_id: str
    started_at: str
    models: List[str]
    results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # results["model"]["task"] = BenchmarkReport.to_dict()

    def to_dict(self):
        return {"run_id": self.run_id, "started_at": self.started_at,
                "models": list(self.models), "results": self.results}

    def aggregates(self) -> Dict[str, Dict[str, Any]]:
        """Per-model rollup: success rate, averages, totals."""
        out: Dict[str, Dict[str, Any]] = {}
        for model, tasks in self.results.items():
            count = len(tasks)
            successes = sum(1 for t in tasks.values() if t.get("success"))
            out[model] = {
                "tasks": count,
                "successes": successes,
                "success_rate": round(successes / count, 3) if count else 0.0,
                "avg_iterations": round(
                    sum(t.get("iterations", 0) for t in tasks.values())
                    / count, 1) if count else 0.0,
                "avg_duration_seconds": round(
                    sum(t.get("duration_seconds", 0) for t in
                        tasks.values()) / count, 1) if count else 0.0,
                "total_tool_calls": sum(t.get("tool_calls", 0)
                                        for t in tasks.values()),
                "total_tool_failures": sum(t.get("tool_failures", 0)
                                           for t in tasks.values()),
                "total_recoveries": sum(t.get("recovery_count", 0)
                                        for t in tasks.values()),
                "total_interventions": sum(t.get("intervention_count", 0)
                                           for t in tasks.values()),
            }
        return out

    def save(self, path: Optional[Path] = None) -> Path:
        target = Path(path) if path else eval_dir() / f"{self.run_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=1,
                                  ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
        return target

    @classmethod
    def load(cls, path: Path) -> "EvalReport":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            raise EvalError(f"cannot load eval run {path}: {exc}") from exc
        report = cls(run_id=data.get("run_id", "unknown"),
                     started_at=data.get("started_at", ""),
                     models=data.get("models", []))
        report.results = data.get("results", {})
        return report


def compare(old: EvalReport, new: EvalReport) -> Dict[str, Any]:
    """Symmetric comparison of two runs: per-model deltas and explicit
    regression/improvement flags on shared (model, task) pairs."""
    regressions: List[Dict[str, Any]] = []
    improvements: List[Dict[str, Any]] = []
    for model in old.results:
        if model not in new.results:
            continue
        for task, old_result in old.results[model].items():
            new_result = new.results.get(model, {}).get(task)
            if new_result is None:
                continue
            was, now = old_result.get("success"), new_result.get("success")
            entry = {"model": model, "task": task, "was": was, "now": now}
            if was and not now:
                regressions.append(entry)
            elif not was and now:
                improvements.append(entry)
    old_agg, new_agg = old.aggregates(), new.aggregates()
    deltas = {}
    for model in old_agg:
        if model in new_agg:
            deltas[model] = {
                "success_rate": round(new_agg[model]["success_rate"]
                                      - old_agg[model]["success_rate"], 3),
                "avg_iterations": round(
                    new_agg[model]["avg_iterations"]
                    - old_agg[model]["avg_iterations"], 1),
            }
    return {"regressions": regressions, "improvements": improvements,
            "deltas": deltas}


def run_evaluation(models: Dict[str, Callable[[Optional[str]], Any]],
                   tasks: Optional[List[EvalTask]] = None,
                   store: Optional[ExperienceStore] = None,
                   events: Optional[EventStream] = None,
                   run_id: Optional[str] = None,
                   tool_catalog: Optional[Any] = None,
                   ) -> EvalReport:
    """Full cross product: every model x every task. tool_catalog=None
    defers to the benchmark's lean default."""
    import uuid as uuid_mod
    from .benchmark import LEAN_MODEL_CATALOG

    tasks = tasks if tasks is not None else default_tasks()
    catalog = tool_catalog if tool_catalog is not None         else LEAN_MODEL_CATALOG
    report = EvalReport(run_id=run_id or uuid_mod.uuid4().hex[:12],
                        started_at=_utc_stamp(), models=list(models))
    for model_name, factory in models.items():
        report.results[model_name] = {}
        for task in tasks:
            root = Path(tempfile.mkdtemp(prefix=f"eval-{task.name}-"))
            task.write_fixture(root)
            report.results[model_name][task.name] = run_benchmark(
                factory(model_name), workspace_root=str(root),
                experience_store=store, events=events or EventStream(),
                tool_catalog=catalog,
                fixture_writer=lambda ws, _task=task: _task.write_fixture(
                    ws.root),
                goal=task.goal,
            ).to_dict()
    return report
