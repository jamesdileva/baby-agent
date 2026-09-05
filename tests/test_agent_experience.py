"""S47 experience memory tests: store, reinforcement, retrieval, unified
MemoryLayer, tools. All hermetic with temp files."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import ToolCall, ToolRegistry, Workspace
from qacompanion.agent.experience import (
    Experience,
    ExperienceError,
    ExperienceStore,
    MemoryLayer,
    MemoryToolkit,
    _normalize_goal,
)
from qacompanion.agent.fs_tools import agent_registry
from qacompanion.skills import digest as digest_mod
from qacompanion.skills import journal as journal_mod
from qacompanion.store import CaseStore

RECOVERY = Experience(
    goal="fix failing websocket reconnect test",
    outcome="recovered",
    diagnosis="client reused a closed session object",
    resolution="recreate the session inside the retry loop",
    tags=["websocket", "reconnect", "test-failure"],
    confidence=0.8,
)


class ExperienceBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store_path = self.tmp / "experience.jsonl"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestExperienceRecord(unittest.TestCase):
    def test_round_trip_non_ascii(self):
        e = Experience(goal="déjà vu 处理 ✅", outcome="success")
        restored = Experience.from_dict(json.loads(json.dumps(e.to_dict())))
        self.assertEqual(restored.goal, e.goal)
        self.assertEqual(restored.experience_id, e.experience_id)

    def test_strict_validation(self):
        with self.assertRaises(ValueError):
            Experience(goal="   ", outcome="success")
        with self.assertRaises(ValueError):
            Experience(goal="g", outcome="vibes")
        with self.assertRaises(ValueError):
            Experience(goal="g", outcome="success", confidence=1.5)
        with self.assertRaises(ValueError):
            Experience.from_dict(["not", "an", "object"])
        with self.assertRaises(ValueError):
            Experience.from_dict({"goal": "g"})

    def test_normalize_goal(self):
        self.assertEqual(_normalize_goal("Fix: Failing-Test!"),
                         _normalize_goal("fix failing test"))


class TestExperienceStore(ExperienceBase):
    def test_persist_and_reload(self):
        store = ExperienceStore(self.store_path)
        store.record(RECOVERY)
        reloaded = ExperienceStore(self.store_path).load()
        self.assertEqual(len(reloaded), 1)
        self.assertEqual(reloaded[0].goal, RECOVERY.goal)
        self.assertEqual(reloaded[0].diagnosis, RECOVERY.diagnosis)

    def test_recurrence_reinforces_not_duplicates(self):
        store = ExperienceStore(self.store_path)
        first = store.record(Experience(
            goal="Fix failing websocket reconnect test!",
            outcome="failed"))
        second = store.record(Experience(
            goal="fix failing websocket reconnect test",
            outcome="recovered", confidence=0.9))
        self.assertEqual(first.experience_id, second.experience_id)
        self.assertEqual(second.times_seen, 2)
        self.assertEqual(second.outcome, "recovered")
        self.assertEqual(len(store.load()), 1)

    def test_distinct_goals_append(self):
        store = ExperienceStore(self.store_path)
        store.record(Experience(goal="a", outcome="success"))
        store.record(Experience(goal="completely different", outcome="failed"))
        self.assertEqual(len(store.load()), 2)

    def test_bom_and_crlf_tolerated(self):
        self.store_path.write_bytes(
            b"\xef\xbb\xbf" + json.dumps(RECOVERY.to_dict()).encode("utf-8")
            + b"\r\n")
        loaded = ExperienceStore(self.store_path).load()
        self.assertEqual(len(loaded), 1)

    def test_malformed_line_is_strict(self):
        self.store_path.write_text("not json\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            ExperienceStore(self.store_path).load()

    def test_missing_store_is_empty(self):
        self.assertEqual(ExperienceStore(self.tmp / "nope.jsonl").load(), [])


class TestRetrieval(ExperienceBase):
    def test_keyword_ranking(self):
        store = ExperienceStore(self.store_path)
        store.record(RECOVERY)
        store.record(Experience(
            goal="center a css grid layout",
            outcome="success", tags=["css", "layout"]))
        matches = store.find_similar("websocket reconnect keeps failing")
        self.assertEqual(matches[0].goal, RECOVERY.goal)

    def test_times_seen_boosts_rank(self):
        store = ExperienceStore(self.store_path)
        store.record(Experience(goal="deploy via docker compose",
                                outcome="success", confidence=0.5))
        recurring = store.record(Experience(goal="deploy via docker compose",
                                            outcome="success",
                                            confidence=0.5))
        self.assertGreaterEqual(recurring.times_seen, 2)
        matches = store.find_similar("how do I deploy docker")
        self.assertEqual(matches[0].goal, "deploy via docker compose")

    def test_k_limit_and_empty_store(self):
        store = ExperienceStore(self.store_path)
        self.assertEqual(store.find_similar("anything"), [])
        for i in range(4):
            store.record(Experience(goal=f"websocket issue {i}",
                                    outcome="recovered"))
        self.assertEqual(len(store.find_similar("websocket", k=2)), 2)


class TestMemoryLayer(ExperienceBase):
    def setUp(self):
        super().setUp()
        self.cases_path = self.tmp / "cases.jsonl"
        self.digest_path = self.tmp / "digest.jsonl"
        self.journal_path = self.tmp / "journal.md"
        CaseStore(self.cases_path).record(
            "ZeroDivisionError: division by zero", "traceback",
            "guard the denominator before dividing", by="test")
        digest_mod.DigestStore(self.digest_path).add(
            "deploy.md", "Deploy", "Deploy with docker compose up -d.")
        journal_mod.add("VOID-L1 residual: BOM in configs breaks JSONL",
                        ledger=str(self.journal_path))
        self.store = ExperienceStore(self.store_path)
        self.store.record(RECOVERY)
        self.layer = MemoryLayer(
            experience_store=self.store, cases_path=self.cases_path,
            digest_path=self.digest_path, journal_path=self.journal_path)

    def test_merged_results_are_source_labeled(self):
        results = self.layer.search("websocket")
        self.assertTrue(results)
        self.assertEqual(results[0]["source"], "experience")

        results = self.layer.search("ZeroDivisionError")
        sources = {r["source"] for r in results}
        self.assertIn("case", sources)

        results = self.layer.search("docker compose")
        sources = {r["source"] for r in results}
        self.assertIn("doc", sources)

        results = self.layer.search("BOM")
        sources = {r["source"] for r in results}
        self.assertIn("journal", sources)

    def test_missing_stores_degrade_to_empty(self):
        bare = MemoryLayer(
            experience_store=ExperienceStore(self.tmp / "none.jsonl"),
            cases_path=self.tmp / "no-cases.jsonl",
            digest_path=self.tmp / "no-digest.jsonl",
            journal_path=self.tmp / "no-journal.md")
        self.assertEqual(bare.search("anything at all"), [])


class TestMemoryTools(ExperienceBase):
    def setUp(self):
        super().setUp()
        self.ws = Workspace(self.tmp)
        self.toolkit = MemoryToolkit(
            ExperienceStore(self.store_path),
            cases_path=self.tmp / "cases.jsonl",
            digest_path=self.tmp / "digest.jsonl",
            journal_path=self.tmp / "journal.md")
        self.reg = ToolRegistry()
        for tool in self.toolkit.tools():
            self.reg.register(tool)

    def test_side_effect_matrix(self):
        described = {d["name"]: d for d in self.reg.describe()}
        self.assertEqual(
            set(described),
            {"experience_record", "experience_search", "memory_search"},
        )
        self.assertEqual(described["experience_record"]["side_effect_level"],
                         "SAFE_WRITE")
        for name in ("experience_search", "memory_search"):
            self.assertEqual(described[name]["side_effect_level"], "READ_ONLY")
        self.assertTrue(all(not d["requires_workspace"]
                            for d in described.values()))

    def test_record_and_search_through_registry(self):
        out = self.call("experience_record",
                        goal="fix flaky login test",
                        outcome="recovered",
                        diagnosis="test order dependency",
                        resolution="reset session between tests",
                        tags=["flaky"])
        self.assertTrue(out.ok, out.error)
        payload = json.loads(out.output)
        self.assertEqual(payload["times_seen"], 1)

        search = self.payload("experience_search", query="flaky login test")
        self.assertEqual(search["count"], 1)
        self.assertEqual(search["experiences"][0]["outcome"], "recovered")

    def test_invalid_outcome_structured_error(self):
        out = self.call("experience_record", goal="g", outcome="vibes")
        self.assertFalse(out.ok)
        self.assertIn("invalid experience record", out.error)

    def test_memory_search_through_registry(self):
        self.payload("experience_record", goal="port already in use fix",
                     outcome="success", resolution="kill the stale server")
        results = self.payload("memory_search", query="port already in use")
        self.assertTrue(results["results"])
        self.assertEqual(results["results"][0]["source"], "experience")

    def call(self, name, **arguments):
        return self.reg.execute(ToolCall(name=name, arguments=arguments),
                                workspace=self.ws)

    def payload(self, name, **arguments):
        out = self.call(name, **arguments)
        self.assertTrue(out.ok, f"{name} failed: {out.error}")
        return json.loads(out.output)


class TestAgentRegistryIncludesMemory(unittest.TestCase):
    def test_membership(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            reg = agent_registry(
                Workspace(tmp), experience_store=ExperienceStore(
                    tmp / "experience.jsonl"))
            for name in ("experience_record", "experience_search",
                         "memory_search"):
                self.assertIn(name, reg.names())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
