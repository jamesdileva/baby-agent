"""S64/S66 ep1 corpus builder tests: scripted curriculum demonstrators
through the REAL loop, honest provenance, strategy diversity, training
kit export.
"""

import json
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent.curation import TrajectoryCurator
from qacompanion.agent.ep1 import (
    DEMO_MODEL_TAG, STRATEGIES, ScriptedDemonstrator, build_corpus,
    build_demo, export_training_kit, format_corpus_report)
from qacompanion.agent.experience import ExperienceStore
from qacompanion.agent.training import build_training
from qacompanion.agent.curriculum import bug_fix_defect
import sys


class DemonstratorTests(unittest.TestCase):
    """S66 contract: explore-first scripts, strategy diversity."""

    def test_explore_clean_starts_with_discovery(self):
        script, files, goal, tag = build_demo(
            "bug_fix", "explore_clean", 0, 3, sys.executable)
        self.assertEqual("explore_clean", tag)
        self.assertEqual("list_directory", script[0].name)
        self.assertEqual("read_file", script[1].name)
        edit = [t for t in script
                if getattr(t, "name", None) == "edit_file"][0]
        _module, func, good, bad = bug_fix_defect(0)
        self.assertEqual(bad, edit.arguments["old_string"])
        self.assertEqual(good, edit.arguments["new_string"])
        self.assertIn(func, script[-1].text)
        # every read/edit targets the DISCOVERED module, no guesses
        calls = [t for t in script if getattr(t, "name", None) in
                 ("read_file", "edit_file")]
        self.assertTrue(all("src/" not in str(t.arguments.get("path", ""))
                            for t in calls))

    def test_explore_recovery_embeds_a_real_wrong_turn(self):
        script, _files, _goal, tag = build_demo(
            "bug_fix", "explore_recovery", 1, 1, sys.executable)
        self.assertEqual("explore_recovery", tag)
        reads = [t for t in script
                 if getattr(t, "name", None) == "read_file"]
        self.assertTrue(any(str(t.arguments["path"]).startswith("src/")
                            for t in reads),
                        "recovery scripts must contain the wrong turn")

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
        self.assertEqual("success", record.outcome)
        self.assertIn(DEMO_MODEL_TAG, record.tags)
        self.assertIn("(benchmark run", record.goal)
        # S66: EXPLORE-FIRST — the first captured step is discovery
        steps = record.context["tool_calls"]
        self.assertEqual("list_directory", steps[0]["tool"])
        self.assertTrue(steps[0]["ok"])
        edit = [s for s in steps if s["tool"] == "edit_file"][0]
        self.assertTrue(edit["ok"])
        self.assertIn("implemented incorrectly",
                      record.context["final_answer"])

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
        build_corpus(self.store, python=sys.executable,
                     categories={"bug_fix": 1}, levels=(2,))
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
            self.assertIn('{"messages": r["messages"]}', script)
            self.assertIn("fp16=True", script)
            self.assertIn('"use_reentrant": False', script)
            self.assertIn("merge_and_unload", script)
            # verdict-day fixes, pinned: disk-level untie + legacy
            # rope_theta (transformers v5 config format broke ollama's
            # converter -> freq_base 0.0 -> one repeated token)
            self.assertIn('lm_head.weight', script)
            self.assertIn('rope_theta', script)
            # the kit imports nothing from qacompanion — it runs outside
            # (prose mentions of the repo are fine; imports are not)
            self.assertNotIn("import qacompanion", script)
            self.assertNotIn("from qacompanion", script)
            self.assertIn("compare()", readme)


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
