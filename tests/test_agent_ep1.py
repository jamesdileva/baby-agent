"""S64 ep1 corpus builder tests: scripted curriculum demonstrators
through the REAL loop, honest provenance, training kit export.
"""

import json
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent.curation import TrajectoryCurator
from qacompanion.agent.ep1 import (
    DEMO_MODEL_TAG, ScriptedDemonstrator, build_corpus,
    export_training_kit, format_corpus_report)
from qacompanion.agent.experience import ExperienceStore
from qacompanion.agent.training import build_training
from qacompanion.agent.curriculum import bug_fix_defect
import sys


class DemonstratorTests(unittest.TestCase):
    def test_script_fixes_the_declared_defect(self):
        module, func, good, bad = bug_fix_defect(0)
        demo = ScriptedDemonstrator(
            module_file=f"{module}.py", test_command='"py" -m unittest',
            old_string=bad, new_string=good,
            diagnosis=f"{func} was implemented incorrectly.")
        script = demo._script
        self.assertEqual(5, len(script))
        self.assertEqual("read_file", script[0].name)
        self.assertEqual("run_tests", script[1].name)
        edit = script[2]
        self.assertEqual("edit_file", edit.name)
        self.assertEqual(bad, edit.arguments["old_string"])
        self.assertEqual(good, edit.arguments["new_string"])
        self.assertEqual("run_tests", script[3].name)
        self.assertIn(func, script[4].text)


class CorpusChainTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.store = ExperienceStore(self.tmp / "exp.jsonl")

    def test_single_run_yields_verified_scripted_record(self):
        stats = build_corpus(self.store, python=sys.executable,
                             variants=(0,), levels=(1,))
        self.assertEqual(1, stats["runs"])
        self.assertEqual(1, stats["passed"], stats)
        records = self.store.load()
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual("success", record.outcome)
        self.assertIn(DEMO_MODEL_TAG, record.tags)
        self.assertTrue(record.goal.startswith(
            "The test suite in this project fails because"))
        self.assertIn("(benchmark run", record.goal)
        # step capture: inspect -> fail -> edit -> pass
        steps = record.context["tool_calls"]
        self.assertEqual(4, len(steps))
        self.assertEqual("edit_file", steps[2]["tool"])
        self.assertTrue(steps[3]["ok"])
        self.assertIn("implemented incorrectly",
                      record.context["final_answer"])

    def test_full_chain_to_step_trainable_training_record(self):
        build_corpus(self.store, python=sys.executable,
                     variants=(1,), levels=(2,))
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
        self.assertIn("[TOOL: read_file(", assistants[0]["content"])
        self.assertIn("scripted-demo", json.dumps(chat["metadata"]))


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
            self.assertIn("merge_and_unload", script)
            # the kit imports nothing from qacompanion — it runs outside
            # (prose mentions of the repo are fine; imports are not)
            self.assertNotIn("import qacompanion", script)
            self.assertNotIn("from qacompanion", script)
            self.assertIn("compare()", readme)


class ReportFormatTests(unittest.TestCase):
    def test_report_lists_failures_honestly(self):
        stats = {"runs": 2, "passed": 1, "failed": 1, "durations_s": 12.5,
                 "tasks": [{"variant": 0, "level": 1, "goal": "g",
                            "success": True, "iterations": 5,
                            "termination": "goal completed"},
                           {"variant": 1, "level": 2, "goal": "g2",
                            "success": False, "iterations": 6,
                            "termination": "verification failed"}]}
        text = format_corpus_report(stats)
        self.assertIn("passed: 1", text)
        self.assertIn("FAILED variant=1 level=2", text)

    def test_report_notes_all_verified(self):
        stats = {"runs": 1, "passed": 1, "failed": 0, "durations_s": 3.0,
                 "tasks": [{"variant": 0, "level": 1, "goal": "g",
                            "success": True, "iterations": 5,
                            "termination": "goal completed"}]}
        self.assertIn("all demonstrations verified",
                      format_corpus_report(stats))


if __name__ == "__main__":
    unittest.main()
