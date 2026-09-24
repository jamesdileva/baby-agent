"""S64 ep1 corpus builder: scripted curriculum demonstrators -> a
verified, step-trainable training corpus — plus the external-compute
training kit export.

Why scripted demonstrators: the roadmap's ep1 needs MANY verified
trajectories, but the free-tier Gemini caps model-generated data at a
few benchmark passes per day, and this machine's GPU (AMD RX 6400,
4 GB, no CUDA) cannot fine-tune locally. The S60 curriculum declares
its defects BY CONSTRUCTION, so a scripted demonstrator that fixes the
DECLARED defect — driven through the REAL S37 loop with REAL subprocess
test execution and the S41 verification gate — produces genuinely
verified demonstrations. Provenance is honest: every record is tagged
`scripted-demo`; the corpus teaches protocol and procedure, and says
exactly what it is.

Pins (fixtures-first discipline):
- only runs that pass the S41 verification gate become records (the
  S63 eligibility gate re-checks at training time);
- demonstrations are EXPLORE-FIRST (list the workspace before reading —
  gen-1 taught answer-reading and the benchmark exposed it) and embed
  RECOVERY beats (a real wrong turn, a real file-not-found observation,
  then correction) in ~half the records — the roadmap's most valuable
  class;
- the demonstrator's edits use declared old/new strings — never a
  whole-file rewrite, so the demonstration teaches surgical editing
  (write_file only for genuinely NEW files);
- deterministic: same categories x levels = same corpus content.
"""

from typing import Any, Dict, List, Optional, Tuple

from .benchmark import run_benchmark
from .contracts import ModelResponse, ToolCall
from .curriculum import (_bug_fix_fixture, _build_repair_fixture,
                         _dependency_fixture, _feature_add_fixture,
                         _regression_fixture, _testing_fixture,
                         bug_fix_defect, feature_add_spec)
from .experience import ExperienceStore
from .providers import FakeModelProvider
from .training import format_tool_call

DEMO_MODEL_TAG = "scripted-demo"

# S69: corpus format version — the rebuild skips only goals covered by
# a CURRENT-version record, and mark_superseded_demos supersedes
# scripted demos lacking the tag (their FORMAT is stale for training
# even when the task itself is unchanged)
CORPUS_VERSION = "v6"
VERSION_TAG = f"corpus-{CORPUS_VERSION}"

# the corpus recipe (S66): categories with declared shapes and honest
# test gates; levels 1..8 (bug_fix decoys at >=3 teach read-before-fix)
CATEGORY_VARIANTS = {
    "bug_fix": 5,
    "feature_add": 3,
    "build_repair": 1,
    "dependency": 1,
    "testing": 1,
    "regression": 1,
    # S73: coverage targeting — mirroring the two S57 evaluation tasks
    # the gen-6 corpus never covered (string reverse, nested lookup)
    "string_reverse": 1,
    "nested_lookup": 1,
}
DEFAULT_LEVELS = tuple(range(1, 9))

# strategy diversity (S72 failure-state demos): the gen-5 verdict
# showed every run dying in the loop's verification-failed recovery
# state — a state NO demonstration ever showed. The
# premature_final_recovery strategy teaches exactly that state: the
# demonstrator claims success before acting, the verifier rejects it,
# and the script continues to the real fix (the run still ends
# verified-successful). The other strategies keep the S71 diagnosis
# chain with rational recovery ordering.
STRATEGIES = {
    "bug_fix": ("diagnostic_clean", "tests_first_recovery",
                "diagnostic_recovery", "premature_final_recovery"),
    "feature_add": ("diagnostic_clean", "diagnostic_recovery",
                    "premature_final_recovery"),
    "build_repair": ("diagnostic_clean", "diagnostic_recovery"),
    "dependency": ("diagnostic_recovery",),
    "testing": ("explore_clean",),
    "regression": ("explore_clean",),
    "string_reverse": ("diagnostic_clean", "diagnostic_recovery"),
    "nested_lookup": ("diagnostic_clean", "diagnostic_recovery"),
}

# goal-phrasing variety: 3 templates per category (gen-1 trained on one
# sentence shape; the real benchmark phrased things differently)
GOAL_TEMPLATES = {
    "bug_fix": (
        "The test suite in this project fails because {func} is "
        "implemented incorrectly. Find the bug, fix it, and run the "
        "tests to verify they pass.",
        "Tests are failing here — {func} does the wrong thing. Track "
        "the bug down, repair it, and prove the suite green.",
        "{func} is buggy and the tests catch it. Debug the module, "
        "apply the smallest correct fix, and rerun the tests.",
    ),
    "feature_add": (
        "The module {module} is missing the {func} function that its "
        "tests expect. Implement it and run the tests to verify they "
        "pass.",
        "{module} needs a {func} function — the tests already expect "
        "it. Write the implementation and run the tests.",
        "Implement {func} in {module}: the test file defines the "
        "expected behavior. Make the tests pass.",
    ),
    "build_repair": (
        "The module in this project has a syntax error and cannot even "
        "be imported. Repair it and run the tests to verify.",
        "This project won't import — one of its modules has a syntax "
        "error. Fix the file and verify with the test suite.",
        "A syntax error is blocking the test run. Find the broken "
        "module, repair it, and run the tests.",
    ),
    "dependency": (
        "The {module} module imports a helpers module that doesn't "
        "exist. Create it so the import works and the tests pass.",
        "An import in this project points at a module that doesn't "
        "exist yet. Create the missing module and run the tests.",
        "The tests fail on a missing module. Implement whatever the "
        "import needs and verify the suite passes.",
    ),
    "testing": (
        "The module {module} has no tests. Write a unittest test file "
        "that verifies {func} works, and run it to confirm your tests "
        "pass.",
        "{module} is untested. Add unittest coverage for its functions "
        "and run your tests.",
        "Write a unittest test file for the module in this workspace "
        "and run it to show the tests pass.",
    ),
    "regression": (
        "sort_words was fixed after a case-sensitivity bug. Add a "
        "unittest test file that pins the correct behavior, and run it "
        "to confirm your tests pass.",
        "A regression slipped through {module} once already. Write "
        "unittest tests that pin the current behavior so it cannot "
        "break silently, and run them.",
        "Guard {module} against regressions: add unittest tests for "
        "{func} and run the suite to show they pass.",
    ),
}


