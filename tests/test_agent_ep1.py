"""S64/S66 ep1 corpus builder tests: scripted curriculum demonstrators
through the REAL loop, honest provenance, strategy diversity, training
kit export.
"""

import json
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import ModelResponse
from qacompanion.agent.curation import TrajectoryCurator
from qacompanion.agent.ep1 import (
    DEMO_MODEL_TAG, STRATEGIES, build_corpus, build_demo,
    export_training_kit, format_corpus_report)
from qacompanion.agent.experience import ExperienceStore
from qacompanion.agent.training import build_training
from qacompanion.agent.curriculum import bug_fix_defect
import sys


class DemonstratorTests(unittest.TestCase):
    """S66 contract: explore-first scripts, strategy diversity."""

    def test_diagnostic_clean_derives_the_fix(self):
        # S71: the failing suite is RUN FIRST, then the test file and
        # the module are read BEFORE the edit — the fix is derived
        script, _files, _goal, tag = build_demo(
            "bug_fix", "diagnostic_clean", 0, 3, sys.executable)
        self.assertEqual("diagnostic_clean", tag)
        names = [t.name for t in script if getattr(t, "name", None)]
        self.assertEqual(
            ["list_directory", "run_tests", "read_file", "read_file",
             "edit_file", "run_tests"], names)
        edit = [t for t in script
                if getattr(t, "name", None) == "edit_file"][0]
        _module, func, good, bad = bug_fix_defect(0)
        self.assertEqual(bad, edit.arguments["old_string"])
        self.assertEqual(good, edit.arguments["new_string"])
        # the final answer WALKS the chain
        self.assertIn("Reading", script[-1].text)
        # the reads target the test file and the module — no guesses
        paths = [t.arguments["path"] for t in script
                 if getattr(t, "name", None) == "read_file"]
        self.assertNotIn("src/" + paths[-1], paths)

    def test_diagnostic_recovery_guesses_before_discovery(self):
        # S71: the wrong turn moves BEFORE discovery — a rational first
        # hypothesis overturned by the evidence (gen-3's version taught
        # "list, then guess anyway")
        script, _files, _goal, tag = build_demo(
            "bug_fix", "diagnostic_recovery", 1, 1, sys.executable)
        self.assertEqual("diagnostic_recovery", tag)
        self.assertEqual("read_file", script[0].name)
        self.assertTrue(script[0].arguments["path"].startswith("src/"))
        names = [t.name for t in script if getattr(t, "name", None)]
        self.assertEqual("read_file", names[0])
        self.assertGreater(names.index("list_directory"), 0)

    def test_tests_first_strategy_runs_the_suite_before_reading(self):
        script, _files, _goal, tag = build_demo(
            "bug_fix", "tests_first_recovery", 2, 2, sys.executable)
        self.assertEqual("tests_first_recovery", tag)
        self.assertEqual("run_tests", script[0].name)
        self.assertEqual("list_directory",
                         [t for t in script
                          if getattr(t, "name", None) == "list_directory"]
                         [0].name)

    def test_unknown_strategy_rejected(self):
        with self.assertRaises(KeyError):
            build_demo("bug_fix", "yolo", 0, 1, sys.executable)

    def test_commands_are_quote_free(self):
        # S69: the taught protocol forbids quotes inside values, and
        # gen-3 showed quoted interpreter paths mangling into
        # command="\\" garbage
        for category in ("bug_fix", "feature_add", "build_repair",
                         "dependency", "testing", "regression"):
            strategy = STRATEGIES[category][0]
            script, _files, _goal, _tag = build_demo(
                category, strategy, 0, 1, sys.executable)
            for turn in script:
                if getattr(turn, "name", None) in ("run_tests",
                                                   "run_command"):
                    self.assertNotIn('"', turn.arguments.get("command", ""),
                                     (category, turn.arguments))


class CorpusChainTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.store = ExperienceStore(self.tmp / "exp.jsonl")

    def test_single_run_yields_verified_scripted_record(self):
        # (variant 0, level 3) cycles to the explore_clean strategy
        stats = build_corpus(self.store, python=sys.executable,
                             categories={"bug_fix": 1}, levels=(3,))
        self.assertEqual(1, stats["runs"])
        self.assertEqual(1, stats["passed"], stats)
        records = self.store.load()
        self.assertEqual(1, len(records))
        record = records[0]
        # (0, 3) cycles to premature_final_recovery: first verification
        # attempt failed, the retry passed -> honestly RECOVERED
        self.assertEqual("recovered", record.outcome)
        self.assertIn(DEMO_MODEL_TAG, record.tags)
        from qacompanion.agent.ep1 import VERSION_TAG
        self.assertIn(VERSION_TAG, record.tags)
        self.assertIn("(benchmark run", record.goal)
        # S66: EXPLORE-FIRST — the first captured step is discovery
        steps = record.context["tool_calls"]
        self.assertEqual("list_directory", steps[0]["tool"])
        self.assertTrue(steps[0]["ok"])
        edit = [s for s in steps if s["tool"] == "edit_file"][0]
        self.assertTrue(edit["ok"])
        # S71/S72: the final answer walks the chain and admits the
        # premature claim
        self.assertIn("reading test_", record.context["final_answer"])

    def test_recovery_record_is_tagged(self):
        # (variant 0, level 1) cycles to tests_first_recovery
        stats = build_corpus(self.store, python=sys.executable,
                             categories={"bug_fix": 1}, levels=(1,))
        self.assertEqual(1, stats["passed"])
        self.assertEqual(1, stats["recovery"])
        record = self.store.load()[0]
        self.assertIn("recovery-demo", record.tags)
        steps = record.context["tool_calls"]
        self.assertEqual("run_tests", steps[0]["tool"])
        failed_reads = [s for s in steps
                        if s["tool"] == "read_file" and not s["ok"]]
        self.assertTrue(failed_reads, "the wrong turn must really fail")

    def test_full_chain_to_step_trainable_training_record(self):
        # (variant 0, level 3) cycles to the diagnostic_clean strategy
        build_corpus(self.store, python=sys.executable,
                     categories={"bug_fix": 1}, levels=(3,))
        curated = self.tmp / "curated"
        TrajectoryCurator(self.store).curate(out_dir=curated)
        training = build_training(curated_dir=curated,
                                  out_dir=self.tmp / "training")
        self.assertEqual(1, training["eligible"])
        self.assertEqual(1, training["step_trainable"])
        chat = json.loads((self.tmp / "training" / "training.jsonl")
                          .read_text(encoding="utf-8"))
        assistants = [m for m in chat["messages"]
                      if m["role"] == "assistant"]
        self.assertIn("[TOOL: list_directory(", assistants[0]["content"])
        self.assertIn("scripted-demo", json.dumps(chat["metadata"]))


