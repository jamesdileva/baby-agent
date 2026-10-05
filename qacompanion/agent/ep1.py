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

import re
from typing import Any, Dict, List, Optional, Tuple

from .benchmark import run_benchmark
from .contracts import ModelResponse, ToolCall
from .curriculum import (_bug_fix_fixture, _build_repair_fixture,
                         _dependency_fixture, _feature_add_fixture,
                         _regression_fixture, _testing_fixture,
                         bug_fix_defect, feature_add_spec)
from .experience import Experience, ExperienceStore
from .providers import FakeModelProvider
from .training import format_tool_call

DEMO_MODEL_TAG = "scripted-demo"

# S69: corpus format version — the rebuild skips only goals covered by
# a CURRENT-version record, and mark_superseded_demos supersedes
# scripted demos lacking the tag (their FORMAT is stale for training
# even when the task itself is unchanged)
CORPUS_VERSION = "v8"
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
    # S77: the json wall — chained-descent synthesis needs more
    # examples (4 variants x 8 levels = 32 nested-lookup runs)
    "nested_lookup": 4,
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


# S77: nested-lookup variants — the chained-descent expression is the
# two-hop synthesis the json wall demands, and it needs more examples
# than one variant provides. v0 is the exact S57 eval-task shape;
# v1-v3 generalize the pattern (section names, depth, defaults).
# (module, sections, key, leaf_literal, default_or_None)
_NESTED_SECTION_POOL = ("settings", "database", "server", "cache",
                        "auth", "logging", "network", "storage")
_NESTED_KEY_POOL = ("timeout", "host", "retries", "size", "mode",
                    "region", "retries", "port", "theme", "user",
                    "timeout", "version")
# S78: volume-teach the chained-descent synthesis — 24 deterministic
# variants from fixed pools (no randomness): depths 1-2, varied
# sections/keys/leaves, a default on every fourth variant.
_NESTED_LOOKUP_VARIANTS = [
    ("config_parser", ("settings",), "timeout", "30", None),
    ("db_config", ("database",), "host", '"localhost"', None),
    ("prefs", ("ui", "font"), "size", "12", None),
    ("service_config", ("settings",), "retries", "5", "3"),
]
for _i in range(20):
    _sections = (_NESTED_SECTION_POOL[_i % 8],) if _i % 3 == 0 else (
        _NESTED_SECTION_POOL[_i % 8], _NESTED_KEY_POOL[_i % 12])
    _default = str(_i) if _i % 4 == 3 else None
    _NESTED_LOOKUP_VARIANTS.append((
        f"config_mod{_i}", _sections, _NESTED_KEY_POOL[(_i + 3) % 12],
        str(10 + _i), _default))


def _nested_lookup_script(strategy: str, variant: int, level: int,
                          python: str):
    """S73/S77: the nested-JSON-lookup eval-task shape, generalized."""
    module, sections, key, leaf, default = _NESTED_LOOKUP_VARIANTS[
        variant % len(_NESTED_LOOKUP_VARIANTS)]
    func = "lookup"
    path = f"{module}.py"
    test_path = f"test_{module}.py"
    module_code = "def lookup(data, key):\n    return data.get(key)\n"
    # the leaf lives under the KEY inside the innermost section, then
    # the sections wrap outward: {"settings": {"timeout": 30}}
    data_literal = '{{"{}": {}}}'.format(key, leaf)
    for section in reversed(sections):
        data_literal = '{{"{}": {}}}'.format(section, data_literal)
    test_code = (
        "import unittest\n\nfrom {} import lookup\n\n\n"
        "class TestLookup(unittest.TestCase):\n"
        "    def test_nested(self):\n"
        "        data = {}\n"
        '        self.assertEqual(lookup(data, "{}"), {})\n'.format(
            module, data_literal, key, leaf))
    if default is not None:
        test_code += (
            "    def test_missing_section_uses_default(self):\n"
            '        self.assertEqual(lookup({{}}, "{}"), {})\n'.format(
                key, default))
    test_code += '\nif __name__ == "__main__":\n    unittest.main()\n'
    broken = "    return data.get(key)\n"
    descent = "data" + "".join(
        '.get("{}", {{}})'.format(section) for section in sections)
    fixed = '    return {}.get(key{})\n'.format(
        descent, ', {}'.format(default) if default is not None else '')
    diagnosis = (
        "The test showed lookup must descend through the {} section(s) "
        "of the data before reading the key, but the code only checked "
        "the top level. I chained the lookups and the tests pass.".format(
            " -> ".join(sections)))
    core = [_tests(python), _read(test_path), _read(path),
            _edit(path, broken, fixed), _tests(python)]
    script = [_list()] + core + [_final(diagnosis)]
    if strategy == "diagnostic_recovery":
        script = [_read(f"src/{path}"), _list()] + core + [_final(diagnosis)]
    files = {path: module_code, test_path: test_code}
    # S78: the goal carries the variant's module + descent path — the
    # store's goal-dedupe would otherwise collapse 24 distinct
    # demonstrations into 3 goal texts, defeating the volume teaching
    sections_text = "/".join(sections)
    goals = (
        f"The tests in this project are failing: {func} misses keys "
        f"nested under the {sections[0]} section of {module}. Fix the "
        f"lookup and run the tests to verify they pass.",
        f"The config lookup in {module} is not finding keys nested "
        f"under {sections_text}. Diagnose the failure from the tests "
        f"and repair the lookup.",
        f"{module}.{func} misses keys nested under {sections_text}. "
        f"Find the defect from the failing test, fix the lookup, and "
        f"verify the suite passes.",
    )
    goal = goals[(variant + level) % len(goals)]
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


def repair_agent_corpus_tags(store: ExperienceStore) -> Dict[str, Any]:
    """S106 one-time repair: agent-authored records were recorded
    WITHOUT the corpus version tag, so every hygiene run superseded
    the whole lane (72/72 records dead) — each generation trained on
    only that cycle's fresh drills. The lane is validator-enforced
    current-format by construction, so the supersession was an
    artifact of the missing stamp, not a format judgment: un-supersede
    every agent-authored record, stamp the current version tag, and
    dedupe by normalized goal keeping the NEWEST record (the treadmill
    re-recorded drills after each wave died, leaving duplicates);
    older duplicates stay superseded (same content, one current
    record). Scripted records are untouched."""
    from .experience import _normalize_goal

    records = store.load()
    repaired = 0
    agent_records = [r for r in records
                     if AGENT_AUTHORED_TAG in (r.tags or [])]
    for record in agent_records:
        tags = record.tags or []
        if "superseded-pattern" in tags:
            tags.remove("superseded-pattern")
            repaired += 1
        if VERSION_TAG not in tags:
            tags.append(VERSION_TAG)
    best: Dict[str, Experience] = {}
    for record in agent_records:
        key = _normalize_goal(record.goal.split(" (benchmark run")[0])
        incumbent = best.get(key)
        if incumbent is None or (record.recorded_at,
                                 record.experience_id) > (
                incumbent.recorded_at, incumbent.experience_id):
            if incumbent is not None:
                if "superseded-pattern" not in incumbent.tags:
                    incumbent.tags.append("superseded-pattern")
            best[key] = record
        else:
            if "superseded-pattern" not in record.tags:
                record.tags.append("superseded-pattern")
    deduped = sum(1 for r in agent_records
                  if "superseded-pattern" in r.tags)
    store.save(records)
    return {"scanned": len(records), "agent_records": len(agent_records),
            "repaired": repaired, "current_after": len(agent_records)
            - deduped, "deduped": deduped}


def supersede_opening_guess_demos(store: ExperienceStore) -> Dict[str, Any]:
    """S110 one-time repair: an agent-authored record whose FIRST
    captured read_file step FAILED demonstrates path-guessing as an
    opening move — and gen-22 imitated it (guessed_path 0.4444 vs
    ep21's 0.0; the S100 lesson in a new form: a failure demonstrated
    early gets imitated early). Recovery beats belong MID-CHAIN. The
    S108/S109 recovery drills are the only records matching (every
    other drill's first read succeeds); superseded records are
    excluded from training and their demo dicts are removed from the
    lane in the same slice."""
    records = store.load()
    superseded = 0
    for record in records:
        tags = record.tags or []
        if "agent-authored" not in tags or "superseded-pattern" in tags:
            continue
        steps = record.context.get("tool_calls") or []
        first_read = next((s for s in steps if s.get("tool") == "read_file"),
                          None)
        if first_read is not None and first_read.get("ok") is False:
            record.tags.append("superseded-pattern")
            superseded += 1
    if superseded:
        store.save(records)
    return {"scanned": len(records), "superseded": superseded}


def mark_superseded_demos(store: ExperienceStore) -> Dict[str, Any]:
    """S68/S69 corpus hygiene: scripted-demo records are superseded
    when their FIRST captured step is read_file (the pre-S66
    answer-reading policy) OR when they lack the current corpus version
    tag (their FORMAT is stale for training). Kept in the store for
    provenance; the idempotent rebuild re-demos their tasks.
    S104.1: records carrying a deliberate-recovery tag (recovery-demo,
    edit-recovery) are EXEMPT from the read-first rule — S71's rational
    recovery ordering puts the wrong-turn read FIRST by design, so the
    read-first identifier was convicting every recovery variant and
    each rebuild superseded the previous wave (the demo treadmill: the
    deliberate pool oscillated 188 -> 122 -> 144 across rebuilds as
    waves were killed and re-demoed). Format staleness (the version
    tag) still applies to them."""
    records = store.load()
    superseded = 0
    deliberate_recovery = {"recovery-demo", "edit-recovery"}
    for record in records:
        tags = record.tags or []
        if "scripted-demo" not in tags or "superseded-pattern" in tags:
            continue
        if VERSION_TAG not in tags:
            record.tags.append("superseded-pattern")
            superseded += 1
            continue
        steps = record.context.get("tool_calls") or []
        stale_first_step = bool(steps) and \
            steps[0].get("tool") == "read_file"
        if stale_first_step and not (deliberate_recovery & set(tags)):
            record.tags.append("superseded-pattern")
            superseded += 1
    if superseded:
        store.save(records)
    return {"scanned": len(records), "superseded": superseded}


AGENT_AUTHORED_TAG = "agent-authored"

# S100: deliberate failed-edit-recovery beat (declared stale-memory
# miss + genuine corrective edit). Records carrying this tag teach
# recovery BY DESIGN, so the thrash-turn surgery in training.py
# keeps their failed turns instead of stripping them.
EDIT_RECOVERY_TAG = "edit-recovery"