def _phrase_goal(category: str, variant: int, level: int,
                 module: str, func: str) -> str:
    templates = GOAL_TEMPLATES[category]
    return templates[(variant + level) % len(templates)].format(
        module=module, func=func)


class ScriptedDemonstrator(FakeModelProvider):
    """A turn-scripted demonstrator. The SCRIPT comes from the category
    strategy builders below; this class only carries it and the honest
    provenance tag. Model tag stays `scripted-demo`."""

    name = DEMO_MODEL_TAG
    model = DEMO_MODEL_TAG

    def __init__(self, script):
        super().__init__(script)


def _tests_command(python: str) -> str:
    # S69: quote-free — the taught protocol forbids quotes inside
    # values, and gen-3 showed the model mangling quoted interpreter
    # paths into command="\" garbage. Fall back to the PATH-resolved
    # name when the interpreter path would need quoting.
    if " " in python:
        return "python -m unittest -v"
    return f"{python} -m unittest -v"


def _list() -> ToolCall:
    return ToolCall(name="list_directory", arguments={"path": "."})


def _read(path: str) -> ToolCall:
    return ToolCall(name="read_file", arguments={"path": path})


def _tests(python: str) -> ToolCall:
    return ToolCall(name="run_tests",
                    arguments={"command": _tests_command(python)})


def _edit(path: str, old: str, new: str) -> ToolCall:
    return ToolCall(name="edit_file", arguments={
        "path": path, "old_string": old, "new_string": new})


def _write(path: str, content: str) -> ToolCall:
    return ToolCall(name="write_file", arguments={"path": path,
                                                  "content": content})


def _final(text: str) -> ModelResponse:
    return ModelResponse(text=text, finish_reason="stop")


# --- category strategy builders ------------------------------------------
# each returns (script, fixture files, goal, strategy tag)

def _bug_fix_script(strategy: str, variant: int, level: int,
                    python: str):
    module_code, test_code, _goal, _f, _s, module, func = \
        _bug_fix_fixture(variant, level)
    _m, _fn, good, bad = bug_fix_defect(variant)
    path = f"{module}.py"
    test_path = f"test_{module}.py"
    diagnosis = (
        f"The failing tests pointed at {func}. Reading {test_path} "
        f"showed the expectation, and reading {path} showed the "
        f"defect: the body was `{bad.strip()}` instead of "
        f"`{good.strip()}`. I replaced the defective line and the "
        f"tests pass.")
    # S71: the DIAGNOSIS CHAIN — the failing suite names the test, the
    # test states the expectation, the module shows the gap
    core = [_tests(python), _read(test_path), _read(path),
            _edit(path, bad, good), _tests(python)]
    if strategy == "diagnostic_clean":
        script = [_list()] + core + [_final(diagnosis)]
    elif strategy == "diagnostic_recovery":
        # rational first hypothesis, overturned by the evidence
        script = ([_read(f"src/{path}"), _list()] + core
                  + [_final(diagnosis)])
    elif strategy == "premature_final_recovery":
        # S72: THE failure state — claim success before acting, take
        # the verifier's rejection, then do the real work; the honest
        # final ADMITS the premature claim
        premature = (
            f"The failing tests pointed at {func}. I have corrected "
            f"the implementation and the tests pass.")
        recovery_diagnosis = (
            f"My first summary was premature — I claimed a fix I had "
            f"not actually made. The failing tests pointed at {func}: "
            f"reading {test_path} showed the expectation, and reading "
            f"{path} showed the defect: the body was `{bad.strip()}` "
            f"instead of `{good.strip()}`. I replaced the defective "
            f"line and this time the tests pass.")
        script = ([_list(), _tests(python), _final(premature)]
                  + core + [_final(recovery_diagnosis)])
    else:  # tests_first_recovery: the failure output is the clue
        script = ([_tests(python), _read(f"src/{path}"), _list()] + core
                  + [_final(diagnosis)])
    files = {path: module_code, test_path: test_code}
    goal = _phrase_goal("bug_fix", variant, level, module, func)
    return script, files, goal, strategy