class CategoryCoverageTests(unittest.TestCase):
    """S66: one verified demonstrator per new category."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.store = ExperienceStore(self.tmp / "exp.jsonl")

    def _run(self, category):
        stats = build_corpus(self.store, python=sys.executable,
                             categories={category: 1}, levels=(1,))
        self.assertEqual(1, stats["passed"], stats)
        return self.store.load()[-1]

    def test_feature_add_implements_the_declared_feature(self):
        record = self._run("feature_add")
        writes = [s for s in record.context["tool_calls"]
                  if s["tool"] == "edit_file"]
        self.assertTrue(writes)
        self.assertIn("def ", writes[0]["args"]["new_string"])
        self.assertEqual("success", record.outcome)

    def test_build_repair_fixes_the_syntax_error(self):
        record = self._run("build_repair")
        edit = [s for s in record.context["tool_calls"]
                if s["tool"] == "edit_file"][0]
        self.assertIn("sum(values)", edit["args"]["new_string"])
        self.assertEqual("success", record.outcome)

    def test_dependency_creates_the_missing_module(self):
        record = self._run("dependency")
        steps = record.context["tool_calls"]
        # the natural recovery beat: reading helpers.py genuinely fails
        self.assertTrue(any(s["tool"] == "read_file" and not s["ok"]
                            and "helpers" in s["args"]["path"]
                            for s in steps))
        write = [s for s in steps if s["tool"] == "write_file"][0]
        self.assertIn("helpers", write["args"]["path"])
        self.assertEqual("success", record.outcome)

    def test_testing_writes_a_real_test_file(self):
        record = self._run("testing")
        write = [s for s in record.context["tool_calls"]
                 if s["tool"] == "write_file"][0]
        self.assertIn("unittest", write["args"]["content"])
        self.assertEqual("success", record.outcome)

    def test_regression_pins_the_behavior(self):
        record = self._run("regression")
        write = [s for s in record.context["tool_calls"]
                 if s["tool"] == "write_file"][0]
        self.assertIn("sort_words", write["args"]["content"])
        self.assertEqual("success", record.outcome)

    def test_goal_phrasing_varies_across_records(self):
        build_corpus(self.store, python=sys.executable,
                     categories={"bug_fix": 5}, levels=(1,))
        goals = [r.goal.split(" (benchmark run")[0]
                 for r in self.store.load()]
        self.assertGreater(len(set(goals)), 1,
                           "paraphrase templates must vary the goals")

    def test_mixed_corpus_recovery_share_at_least_quarter(self):
        build_corpus(self.store, python=sys.executable,
                     levels=(1, 2, 3))
        recovery = sum(1 for r in self.store.load()
                       if "recovery-demo" in r.tags)
        total = sum(1 for r in self.store.load())
        self.assertGreaterEqual(recovery / max(total, 1), 0.25)


class CoverageTargetingTests(unittest.TestCase):
    """S73: the two S57 eval-task shapes the gen-6 corpus never covered."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.store = ExperienceStore(self.tmp / "exp.jsonl")

    def test_string_reverse_demo_fixes_the_task_shape(self):
        stats = build_corpus(self.store, python=sys.executable,
                             categories={"string_reverse": 1},
                             levels=(1,))
        self.assertEqual(1, stats["passed"], stats)
        record = self.store.load()[-1]
        edit = [s for s in record.context["tool_calls"]
                if s["tool"] == "edit_file"][0]
        self.assertIn("return text[::-1]",
                      edit["args"]["new_string"])
        self.assertEqual("success", record.outcome)

    def test_nested_lookup_demo_fixes_the_task_shape(self):
        stats = build_corpus(self.store, python=sys.executable,
                             categories={"nested_lookup": 1},
                             levels=(1,))
        self.assertEqual(1, stats["passed"], stats)
        edit = [s for s in self.store.load()[-1].context["tool_calls"]
                if s["tool"] == "edit_file"][0]
        self.assertIn('data.get("settings", {})',
                      edit["args"]["new_string"])
        self.assertEqual("success", self.store.load()[-1].outcome)

    def test_goal_phrasing_varies_in_new_categories(self):
        build_corpus(self.store, python=sys.executable,
                     categories={"string_reverse": 1}, levels=(1, 2))
        goals = [r.goal.split(" (benchmark run")[0]
                 for r in self.store.load()]
        self.assertGreater(len(set(goals)), 1)