def agent_authored_demos(python: str) -> List[Dict[str, Any]]:
    """S80: the first agent-authored batches — json synthesis drills
    (teaching the fixture-inference step: the diagnosis narrative
    walks the TEST FIXTURE, not just the expression) and cascade
    persistence demos (the double chain: hit the second failure,
    re-diagnose from scratch, name BOTH fixes). Authored by the
    session that ran ten generations; verified by the gate; validated
    by the quality bar.
    S82 batch 2 (same rungs, no rung 3+ per the anti-flaky gate):
    two more json drills — one two-level descent with a genuine
    wrong-turn read, one clean single-level — plus a second cascade
    on string_ops so the persistence lesson is not a single module.
    S91 batch 3 (rung-2 strengthening): three more double-chains on
    FRESH modules (math_ops, text_ops, list_ops — never calc_ops,
    which shares the eval task's module).
    S94 strings-repair batch (rung-1 holding): the authored batches
    added 5 json + 5 cascade drills and ZERO string drills while
    scripted string_reverse sits at volume 1 — strings is the
    thinnest volume in the modern corpus, and ep12/ep13 flicker it
    (0,3,0 / 1,0) while ep11 holds 3s. Three string drills on fresh
    modules with fixture-inference narratives (the test's expected
    value teaches the shape, as in the json drills), one with a
    genuine wrong-turn read.
    S100 failed-edit-recovery drills (the ep15 lesson): R1 replays
    ep15's exact strings failure prefix (whole-file rewrite breaking
    the sibling + stale-memory retry missing) then recovers from a
    fresh read; R2/R3 generalize the shape to fresh two-function
    modules. The stale miss rides recovery_anchors so the validator
    can demand it be genuine, consumed, and corrected.
    S101 wrong-value recovery drill (the ep16 indirect lesson): the
    first edit guesses a rate (1.4) instead of deriving it (36/30 =
    1.2 from the test's own expectation); the suite rejects the
    guess and the script re-derives before correcting. Fresh
    order/fees modules; all anchors match, so no declaration needed."""
    demos: List[Dict[str, Any]] = []

    # --- json synthesis drills (the 3B wall, taught directly) ---
    drills = [
        ("config_parser", ("settings",), "timeout", "30",
         "The config_parser lookup misses keys nested under settings. "
         "Find the bug from the failing test, fix it, and run the "
         "tests to verify they pass."),
        ("db_config", ("database", "pool"), "size", "8",
         "The database config lookup in this project returns nothing "
         "for pool size. Diagnose from the failing test and repair it."),
        ("auth_prefs", ("auth",), "session_minutes", "45",
         "A config lookup here misses keys nested under the auth "
         "section. Track down the defect and prove the fix."),
    ]
    for module, sections, key, leaf, goal in drills:
        path = f"{module}.py"
        test_path = f"test_{module}.py"
        module_code = "def lookup(data, key):\n    return data.get(key)\n"
        data_literal = '{{"{}": {}}}'.format(key, leaf)
        for section in reversed(sections):
            data_literal = '{{"{}": {}}}'.format(section, data_literal)
        test_code = (
            "import unittest\n\nfrom {} import lookup\n\n\n"
            "class TestLookup(unittest.TestCase):\n"
            "    def test_nested(self):\n"
            "        data = {}\n"
            '        self.assertEqual(lookup(data, "{}"), {})\n\n\n'
            'if __name__ == "__main__":\n    unittest.main()\n'.format(
                module, data_literal, key, leaf))
        broken = "    return data.get(key)\n"
        descent = "data" + "".join(
            '.get("{}", {{}})'.format(section) for section in sections)
        fixed = '    return {}.get(key)\n'.format(descent)
        # the fixture-inference narrative: the reasoning the 3B models
        # could not produce — WHERE the nesting comes from
        diagnosis = (
            "The failing test builds its own fixture: data = "
            f"{data_literal} — so the value for "
            f"'{key}' does not sit at the top level, it lives under "
            f"the {' -> '.join(sections)} section. The test is telling "
            f"me the shape of the data. Reading {path} confirmed the "
            f"lookup only checked the top level. The fix is to chain "
            f"the gets: {fixed.strip()} — each level with an empty-dict "
            f"default so a missing section cannot crash. Tests pass.")
        core = [_tests(python), _read(test_path), _read(path),
                _edit(path, broken, fixed), _tests(python)]
        script = [_list()] + core + [_final(diagnosis)]
        files = {path: module_code, test_path: test_code}
        demos.append({"script": script, "files": files, "goal": goal})

    # --- cascade persistence (rung 2: the chain runs twice) ---
    calc_module = ("def add(a, b):\n    return a - b\n\n\n"
                   "def multiply(a, b):\n    return a + b\n")
    calc_tests = (
        "import unittest\n\nfrom calc_ops import add, multiply\n\n\n"
        "class TestCalcOps(unittest.TestCase):\n"
        "    def test_add(self):\n"
        "        self.assertEqual(add(2, 3), 5)\n\n"
        "    def test_multiply(self):\n"
        "        self.assertEqual(multiply(3, 4), 12)\n\n\n"
        'if __name__ == "__main__":\n    unittest.main()\n')
    cascade_goal = ("The tests in this project are failing. There may "
                    "be more than one bug — keep diagnosing and fixing "
                    "until the whole suite passes.")
    cascade_diagnosis = (
        "First failure: test_add expected add(2, 3) to be 5 but add "
        "was subtracting — I fixed add to return a + b and reran. "
        "Second failure: the suite STILL failed, so there was more "
        "than one bug — test_multiply expected multiply(3, 4) to be 12 "
        "but multiply was adding. I re-read calc_ops.py, fixed "
        "multiply to return a * b, and reran: the whole suite passes. "
        "Two bugs, both fixed: add now sums and multiply now "
        "multiplies.")
    cascade_script = [
        _list(),
        _tests(python),
        _read("test_calc_ops.py"),
        _read("calc_ops.py"),
        _edit("calc_ops.py",
              "def add(a, b):\n    return a - b",
              "def add(a, b):\n    return a + b"),
        _tests(python),   # second failure: multiply still broken
        _read("calc_ops.py"),   # re-diagnose from scratch
        _edit("calc_ops.py",
              "def multiply(a, b):\n    return a + b",
              "def multiply(a, b):\n    return a * b"),
        _tests(python),
        _final(cascade_diagnosis),
    ]
    demos.append({"script": cascade_script,
                   "files": {"calc_ops.py": calc_module,
                             "test_calc_ops.py": calc_tests},
                   "goal": cascade_goal})

    # --- S82 batch 2: same rungs, more volume ---
    # json drill 4: two-level descent WITH a genuine wrong turn — the
    # first hypothesis (src/ layout) fails, the test fixture gives the
    # real shape. Recovery beat for the json rung set.
    module, sections, key, leaf = ("session_store", ("session", "user"),
                                   "name", '"ann"')
    path = f"{module}.py"
    test_path = f"test_{module}.py"
    module_code = "def lookup(data, key):\n    return data.get(key)\n"
    data_literal = '{{"{}": {}}}'.format(key, leaf)
    for section in reversed(sections):
        data_literal = '{{"{}": {}}}'.format(section, data_literal)
    test_code = (
        "import unittest\n\nfrom {} import lookup\n\n\n"
        "class TestLookup(unittest.TestCase):\n"
        "    def test_nested(self):\n"
        "        data = {}\n"
        '        self.assertEqual(lookup(data, "{}"), {})\n\n\n'
        'if __name__ == "__main__":\n    unittest.main()\n'.format(
            module, data_literal, key, leaf))
    broken = "    return data.get(key)\n"
    descent = "data" + "".join(
        '.get("{}", {{}})'.format(section) for section in sections)
    fixed = '    return {}.get(key)\n'.format(descent)
    diagnosis = (
        "My first guess was the src/ layout — reading "
        f"src/{path} failed, so that hypothesis was wrong. The failing "
        "test builds its own fixture: data = "
        f"{data_literal} — so the value for "
        f"'{key}' lives under "
        f"the {' -> '.join(sections)} sections, not at the top level. "
        f"Reading {test_path} gave the shape and reading {path} "
        "confirmed the lookup only checked the top level. The fix "
        f"chains the gets: {fixed.strip()} — each level with an "
        "empty-dict default so a missing section cannot crash. "
        "Tests pass.")
    script = [_list(), _read(f"src/{path}"), _tests(python),
              _read(test_path), _read(path),
              _edit(path, broken, fixed), _tests(python),
              _final(diagnosis)]
    files = {path: module_code, test_path: test_code}
    demos.append({
        "script": script, "files": files,
        "goal": ("The session_store lookup misses keys nested under the "
                 "session -> user sections. Find the bug from the failing "
                 "test, fix it, and run the tests to verify they pass.")})

    # json drill 5: clean single-level drill on a fresh module so the
    # synthesis pattern gets volume beyond the S80 three.
    module, sections, key, leaf = ("retry_policy", ("retry",),
                                   "max_attempts", "5")
    path = f"{module}.py"
    test_path = f"test_{module}.py"
    module_code = "def lookup(data, key):\n    return data.get(key)\n"
    data_literal = '{{"{}": {}}}'.format(key, leaf)
    for section in reversed(sections):
        data_literal = '{{"{}": {}}}'.format(section, data_literal)
    test_code = (
        "import unittest\n\nfrom {} import lookup\n\n\n"
        "class TestLookup(unittest.TestCase):\n"
        "    def test_nested(self):\n"
        "        data = {}\n"
        '        self.assertEqual(lookup(data, "{}"), {})\n\n\n'
        'if __name__ == "__main__":\n    unittest.main()\n'.format(
            module, data_literal, key, leaf))
    broken = "    return data.get(key)\n"
    descent = "data" + "".join(
        '.get("{}", {{}})'.format(section) for section in sections)
    fixed = '    return {}.get(key)\n'.format(descent)
    diagnosis = (
        "The failing test builds its own fixture: data = "
        f"{data_literal} — so the value for "
        f"'{key}' does not sit at the top level, it lives under "
        f"the {' -> '.join(sections)} section. The test is telling "
        f"me the shape of the data. Reading {path} confirmed the "
        f"lookup only checked the top level. The fix is to chain "
        f"the gets: {fixed.strip()} — each level with an empty-dict "
        f"default so a missing section cannot crash. Tests pass.")
    core = [_tests(python), _read(test_path), _read(path),
            _edit(path, broken, fixed), _tests(python)]
    script = [_list()] + core + [_final(diagnosis)]
    files = {path: module_code, test_path: test_code}
    demos.append({
        "script": script, "files": files,
        "goal": ("The retry_policy lookup misses keys nested under the "
                 "retry section. Diagnose from the failing test and "
                 "repair it.")})

    # cascade 2 (rung 2 on a second module): reverse + shout both
    # broken — the chain must run twice and the final names BOTH.
    str_module = ("def reverse(text):\n    return text\n\n\n"
                  "def shout(text):\n    return text.lower()\n")
    str_tests = (
        "import unittest\n\nfrom string_ops import reverse, shout\n\n\n"
        "class TestStringOps(unittest.TestCase):\n"
        "    def test_reverse(self):\n"
        '        self.assertEqual(reverse("abc"), "cba")\n\n'
        "    def test_shout(self):\n"
        '        self.assertEqual(shout("hey"), "HEY")\n\n\n'
        'if __name__ == "__main__":\n    unittest.main()\n')
    str_goal = ("The string_ops tests are failing on two functions. "
                "There may be more than one bug — keep diagnosing and "
                "fixing until the whole suite passes.")
    str_diagnosis = (
        "First failure: test_reverse expected reverse('abc') to be "
        "'cba' but reverse returned the text unchanged — I fixed "
        "reverse to return text[::-1] and reran. Second failure: the "
        "suite STILL failed, so there was more than one bug — "
        "test_shout expected shout('hey') to be 'HEY' but shout was "
        "lowercasing. I re-read string_ops.py, fixed shout to return "
        "text.upper(), and reran: the whole suite passes. Two bugs, "
        "both fixed: reverse now reverses and shout now shouts.")
    str_script = [
        _list(),
        _tests(python),
        _read("test_string_ops.py"),
        _read("string_ops.py"),
        _edit("string_ops.py",
              "def reverse(text):\n    return text",
              "def reverse(text):\n    return text[::-1]"),
        _tests(python),   # second failure: shout still broken
        _read("string_ops.py"),   # re-diagnose from scratch
        _edit("string_ops.py",
              "def shout(text):\n    return text.lower()",
              "def shout(text):\n    return text.upper()"),
        _tests(python),
        _final(str_diagnosis),
    ]
    demos.append({"script": str_script,
                  "files": {"string_ops.py": str_module,
                            "test_string_ops.py": str_tests},
                  "goal": str_goal})

    # --- S91 batch 3: rung-2 strengthening on FRESH modules (never
    # calc_ops — the S80 cascade shares the eval task's module, so it
    # may teach the instance more than the capability). Three new
    # double-chains, same discipline: chain → second failure →
    # re-diagnose from scratch → final names BOTH fixes.
    cascades = [
        ("math_ops",
         "def subtract(a, b):\n    return a + b\n\n\n"
         "def divide(a, b):\n    return a * b\n",
         "import unittest\n\n"
         "from math_ops import subtract, divide\n\n\n"
         "class TestMathOps(unittest.TestCase):\n"
         "    def test_subtract(self):\n"
         "        self.assertEqual(subtract(5, 3), 2)\n\n"
         "    def test_divide(self):\n"
         "        self.assertEqual(divide(8, 2), 4)\n\n\n"
         'if __name__ == "__main__":\n    unittest.main()\n',
         "def subtract(a, b):\n    return a + b",
         "def subtract(a, b):\n    return a - b",
         "def divide(a, b):\n    return a * b",
         "def divide(a, b):\n    return a / b",
         "The math_ops tests are failing on subtract and divide. "
         "There may be more than one bug — keep diagnosing and "
         "fixing until the whole suite passes.",
         "First failure: test_subtract expected subtract(5, 3) to be "
         "2 but subtract was adding — I fixed subtract to return "
         "a - b and reran. Second failure: the suite STILL failed, "
         "so there was more than one bug — test_divide expected "
         "divide(8, 2) to be 4 but divide was multiplying. I "
         "re-read math_ops.py, fixed divide to return a / b, and "
         "reran: the whole suite passes. Two bugs, both fixed: "
         "subtract now subtracts and divide now divides."),
        ("text_ops",
         "def concat(a, b):\n    return a\n\n\n"
         "def exclaim(text):\n    return text\n",
         "import unittest\n\n"
         "from text_ops import concat, exclaim\n\n\n"
         "class TestTextOps(unittest.TestCase):\n"
         "    def test_concat(self):\n"
         '        self.assertEqual(concat("foo", "bar"), "foobar")\n\n'
         "    def test_exclaim(self):\n"
         '        self.assertEqual(exclaim("hey"), "hey!")\n\n\n'
         'if __name__ == "__main__":\n    unittest.main()\n',
         "def concat(a, b):\n    return a",
         "def concat(a, b):\n    return a + b",
         "def exclaim(text):\n    return text",
         'def exclaim(text):\n    return text + "!"',
         "The text_ops tests are failing on concat and exclaim. "
         "There may be more than one bug — keep diagnosing and "
         "fixing until the whole suite passes.",
         "First failure: test_concat expected concat('foo', 'bar') "
         "to be 'foobar' but concat dropped the second half — I "
         "fixed concat to return a + b and reran. Second failure: "
         "the suite STILL failed, so there was more than one bug — "
         "test_exclaim expected exclaim('hey') to be 'hey!' but "
         "exclaim returned the text unchanged. I re-read "
         "text_ops.py, fixed exclaim to append '!', and reran: the "
         "whole suite passes. Two bugs, both fixed: concat now "
         "concatenates and exclaim now exclaims."),
        ("list_ops",
         "def first(items):\n    return items[-1]\n\n\n"
         "def total(items):\n    return len(items)\n",
         "import unittest\n\n"
         "from list_ops import first, total\n\n\n"
         "class TestListOps(unittest.TestCase):\n"
         "    def test_first(self):\n"
         "        self.assertEqual(first([1, 2, 3]), 1)\n\n"
         "    def test_total(self):\n"
         "        self.assertEqual(total([1, 2, 3]), 6)\n\n\n"
         'if __name__ == "__main__":\n    unittest.main()\n',
         "def first(items):\n    return items[-1]",
         "def first(items):\n    return items[0]",
         "def total(items):\n    return len(items)",
         "def total(items):\n    return sum(items)",
         "The list_ops tests are failing on first and total. "
         "There may be more than one bug — keep diagnosing and "
         "fixing until the whole suite passes.",
         "First failure: test_first expected first([1, 2, 3]) to be "
         "1 but first returned the last item — I fixed first to "
         "return items[0] and reran. Second failure: the suite "
         "STILL failed, so there was more than one bug — "
         "test_total expected total([1, 2, 3]) to be 6 but total "
         "was counting items instead of summing. I re-read "
         "list_ops.py, fixed total to return sum(items), and reran: "
         "the whole suite passes. Two bugs, both fixed: first now "
         "takes the first and total now totals."),
    ]
    for (module, module_code, test_code, old1, new1, old2, new2,
            goal, diagnosis) in cascades:
        test_path = f"test_{module}.py"
        path = f"{module}.py"
        script = [
            _list(),
            _tests(python),
            _read(test_path),
            _read(path),
            _edit(path, old1, new1),
            _tests(python),   # second failure still present
            _read(path),   # re-diagnose from scratch
            _edit(path, old2, new2),
            _tests(python),
            _final(diagnosis),
        ]
        demos.append({"script": script,
                      "files": {path: module_code,
                                test_path: test_code},
                      "goal": goal})
    # --- S94 strings-repair batch (rung-1 holding, fresh modules) ---
    string_drills = [
        # (module, fixture_test_body, broken_line, fixed_line,
        #  goal, diagnosis, recovery?)
        ("greeting",
         '        self.assertEqual(greet("Ann"), "Hello, Ann")\n',
         '    return "Hello"\n',
         '    return "Hello, " + name\n',
         "The greeting function drops the name. Find the bug from "
         "the failing test, fix it, and run the tests to verify "
         "they pass.",
         "The failing test builds its own fixture: it calls "
         'greet("Ann") and expects "Hello, Ann" — so the name must '
         "appear in the output after a comma. Reading "
         "test_greeting.py gave the shape and reading greeting.py "
         "confirmed the function returned a constant. The fix "
         'returns "Hello, " + name. Tests pass.',
         False),
        ("word_ops",
         '        self.assertEqual(join_words(["a", "b"]), "a b")\n',
         '    return "".join(words)\n',
         '    return " ".join(words)\n',
         "The word joiner mashes words together. Diagnose from the "
         "failing test and repair it.",
         "The failing test builds its own fixture: it joins "
         '["a", "b"] and expects "a b" — so the separator must be '
         "a space, not the empty string. Reading test_word_ops.py "
         "gave the shape and reading word_ops.py confirmed the "
         "empty join. The fix joins with \" \". Tests pass.",
         False),
        ("text_utils",
         '        self.assertEqual(strip_punct("hey!"), "hey")\n',
         "    return text\n",
         '    return text.rstrip("!")\n',
         "The punctuation stripper returns text unchanged. Track "
         "down the defect and prove the fix.",
         "My first guess was the src/ layout — reading "
         "src/text_utils.py failed, so that hypothesis was wrong. "
         "The failing test builds its own fixture: it passes "
         '"hey!" and expects "hey" — so a trailing bang must go. '
         "Reading test_text_utils.py gave the shape and reading "
         "text_utils.py confirmed the function returned its input "
         "untouched. The fix strips trailing bangs with "
         'rstrip("!"). Tests pass.',
         True),
    ]
    for (module, test_body, broken, fixed,
            goal, diagnosis, recovery) in string_drills:
        path = f"{module}.py"
        test_path = f"test_{module}.py"
        func = {"greeting": "greet", "word_ops": "join_words",
                "text_utils": "strip_punct"}[module]
        module_code = (f"def {func}({('name' if module == 'greeting' else 'words' if module == 'word_ops' else 'text')}):\n"
                       f"{broken}")
        test_code = (
            "import unittest\n\nfrom {} import {}\n\n\n"
            "class TestStringDrill(unittest.TestCase):\n"
            "    def test_shape(self):\n"
            "{}\n\n"
            'if __name__ == "__main__":\n    unittest.main()\n'.format(
                module, func, test_body))
        core = [_tests(python), _read(test_path), _read(path),
                _edit(path, broken, fixed), _tests(python)]
        if recovery:
            script = ([_list(), _read(f"src/{path}")] + core
                      + [_final(diagnosis)])
        else:
            script = [_list()] + core + [_final(diagnosis)]
        files = {path: module_code, test_path: test_code}
        demos.append({"script": script, "files": files, "goal": goal})

    # --- S100 failed-edit-recovery drills (the ep15 strings lesson) ---
    # New shape: the script BREAKS a working sibling with a
    # whole-file rewrite, the stale-memory retry genuinely fails
    # (old_string not found — the exact ep15 failure, replayed with
    # its real args in R1), then re-reads and lands a minimal
    # corrective anchor from the FRESH observation. The stale miss is
    # declared in recovery_anchors so the validator can demand it be
    # genuine, consumed, and corrected. R1 replays ep15's saved
    # trajectory (on-policy error states); R2/R3 generalize the shape
    # to fresh two-function modules.
    recovery_drills = [
        {
            "module": "string_utils",
            "test_module": "test_string_utils",
            "module_code":
                'def reverse(text):\n    return text\n\n\n'
                'def shout(text):\n    return text.upper() + "!"\n',
            "test_code":
                "import unittest\n\n"
                "from string_utils import reverse, shout\n\n\n"
                "class TestRecovery(unittest.TestCase):\n"
                "    def test_reverse(self):\n"
                '        self.assertEqual(reverse("abc"), "cba")\n\n'
                "    def test_shout(self):\n"
                '        self.assertEqual(shout("hey"), "HEY!")\n\n\n'
                'if __name__ == "__main__":\n    unittest.main()\n',
            # ep15's real step-6 args: whole-file rewrite fixing
            # reverse while dropping the shout bang
            "fumble_old":
                'def reverse(text):\n    return text\n\n\n'
                'def shout(text):\n    return text.upper() + "!"',
            "fumble_new":
                'def reverse(text):\n    return text[::-1]\n\n\n'
                'def shout(text):\n    return text.upper()',
            # ep15's real step-8 args: stale-memory retry, misses
            "stale_old":
                'def shout(text):\n    return text.upper() + "!"',
            "stale_new":
                'def shout(text):\n    return text.upper()',
            # the correction, anchored on the FRESH file content
            "fix_old": '    return text.upper()\n',
            "fix_new": '    return text.upper() + "!"\n',
            "goal":
                "The string_utils repair broke its sibling: reverse "
                "is fixed but shout lost its bang in a whole-file "
                "rewrite. Re-anchor from the fresh file content and "
                "finish the repair.",
            "diagnosis":
                "My first edit fixed reverse in string_utils.py but "
                "rewrote the file from memory and dropped the bang "
                "from shout — test_string_utils.py caught it. My "
                "retry anchored on the file I remembered instead of "
                "the file I made, so old_string was not found. "
                "Re-reading string_utils.py showed shout returning "
                "text.upper() with no bang; anchoring that fresh "
                "line and restoring the bang passed the suite. "
                "Anchor on what you just read, not what you "
                "remember.",
        },
        {
            "module": "whisper",
            "test_module": "test_whisper",
            "module_code":
                'def whisper(text):\n    return text\n\n\n'
                'def exclaim(text):\n    return text + "!"\n',
            "test_code":
                "import unittest\n\n"
                "from whisper import whisper, exclaim\n\n\n"
                "class TestRecovery(unittest.TestCase):\n"
                "    def test_whisper(self):\n"
                '        self.assertEqual(whisper("HEY"), "hey")\n\n'
                "    def test_exclaim(self):\n"
                '        self.assertEqual(exclaim("hey"), "hey!")\n\n\n'
                'if __name__ == "__main__":\n    unittest.main()\n',
            "fumble_old":
                'def whisper(text):\n    return text\n\n\n'
                'def exclaim(text):\n    return text + "!"',
            "fumble_new":
                'def whisper(text):\n    return text.lower()\n\n\n'
                'def exclaim(text):\n    return text',
            "stale_old":
                'def exclaim(text):\n    return text + "!"',
            "stale_new":
                'def exclaim(text):\n    return text',
            "fix_old":
                'def exclaim(text):\n    return text',
            "fix_new":
                'def exclaim(text):\n    return text + "!"',
            "goal":
                "The whisper repair dropped exclaim's bang the same "
                "way: a stale-memory retry failed, so re-read "
                "whisper.py and land the fix from what the file "
                "actually says.",
            "diagnosis":
                "My first edit fixed whisper in whisper.py but "
                "rewrote the file from memory and dropped the bang "
                "from exclaim — test_whisper.py caught it. My retry "
                "anchored on the remembered file, so old_string was "
                "not found. Re-reading whisper.py showed exclaim "
                "returning bare text; anchoring the fresh def lines "
                "and restoring the bang passed the suite. Anchor on "
                "what you just read, not what you remember.",
        },
        {
            "module": "label",
            "test_module": "test_label",
            "module_code":
                'def shouty(text):\n    return text\n\n\n'
                'def quiet(text):\n    return text.lower()\n',
            "test_code":
                "import unittest\n\n"
                "from label import shouty, quiet\n\n\n"
                "class TestRecovery(unittest.TestCase):\n"
                "    def test_shouty(self):\n"
                '        self.assertEqual(shouty("hey"), "HEY")\n\n'
                "    def test_quiet(self):\n"
                '        self.assertEqual(quiet("HEY"), "hey")\n\n\n'
                'if __name__ == "__main__":\n    unittest.main()\n',
            "fumble_old":
                'def shouty(text):\n    return text\n\n\n'
                'def quiet(text):\n    return text.lower()',
            "fumble_new":
                'def shouty(text):\n    return text.upper()\n\n\n'
                'def quiet(text):\n    return text',
            "stale_old":
                'def quiet(text):\n    return text.lower()',
            "stale_new":
                'def quiet(text):\n    return text',
            "fix_old": '    return text\n',
            "fix_new": '    return text.lower()\n',
            "goal":
                "A whole-file rewrite fixed shouty but mangled quiet "
                "in label.py, and the stale retry missed. Diagnose "
                "from the failing test, re-read, and correct from "
                "fresh observation.",
            "diagnosis":
                "My first edit fixed shouty in label.py but rewrote "
                "the file from memory and dropped the lowering from "
                "quiet — test_label.py caught it. My retry anchored "
                "on the remembered file, so old_string was not "
                "found. Re-reading label.py showed quiet returning "
                "bare text; anchoring that fresh line and restoring "
                "the lowering passed the suite. Anchor on what you "
                "just read, not what you remember.",
        },
    ]
    for drill in recovery_drills:
        path = f"{drill['module']}.py"
        test_path = f"{drill['test_module']}.py"
        script = [_list(), _tests(python), _read(test_path),
                  _read(path),
                  _edit(path, drill["fumble_old"], drill["fumble_new"]),
                  _tests(python),   # sibling broken: suite still fails
                  _edit(path, drill["stale_old"], drill["stale_new"]),
                  _read(path),   # re-anchor from FRESH observation
                  _edit(path, drill["fix_old"], drill["fix_new"]),
                  _tests(python),
                  _final(drill["diagnosis"])]
        demos.append({"script": script,
                      "files": {path: drill["module_code"],
                                test_path: drill["test_code"]},
                      "goal": drill["goal"],
                      "recovery_anchors": [drill["stale_old"]]})

    # --- S101 wrong-value recovery drill (the ep16 indirect lesson) ---
    # Same recovery shape as R1–R3, new instance: the first edit
    # GUESSES a value (1.4) instead of deriving it, the suite rejects
    # it, and the script re-derives the rate from the test's own
    # expectation (36 from [10, 20]: 10 + 20 = 30, 36 / 30 = 1.2)
    # before landing the corrective edit. All anchors match — no
    # recovery_anchors declaration needed (nothing goes stale; the
    # defect is arithmetic, not anchoring). Fresh modules, never
    # taxcalc/cart (S91) nor invoice/prices/checkout/register/
    # basket/discount (S95).
    order_files = {
        "fees.py": "def with_fee(amount):\n    return amount * 1.5\n",
        "order.py": "from fees import with_fee\n\n\n"
                    "def bill(items):\n"
                    "    return sum(with_fee(p) for p in items)\n",
        "test_order.py":
            "import unittest\n\nfrom order import bill\n\n\n"
            "class TestOrder(unittest.TestCase):\n"
            "    def test_bill(self):\n"
            "        self.assertEqual(bill([10, 20]), 36)\n\n\n"
            'if __name__ == "__main__":\n    unittest.main()\n',
    }
    order_script = [
        _list(),
        _tests(python),
        _read("test_order.py"),
        _read("order.py"),
        _read("fees.py"),
        _edit("fees.py",
              "    return amount * 1.5\n",
              "    return amount * 1.4\n"),
        _tests(python),   # guessed rate rejected: suite still fails
        _read("test_order.py"),   # re-derive from the expectation
        _edit("fees.py",
              "    return amount * 1.4\n",
              "    return amount * 1.2\n"),
        _tests(python),
        _final("The bill test covers order.py, but order.py only "
               "sums with_fee over the items — following the import "
               "led to fees.py, where the rate was 1.5. My first "
               "edit guessed 1.4 and the suite rejected it. "
               "Re-reading test_order.py gave the derivation: the "
               "test expects 36 from [10, 20], 10 + 20 is 30, and "
               "36 / 30 is 1.2. Anchoring the guessed line and "
               "setting the derived rate passed the suite. Derive "
               "the value from the test's expectation — never guess "
               "it."),
    ]
    demos.append({"script": order_script, "files": order_files,
                  "goal": "The order totals guess the fee rate wrong: "
                          "bill applies 1.4 but the test expects 36. "
                          "Derive the rate from the test expectation "
                          "and correct it in the source module."})

    # --- S95 rung-3 demos (gate OPEN: 3 pinned cascade points) ---
    # Import-following via PLAIN READS (code_imports/code_references
    # are NOT in the lean benchmark catalog, and demos must use only
    # tools the model is offered at inference — the S72 catalog
    # lesson). Fresh modules, never taxcalc/cart (S91 eval-module
    # lesson): failing test → read B (sees the import) → read A →
    # fix A → rerun → final walks the import chain.
    indirects = [
        # (b_mod, a_mod, full A module, A old anchor, A new anchor,
        #  full B module, test file, goal, diagnosis, recovery?)
        ("invoice", "prices",
         "def with_tax(amount):\n    return amount * 1.5\n",
         "    return amount * 1.5\n",
         "    return amount * 1.2\n",
         "from prices import with_tax\n\n\n"
         "def bill(items):\n"
         "    return sum(with_tax(p) for p in items)\n",
         "import unittest\n\nfrom invoice import bill\n\n\n"
         "class TestInvoice(unittest.TestCase):\n"
         "    def test_bill(self):\n"
         "        self.assertEqual(bill([10, 20]), 36)\n\n\n"
         'if __name__ == "__main__":\n    unittest.main()\n',
         "The invoice totals are wrong but the invoice code looks "
         "clean. Follow the import to the source module, fix it "
         "there, and run the tests to verify they pass.",
         "The failing test covers bill in invoice.py, but reading "
         "invoice.py showed it only sums with_tax over the items — "
         "the arithmetic lives elsewhere. Following the import led "
         "to prices.py, where with_tax multiplied by 1.5 instead "
         "of 1.2. I fixed prices.py and the suite passes: the bug "
         "was across the import boundary, not where the test "
         "pointed.",
         False),
        ("checkout", "rates",
         "def discount(price):\n    return price * 0.95\n",
         "    return price * 0.95\n",
         "    return price * 0.8\n",
         "from rates import discount\n\n\n"
         "def checkout(cart):\n"
         "    return sum(discount(p) for p in cart)\n",
         "import unittest\n\nfrom checkout import checkout\n\n\n"
         "class TestCheckout(unittest.TestCase):\n"
         "    def test_checkout(self):\n"
         "        self.assertEqual(checkout([100, 50]), 120)\n\n\n"
         'if __name__ == "__main__":\n    unittest.main()\n',
         "The checkout totals are off though the checkout code is "
         "correct. Trace the dependency to its origin, repair it, "
         "and prove the suite green.",
         "The failing test covers checkout in checkout.py, but "
         "reading checkout.py showed a clean pass-through over "
         "discount. Tracing the dependency to rates.py revealed "
         "discount shaving only 5% instead of 20%. I fixed "
         "rates.py and the suite passes: read the importer, then "
         "read what it imports.",
         False),
        ("basket", "fees",
         "def add_fee(x):\n    return x + 10\n",
         "    return x + 10\n",
         "    return x + 2\n",
         "from fees import add_fee\n\n\n"
         "def checkout(items):\n"
         "    return sum(add_fee(p) for p in items)\n",
         "import unittest\n\nfrom basket import checkout\n\n\n"
         "class TestBasket(unittest.TestCase):\n"
         "    def test_checkout(self):\n"
         "        self.assertEqual(checkout([5, 5]), 14)\n\n\n"
         'if __name__ == "__main__":\n    unittest.main()\n',
         "The basket checkout overcharges while the basket module "
         "reads clean. Diagnose across the import boundary and "
         "verify the fix.",
         "My first guess was the src/ layout — reading "
         "src/basket.py failed, so that hypothesis was wrong. The "
         "failing test covers checkout in basket.py, which read "
         "clean — a correct-looking importer with a wrong total "
         "means the defect is upstream. Following the import to "
         "fees.py showed add_fee adding 10 instead of 2. I fixed "
         "fees.py and the suite passes.",
         True),
    ]
    for (b_mod, a_mod, a_code, old, new,
            b_code, test_code, goal, diagnosis,
            recovery) in indirects:
        b_path = f"{b_mod}.py"
        a_path = f"{a_mod}.py"
        test_path = f"test_{b_mod}.py"
        core = [_tests(python), _read(test_path), _read(b_path),
                _read(a_path),
                _edit(a_path, old, new),
                _tests(python)]
        if recovery:
            script = ([_list(), _read(f"src/{b_path}")] + core
                      + [_final(diagnosis)])
        else:
            script = [_list()] + core + [_final(diagnosis)]
        files = {a_path: a_code, b_path: b_code,
                 test_path: test_code}
        demos.append({"script": script, "files": files, "goal": goal})

    # --- S104 cascade re-anchor drills (the gen-17 forensics) ---
    # W1: the schema-error loop — one deliberate code_diagnostics call
    # with an invented argument is rejected and the script falls back
    # to read_file (teach: an invalid-args error means switch to
    # reading, never retry the same call). W2: the self-ambiguating
    # fixture — fixing defect 1 creates a second copy of defect 2's
    # body line, the naive anchor matches 2x and edit_file rejects it,
    # and the corrective edit re-anchors on the def line from a FRESH
    # read. The ambiguous anchor rides ambiguous_anchors so the
    # validator can demand the collision be genuine (>= 2) and
    # consumed. Fresh modules: never calc_ops (S91/S95) nor the
    # S100/S101 fixtures.
    reanchor_drills = [
        {
            "module": "metrics",
            "module_code":
                'def total(a, b):\n    return a - b\n\n\n'
                'def difference(a, b):\n    return a + b\n',
            "test_code":
                "import unittest\n\n"
                "from metrics import total, difference\n\n\n"
                "class TestMetrics(unittest.TestCase):\n"
                "    def test_total(self):\n"
                "        self.assertEqual(total(2, 3), 5)\n\n"
                "    def test_difference(self):\n"
                "        self.assertEqual(difference(5, 2), 3)\n\n\n"
                'if __name__ == "__main__":\n    unittest.main()\n',
            "fix1_old": '    return a - b',
            "fix1_new": '    return a + b',
            "amb_old": '    return a + b',
            "amb_new": '    return a - b',
            "wide_old": 'def difference(a, b):\n    return a + b',
            "wide_new": 'def difference(a, b):\n    return a - b',
            "goal":
                "The metrics suite fails twice and fixing total makes "
                "difference's edit anchor match twice: when edit_file "
                "rejects the anchor in metrics.py, re-read and "
                "re-anchor with the def line.",
            "diagnosis":
                "test_metrics.py failed on both total and difference "
                "in metrics.py. A code_diagnostics call with a path "
                "argument was rejected as invalid — the tool takes no "
                "arguments — so I read the module instead. Fixing "
                "total to return a + b landed, but the same-shaped "
                "anchor for difference then matched twice and "
                "edit_file refused it. Re-reading metrics.py showed "
                "the collision: total now equals difference's broken "
                "line. Anchoring on the def difference line made the "
                "edit unique and the suite passes. When an anchor "
                "matches twice, widen it with context instead of "
                "retrying.",
        },
        {
            "module": "scale",
            "module_code":
                'def grow(n):\n    return n - 1\n\n\n'
                'def shrink(n):\n    return n + 1\n',
            "test_code":
                "import unittest\n\n"
                "from scale import grow, shrink\n\n\n"
                "class TestScale(unittest.TestCase):\n"
                "    def test_grow(self):\n"
                "        self.assertEqual(grow(5), 6)\n\n"
                "    def test_shrink(self):\n"
                "        self.assertEqual(shrink(5), 4)\n\n\n"
                'if __name__ == "__main__":\n    unittest.main()\n',
            "fix1_old": '    return n - 1',
            "fix1_new": '    return n + 1',
            "amb_old": '    return n + 1',
            "amb_new": '    return n - 1',
            "wide_old": 'def shrink(n):\n    return n + 1',
            "wide_new": 'def shrink(n):\n    return n - 1',
            "goal":
                "The scale tests fail on both functions and the first "
                "fix in scale.py makes the second anchor ambiguous: "
                "on the matches-twice rejection, re-read and widen "
                "the anchor with the def line.",
            "diagnosis":
                "test_scale.py failed on grow and shrink in scale.py. "
                "code_diagnostics rejects arguments, so I read the "
                "module directly. Fixing grow landed, but shrink's "
                "anchor return n + 1 then matched twice — grow's fix "
                "created the collision — and edit_file rejected it. "
                "Re-reading scale.py and anchoring on the def shrink "
                "line made the edit unique and both tests pass. A "
                "matches-twice rejection means widen the anchor, not "
                "retry it.",
        },
    ]
    for drill in reanchor_drills:
        path = f"{drill['module']}.py"
        test_path = f"test_{drill['module']}.py"
        script = [
            _list(),
            _tests(python),
            # S104/W1: the schema-fallback beat — an invented argument
            # is honestly rejected; the script reads instead of
            # retrying the call
            ToolCall(name="code_diagnostics",
                     arguments={"path": path}),
            _read(test_path),
            _read(path),
            _edit(path, drill["fix1_old"], drill["fix1_new"]),
            _tests(python),
            # S104/W2: the ambiguous anchor is genuinely rejected at
            # runtime (matches 2x after fix 1)
            _edit(path, drill["amb_old"], drill["amb_new"]),
            _read(path),   # re-anchor from FRESH observation
            _edit(path, drill["wide_old"], drill["wide_new"]),
            _tests(python),
            _final(drill["diagnosis"]),
        ]
        demos.append({"script": script,
                      "files": {path: drill["module_code"],
                                test_path: drill["test_code"]},
                      "goal": drill["goal"],
                      "ambiguous_anchors": [drill["amb_old"]]})

    # --- S107 drill persistence (the gen-19 forensics) ---
    # The gen-19 double reading named three shapes: S1 the chain-2
    # catalog-tool loop (after the first fix lands, the model loops on
    # rejected code_diagnostics / experience_record calls instead of
    # editing); S2 the fabricated anchor (the indirect edit anchor is
    # invented from memory, rejected as not-found, and the model
    # re-reads the file WITHOUT copying the actual line); S3 the beats
    # are one-shot (the S104 drills demonstrate them only in chain 1).
    # The fix: drills whose SECOND chain carries the same beats —
    # invalid-codeintel-call -> honest rejection -> READ instead —
    # plus a fabricated-anchor indirect drill whose corrective edit
    # copies the line the fresh read actually showed.
    # metrics/scale reuse their proven S104 fixtures with NEW goals
    # (the lesson is new); budget and parcel/shipcalc are fresh
    # modules (S95: never the eval fixtures).
    persist_drills = [
        {
            "module": "metrics",
            "module_code":
                'def total(a, b):\n    return a - b\n\n\n'
                'def difference(a, b):\n    return a + b\n',
            "test_code":
                "import unittest\n\n"
                "from metrics import total, difference\n\n\n"
                "class TestMetrics(unittest.TestCase):\n"
                "    def test_total(self):\n"
                "        self.assertEqual(total(2, 3), 5)\n\n"
                "    def test_difference(self):\n"
                "        self.assertEqual(difference(5, 2), 3)\n\n\n"
                'if __name__ == "__main__":\n    unittest.main()\n',
            "fix1_old": '    return a - b',
            "fix1_new": '    return a + b',
            "amb_old": '    return a + b',
            "amb_new": '    return a - b',
            "wide_old": 'def difference(a, b):\n    return a + b',
            "wide_new": 'def difference(a, b):\n    return a - b',
            "goal":
                "The metrics suite fails twice, and BOTH diagnosis "
                "chains start with a tool call that gets rejected: "
                "read metrics.py instead, fix total, then fix "
                "difference by widening its matches-twice anchor with "
                "the def line.",
            "diagnosis":
                "Both chains of metrics.py taught me the same rule. "
                "Chain one: a code_diagnostics call with a path "
                "argument was rejected as invalid, so I read the "
                "module and fixed total. Chain two: after the suite "
                "still failed I tried code_diagnostics AGAIN and it "
                "was rejected again — the rule from chain one still "
                "held, so I read instead. difference's naive anchor "
                "then matched twice (my own total fix created the "
                "collision), and widening with the def difference "
                "line landed it. After any fix, diagnose by reading, "
                "in every chain.",
        },
        {
            "module": "scale",
            "module_code":
                'def grow(n):\n    return n - 1\n\n\n'
                'def shrink(n):\n    return n + 1\n',
            "test_code":
                "import unittest\n\n"
                "from scale import grow, shrink\n\n\n"
                "class TestScale(unittest.TestCase):\n"
                "    def test_grow(self):\n"
                "        self.assertEqual(grow(5), 6)\n\n"
                "    def test_shrink(self):\n"
                "        self.assertEqual(shrink(5), 4)\n\n\n"
                'if __name__ == "__main__":\n    unittest.main()\n',
            "fix1_old": '    return n - 1',
            "fix1_new": '    return n + 1',
            "amb_old": '    return n + 1',
            "amb_new": '    return n - 1',
            "wide_old": 'def shrink(n):\n    return n + 1',
            "wide_new": 'def shrink(n):\n    return n - 1',
            "goal":
                "The scale tests fail on both functions and each "
                "diagnosis chain opens with a rejected tool call: "
                "read scale.py in chain one and again in chain two, "
                "fix grow, then widen shrink's matches-twice anchor "
                "with the def line.",
            "diagnosis":
                "scale.py needed the read-first rule TWICE. Chain "
                "one: code_diagnostics rejects arguments, so I read "
                "the module and fixed grow. Chain two: the suite "
                "still failed and code_diagnostics was rejected "
                "again — same rule, read again. shrink's anchor then "
                "matched twice because grow's fix created the "
                "collision; anchoring on the def shrink line made "
                "the edit unique. The chain-one rules do not expire "
                "in chain two.",
        },
        {
            "module": "budget",
            "module_code":
                'def spend(a, b):\n    return a + b\n\n\n'
                'def save(a, b):\n    return a - b\n',
            "test_code":
                "import unittest\n\n"
                "from budget import spend, save\n\n\n"
                "class TestBudget(unittest.TestCase):\n"
                "    def test_spend(self):\n"
                "        self.assertEqual(spend(10, 3), 7)\n\n"
                "    def test_save(self):\n"
                "        self.assertEqual(save(10, 5), 15)\n\n\n"
                'if __name__ == "__main__":\n    unittest.main()\n',
            "fix1_old": '    return a + b',
            "fix1_new": '    return a - b',
            "amb_old": '    return a - b',
            "amb_new": '    return a + b',
            "wide_old": 'def save(a, b):\n    return a - b',
            "wide_new": 'def save(a, b):\n    return a + b',
            "goal":
                "The budget tests fail on spend and save, and both "
                "diagnosis chains begin with a tool call that is "
                "rejected: read budget.py each time, fix spend, then "
                "widen save's matches-twice anchor with the def line.",
            "diagnosis":
                "budget.py ran the read-first rule in both chains. "
                "Chain one: the diagnostic tool rejected my path "
                "argument, so I read the module and fixed spend. "
                "Chain two: code_diagnostics was rejected again — "
                "the rule carries over — so I read budget.py again. "
                "save's anchor then matched twice (my spend fix "
                "created the collision) and the def save line made "
                "the widened edit unique. Read in every chain; the "
                "rule never expires.",
        },
    ]
    for drill in persist_drills:
        path = f"{drill['module']}.py"
        test_path = f"test_{drill['module']}.py"
        script = [
            _list(),
            _tests(python),
            # chain-1 schema-fallback beat
            ToolCall(name="code_diagnostics",
                     arguments={"path": path}),
            _read(test_path),
            _read(path),
            _edit(path, drill["fix1_old"], drill["fix1_new"]),
            _tests(python),
            # S107/S1: the chain-2 beat — the SAME rejected-call-then-
            # read shape, exactly where the live model loops instead
            ToolCall(name="code_diagnostics",
                     arguments={"path": path}),
            _read(path),
            # S104/W2: the ambiguous anchor is genuinely rejected
            _edit(path, drill["amb_old"], drill["amb_new"]),
            _read(path),
            _edit(path, drill["wide_old"], drill["wide_new"]),
            _tests(python),
            _final(drill["diagnosis"]),
        ]
        demos.append({"script": script,
                      "files": {path: drill["module_code"],
                                test_path: drill["test_code"]},
                      "goal": drill["goal"],
                      "ambiguous_anchors": [drill["amb_old"]]})

    # S107/S2: the fabricated-anchor indirect drill — the first edit
    # anchor is REMEMBERED, not read (matches 0 times; the S100
    # recovery_anchors mechanism demands the miss be genuine and
    # corrected), and the corrective edit copies the line the fresh
    # read actually showed. Fresh pair, never taxcalc/cart nor the
    # S95 modules.
    ship_code = "def with_rate(amount):\n    return amount * 5\n"
    parcel_code = ("from shipcalc import with_rate\n\n\n"
                   "def parcel_price(weight):\n"
                   "    return with_rate(weight)\n")
    parcel_test = (
        "import unittest\n\nfrom parcel import parcel_price\n\n\n"
        "class TestParcel(unittest.TestCase):\n"
        "    def test_price(self):\n"
        "        self.assertEqual(parcel_price(50), 60)\n\n\n"
        'if __name__ == "__main__":\n    unittest.main()\n')
    demos.append({
        "script": [
            _list(),
            _tests(python),
            _read("test_parcel.py"),
            _read("parcel.py"),
            _read("shipcalc.py"),
            # S2: the fabricated anchor — remembered from a guess,
            # never in the file; genuinely rejected at runtime
            _edit("shipcalc.py", "    return amount * 3",
                  "    return amount * 1.2"),
            _read("shipcalc.py"),   # fresh observation
            # the corrective edit copies the ACTUAL line just read
            _edit("shipcalc.py", "    return amount * 5",
                  "    return amount * 1.2"),
            _tests(python),
            _final(
                "The failing test covered parcel_price in parcel.py, "
                "but reading it showed a clean pass-through over "
                "with_rate — the arithmetic lives in shipcalc.py. My "
                "first edit anchored on a remembered multiplier that "
                "was never in the file, and the rejection said as "
                "much. Re-reading shipcalc.py showed with_rate "
                "returning amount * 5; copying THAT line as the "
                "anchor and setting the rate to 1.2 passed the "
                "suite. Anchor on what the file says, never on what "
                "you remember."),
        ],
        "files": {"shipcalc.py": ship_code,
                  "parcel.py": parcel_code,
                  "test_parcel.py": parcel_test},
        "goal":
            "The parcel price is wrong but parcel.py reads clean: "
            "follow the import to shipcalc.py, and when your first "
            "edit anchor is not found, copy the actual line from the "
            "fresh read instead of retrying the remembered one.",
        "recovery_anchors": ["    return amount * 3"],
    })

    # --- S108 rung-7 explore-qa drills (the 0/6 zero-shot wall) ---
    # The live forensics (S102.4) and the 0/6 baseline agree on the
    # failure: the model guesses entry paths while the listing sits
    # unread. The rule the drills teach: THE LISTING IS THE MAP — read
    # it, open what it names, never guess a path that is not on it.
    # Per the S107 discipline the beats repeat: when a doc does not
    # answer, the demonstrator RETURNS TO THE LISTING instead of
    # guessing. Answer-QA demos declare fact_gate and run under the
    # containment verifier (no tests exist; the loop only COMPLETEDs
    # when the final answer carries the planted facts).
    server_files = {
        "README.md":
            "# serverctl\n\nA small service for local projects. "
            "Configuration lives in code; see the docs folder for "
            "operational details.\n",
        "docs/api.md":
            "# API\n\nThe client talks to the server over HTTP. "
            "Endpoints are versioned; see the changelog for details."
            "\n",
        "docs/running.md":
            "# Running\n\nStart the dashboard server from the repo "
            "root:\n\n    python -m serverctl --port 8765\n\nThe "
            "port is fixed; tools that scan for it assume 8765.\n",
    }
    demos.append({
        "script": [
            _list(),
            _read("README.md"),
            _read("docs/api.md"),
            # the persistence beat: two docs, no answer — return to
            # the map instead of guessing entry paths
            _list(),
            _read("docs/running.md"),
            _final(
                "docs/running.md answers it: start the server from "
                "the repo root with python -m serverctl --port 8765. "
                "I read README.md and docs/api.md first and neither "
                "answered, so I went back to the directory listing "
                "and opened the one doc I had not read instead of "
                "guessing entry files."),
        ],
        "files": server_files,
        "goal":
            "How do you start this project's server? The answer is "
            "in the docs somewhere — read the listing, open the docs "
            "until one answers, and tell me the exact command.",
        "fact_gate": ["python -m serverctl", "8765"],
    })

    config_files = {
        "README.md":
            "# toolsvc\n\nA tiny utility service. Behavior is "
            "configured in code; the docs folder covers the details."
            "\n",
        "docs/configuration.md":
            "# Configuration\n\nrequest_timeout = 45\n"
            "max_retries = 3\n\nBoth values are fixed defaults; the "
            "service reads them at startup.\n",
    }
    demos.append({
        "script": [
            _list(),
            _read("README.md"),
            # the persistence beat again: the README points at the
            # docs folder, so back to the listing, then read what is
            # there
            _list(),
            _read("docs/configuration.md"),
            _final(
                "docs/configuration.md has both values: "
                "request_timeout = 45 and max_retries = 3. The "
                "README only pointed at the docs folder, so I listed "
                "it and read the configuration doc directly — the "
                "answer came from the file, not a guess."),
        ],
        "files": config_files,
        "goal":
            "What are this tool's default request timeout and retry "
            "count? Check the docs folder and tell me the exact "
            "values.",
        "fact_gate": ["request_timeout = 45", "max_retries = 3"],
    })

    testing_files = {
        "README.md":
            "# checkmate\n\nA linter for tiny repos. See the docs "
            "folder for how we run things.\n",
        "docs/testing.md":
            "# Testing\n\nCI runs the suite with branch coverage:\n\n"
            "    python -m coverage run -m unittest --branch\n\nThe "
            "branch flag is required; plain runs miss branches.\n",
    }
    # S110: the S108 recovery drill (opening guessed read) is removed
    # from the lane and its record superseded by
    # supersede_opening_guess_demos — gen-22 imitated the demonstrated
    # opening guess (guessed_path 0.4444 vs ep21's 0.0). Its
    # replacement (testing-v3) corrects the wandering MID-CHAIN, and
    # five new answer drills raise the read-then-ANSWER-immediately
    # share (the gen-22 run_tests ritual: a no-test question never
    # needs the suite).

    # --- S110 testing-v3: both wandering shapes corrected MID-CHAIN
    # (after a productive pattern is established), answer immediate
    demos.append({
        "script": [
            _list(),
            _read("README.md"),
            # the seam beat (S109, proven in gen-22: the doc gets read)
            ToolCall(name="code_references",
                     arguments={"symbol": "main"}),
            _list(),
            # a mid-chain wrong-turn read — AFTER the productive
            # pattern, corrected by the map (the S100 shape that
            # works; never as an opening move)
            _read("checkmate.py"),
            _read("docs/testing.md"),
            _final(
                "docs/testing.md answers it: the suite runs with "
                "branch coverage via python -m coverage run -m "
                "unittest --branch. Two detours on the way — a symbol "
                "hunt was rejected and a guessed module read failed — "
                "and both were the same mistake after the README "
                "pointed me at the docs: hunting instead of reading. "
                "No test run was needed; the question is answered by "
                "the doc itself."),
        ],
        "files": testing_files,
        "goal":
            "How does this project run its test suite with coverage? "
            "The docs folder carries the command — find it, and "
            "remember a question needs no test run, only the answer.",
        "fact_gate": ["coverage run -m unittest", "--branch"],
    })

    # --- S110 answer-QA volume: five fresh read-then-ANSWER drills,
    # no run_tests anywhere, beats varied, no opening guessed reads
    license_files = {
        "README.md":
            "# tinyhook\n\nA minimal webhook relay. Project details "
            "live in the docs folder.\n",
        "docs/license.md":
            "# License\n\ntinyhook is released under the MIT license, "
            "copyright 2026 antfarm. Redistributions must keep the "
            "notice.\n",
    }
    demos.append({
        "script": [
            _list(),
            _read("README.md"),
            _read("docs/license.md"),
            _final(
                "docs/license.md answers it: tinyhook is released "
                "under the MIT license, copyright 2026 antfarm. No "
                "test run was needed — the question is answered by "
                "the doc itself."),
        ],
        "files": license_files,
        "goal":
            "What license is this project released under? The docs "
            "folder carries it — find the file and tell me the "
            "license and copyright.",
        "fact_gate": ["MIT license", "2026 antfarm"],
    })

    deploy_files = {
        "README.md":
            "# relaysvc\n\nA deployment helper. Operational facts are "
            "documented in the docs folder.\n",
        "docs/deploy.md":
            "# Deployment\n\nDEPLOY_TARGET = staging\nImage tag: "
            "v2.4\n\nBoth are pinned for this environment.\n",
    }
    demos.append({
        "script": [
            _list(),
            _read("README.md"),
            _read("docs/deploy.md"),
            _final(
                "docs/deploy.md pins both facts: DEPLOY_TARGET = "
                "staging and the image tag is v2.4. Read straight "
                "from the doc — no test run was needed, the question "
                "is answered by the file."),
        ],
        "files": deploy_files,
        "goal":
            "What deployment target and image tag does this project "
            "pin? Check the docs folder and quote the exact values.",
        "fact_gate": ["DEPLOY_TARGET = staging", "v2.4"],
    })

    cli_files = {
        "README.md":
            "# sweep\n\nA cleanup utility. Command details are in the "
            "docs folder.\n",
        "docs/cli.md":
            "# CLI\n\nsweep clean --dry-run verifies first; the "
            "verify-first flag is mandatory on production paths.\n",
    }
    demos.append({
        "script": [
            _list(),
            _read("README.md"),
            _read("docs/cli.md"),
            _final(
                "docs/cli.md answers it: sweep clean --dry-run "
                "verifies first, and verify-first is mandatory on "
                "production paths. The doc carried both facts — no "
                "test run needed for a question."),
        ],
        "files": cli_files,
        "goal":
            "Which flag makes sweep's clean command verify before "
            "deleting? The docs folder documents the CLI — find the "
            "exact flags.",
        "fact_gate": ["--dry-run", "verify-first"],
    })

    logging_files = {
        "README.md":
            "# gater\n\nA tiny event gate. Configuration facts live "
            "in the docs folder.\n",
        "docs/logging.md":
            "# Logging\n\nLOG_DIR = /var/log/gater\nRotation: daily. "
            "The directory must exist at startup.\n",
    }
    demos.append({
        "script": [
            _list(),
            _read("README.md"),
            _read("docs/logging.md"),
            _final(
                "docs/logging.md answers it: LOG_DIR = /var/log/gater "
                "with daily rotation. Straight from the file — a "
                "question needs the doc, not a test run."),
        ],
        "files": logging_files,
        "goal":
            "Where does this project write its logs? The docs folder "
            "documents the log directory — find it and quote the "
            "exact path.",
        "fact_gate": ["/var/log/gater"],
    })

    changelog_files = {
        "README.md":
            "# pinbox\n\nA version-pinning tool. Release facts are in "
            "the docs folder.\n",
        "docs/changelog.md":
            "# Changelog\n\nCurrent stable: 0.9.2 (the 0.9.1 yank is "
            "resolved). Older lines kept for reference.\n",
    }
    demos.append({
        "script": [
            _list(),
            _read("README.md"),
            _read("docs/changelog.md"),
            _final(
                "docs/changelog.md answers it: the current stable is "
                "0.9.2 (the 0.9.1 yank is resolved). Quoted from the "
                "file — no test run was needed, the question is "
                "answered by the doc."),
        ],
        "files": changelog_files,
        "goal":
            "What is the current stable version of this project? The "
            "docs folder has the changelog — find it and quote the "
            "exact version.",
        "fact_gate": ["0.9.2"],
    })

    # --- S109 the post-README seam (the gen-21 forensics) ---
    # ep21's explore-qa failures: listing-first and the anti-guess
    # beat TRANSFERRED, but at the post-README moment the model loops
    # code_references(symbol="main") / code_symbols(name="main") with
    # invented args x9 instead of returning to the listing. Third
    # instance of the continuation-seam pattern. The v2 drills
    # demonstrate the TEMPTED CALL BEING REJECTED at exactly that
    # seam — same fixtures, new goals (the lane skips covered goals;
    # the lesson is new).
    demos.append({
        "script": [
            _list(),
            _read("README.md"),
            # S109: the tempted call at the post-README seam —
            # honestly rejected; the correction is the listing
            ToolCall(name="code_references",
                     arguments={"symbol": "main"}),
            _list(),
            _read("docs/running.md"),
            _final(
                "The README pointed at the docs folder — my next "
                "action was the listing, not a symbol hunt: a "
                "code_references call was rejected as invalid, and "
                "docs/running.md answers it anyway. Start the server "
                "from the repo root with python -m serverctl --port "
                "8765. When a doc points somewhere, go there and "
                "read; do not go hunting for symbols."),
        ],
        "files": server_files,
        "goal":
            "How do you start this project's server? The docs have "
            "it: when the README points you at the docs folder, "
            "read the folder's files instead of hunting symbols, "
            "and give me the exact command.",
        "fact_gate": ["python -m serverctl", "8765"],
    })
    demos.append({
        "script": [
            _list(),
            _read("README.md"),
            ToolCall(name="code_symbols",
                     arguments={"name": "main"}),
            _list(),
            _read("docs/configuration.md"),
            _final(
                "The README sent me to the docs folder. A code_symbols "
                "call was rejected as invalid — symbol hunts are not "
                "how this question gets answered — so I listed the "
                "directory and read docs/configuration.md: "
                "request_timeout = 45 and max_retries = 3. Read what "
                "the docs point at; the file carries the values."),
        ],
        "files": config_files,
        "goal":
            "What are this tool's default request timeout and retry "
            "count? The docs folder holds the configuration values: "
            "after the README points you there, open the file and "
            "quote them exactly.",
        "fact_gate": ["request_timeout = 45", "max_retries = 3"],
    })
    # S110: the S109 recovery-v2 drill (opening guessed read) is also
    # removed — gen-22 imitated the demonstrated opening guess; its
    # record is superseded by supersede_opening_guess_demos, and
    # testing-v3 above carries the mid-chain version of the lesson.
    return demos