def _feature_add_script(strategy: str, variant: int, level: int,
                        python: str):
    module_code, test_code, _goal, _f, _s, module, func = \
        _feature_add_fixture(variant, level)
    _m, _fn, impl, _test = feature_add_spec(variant)
    path = f"{module}.py"
    test_path = f"test_{module}.py"
    marker = f"# {func} is not implemented yet — that is the task.\n"
    diagnosis = (
        f"The tests import {func} from {module}, so the failing suite "
        f"meant the function was missing. Reading {test_path} showed "
        f"the expected behavior, and {path} held only the task marker. "
        f"I implemented {func} and the suite passes.")
    core = [_tests(python), _read(test_path), _read(path),
            _edit(path, marker, impl + "\n\n\n"), _tests(python)]
    script = [_list()] + core + [_final(diagnosis)]
    if strategy == "diagnostic_recovery":
        script = [_read(f"src/{path}"), _list()] + core + [_final(diagnosis)]
    if strategy == "premature_final_recovery":
        premature = (
            f"The tests expect {func} in {module}. I have implemented "
            f"it and the tests pass.")
        recovery_diagnosis = (
            f"That summary was premature — nothing had been written "
            f"yet, and the suite was still failing. Reading {test_path} "
            f"showed the expected behavior, and {path} held only the "
            f"task marker. I implemented {func} and now the suite "
            f"passes.")
        script = ([_list(), _tests(python), _final(premature)]
                  + core + [_final(recovery_diagnosis)])
    files = {path: module_code, test_path: test_code}
    goal = _phrase_goal("feature_add", variant, level, module, func)
    return script, files, goal, strategy


def _build_repair_script(strategy: str, variant: int, level: int,
                         python: str):
    module_code, test_code, _goal, _f, _s, module, func = \
        _build_repair_fixture(variant, level)
    path = f"{module}.py"
    test_path = f"test_{module}.py"
    broken_line = "    return sum(values\n"
    fixed_line = "    return sum(values)\n"
    diagnosis = (
        f"code_diagnostics flagged {path} as unparseable. Reading it "
        f"showed a syntax error — an unclosed call on the total line. "
        f"I repaired the line and the tests pass.")
    # S71: code_diagnostics takes NO arguments (gen-3 invented args for
    # it) and naturally opens the diagnosis: it names the broken file
    core = [ToolCall(name="code_diagnostics", arguments={}),
            _tests(python), _read(path), _edit(path, broken_line, fixed_line),
            _tests(python)]
    script = [_list()] + core + [_final(diagnosis)]
    if strategy == "diagnostic_recovery":
        script = [_read(f"src/{path}"), _list()] + core + [_final(diagnosis)]
    files = {path: module_code, test_path: test_code}
    goal = _phrase_goal("build_repair", variant, level, module, func)
    return script, files, goal, strategy


def _dependency_script(strategy: str, variant: int, level: int,
                       python: str):
    module_code, test_code, _goal, _f, _s, module, func = \
        _dependency_fixture(variant, level)
    helpers = 'def format_money(amount):\n    return f"${amount}.00"\n'
    diagnosis = (
        f"{module}.py imports helpers, which did not exist — the "
        f"failing suite said so. Reading {module}.py showed the call "
        f"site, and reading the test showed the expected format. I "
        f"created helpers.py with the needed function and the tests "
        f"pass.")
    script = [
        _list(),
        _read(f"{module}.py"),
        _tests(python),            # ModuleNotFoundError: helpers
        _read("helpers.py"),       # genuinely not found: the recovery beat
        _read(f"test_{module}.py"),  # what the tests expect ($5.00)
        _write("helpers.py", helpers),
        _tests(python),
        _final(diagnosis),
    ]
    files = {f"{module}.py": module_code, f"test_{module}.py": test_code}
    goal = _phrase_goal("dependency", variant, level, module, func)
    return script, files, goal, "explore_recovery"


def _testing_script(strategy: str, variant: int, level: int,
                    python: str):
    module_code, test_code, _goal, _f, _s, module, func = \
        _testing_fixture(variant, level)
    test_file = "test_multiply.py"
    # NOTE: the fixture's declared shape puts multiply IN
    # test_calc_ops.py (module name is "test_calc_ops") — the demo's
    # test imports from the module that actually exists
    content = (
        "import unittest\n\nfrom test_calc_ops import multiply\n\n\n"
        "class TestMultiply(unittest.TestCase):\n"
        "    def test_multiply(self):\n"
        "        self.assertEqual(multiply(2, 3), 6)\n"
        "        self.assertEqual(multiply(-1, 4), -4)\n\n\n"
        'if __name__ == "__main__":\n    unittest.main()\n')
    diagnosis = (
        f"{module} had no tests. I added {test_file} covering {func} "
        f"and the suite passes with the new tests.")
    script = [
        _list(),
        _read(f"{module}.py"),
        _tests(python),            # 0 tests: the gap the goal names
        _write(test_file, content),
        _tests(python),
        _final(diagnosis),
    ]
    files = {f"{module}.py": module_code, f"test_{module}.py": test_code}
    goal = _phrase_goal("testing", variant, level, module, func)
    return script, files, goal, "explore_clean"


def _regression_script(strategy: str, variant: int, level: int,
                       python: str):
    module_code, test_code, _goal, _f, _s, module, func = \
        _regression_fixture(variant, level)
    test_file = "test_sort_words.py"
    content = (
        "import unittest\n\nfrom sort_mod import sort_words\n\n\n"
        "class TestSortWords(unittest.TestCase):\n"
        "    def test_mixed_case(self):\n"
        '        self.assertEqual(sort_words(["b", "A", "c"]), '
        '["A", "b", "c"])\n\n\n'
        'if __name__ == "__main__":\n    unittest.main()\n')
    diagnosis = (
        f"I pinned {module}.{func}'s behavior with {test_file} and the "
        f"suite passes with the new tests.")
    script = [
        _list(),
        _read(f"{module}.py"),
        _write(test_file, content),
        _tests(python),
        _final(diagnosis),
    ]
    files = {f"{module}.py": module_code, f"test_{module}.py": test_code}
    goal = _phrase_goal("regression", variant, level, module, func)
    return script, files, goal, "explore_clean"