class TrainingKitTests(unittest.TestCase):
    def test_kit_export_writes_selfcontained_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = export_training_kit(out_dir=Path(tmp) / "kit")
            self.assertEqual(str(Path(tmp) / "kit"), kit["out_dir"])
            script = (Path(tmp) / "kit" / "train_ep1.py").read_text(
                encoding="utf-8")
            readme = (Path(tmp) / "kit" / "README.md").read_text(
                encoding="utf-8")
            self.assertIn("Qwen2.5-Coder-3B-Instruct", script)
            self.assertIn("training.jsonl", script)
            # Colab-found regressions, pinned: the dataset must be
            # conversational dicts (a bare list-of-lists 400s in
            # Dataset.from_list) and T4 has no bf16
            self.assertIn("masked_rows.append(example)", script)
            # transformers v5 batched-return normalization (the
            # 0/116 mask-gate catch)
            self.assertIn('isinstance(full, dict)', script)
            self.assertIn("_to_flat_token_ids", script)
            self.assertIn("first-render shapes", script)
            self.assertIn("KIT_VERSION = \"s76.2\"", script)
            # S76: the generation name is a script argument — outputs
            # land as epN-merged directly (no manual renames)
            self.assertIn('GEN = sys.argv[1] if len(sys.argv) > 1', script)
            self.assertIn('MERGED_DIR = f"{GEN}-merged"', script)
            self.assertIn("fp16=True", script)
            self.assertIn('"use_reentrant": False', script)
            self.assertIn("merge_and_unload", script)
            # verdict-day fixes, pinned: disk-level untie + legacy
            # rope_theta (transformers v5 config format broke ollama's
            # converter -> freq_base 0.0 -> one repeated token)
            self.assertIn('lm_head.weight', script)
            self.assertIn('rope_theta', script)
            # S76: assistant-only loss (gen-8's one variable) with a
            # mask-ratio gate, and the llama.cpp import path (ollama
            # 0.34.4 dropped safetensors import + q4_K_M quantize)
            self.assertIn('-100', script)
            self.assertIn('skip_prepare_dataset', script)
            self.assertIn('assistant-token ratio', script)
            self.assertIn('MASK GATE FAILED', script)
            self.assertIn('convert_hf_to_gguf.py', readme)
            self.assertIn('FROM ./epN.gguf', readme)
            # the kit imports nothing from qacompanion — it runs outside
            # (prose mentions of the repo are fine; imports are not)
            self.assertNotIn("import qacompanion", script)
            self.assertNotIn("from qacompanion", script)
            # the README's eval step references the S74 rate-based
            # verdict harness (compare() was its S57-era phrasing)
            self.assertIn("per-task success rates", readme)
            self.assertIn("repetitions=3", readme)


class SupersedeTests(unittest.TestCase):
    """S68 corpus hygiene: stale-policy demos are tagged and excluded."""

    def _record(self, store, first_tool="read_file", tag_model=True,
                goal="demo task"):
        from qacompanion.agent.experience import Experience
        steps = [{"tool": first_tool, "args": {"path": "x"},
                  "ok": True, "result_head": "ok"}]
        tags = ["autonomous-session", "scripted-demo"] if tag_model \
            else ["autonomous-session"]
        store.record(Experience(
            goal=goal, outcome="success", tags=tags,
            actions=[first_tool],
            context={"tool_calls": steps, "model": "scripted-demo"}))

    def test_old_pattern_and_stale_format_superseded(self):
        from qacompanion.agent.ep1 import VERSION_TAG, mark_superseded_demos
        with tempfile.TemporaryDirectory() as tmp:
            store = ExperienceStore(Path(tmp) / "e.jsonl")
            # read-first without version tag: doubly stale
            self._record(store, first_tool="read_file", goal="task one")
            # list-first but no version tag: stale FORMAT (S69)
            self._record(store, first_tool="list_directory",
                         goal="task two")
            # list-first WITH the current version tag: current, kept
            self._record(store, first_tool="list_directory",
                         goal="task three")
            records = store.load()
            records[-1].tags.append(VERSION_TAG)
            store.save(records)
            # a non-scripted record is never touched
            self._record(store, first_tool="read_file", goal="task four",
                         tag_model=False)
            stats = mark_superseded_demos(store)
            self.assertEqual(4, stats["scanned"])
            self.assertEqual(2, stats["superseded"])
            superseded = [r for r in store.load()
                          if "superseded-pattern" in r.tags]
            self.assertEqual({"task one", "task two"},
                             {r.goal for r in superseded})

    def test_training_excludes_superseded_with_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            curated = Path(tmp) / "curated"
            curated.mkdir(parents=True)
            row = {
                "experience_id": "x1", "session_id": "s1",
                "source": "opencode", "goal": "demo task",
                "outcome": "success", "classification": "SUCCESS",
                "verdict": "ACCEPT",
                "score": {"overall": 0.7, "dimensions": {},
                          "unknown_dims": []},
                "hard_flags": [], "penalties": [], "reasons": [],
                "confidence": 0.9, "times_seen": 1,
                "diversity_score": 0.5, "actions": ["read_file"],
                "failure": None, "diagnosis": None, "resolution": None,
                "verification": {"attempts": [{"ok": True}]},
                "steps": [{"tool": "read_file", "args": {"path": "x"},
                           "ok": True, "result_head": "ok"}],
                "final_answer": "done", "model": "scripted-demo",
                "tags": ["autonomous-session", "scripted-demo",
                         "superseded-pattern"],
            }
            (curated / "trajectory.jsonl").write_text(
                json.dumps(row) + "\n", encoding="utf-8")
            from qacompanion.agent.training import build_records
            records = build_records(curated_dir=curated)
            self.assertFalse(records[0].eligible)
            self.assertTrue(any("superseded-pattern" in r
                                for r in records[0].eligibility_reasons))


class IdempotentRebuildTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.store = ExperienceStore(self.tmp / "exp.jsonl")

    def test_second_rebuild_skips_covered_tasks(self):
        first = build_corpus(self.store, python=sys.executable,
                             categories={"bug_fix": 1}, levels=(3,))
        self.assertEqual(1, first["passed"])
        second = build_corpus(self.store, python=sys.executable,
                              categories={"bug_fix": 1}, levels=(3,))
        self.assertEqual(0, second["runs"], second)
        self.assertEqual(1, second["skipped_existing"])

    def test_stale_goal_gets_redemoed_in_new_style(self):
        from qacompanion.agent.experience import Experience
        goal = ("The test suite in this project fails because add is "
                "implemented incorrectly. Find the bug, fix it, and run "
                "the tests to verify they pass.")
        self.store.record(Experience(
            goal=goal, outcome="success",
            tags=["autonomous-session", "scripted-demo"],
            actions=["read_file"],
            context={"tool_calls": [{"tool": "read_file",
                                     "args": {"path": "math_ops.py"},
                                     "ok": True, "result_head": "x"}],
                     "model": "scripted-demo"}))
        stats = build_corpus(self.store, python=sys.executable,
                             categories={"bug_fix": 1}, levels=(3,))
        # the old goal == the (0,3) task's goal -> re-demoed new-style
        self.assertEqual(1, stats["runs"], stats)
        self.assertEqual(1, stats["superseded"])
        new_record = self.store.load()[-1]
        self.assertEqual("list_directory",
                         new_record.context["tool_calls"][0]["tool"])


    def test_premature_final_recovery_teaches_the_failure_state(self):
        # S72: claim success before acting -> the verifier rejects it ->
        # the real work -> an honest final that admits the premature
        # claim. The run still ends verified-successful.
        script, _files, _goal, tag = build_demo(
            "bug_fix", "premature_final_recovery", 0, 3, sys.executable)
        self.assertEqual("premature_final_recovery", tag)
        finals = [t for t in script
                  if isinstance(t, ModelResponse)]
        self.assertEqual(2, len(finals))
        edit_index = [i for i, t in enumerate(script)
                      if getattr(t, "name", None) == "edit_file"][0]
        premature_index = script.index(finals[0])
        self.assertLess(premature_index, edit_index,
                        "the premature claim must precede any edit")
        self.assertIn("I have corrected", finals[0].text)
        self.assertIn("premature", finals[1].text.lower())

    def test_premature_final_run_passes_end_to_end(self):
        # (variant 0, level 3) cycles to premature_final_recovery under
        # the 4-strategy bug_fix rotation — the loop's verifier must
        # reject the premature final and the run must still complete
        stats = build_corpus(self.store, python=sys.executable,
                             categories={"bug_fix": 1}, levels=(3,))
        self.assertEqual(1, stats["passed"], stats)
        record = self.store.load()[-1]
        self.assertEqual("recovered", record.outcome)
        failures = record.context["verification_failures"]
        self.assertTrue(failures, "the rejected attempt must be captured")
        self.assertIn("I have corrected",
                      failures[0]["premature_final"])
        self.assertIn("Verification failed", failures[0]["detail"])
        self.assertIn("recovery-demo", record.tags)