def validate_demonstration(script: List[Any], files: Dict[str, str],
                            goal: str,
                            recovery_anchors: Optional[List[str]] = None,
                            ambiguous_anchors: Optional[List[str]] = None
                            ) -> "tuple[bool, List[str]]":
    """S80 demo quality validator — the anti-flakiness bar every
    demonstration must clear BEFORE it can enter the corpus
    (deterministic; the verification gate stays the separate real-world
    check). The validator makes authoring untrusted-by-design: any
    author (this session, muse-spark, a future epN) can write demos,
    and the bar enforces quality.
    S100: recovery_anchors declares the script's deliberate
    stale-memory misses (the failed-edit-recovery shape). File state
    is simulated through the script in order, so a declared miss must
    genuinely MISS (count 0) against current content, be followed by
    a successful corrective edit on the same path, and every
    declaration must be consumed — a declared anchor that actually
    matches is rejected, so authors cannot smuggle unverified edits.
    S104: ambiguous_anchors declares the deliberate AMBIGUOUS anchors
    (the cascade re-anchor shape — an anchor that matches >= 2 in
    current content and is rejected by the runtime edit_file). The
    same consumption rules apply: the collision must be genuine (a
    0- or 1-hit "ambiguity" is staged and rejected), and a corrective
    edit with a unique anchor must follow on the same path."""
    reasons: List[str] = []
    tool_calls = [t for t in script if isinstance(t, ToolCall)]
    finals = [t for t in script if isinstance(t, ModelResponse)]

    # 1. discovery-first: inspect before touching files
    if not tool_calls or tool_calls[0].name not in ("list_directory",
                                                    "run_tests"):
        reasons.append("first tool must be list_directory or run_tests "
                       "(discovery-first)")

    # 2. the diagnosis chain: the module under repair must be read
    if not any(t.name == "read_file" for t in tool_calls):
        reasons.append("no read_file: the diagnosis chain is absent")

    # 3. ends with exactly one honest final
    if len(finals) != 1 or not (finals[0].text or "").strip():
        reasons.append("demonstration must end with one non-empty final")

    # 4. evidence-referencing narrative: the final names the file it
    # edited or the test it read (no free-floating diagnosis)
    if finals and (finals[0].text or "").strip():
        touched = {t.arguments.get("path") for t in tool_calls
                   if t.name in ("read_file", "edit_file", "write_file")
                   and isinstance(t.arguments.get("path"), str)}
        if touched and not any(name in finals[0].text
                               for name in touched):
            reasons.append("final answer references none of the files "
                           f"actually read/edited ({sorted(touched)})")

    # 5. unique anchors (the S78 cascade lesson), simulated through
    # the script in order (S100: file state evolves as edits land).
    # Undeclared edits must match exactly once in CURRENT content. A
    # declared recovery anchor must genuinely miss (count 0 — the
    # stale-memory beat changes nothing, matching the runtime) and be
    # followed by a successful corrective edit on the same path.
    state = dict(files)
    pending = list(recovery_anchors or [])
    ambiguous = list(ambiguous_anchors or [])
    awaiting_correction: Dict[str, int] = {}
    for t in tool_calls:
        if t.name != "edit_file":
            continue
        target = t.arguments.get("path")
        content = state.get(target)
        if content is None:
            reasons.append(f"edit targets unwritten file: {target}")
            continue
        old = t.arguments.get("old_string") or ""
        new = t.arguments.get("new_string") or ""
        hits = content.count(old)
        if old in pending and hits == 0:
            pending.remove(old)
            awaiting_correction[target] = awaiting_correction.get(
                target, 0) + 1
            continue
        if old in pending:
            reasons.append(f"declared recovery anchor for {target} "
                           f"matches ({hits}x) — the miss must be "
                           f"genuine, not staged")
            continue
        if old in ambiguous:
            # S104: the collision must be genuine — 0 or 1 hits means
            # the "ambiguity" is staged (0 is the stale shape, 1 would
            # simply have succeeded)
            if hits < 2:
                reasons.append(f"declared ambiguous anchor for {target} "
                               f"matches {hits}x — the collision must "
                               f"be genuine (>= 2)")
            else:
                ambiguous.remove(old)
                awaiting_correction[target] = awaiting_correction.get(
                    target, 0) + 1
            continue
        if hits != 1:
            reasons.append(f"edit anchor for {target} matches "
                           f"{hits} times (must be 1)")
            continue
        state[target] = content.replace(old, new, 1)
        if awaiting_correction.get(target):
            awaiting_correction[target] -= 1
    if pending:
        reasons.append(f"{len(pending)} declared recovery anchor(s) "
                       f"never missed their target")
    if ambiguous:
        reasons.append(f"{len(ambiguous)} declared ambiguous anchor(s) "
                       f"never collided with their target")
    if any(awaiting_correction.values()):
        reasons.append("recovery miss without a later corrective edit "
                       "on the same path")

    # 6. goal identity (the S78 goal-dedupe lesson): no placeholder or
    # generic-only goals
    words = [w for w in re.split(r"\W+", goal.lower()) if w]
    filler = {"the", "tests", "test", "in", "this", "project", "are",
              "failing", "find", "bug", "fix", "it", "and", "run", "to",
              "verify", "they", "pass", "a"}
    if len([w for w in words if w not in filler]) < 3:
        reasons.append("goal lacks identity (too few substantive words)")

    return (not reasons, reasons)