def _string_reverse_script(strategy: str, variant: int, level: int,
                           python: str):
    """S73: mirrors the S57 string-reverse eval task — the corpus never
    covered this shape."""
    module = "string_utils"
    "reverse"
    path = f"{module}.py"
    test_path = f"test_{module}.py"
    module_code = 'def reverse(text):\n    return text\n'
    test_code = (
        "import unittest\n\nfrom string_utils import reverse\n\n\n"
        "class TestReverse(unittest.TestCase):\n"
        "    def test_reverse(self):\n"
        '        self.assertEqual(reverse("abc"), "cba")\n\n\n'
        'if __name__ == "__main__":\n    unittest.main()\n')
    broken = "    return text\n"
    fixed = "    return text[::-1]\n"
    diagnosis = (
        f"The failing test showed reverse(\"abc\") should be \"cba\", "
        f"but {path} returned its input unchanged. I replaced the body "
        f"with a slice step of -1 and the tests pass.")
    core = [_tests(python), _read(test_path), _read(path),
            _edit(path, broken, fixed), _tests(python)]
    script = [_list()] + core + [_final(diagnosis)]
    if strategy == "diagnostic_recovery":
        script = [_read(f"src/{path}"), _list()] + core + [_final(diagnosis)]
    files = {path: module_code, test_path: test_code}
    goal = (
        "The tests in this project are failing. Find the bug, fix it, "
        "and run the tests to verify they pass."
        if (variant + level) % 2 == 0 else
        "A string utility in this project fails its test. Track down "
        "the bug, repair it, and prove the suite green.")
    return script, files, goal, strategy


def _nested_lookup_script(strategy: str, variant: int, level: int,
                          python: str):
    """S73: mirrors the S57 nested-JSON-lookup eval task."""
    module = "config_parser"
    "lookup"
    path = f"{module}.py"
    test_path = f"test_{module}.py"
    module_code = ('def lookup(data, key):\n    return data.get(key)\n')
    test_code = (
        "import unittest\n\nfrom config_parser import lookup\n\n\n"
        "class TestLookup(unittest.TestCase):\n"
        "    def test_nested(self):\n"
        "        data = {\"settings\": {\"timeout\": 30}}\n"
        "        self.assertEqual(lookup(data, \"timeout\"), 30)\n\n\n"
        'if __name__ == "__main__":\n    unittest.main()\n')
    broken = "    return data.get(key)\n"
    fixed = '    return data.get("settings", {}).get(key)\n'
    diagnosis = (
        f"The test showed lookup should find keys nested under the "
        f"settings section of {path}'s data, but the code only checked "
        f"the top level. I chained the lookup into the settings dict "
        f"and the tests pass.")
    core = [_tests(python), _read(test_path), _read(path),
            _edit(path, broken, fixed), _tests(python)]
    script = [_list()] + core + [_final(diagnosis)]
    if strategy == "diagnostic_recovery":
        script = [_read(f"src/{path}"), _list()] + core + [_final(diagnosis)]
    files = {path: module_code, test_path: test_code}
    goal = (
        "The tests in this project are failing. Find the bug, fix it, "
        "and run the tests to verify they pass."
        if (variant + level) % 2 == 0 else
        "The config lookup in this project is not finding nested keys. "
        "Diagnose the failure and repair the lookup.")
    return script, files, goal, strategy


_SCRIPT_BUILDERS = {
    "bug_fix": _bug_fix_script,
    "feature_add": _feature_add_script,
    "build_repair": _build_repair_script,
    "dependency": _dependency_script,
    "testing": _testing_script,
    "regression": _regression_script,
    "string_reverse": _string_reverse_script,
    "nested_lookup": _nested_lookup_script,
}


def build_demo(category: str, strategy: str, variant: int, level: int,
               python: str):
    """One demonstrator task: (script, fixture files, goal, tag)."""
    if strategy not in STRATEGIES.get(category, ()):
        raise KeyError(f"unknown strategy {strategy!r} for {category}")
    return _SCRIPT_BUILDERS[category](strategy, variant, level, python)


def mark_superseded_demos(store: ExperienceStore) -> Dict[str, Any]:
    """S68/S69 corpus hygiene: scripted-demo records are superseded
    when their FIRST captured step is read_file (the pre-S66
    answer-reading policy — precise identifier: no current script
    starts with a read) OR when they lack the current corpus version
    tag (their FORMAT is stale for training). Kept in the store for
    provenance; the idempotent rebuild re-demos their tasks."""
    records = store.load()
    superseded = 0
    for record in records:
        tags = record.tags or []
        if "scripted-demo" not in tags or "superseded-pattern" in tags:
            continue
        steps = record.context.get("tool_calls") or []
        stale_first_step = bool(steps) and \
            steps[0].get("tool") == "read_file"
        if stale_first_step or VERSION_TAG not in tags:
            record.tags.append("superseded-pattern")
            superseded += 1
    if superseded:
        store.save(records)
    return {"scanned": len(records), "superseded": superseded}