class VerdictTests(unittest.TestCase):
    """S68: run_verdict with injected fakes — structure + metrics."""

    def test_verdict_structure_and_metrics(self):
        from qacompanion.agent import (FakeModelProvider, ModelResponse,
                                       ToolCall)
        from qacompanion.agent.ep1 import run_verdict

        class _Stateless(FakeModelProvider):
            def __init__(self):
                super().__init__([])

            def generate(self, request):
                has_tool_result = any(m.role == "tool"
                                      for m in request.messages)
                if has_tool_result:
                    return ModelResponse(text="fixed",
                                         finish_reason="stop")
                return ModelResponse(text="", tool_calls=[
                    ToolCall(name="edit_file", arguments={
                        "path": "calculator.py",
                        "old_string": "    return a - b",
                        "new_string": "    return a + b",
                    })], finish_reason="tool_calls")

        with tempfile.TemporaryDirectory() as tmp:
            store = ExperienceStore(Path(tmp) / "e.jsonl")
            verdict = run_verdict({"fake": _Stateless()}, task_count=1,
                                  store=store, max_iterations=6,
                                  ab_demos=True, repetitions=2)
            self.assertEqual(["defect-fix-calculator"], verdict["tasks"])
            self.assertEqual(2, verdict["repetitions"])
            self.assertIn("fake", verdict["results"])
            task_result = verdict["results"]["fake"]["defect-fix-calculator"]
            self.assertEqual(2, len(task_result["runs"]))
            self.assertIn(task_result["success_count"], (0, 1, 2))
            self.assertIn("fake", verdict["metrics"])
            metrics = verdict["metrics"]["fake"]
            self.assertEqual(1.0, metrics["with_calls_rate"])
            pair = verdict["ab_demos"]["fake"]
            self.assertEqual({"without", "with"}, set(pair))

    def test_format_verdict_lines(self):
        from qacompanion.agent.ep1 import format_verdict
        verdict = {"tasks": ["t1"], "repetitions": 3,
                   "results": {"m": {"t1": {
                       "success_count": 1, "success_rate": 0.3333,
                       "runs": [
                           {"success": True,
                            "termination_reason": "goal completed",
                            "iterations": 7, "tool_calls": 6,
                            "tool_failures": 0},
                           {"success": False,
                            "termination_reason": "max iterations",
                            "iterations": 12, "tool_calls": 10,
                            "tool_failures": 3},
                           {"success": False,
                            "termination_reason": "max iterations",
                            "iterations": 12, "tool_calls": 9,
                            "tool_failures": 2}]}}},
                   "metrics": {"m": {"runs": 3, "with_calls_rate": 1.0,
                                     "discovery_first_rate": 0.0,
                                     "success_rate": 0.3333,
                                     "guessed_path_rate": 0.0,
                                     "diagnosis_chaining_rate": 1.0,
                                     "tool_failures": 5}}}
        text = format_verdict(verdict)
        self.assertIn("generation verdict (n=3):", text)
        self.assertIn("m / t1: 1/3 SUCCESS | rate=0.3333", text)
        self.assertIn("run 1: SUCCESS", text)
        self.assertIn("run 3: FAILED", text)
        self.assertIn("metrics m:", text)


class ReportFormatTests(unittest.TestCase):
    def test_report_lists_failures_honestly(self):
        stats = {"runs": 2, "passed": 1, "failed": 1, "recovery": 1,
                 "durations_s": 12.5,
                 "by_category": {"bug_fix": {"runs": 2, "passed": 1,
                                             "recovery": 1}},
                 "tasks": [{"category": "bug_fix", "strategy": "explore_clean",
                            "variant": 0, "level": 1, "goal": "g",
                            "success": True, "iterations": 5,
                            "termination": "goal completed"},
                           {"category": "bug_fix",
                            "strategy": "tests_first_recovery",
                            "variant": 1, "level": 2, "goal": "g2",
                            "success": False, "iterations": 6,
                            "termination": "verification failed"}]}
        text = format_corpus_report(stats)
        self.assertIn("passed: 1", text)
        self.assertIn("recovery-strategy: 1", text)
        self.assertIn("FAILED bug_fix/tests_first_recovery", text)

    def test_report_notes_all_verified(self):
        stats = {"runs": 1, "passed": 1, "failed": 0, "recovery": 0,
                 "durations_s": 3.0, "by_category": {},
                 "tasks": [{"category": "bug_fix", "strategy": "explore_clean",
                            "variant": 0, "level": 1, "goal": "g",
                            "success": True, "iterations": 5,
                            "termination": "goal completed"}]}
        self.assertIn("all demonstrations verified",
                      format_corpus_report(stats))


if __name__ == "__main__":
    unittest.main()