def build_agent_corpus(experience_store: ExperienceStore,
                       python: str,
                       demos: Optional[List[Dict[str, Any]]] = None
                       ) -> Dict[str, Any]:
    """S80: the agent-authored lane — demonstrations authored by the
    agent (or any verified provider) run through the REAL benchmark
    with the quality validator AND the verification gate. The author
    is untrusted-by-design: the validator + gate are what make
    external authoring (this session, muse-spark, a future epN) safe.
    Returns honest stats; failures are recorded, never hidden.
    S95: idempotent like build_corpus — demos whose normalized goal
    already has a successful agent-authored record are skipped
    (re-running the lane used to re-record every demo under a fresh
    session suffix, doubling the authored share on every rebuild)."""
    import sys

    from .experience import _normalize_goal

    python = python or sys.executable
    if demos is None:
        demos = agent_authored_demos(python)
    covered = set()
    for record in experience_store.load():
        tags = record.tags or []
        if (AGENT_AUTHORED_TAG in tags
                and "superseded-pattern" not in tags
                and record.outcome in ("success", "recovered")):
            base_goal = record.goal.split(" (benchmark run")[0]
            covered.add(_normalize_goal(base_goal))
    stats: Dict[str, Any] = {"runs": 0, "passed": 0, "failed": 0,
                             "rejected": 0, "skipped_existing": 0,
                             "durations_s": 0.0,
                             "tasks": []}
    for demo in demos:
        script, files, goal = demo["script"], demo["files"], demo["goal"]
        if _normalize_goal(goal) in covered:
            stats["skipped_existing"] += 1
            continue
        ok, reasons = validate_demonstration(
            script, files, goal,
            recovery_anchors=demo.get("recovery_anchors"),
            ambiguous_anchors=demo.get("ambiguous_anchors"))
        if not ok:
            stats["rejected"] += 1
            stats["tasks"].append({"goal": goal, "success": False,
                                   "iterations": 0,
                                   "termination":
                                   "validator: " + "; ".join(reasons)})
            continue
        provider = ScriptedDemonstrator(script)

        def fixture_writer(ws, _files=files):
            for name, content in _files.items():
                target = ws.root / name
                # S108: nested fixtures (docs/running.md) need the
                # parent dirs — the lane crashed on them before
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

        # S108: an answer-QA demo declares fact_gate and runs under
        # the same containment verifier run_evaluation builds (the
        # default unittest plan would make a no-test demo
        # uncompletable). Demos without fact_gate are unchanged.
        task_verifier = None
        if demo.get("fact_gate"):
            facts = [f.lower() for f in demo["fact_gate"]]

            def lane_fact_verifier(session, _facts=facts):
                # S114: same non-leaking rejection as the eval gate
                text = (getattr(session, "pending_answer", None)
                        or session.final_result or "").lower()
                missing = [f for f in _facts if f not in text]
                if missing:
                    return False, ("final answer must quote the "
                                   "exact command from the "
                                   "documentation")
                return True, "final answer contains the planted facts"

            task_verifier = lane_fact_verifier
        report = run_benchmark(provider, fixture_writer=fixture_writer,
                               goal=goal,
                               experience_store=experience_store,
                               verifier=task_verifier)
        stats["runs"] += 1
        stats["durations_s"] += report.duration_seconds
        if report.success:
            stats["passed"] += 1
            records = experience_store.load()
            if records:
                last = records[-1]
                if AGENT_AUTHORED_TAG not in last.tags:
                    last.tags.append(AGENT_AUTHORED_TAG)
                # S106: the lane MUST stamp the corpus version tag — the
                # hygiene rule supersedes any scripted-demo record
                # lacking it, so unstamped lane records died on the
                # NEXT rebuild (the second treadmill: all 72
                # agent-authored records were superseded wave by wave,
                # and every generation trained on only that cycle's
                # fresh drills)
                if VERSION_TAG not in last.tags:
                    last.tags.append(VERSION_TAG)
                if (demo.get("recovery_anchors")
                        and EDIT_RECOVERY_TAG not in last.tags):
                    last.tags.append(EDIT_RECOVERY_TAG)
                experience_store.save(records)
        else:
            stats["failed"] += 1
        stats["tasks"].append({
            "goal": goal, "success": report.success,
            "iterations": report.iterations,
            "termination": report.termination_reason})
    return stats


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
    # S106: repair the lane's missing version stamps BEFORE hygiene —
    # the one-time un-supersede + dedupe restores the agent-authored
    # corpus, then the version-tagged records survive every rebuild
    # S106 repair first (stamp version tags; its blanket un-supersede
    # was the missing-stamp artifact fix), THEN the S110 opening-guess
    # supersession re-applies — deterministic net effect per rebuild
    repair_agent_corpus_tags(experience_store)
    # S110: supersede the opening-guess demonstrations BEFORE the lane
    # runs — their demo dicts are removed in the same slice, so the
    # superseded goals do not re-record
    supersede_opening_guess_demos(experience_store)
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
# optional base model: `python train_ep1.py ep11
# Qwen/Qwen2.5-Coder-7B-Instruct` (S79; default: the 3B)
GEN = sys.argv[1] if len(sys.argv) > 1 else "ep1"
BASE_MODEL = (sys.argv[2] if len(sys.argv) > 2
              else "Qwen/Qwen2.5-Coder-3B-Instruct")