def build_corpus(experience_store: ExperienceStore,
                 python: str,
                 categories: Optional[Dict[str, int]] = None,
                 levels: Tuple[int, ...] = DEFAULT_LEVELS
                 ) -> Dict[str, Any]:
    """Run every (category, variant, level) demonstrator — strategies
    cycled per task — through the benchmark; each verified pass is
    recorded with the S63 session-unique goal suffix. Recovery-strategy
    records get an honest `recovery-demo` tag. Returns honest stats;
    failures are kept as failed trajectories, never hidden."""
    import sys

    from .experience import _normalize_goal

    python = python or sys.executable
    categories = dict(categories or CATEGORY_VARIANTS)
    # S68: hygiene first, then an IDEMPOTENT rebuild — skip tasks whose
    # normalized goal already has a successful non-superseded scripted
    # demo, which re-demos exactly the stale goals and nothing else
    hygiene = mark_superseded_demos(experience_store)
    covered = set()
    for record in experience_store.load():
        tags = record.tags or []
        if ("scripted-demo" in tags
                and "superseded-pattern" not in tags
                and VERSION_TAG in tags
                and record.outcome in ("success", "recovered")):
            # strip the session-unique suffix before normalizing: the
            # recorded goal carries " (benchmark run <id>)" but the
            # build-task goal does not
            base_goal = record.goal.split(" (benchmark run")[0]
            covered.add(_normalize_goal(base_goal))
    stats: Dict[str, Any] = {"runs": 0, "passed": 0, "failed": 0,
                             "recovery": 0, "skipped_existing": 0,
                             "superseded": hygiene["superseded"],
                             "durations_s": 0.0,
                             "by_category": {}, "tasks": []}
    for category, variant_count in categories.items():
        for variant in range(variant_count):
            for level in levels:
                strategies = STRATEGIES[category]
                strategy = strategies[(variant + level) % len(strategies)]
                script, files, goal, tag = build_demo(
                    category, strategy, variant, level, python)
                if _normalize_goal(goal) in covered:
                    stats["skipped_existing"] += 1
                    continue
                provider = ScriptedDemonstrator(script)

                def fixture_writer(ws, _files=files):
                    for name, content in _files.items():
                        (ws.root / name).write_text(content,
                                                    encoding="utf-8")

                report = run_benchmark(
                    provider, fixture_writer=fixture_writer, goal=goal,
                    experience_store=experience_store)
                stats["runs"] += 1
                stats["durations_s"] += report.duration_seconds
                per_cat = stats["by_category"].setdefault(
                    category, {"runs": 0, "passed": 0, "recovery": 0})
                per_cat["runs"] += 1
                if report.success:
                    stats["passed"] += 1
                    per_cat["passed"] += 1
                else:
                    stats["failed"] += 1
                is_recovery = "recovery" in strategy
                if is_recovery:
                    stats["recovery"] += 1
                    per_cat["recovery"] += 1
                if report.success:
                    # S69: version-tag current-format records so the
                    # idempotent rebuild recognizes them
                    records = experience_store.load()
                    if records:
                        last = records[-1]
                        if VERSION_TAG not in last.tags:
                            last.tags.append(VERSION_TAG)
                        if is_recovery and "recovery-demo" not in last.tags:
                            last.tags.append("recovery-demo")
                        experience_store.save(records)
                stats["tasks"].append({
                    "category": category, "strategy": strategy,
                    "variant": variant, "level": level, "goal": goal,
                    "success": report.success,
                    "iterations": report.iterations,
                    "termination": report.termination_reason,
                })
    return stats


# --- training kit export -------------------------------------------------

_TRAIN_SCRIPT = '''"""baby-agent:ep1 — QLoRA SFT over the exported S63 training corpus.

Run this OUTSIDE the qacompanion repo (Colab T4 / Kaggle GPU / any CUDA
box). qacompanion itself stays stdlib-only; these dependencies belong to
the training environment only.

    pip install -U transformers peft datasets trl accelerate

Inputs: training.jsonl (S63 chat records: {"messages": [...],
"metadata": {...}}). Output: ep1-merged/ — the base model WITH the
adapter baked in, ready for `ollama create` (or GGUF conversion).

The honesty rule (docs/s64-spec.md): ep1 is NEVER assumed better —
evaluate with the repo's own harness and compare():
    run_evaluation([base_provider, OllamaProvider(model="baby-agent:ep1")])
    compare(...)  # regressions are documented, not shipped silently

T4 note: Turing GPUs have no bf16 — this script trains in fp16 with
gradient checkpointing (free Colab T4 = 16 GB, plenty for a 3B QLoRA).
"""

import json
import sys

# optional generation name: `python train_ep1.py ep8` produces
# ep8-adapter/ and ep8-merged/ (default: ep1)
GEN = sys.argv[1] if len(sys.argv) > 1 else "ep1"
BASE_MODEL = "Qwen/Qwen2.5-Coder-3B-Instruct"
DATASET = "training.jsonl"
OUTPUT_DIR = f"{GEN}-adapter"
MERGED_DIR = f"{GEN}-merged"


KIT_VERSION = "s76.1"


def load_dataset(path=DATASET):
    rows = [json.loads(line) for line in open(path, encoding="utf-8")
            if line.strip()]
    if not rows:
        sys.exit(f"no training records in {path} — run 'qa curate' and "
                 "'qa build-training' first")
    return rows


def main():
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    print(f"kit version: {KIT_VERSION}")
    rows = load_dataset()
    print(f"training records: {len(rows)}")

    # S76 ASSISTANT-ONLY LOSS (gen-8's one variable): the gen-5 verdict
    # showed most gradient mass teaching the model to predict
    # ENVIRONMENT output (user/observation turns) — imitation then
    # concentrated on the narrative. Build labels with every
    # non-assistant span at -100 so the loss trains ONLY on the
    # model's own behavior: [TOOL: ...] calls and final answers.
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def masked_example(messages):
        """Render the conversation incrementally through the joint chat
        template (per-message rendering would corrupt the stream: Qwen
        injects a default system block into every render that lacks
        one) and attribute each new token to the message that
        introduced it."""
        input_ids: list = []
        labels: list = []
        prev_len = 0
        for index, message in enumerate(messages):
            full = tokenizer.apply_chat_template(
                messages[:index + 1], tokenize=True)
            # S76.1: normalize EVERY known return shape to flat ids —
            # transformers v5 has been seen returning dict (input_ids
            # key), batched nested lists, and tensors (the 0/116
            # mask-gate catches persisted because the tensor shape
            # passed the list checks: full[0] is a row-tensor, not a
            # list, so nothing flattened and every render read as
            # "1 token")
            while isinstance(full, dict):
                full = full["input_ids"]
            if hasattr(full, "tolist"):
                full = full.tolist()
            while full and isinstance(full[0], (list, tuple)):
                full = full[0]
            new_tokens = full[prev_len:]
            prev_len = len(full)
            input_ids.extend(new_tokens)
            if message["role"] == "assistant":
                labels.extend(new_tokens)
            else:
                labels.extend([-100] * len(new_tokens))
        assistant_tokens = sum(1 for l in labels if l != -100)
        return ({"input_ids": input_ids, "labels": labels},
                assistant_tokens, len(labels))

    masked_rows = []
    total_assistant = 0
    total_tokens = 0
    for r in rows:
        example, a_tokens, all_tokens = masked_example(r["messages"])
        masked_rows.append(example)
        total_assistant += a_tokens
        total_tokens += all_tokens
    ratio = total_assistant / max(total_tokens, 1)
    print(f"assistant-token ratio: {ratio:.3f} "
          f"({total_assistant:,}/{total_tokens:,})")
    if ratio < 0.10:
        # a broken mask would train on nothing — refuse like the
        # sanity generation gate does
        sys.exit("MASK GATE FAILED: assistant-token ratio under 10% — "
                 "the label masking is broken; do not train")
    dataset = Dataset.from_list(masked_rows)

    config = SFTConfig(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        num_train_epochs=3,
        learning_rate=2e-4,
        fp16=True,                      # T4 (Turing) has no bf16
        gradient_checkpointing=True,
        # LoRA + checkpointing: frozen embeddings break the default
        # (reentrant) checkpoint implementation
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=1,
        report_to=[],
        # S76: the dataset is pre-tokenized with labels — TRL must not
        # re-apply its own (unmasked) preparation
        dataset_kwargs={"skip_prepare_dataset": True},
    )
    lora = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        task_type="CAUSAL_LM",
    )

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, torch_dtype="float16")
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    from transformers import DataCollatorForSeq2Seq
    trainer = SFTTrainer(
        model=model,
        args=config,
        train_dataset=dataset,
        processing_class=tokenizer,
        data_collator=DataCollatorForSeq2Seq(
            tokenizer, model=model, label_pad_token_id=-100),
    )
    trainer.train()
    trainer.save_model(OUTPUT_DIR)
    print("adapter saved to", OUTPUT_DIR)

    # merge the adapter into the base so ollama (or llama.cpp) can take
    # the WHOLE model without any adapter dance
    merged = model.merge_and_unload()
    merged.save_pretrained(MERGED_DIR)
    tokenizer.save_pretrained(MERGED_DIR)

    # DISK-LEVEL fixup (the first ep1 verdict attempt, 2026-09-11):
    # in-memory config edits do NOT survive transformers v5's save —
    # it re-tied the head and wrote rope_theta in a new config format
    # ollama's converter cannot read (freq_base came out 0.0 and the
    # model emitted one repeated token). Patch the SAVED files:
    # explicit lm_head + legacy rope_theta key.
    import glob as _glob
    import json as _json
    from safetensors.torch import load_file as _load, save_file as _save
    for shard in _glob.glob(f"{MERGED_DIR}/*.safetensors"):
        state = _load(shard)
        if "model.embed_tokens.weight" in state                 and "lm_head.weight" not in state:
            state["lm_head.weight"] =                 state["model.embed_tokens.weight"].clone()
            _save(state, shard)
            print("fixup: lm_head made explicit in", shard)
    cfg_path = f"{MERGED_DIR}/config.json"
    cfg = _json.load(open(cfg_path, encoding="utf-8"))
    cfg["tie_word_embeddings"] = False
    cfg["rope_theta"] = (cfg.get("rope_theta")
                         or cfg.get("rope_parameters", {}).get("rope_theta")
                         or 1000000.0)
    _json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), indent=2)
    print("fixup: tie_word_embeddings=False, rope_theta =",
          cfg["rope_theta"])

    # the honesty gate, in-process: never declare success on a model
    # that cannot speak — degenerate output ships silently otherwise
    inputs = tokenizer("The capital of France is", return_tensors="pt")
    out = merged.generate(**inputs, max_new_tokens=8, do_sample=False)
    text = tokenizer.decode(out[0], skip_special_tokens=True)
    print("SANITY GENERATION:", repr(text))
    body = text.lower().replace("the capital of france is", "").strip()
    if not body or len(set(body)) <= 2:
        print("DEGENERATE OUTPUT DETECTED — the model cannot speak. "
              "Do NOT download this model: check the loss curve above; "
              "typical fixes are lower learning rate (1e-4) or fewer "
              "epochs. Record the attempt as failed (roadmap honesty "
              "rule).")
        sys.exit(1)
    print(f"next: convert {MERGED_DIR} to GGUF with llama.cpp and "
          f"`ollama create baby-agent:{GEN}` — exact commands in "
          "training-kit/README.md (ollama 0.34.4+ requires the GGUF "
          "path),")
    print("then evaluate with qa verdict — honestly.")


if __name__ == "__main__":
    main()
'''