# S113: the "lean 4-bit path" flag covers 7B AND 9B — qwen3.5:9b is
# the base-step-up candidate (explore-qa 3/3 zero-shot per the 9B
# re-scout) and needs the same memory treatment on the T4/L4.
SEVEN_B = ("7B" in BASE_MODEL) or ("9B" in BASE_MODEL.upper())
NINE_B = "9B" in BASE_MODEL.upper()
# S113: skip records longer than this on the big-model path —
# activations scale with sequence length; the 9B on a 15GB T4 OOMs
# at the prepare step otherwise (7B records are all under this cap).
# S113b: 2048 -> 768 — the gen-24 T4 attempt OOM'd 244MB short in
# the loss pass, and the qwen3.5 vocab (151k) makes the logits the
# hog: sequence length is the only lever big enough.
MAX_SEQ_TOKENS = 768
# S113b: bake the allocator config in BEFORE torch imports — the
# gen-24 OOM message itself recommends it (fragmentation recovery)
import os
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF",
                      "expandable_segments:True")
DATASET = "training.jsonl"
OUTPUT_DIR = f"{GEN}-adapter"
MERGED_DIR = f"{GEN}-merged"


KIT_VERSION = "s92"


def load_dataset(path=DATASET):
    rows = [json.loads(line) for line in open(path, encoding="utf-8")
            if line.strip()]
    if not rows:
        sys.exit(f"no training records in {path} — run 'qa curate' and "
                 "'qa build-training' first")
    return rows