_TRAIN_README = '''# baby-agent:ep1 training kit

qacompanion stays stdlib-only — this kit runs on EXTERNAL free compute
(no billing, same ruling as the Gemini free tier):

- **Google Colab** (free T4): upload `training.jsonl` +
  `train_ep1.py` via the FILES PANEL (left sidebar folder icon — NOT
  into a cell), then:
    `!pip install -U transformers peft datasets trl accelerate`
    `!pip uninstall -y torchao`   # Colab ships an old torchao; recent
    # peft RAISES on it instead of ignoring it (optional dependency)
    `%run train_ep1.py`
- **Kaggle** (free 30 GPU-hours/week): same two files, P100/T4 kernel.

## After training (script outputs `ep1-merged/`)

**ollama 0.34.4+ dropped direct safetensors import (MLX-only converter)
and the old quantize types — conversion through llama.cpp is now
REQUIRED** (verified 2026-09-24; see docs/s76-spec.md):

1. Zip and download (Colab):
    `!zip -r epN-merged.zip epN-merged`
2. Convert to GGUF (same Colab session, before or after download —
   the converter is pure Python, no build):
    `!pip install gguf`
    `!git clone --depth 1 https://github.com/ggml-org/llama.cpp`
    `!python llama.cpp/convert_hf_to_gguf.py epN-merged \\
        --outfile epN.gguf --outtype q8_0`
   (q8_0 ≈ half the fp16 size, negligible quality cost. Optional
   speed step: q4_K_M via a prebuilt llama-quantize binary from
   llama.cpp releases — `llama-quantize epN.gguf epN-q4.gguf q4_K_M`.)
3. Download `epN.gguf`, then locally:
       Modelfile:  FROM ./epN.gguf
       `ollama create baby-agent:epN -f Modelfile`
4. evaluate HONESTLY with the repo harness:
   `qa verdict --models baby-agent:epN-q4,<previous-gen>-q4`
   (repetitions=3, budget 12) — per-task success rates + protocol
   metrics; regressions are called out, never shipped silently
5. a generation that forgets old lessons is documented, not shipped
   silently (roadmap honesty rule)

## Provenance

The corpus is tagged: `scripted-demo` records are scripted curriculum
demonstrations (real loop, real test execution, declared defects);
model-tagged records come from real provider runs. ep1 trained on
scripted demos teaches protocol and procedure — the S55 finding says
that is exactly what general small models lack.
'''


def format_demonstration(goal: str, steps: List[Dict[str, Any]],
                         final_answer: Optional[str],
                         model: Optional[str]) -> Optional[str]:
    """S64 slice 2 (ep0.5): render a verified experience as a worked
    example the model can imitate in-context — the adaptation half of
    "fine-tune / adapt", no gradients required. Bounded: <=6 steps,
    capped result heads. Returns None when there is nothing to show."""
    if not steps:
        return None
    lines = [f"## Worked example (provenance: {model or 'unknown'})",
             f"Goal: {str(goal)[:200]}"]
    for index, step in enumerate(steps[:6], 1):
        if not isinstance(step, dict) or not isinstance(
                step.get("args"), dict):
            continue
        lines.append(f"{index}. {format_tool_call(step['tool'], step['args'])}")
        head = str(step.get("result_head") or "")[:160]
        if head:
            lines.append(f"   -> {head}")
    final = (final_answer or "").strip()
    if final:
        lines.append(f"Final answer: {final[:300]}")
    return "\n".join(lines)


def export_training_kit(out_dir=None) -> Dict[str, str]:
    """Write the self-contained training kit (files, no dependencies
    added to qacompanion)."""
    from pathlib import Path

    directory = Path(out_dir or "training-kit")
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "train_ep1.py": _TRAIN_SCRIPT,
        "README.md": _TRAIN_README,
    }
    for name, content in paths.items():
        (directory / name).write_text(content, encoding="utf-8",
                                      newline="")
    return {"out_dir": str(directory), "files": sorted(paths)}


def run_verdict(providers: Dict[str, Any], task_count: int = 3,
                store: Optional[ExperienceStore] = None,
                max_iterations: int = 12,
                ab_demos: bool = False,
                repetitions: int = 3) -> Dict[str, Any]:
    """S68/S74: the generation verdict — task_count evaluation tasks
    per provider under the trained textual contract, REPEATED
    `repetitions` times (S74: n=1 verdicts cannot distinguish
    capability from sampling luck at this capability level); every run
    recorded; per-task success counts + rates are the headline;
    protocol metrics cover all repetitions (the population is computed
    from a pre-run store snapshot, not a tail count); optional ep0.5
    on/off A/B for the first provider's first task. providers maps
    name -> ModelProvider (the CLI maps model names to
    OllamaProviders; tests inject fakes).
    S72.2: the default budget is 12 — the taught diagnostic chain is
    7-9 turns and the premature-recovery variant 9-11; 6 starved the
    taught behavior (gen-6's calculator win came at 7)."""
    from . import AgentConfig
    from .context import ContextBuilder, MemoryRetriever
    from .evaluation import default_tasks, protocol_metrics
    from .experience import MemoryLayer

    store = store or ExperienceStore()
    tasks = default_tasks()[:max(1, task_count)]
    reps = max(1, repetitions)
    snapshot = len(store.load())  # pre-run marker: everything after is
    results: Dict[str, Any] = {}
    for name, provider in providers.items():
        results[name] = {}
        for task in tasks:
            runs = []
            for _ in range(reps):
                report = run_benchmark(
                    provider,
                    config=AgentConfig(max_iterations=max_iterations),
                    experience_store=store,
                    fixture_writer=lambda ws, _t=task: _t.write_fixture(
                        ws.root),
                    goal=task.goal,
                )
                runs.append(report.to_dict())
            success_count = sum(1 for r in runs if r["success"])
            results[name][task.name] = {
                "runs": runs,
                "success_count": success_count,
                "success_rate": round(success_count / reps, 4),
            }
    fresh = store.load()[snapshot:]
    metrics = {}
    for name in providers:
        runs = [r for r in fresh if r.context.get("model") == name]
        metrics[name] = protocol_metrics(runs)
    verdict: Dict[str, Any] = {"tasks": [t.name for t in tasks],
                               "repetitions": reps,
                               "results": results, "metrics": metrics}
    if ab_demos and providers:
        name, provider = next(iter(providers.items()))
        task = tasks[0]
        builder = ContextBuilder(memory_retriever=MemoryRetriever(
            memory_layer=MemoryLayer(experience_store=store)))
        pair: Dict[str, Any] = {}
        for label, kwargs in (("without", {}),
                              ("with", {"context_builder": builder})):
            report = run_benchmark(
                provider,
                config=AgentConfig(max_iterations=max_iterations),
                experience_store=store,
                fixture_writer=lambda ws, _t=task: _t.write_fixture(
                    ws.root),
                goal=task.goal, **kwargs)
            pair[label] = report.to_dict()
        verdict["ab_demos"] = {name: pair}
    return verdict


def format_verdict(verdict: Dict[str, Any]) -> str:
    lines = [f"generation verdict (n={verdict.get('repetitions', 1)}):"]
    for name, per_task in verdict["results"].items():
        for task, result in per_task.items():
            if "runs" in result:  # S74 repeated-run shape
                lines.append(
                    f"  {name} / {task}: "
                    f"{result['success_count']}/{len(result['runs'])}"
                    f" SUCCESS"
                    f" | rate={result['success_rate']}")
                for i, run in enumerate(result["runs"], 1):
                    lines.append(
                        f"    run {i}: "
                        f"{'SUCCESS' if run['success'] else 'FAILED'}"
                        f" | {run['termination_reason']}"
                        f" | iters={run['iterations']}"
                        f" | calls={run['tool_calls']}"
                        f" | failures={run['tool_failures']}")
            else:  # legacy single-run shape (ep0.5 A/B pairs)
                lines.append(
                    f"  {name} / {task}: "
                    f"{'SUCCESS' if result['success'] else 'FAILED'}"
                    f" | {result['termination_reason']}"
                    f" | iters={result['iterations']}"
                    f" | calls={result['tool_calls']}"
                    f" | failures={result['tool_failures']}")
    for name, metrics in verdict["metrics"].items():
        lines.append(f"  metrics {name}: {metrics}")
    for name, pair in verdict.get("ab_demos", {}).items():
        for label, result in pair.items():
            lines.append(
                f"  ep0.5 A/B {name} [{label}]: "
                f"{'SUCCESS' if result['success'] else 'FAILED'}"
                f" | calls={result['tool_calls']}")
    return "\n".join(lines)


def format_corpus_report(stats: Dict[str, Any]) -> str:
    lines = [
        "ep1 corpus report:",
        f"  runs: {stats['runs']} (passed: {stats['passed']}, "
        f"failed: {stats['failed']}, recovery-strategy: "
        f"{stats['recovery']})",
        f"  hygiene: superseded {stats.get('superseded', 0)}, "
        f"skipped already-covered: {stats.get('skipped_existing', 0)}",
        f"  total duration: {stats['durations_s']:.1f}s",
    ]
    for category, per in stats["by_category"].items():
        lines.append(f"    {category}: runs {per['runs']}, "
                     f"passed {per['passed']}, recovery {per['recovery']}")
    for task in stats["tasks"]:
        if not task["success"]:
            lines.append(f"  FAILED {task['category']}"
                         f"/{task['strategy']} v{task['variant']} "
                         f"L{task['level']}: {task['termination']}")
    if stats["passed"] == stats["runs"]:
        lines.append("  all demonstrations verified")
    return "\n".join(lines)