def main():
    import torch
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

    first_render_shapes: list = []

    def _to_flat_token_ids(rendered):
        """S76.3: normalize EVERY apply_chat_template return shape to a
        flat python list of ints. Observed v5 shapes: dict, batched
        nested lists, tensors, list-wrapped tensors, and — the one that
        defeated two flatten attempts — a BatchEncoding (UserDict, so
        isinstance-dict is False; it SLICES like a batch, so every
        render read as a batch of exactly 1). The input_ids key comes
        FIRST because it is the BatchEncoding contract."""
        for _ in range(6):
            if hasattr(rendered, "input_ids"):
                rendered = rendered["input_ids"]
            elif isinstance(rendered, dict):
                rendered = rendered["input_ids"]
            elif hasattr(rendered, "tolist"):
                rendered = rendered.tolist()
            elif isinstance(rendered, (list, tuple)) and len(rendered) == 1:
                rendered = rendered[0]
            elif isinstance(rendered, (list, tuple)) and rendered                     and isinstance(rendered[0], (list, tuple)):
                rendered = rendered[0]
            elif isinstance(rendered, int):
                rendered = [rendered]
            else:
                break
        return rendered

    def _ids(text):
        return _to_flat_token_ids(tokenizer(text,
                                            add_special_tokens=False))

    def _manual_masked_example(messages):
        """Fallback (used only if the template path yields no assistant
        tokens): construct the Qwen2.5 chat format explicitly —
        <|im_start|>role {content} <|im_end|> — with no
        apply_chat_template involved. Same segment layout the template
        produces for this model family. (The \\n after each segment is
        written as an escape so the generated script tokenizes the
        newline the template emits.)"""
        input_ids: list = []
        labels: list = []
        for message in messages:
            seg = _ids(f"<|im_start|>{message['role']}\\n")
            body = _ids(message["content"])
            end = _ids("<|im_end|>\\n")
            input_ids.extend(seg + body + end)
            if message["role"] == "assistant":
                labels.extend(seg + body + end)
            else:
                labels.extend([-100] * (len(seg) + len(body) + len(end)))
        assistant_tokens = sum(1 for l in labels if l != -100)
        return {"input_ids": input_ids, "labels": labels}, \
            assistant_tokens, len(labels)

    def masked_example(messages):
        """Render the conversation incrementally through the joint chat
        template (per-message rendering would corrupt the stream: Qwen
        injects a default system block into every render that lacks
        one) and attribute each new token to the message that
        introduced it.
        S113: qwen3.5's template REQUIRES a user turn — a system-only
        render raises TemplateError (No user query found). Skip the
        system-only render and render [system, user] jointly at the
        first user message; its tokens stay masked either way
        (behavior identical for qwen2.5)."""
        input_ids: list = []
        labels: list = []
        prev_len = 0
        # qwen3.5 (and possibly other families) cannot render a bare
        # system message — fold it into the first user render
        start = 1 if (messages and messages[0].get("role") == "system"
                      and len(messages) > 1) else 0
        for index, message in enumerate(messages):
            if index < start:
                continue
            raw = tokenizer.apply_chat_template(
                messages[:index + 1], tokenize=True)
            full = _to_flat_token_ids(raw)
            if index == 0:
                first_render_shapes.append(type(raw).__name__)
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

    def build_all(mode):
        masked = []
        a_total = t_total = 0
        skipped_long = 0
        for r in rows:
            if mode == "template":
                example, a, t = masked_example(r["messages"])
            else:
                example, a, t = _manual_masked_example(r["messages"])
            # S113c: the skip is 9B-ONLY — the gen-24 T4 run skipped
            # 463/470 records at the 768 cap (and OOM'd anyway), so
            # the 9B-on-T4 experiment is dead and the cap must never
            # bite the proven qwen2.5 7B path
            if NINE_B and len(example["input_ids"]) > MAX_SEQ_TOKENS:
                skipped_long += 1
                continue
            masked.append(example)
            a_total += a
            t_total += t
        if skipped_long:
            print(f"mask: skipped {skipped_long} over-long records "
                  f"(> {MAX_SEQ_TOKENS} tokens)")
        return masked, a_total, t_total

    masked_rows, total_assistant, total_tokens = build_all("template")
    ratio = total_assistant / max(total_tokens, 1)
    mode_used = "template"
    if ratio < 0.10:
        # the template path is broken under this transformers version —
        # rebuild the whole dataset with the explicit manual format so
        # one broken API cannot silently produce an untrained model
        print("template path yielded no assistant tokens — falling back "
              "to manual Qwen-format construction")
        first_render_shapes.append("fallback-manual")
        masked_rows, total_assistant, total_tokens = build_all("manual")
        ratio = total_assistant / max(total_tokens, 1)
        mode_used = "manual"
    print(f"mask path: {mode_used} | assistant-token ratio: "
          f"{ratio:.3f} ({total_assistant:,}/{total_tokens:,})")
    print(f"first-render shapes: {first_render_shapes[:3]}")
    if ratio < 0.10:
        # a broken mask would train on nothing — refuse like the
        # sanity generation gate does
        sys.exit("MASK GATE FAILED: assistant-token ratio under 10% — "
                 f"the label masking is broken (raw render shapes: "
                 f"{first_render_shapes[:3]}); do not train")
    dataset = Dataset.from_list(masked_rows)

    config = SFTConfig(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=(1 if SEVEN_B else 2),
        gradient_accumulation_steps=(8 if SEVEN_B else 4),
        num_train_epochs=3,
        learning_rate=2e-4,
        fp16=True,                      # T4 (Turing) has no bf16
        gradient_checkpointing=True,
        # S81: 7B needs checkpointing too (was `not SEVEN_B`, which
        # disabled the main activation saver on the hungriest path).
        # LoRA + checkpointing: frozen embeddings break the default
        # (reentrant) checkpoint implementation. The 4-bit path
        # checkpoint via prepare_model_for_kbit_training instead.
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=1,
        report_to=[],
        # S76: the dataset is pre-tokenized with labels — TRL must not
        # re-apply its own (unmasked) preparation
        dataset_kwargs={"skip_prepare_dataset": True},
        # S79: the 4-bit path wants the paged optimizer (adamw_torch is
        # right for the 3B fp16 path). optim is a TrainingArguments/
        # SFTConfig field — NOT an SFTTrainer kwarg (Colab catch).
        optim=("paged_adamw_32bit" if SEVEN_B else "adamw_torch"),
        # S92: clip REVERTED to 0 on the 7B path (the S91.1 verdict
        # convicted the S91 restoration: ep12 6/12 vs ep11 11/12 with
        # strings collapsing 3/3 -> 0/3 on full working chains). The
        # clip touched every gradient update, so it is suspect #1 for
        # the regression; ep13 (this kit + the S91 corpus, clip 0)
        # isolates the clip effect vs ep12 exactly. Restore 1.0 only
        # on verdict evidence, never on theory.
        # 3B keeps 1.0 as ever.
        max_grad_norm=(0 if SEVEN_B else 1.0),
    )
    lora = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        task_type="CAUSAL_LM",
    )

    if SEVEN_B:
        # S79: 7B fp16 (~14GB) does not fit the free T4's 16GB with
        # activations — 4-bit QLoRA is the standard free-T4 7B setup
        from transformers import BitsAndBytesConfig
        # S83: real torch.dtype objects — the "float16" STRINGS were
        # silently unconverted on the Colab stack, so bnb compute fell
        # back to the model default (bf16) and bf16 grads reached the
        # fp16 GradScaler (NotImplementedError THROUGH the S79 fix).
        bnb = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True)
        # torch_dtype MUST be fp16: Qwen2.5-7B's config defaults to
        # bfloat16, and on Turing (T4) bf16 is unsupported — the AMP
        # GradScaler then chokes on bf16 grads
        # (NotImplementedError: _amp_foreach_non_finite_check_and_unscale_
        # cuda not implemented for BFloat16 — Colab catch, S79; object
        # form pinned S83; v5 kwarg name pinned S84 — 5.17 prints
        # "`torch_dtype` is deprecated! Use `dtype` instead!" and the
        # deprecated spelling loaded float32, i.e. it NO-OPs)
        import inspect as _inspect
        _fp_kwargs = ({"dtype": torch.float16}
                      if "dtype" in _inspect.signature(
                          AutoModelForCausalLM.from_pretrained).parameters
                      else {"torch_dtype": torch.float16})
        model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL, quantization_config=bnb, device_map="auto",
            **_fp_kwargs)
        # belt and suspenders: the config default (bf16) leaks into
        # adapter dtypes and compute fallbacks if left in place
        model.config.torch_dtype = torch.float16
        # S81 lean prepare (T4 OOM fix): full
        # prepare_model_for_kbit_training upcasts norms to fp32 (+1GB
        # transient, peft #3265/#3293) and OOMs at
        # param.data.to(torch.float32) with 12+GB already allocated.
        # Lean path: skip the upcast/checkpoint wrapper here, enable
        # checkpointing manually (maintainer-sanctioned for constrained
        # GPUs), disable use_cache, and clear the allocator cache.
        # 7B-only, fail loudly — no silent 3B fallback (S79 attribution).
        import gc as _gc
        import torch as _torch
        _gc.collect()
        if _torch.cuda.is_available():
            _torch.cuda.empty_cache()
        from peft import prepare_model_for_kbit_training
        model = prepare_model_for_kbit_training(
            model, use_gradient_checkpointing=False)
        model.gradient_checkpointing_enable(
            gradient_checkpointing_kwargs={"use_reentrant": False})
        model.config.use_cache = False
        if _torch.cuda.is_available():
            _torch.cuda.empty_cache()
    else:
        model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL, torch_dtype="float16")
    # S83 dtype audit gate (Colab bf16 catch): the GradScaler crash
    # names no module, so assert the evidence HERE — versions, the
    # effective model dtype, and every bf16 param — before LoRA and
    # before the trainer. A single bf16 param on a T4 build refuses
    # loudly instead of dying 8 frames deep in torch/amp.
    try:
        import transformers as _tf_mod
        import peft as _peft_mod
        print(f"versions: transformers={_tf_mod.__version__} "
              f"peft={_peft_mod.__version__} torch={torch.__version__}")
    except Exception as _ver_exc:
        print(f"version probe failed: {_ver_exc}")
    try:
        import bitsandbytes as _bnb_mod
        print(f"bitsandbytes={_bnb_mod.__version__}")
    except Exception as _bnb_exc:
        print(f"bitsandbytes probe failed: {_bnb_exc}")
    _bf16 = sorted({f"{_n}:{_p.dtype}"
                    for _n, _p in model.named_parameters()
                    if "bfloat16" in str(_p.dtype)})
    print(f"dtype audit: model.dtype={model.dtype} "
          f"config.torch_dtype={model.config.torch_dtype} "
          f"bf16_params={len(_bf16)}")
    for _line in _bf16[:10]:
        print(f"  bf16: {_line}")
    # the compute dtype is the other silent fallback: print the
    # EFFECTIVE value (post-load config), not what was requested
    _qconf = getattr(model.config, "quantization_config", None)
    if isinstance(_qconf, dict):
        _eff_compute = _qconf.get("bnb_4bit_compute_dtype")
    else:
        _eff_compute = getattr(_qconf, "bnb_4bit_compute_dtype", None)
    if _eff_compute is None:
        _hq = getattr(model, "hf_quantizer", None)
        _eff_compute = getattr(
            getattr(_hq, "quantization_config", None),
            "bnb_4bit_compute_dtype", None)
    print(f"dtype audit: effective bnb_4bit_compute_dtype={_eff_compute}")
    if _bf16:
        sys.exit("DTYPE GATE FAILED: bf16 params present on a T4 build "
                 "— paste the versions + bf16 list above; do not train")
    if "bfloat16" in str(_eff_compute).lower():
        sys.exit("DTYPE GATE FAILED: bnb compute dtype resolved to bf16 "
                 "— paste the versions + effective dtype above; do not "
                 "train")
    model = get_peft_model(model, lora)
    # second gate, post-LoRA: adapters inherit dtypes from wherever
    # they please (config default, target modules) — census them too,
    # since the S83 crash arrived with a CLEAN pre-LoRA audit and died
    # at the first backward
    _lora_dtypes = sorted({f"{_n}:{_p.dtype}"
                           for _n, _p in model.named_parameters()
                           if "lora_" in _n})
    _bf16_post = [_d for _d in _lora_dtypes if "bfloat16" in _d]
    print(f"dtype audit: lora_params={len(_lora_dtypes)} "
          f"bf16_lora={len(_bf16_post)}")
    for _line in _bf16_post[:10]:
        print(f"  bf16 lora: {_line}")
    if _bf16_post:
        sys.exit("DTYPE GATE FAILED: bf16 LoRA adapters on a T4 build "
                 "— paste the versions + bf16 lora list above; do not "
                 "train")
    if SEVEN_B:
        # S85 setup-time bf16 hunt: the S84 audit proved params,
        # adapters AND bnb compute clean, yet bf16 grads STILL reached
        # the scaler — so the source is runtime, not weights (the
        # process autocast default is the prime suspect on torch 2.11).
        # One micro-batch forward+backward under explicit fp16 autocast
        # censuses grad dtypes BY NAME, then zeroes everything. Either
        # outcome diagnoses: bf16 here = a rogue explicit-bf16 op;
        # clean here + trainer crash = the trainer's autocast default
        # is bf16 (pinned below for the run).
        try:
            _ac_dtype = torch.get_autocast_dtype("cuda")
        except Exception as _ac_exc:
            _ac_dtype = f"probe failed: {_ac_exc}"
        print(f"autocast probe: default cuda autocast dtype={_ac_dtype}")
        if "bfloat16" in str(_ac_dtype).lower():
            for _setter in ("set_autocast_dtype",
                            "set_autocast_gpu_dtype"):
                _fn = getattr(torch, _setter, None)
                if _fn is None:
                    continue
                try:
                    try:
                        _fn("cuda", torch.float16)
                    except TypeError:
                        _fn(torch.float16)
                    print(f"autocast probe: pinned fp16 via "
                          f"torch.{_setter}")
                    break
                except Exception as _pin_exc:
                    print(f"autocast probe: torch.{_setter} failed: "
                          f"{_pin_exc}")
        try:
            _pdev = getattr(model, "device", None)
            if _pdev is None:
                _pdev = next(model.parameters()).device
            _ptok = tokenizer("Probe the dtype census.",
                              return_tensors="pt").to(_pdev)
            with torch.amp.autocast("cuda", dtype=torch.float16):
                _out = model(input_ids=_ptok["input_ids"],
                             labels=_ptok["input_ids"])
            _out.loss.backward()
            _ghist = {}
            _bf16_grads = []
            for _n, _p in model.named_parameters():
                if _p.grad is None:
                    continue
                _gdt = str(_p.grad.dtype)
                _ghist[_gdt] = _ghist.get(_gdt, 0) + 1
                if "bfloat16" in _gdt:
                    _bf16_grads.append(f"{_n}:{_p.grad.dtype}")
            print(f"autocast probe: grad dtype histogram={_ghist}")
            for _line in _bf16_grads[:10]:
                print(f"  bf16 grad: {_line}")
            if _bf16_grads:
                sys.exit("GRAD GATE FAILED: bf16 grads from a clean "
                         "audit — paste the autocast + histogram lines "
                         "above; do not train")
            model.zero_grad()
            del _out, _ptok
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except SystemExit:
            raise
        except Exception as _probe_exc:
            print(f"autocast probe: census skipped: {_probe_exc}")
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
    # S89 adapter dtype (THE fix, from the S88 census): torch 2.11's
    # GradScaler.unscale_() — the clip AND norm-logging path — rejects
    # fp16 grads (ValueError) and lacks a bf16 kernel on sm75
    # (NotImplementedError); fp32 grads pass fine. So the adapters
    # must be FP32, not fp16: the S86 census caught construction
    # casting them fp32->bf16, the S87 cast fp16-fixed the bf16 crash
    # only to meet the fp16 crash. Cast every lora_ param to fp32
    # AFTER SFTTrainer construction (post-construction casts stick —
    # the S87 fp16 census held) with an attesting print. This is the
    # standard mixed-precision recipe: fp32 master weights, fp16
    # compute. 161MB for 40M params — negligible on the T4.
    _cast_n = 0
    for _n, _p in model.named_parameters():
        if "lora_" in _n and str(_p.dtype) != "torch.float32":
            _p.data = _p.data.to(torch.float32)
            _cast_n += 1
    print(f"adapter cast: {_cast_n} lora params -> torch.float32")
    # S86 precision flags (always printed, near-free): what the
    # trainer THINKS it runs — the S85 probe proved the model side
    # clean, so a bf16-leaning trainer/accelerator config is the last
    # unobserved actor
    try:
        _acc = trainer.accelerator
        print(f"precision flags: fp16={config.fp16} bf16={config.bf16} "
              f"half_precision_backend="
              # S87: SFTConfig on transformers 5.17 has NO
              # half_precision_backend (caught live) — getattr, not boom
              f"{getattr(config, 'half_precision_backend', 'n/a')} "
              f"accelerator.mixed_precision="
              f"{getattr(_acc, 'mixed_precision', 'n/a')} "
              f"scaler_enabled="
              f"{getattr(getattr(_acc, 'scaler', None), '_enabled', 'n/a')}")
    except Exception as _flag_exc:
        print(f"precision flags: probe failed: {_flag_exc}")
    # S86 failure-path census: the S85 crash arrived with 392 fp32
    # grads and STILL died on a bf16 group inside the scaler, and
    # Colab collapses the middle traceback frames — so on
    # NotImplementedError, name every bf16 tensor IN SITU (params,
    # grads, autocast default, config) and re-raise. Zero cost when
    # green; the whole diagnosis when red. (S88: also catches
    # ValueError — torch 2.11's unscale_ rejects fp16 grads on the
    # clip path, same fail-loud treatment.)
    try:
        trainer.train()
    except (NotImplementedError, ValueError):
        print("FAILURE CENSUS (trainer died in torch/amp — naming "
              "every bf16 tensor):")
        try:
            _phist = {}
            for _n, _p in model.named_parameters():
                _phist[str(_p.dtype)] = _phist.get(str(_p.dtype), 0) + 1
            print(f"failure census: param dtype histogram={_phist}")
            for _n, _p in model.named_parameters():
                if "bfloat16" in str(_p.dtype):
                    print(f"  bf16 param: {_n}:{_p.dtype}")
        except Exception as _cen_exc:
            print(f"failure census: param scan failed: {_cen_exc}")
        try:
            _ghist2 = {}
            for _n, _p in model.named_parameters():
                if _p.grad is None:
                    continue
                _gdt = str(_p.grad.dtype)
                _ghist2[_gdt] = _ghist2.get(_gdt, 0) + 1
            print(f"failure census: grad dtype histogram={_ghist2}")
            for _n, _p in model.named_parameters():
                if (_p.grad is not None
                        and "bfloat16" in str(_p.grad.dtype)):
                    print(f"  bf16 grad: {_n}:{_p.grad.dtype}")
        except Exception as _cen_exc2:
            print(f"failure census: grad scan failed: {_cen_exc2}")
        try:
            print(f"failure census: autocast default="
                  f"{torch.get_autocast_dtype('cuda')} "
                  f"config.torch_dtype={model.config.torch_dtype}")
        except Exception as _cen_exc3:
            print(f"failure census: misc probe failed: {_cen_exc3}")
        raise
    trainer.save_model(OUTPUT_DIR)
    print("adapter saved to", OUTPUT_DIR)

    # merge the adapter into the base so ollama (or llama.cpp) can take
    # the WHOLE model without any adapter dance
    merged = model.merge_and_unload()
    if SEVEN_B:
        # S90 convertible-output gate: merge_and_unload on the 4-bit
        # base leaves bnb Linear4bit layers + quantization_config
        # behind, and llama.cpp's converter refuses those ("Quant
        # method is not yet supported: 'bitsandbytes'" — Colab catch).
        # A full fp16 dequant (15.2GB) fits neither the T4 (14.56GB)
        # nor free-Colab CPU RAM, so the 7B import path is the
        # GGUF-LoRA merge pipeline (README: base GGUF + adapter GGUF
        # + llama-export-lora), NOT direct conversion of this dir.
        # Census here so the run states what it produced.
        _q4_n = sum(1 for _m in merged.modules()
                    if _m.__class__.__name__ == "Linear4bit")
        _qconf = getattr(merged.config, "quantization_config", None)
        print(f"merge census: surviving Linear4bit={_q4_n} "
              f"quantization_config_present={_qconf is not None}")
        if _q4_n or _qconf is not None:
            print("merge census: this dir is NOT directly convertible "
                  "— use the README GGUF-LoRA pipeline (no retraining: "
                  "the adapter dir is the import artifact)")
    merged.save_pretrained(MERGED_DIR)
    tokenizer.save_pretrained(MERGED_DIR)

    # DISK-LEVEL fixup (the first ep1 verdict attempt, 2026-09-11):
    # in-memory config edits do NOT survive transformers v5's save —
    # it re-tied the head and wrote rope_theta in a new config format
    # ollama's converter cannot read (freq_base came out 0.0 and the
    # model emitted one repeated token). Patch the SAVED files:
    # explicit lm_head + legacy rope_theta key.
    # S113: these fixups are QWEN2.5-specific — qwen3.5 ships its own
    # chat template and a different config layout, so untying the head
    # and forcing the legacy rope key would corrupt it. The family
    # check skips the whole block for non-qwen2.5 bases.
    import glob as _glob
    import json as _json
    from safetensors.torch import load_file as _load, save_file as _save
    QWEN25_FAMILY = "qwen2.5" in BASE_MODEL.lower()
    for shard in _glob.glob(f"{MERGED_DIR}/*.safetensors"):
        state = _load(shard)
        if "model.embed_tokens.weight" in state                 and "lm_head.weight" not in state:
            state["lm_head.weight"] =                 state["model.embed_tokens.weight"].clone()
            _save(state, shard)
            print("fixup: lm_head made explicit in", shard)
    cfg_path = f"{MERGED_DIR}/config.json"
    cfg = _json.load(open(cfg_path, encoding="utf-8"))
    if SEVEN_B and _q4_n == 0 and cfg.pop("quantization_config", None) \
            is not None:
        # S90: strip a STALE bnb claim only — safe iff no Linear4bit
        # survived (censused above), i.e. the tensors are already
        # plain fp16 and only the config would make the converter
        # refuse the dir
        print("fixup: stale quantization_config removed from config.json")
    if QWEN25_FAMILY:
        cfg["tie_word_embeddings"] = False
        cfg["rope_theta"] = (cfg.get("rope_theta")
                             or cfg.get("rope_parameters", {}).get("rope_theta")
                             or 1000000.0)
        _json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), indent=2)
        print("fixup: tie_word_embeddings=False, rope_theta =",
              cfg["rope_theta"])
    else:
        print("fixup: qwen2.5-specific fixups skipped for",
              BASE_MODEL, "(family: qwen3.5 — keep the shipped config)")

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
    `%run train_ep1.py ep10`   (arg 1 names the generation — outputs
    land in ep10-adapter/ and ep10-merged/; default: ep1)
    `%run train_ep1.py ep11 Qwen/Qwen2.5-Coder-7B-Instruct`   (S79:
    arg 2 selects the base — 7B trains in 4-bit QLoRA on the T4; add
    `!pip install bitsandbytes` for the 4-bit path)
    S81 7B OOM runbook (T4 15GB): Runtime → Restart runtime first
    (a re-run in the same runtime keeps the old model allocated);
    `%env PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`;
    7B runs batch 1 x accum 8 with checkpointing (slower, fits).
- **Kaggle** (free 30 GPU-hours/week): same two files, P100/T4 kernel.

## After training (script outputs `ep1-merged/`)

**ollama 0.34.4+ dropped direct safetensors import (MLX-only converter)
and the old quantize types — conversion through llama.cpp is now
REQUIRED** (verified 2026-09-24; see docs/s76-spec.md):

1. Zip and download (Colab):
    `!zip -r epN-merged.zip epN-merged`
    `!zip -r epN-adapter.zip epN-adapter`   (S90: the 7B import path
    needs the ADAPTER dir — keep it)
2. Convert to GGUF (same Colab session, before or after download —
   the converter is pure Python, no build):
    `!pip install gguf`
    `!git clone --depth 1 https://github.com/ggml-org/llama.cpp`
    3B path (fp16 merged dir converts directly):
    `!python llama.cpp/convert_hf_to_gguf.py epN-merged \\
        --outfile epN.gguf --outtype q8_0`
    (q8_0 ≈ half the fp16 size, negligible quality cost. Optional
    speed step: q4_K_M via a prebuilt llama-quantize binary from
    llama.cpp releases — `llama-quantize epN.gguf epN-q4.gguf q4_K_M`.)
    7B path (S90: the merged dir keeps bnb quantization, which the
    converter refuses — full fp16 dequant is 15.2GB and fits neither
    the T4 nor free-Colab RAM — so merge at the GGUF level, which
    streams and never materializes 15GB; no retraining, the adapter
    dir is the import artifact):
    `!python llama.cpp/convert_hf_to_gguf.py <base-HF-dir> \\
        --outfile base.gguf --outtype f16`   (base weights dir;
    reuses the training download from the HF cache when present)
    `!python llama.cpp/convert_lora_to_gguf.py epN-adapter \\
        --outfile epN-lora.gguf`   (needs only the base CONFIG —
    fetched from the hub via adapter_config.json; our adapters
    touch no embeddings so the tied-head restriction does not apply)
    `!cmake -B llama.cpp/build -S llama.cpp` then
    `!cmake --build llama.cpp/build --target llama-export-lora -j`
    (CPU build is fine — one-shot merge, no GPU needed)
    `!llama.cpp/build/bin/llama-export-lora -m base.gguf \\
        --lora epN-lora.gguf -o epN.gguf`
    (then optional `llama-quantize epN.gguf epN-q4.gguf q4_K_M` —
    q8_0 ≈ 8.1GB, q4_K_M ≈ 4.7GB for 7B)
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
    from .evaluation import (build_fact_verifier, default_tasks,
                             protocol_metrics)
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
                    # S118: the verdict path MUST honor the fact gate —
                    # without it explore-qa ran the unittest plan on a
                    # no-test fixture (structurally impossible to pass)
                    # and every verdict-based explore-qa score was
                    # invalid (gen-21..25)
                    verifier=(build_fact_verifier(task.fact_gate)
                              if task.fact_gate else None),
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
