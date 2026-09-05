"""S50 learning-from-sessions tests: classification, capture, curation,
miner enrichment. All hermetic."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import (
    AgentConfig,
    AgentState,
    FakeModelProvider,
    ModelResponse,
    ToolCall,
    Workspace,
)
from qacompanion.agent.benchmark import run_benchmark
from qacompanion.agent.experience import Experience, ExperienceStore
from qacompanion.agent.opencode_mine import OpencodeMiner
from qacompanion.agent.session_learning import (
    classify_outcome,
    curate,
    record_session,
    session_to_experience,
    write_resume_skill,
)
from qacompanion.agent.session import AgentSession

SCHEMA = """
CREATE TABLE session (id TEXT PRIMARY KEY, directory TEXT, title TEXT,
                      time_created INTEGER);
CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT,
                      time_created INTEGER, data TEXT);
CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,
                   time_created INTEGER, data TEXT);
"""


def _session(state=AgentState.COMPLETED, verifications=None,
             with_advice=False, tool_calls=1):
    session = AgentSession(goal="fix the login bug")
    session.state = state
    session.verification_results = verifications or []
    session.iterations = 3
    session.tool_calls = [ToolCall(name="read_file", arguments={}),
                          ToolCall(name="edit_file", arguments={}),
                          ToolCall(name="run_tests", arguments={})][:tool_calls]
    session.observations = []
    if with_advice:
        session.messages.append(__import__(
            "qacompanion.agent", fromlist=["ModelMessage"]).ModelMessage(
            role="system",
            content=json.dumps({"qa_memory": {
                "source": "case", "diagnosis": "guard the denominator"}})))
    return session


class TestClassification(unittest.TestCase):
    def test_matrix(self):
        verified_ok = [{"ok": True, "detail": "d"}]
        recovered = [{"ok": False}, {"ok": True}]
        s = _session(state=AgentState.COMPLETED, verifications=verified_ok)
        self.assertEqual(classify_outcome(s), "success")
        s = _session(state=AgentState.COMPLETED, verifications=recovered)
        self.assertEqual(classify_outcome(s), "recovered")
        s = _session(state=AgentState.FAILED)
        self.assertEqual(classify_outcome(s), "failed")
        s = _session(state=AgentState.CANCELLED)
        self.assertEqual(classify_outcome(s), "partial")

    def test_unverified_completion_is_honest_partial(self):
        s = _session(state=AgentState.COMPLETED, verifications=[])
        self.assertEqual(classify_outcome(s), "partial")


class TestSessionToExperience(unittest.TestCase):
    def test_capture_with_advice_harvest(self):
        session = _session(
            state=AgentState.COMPLETED,
            verifications=[{"ok": True}],
            with_advice=True,
            tool_calls=3)
        experience = session_to_experience(session, model="qwen2.5-coder:1.5b")
        self.assertEqual(experience.goal, "fix the login bug")
        self.assertEqual(experience.outcome, "success")
        self.assertEqual(experience.actions,
                         ["read_file", "edit_file", "run_tests"])
        self.assertEqual(experience.diagnosis, "guard the denominator")
        self.assertIn("autonomous-session", experience.tags)
        self.assertIn("qwen2.5-coder:1.5b", experience.tags)
        self.assertEqual(experience.session_id, session.session_id)

    def test_unverified_tagged(self):
        session = _session(state=AgentState.COMPLETED, verifications=[])
        experience = session_to_experience(session)
        self.assertEqual(experience.outcome, "partial")
        self.assertIn("unverified", experience.tags)

    def test_record_session_persists(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            store = ExperienceStore(tmp / "experience.jsonl")
            record_session(_session(state=AgentState.FAILED), store,
                           model="m1")
            loaded = store.load()
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].outcome, "failed")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestCurator(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.skill_dir = self.tmp / "skills" / "agent"
        self.store = ExperienceStore(self.tmp / "experience.jsonl")
        self.store.record(Experience(goal="hello", outcome="success"))
        self.store.record(Experience(
            goal="Your previous response was interrupted. Continue where "
                 "you left off",
            outcome="partial"))
        self.store.record(Experience(goal="fix the divide by zero crash",
                                     outcome="recovered"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_backlog_rules_applied(self):
        stats = curate(self.store, skill_dir=self.skill_dir)
        self.assertEqual(stats["before"], 3)
        self.assertEqual(stats["removed_greeting"], 1)
        self.assertEqual(stats["removed_resume_pattern"], 1)
        self.assertEqual(stats["kept"], 1)
        remaining = [e.goal for e in self.store.load()]
        self.assertEqual(remaining, ["fix the divide by zero crash"])

    def test_resume_skill_seed_written(self):
        curate(self.store, skill_dir=self.skill_dir)
        seed = self.skill_dir / "resume_interrupted_task.json"
        self.assertTrue(seed.exists())
        skill = json.loads(seed.read_text(encoding="utf-8"))
        self.assertEqual(skill["name"], "resume_interrupted_task")
        for field in ("goal", "description", "required_tools",
                      "preconditions", "procedure", "verification",
                      "failure_modes", "examples", "confidence"):
            self.assertIn(field, skill)

    def test_curation_is_idempotent(self):
        curate(self.store, skill_dir=self.skill_dir)
        stats = curate(self.store, skill_dir=self.skill_dir)
        self.assertEqual(stats["removed_greeting"], 0)
        self.assertEqual(stats["removed_resume_pattern"], 0)
        self.assertEqual(stats["kept"], 1)


class TestMinerEnrichment(unittest.TestCase):
    def setUp(self):
        import shutil
        self.tmp = Path(tempfile.mkdtemp())
        self._shutil = shutil
        self.db = self.tmp / "opencode.db"
        con = sqlite3.connect(self.db)
        con.executescript(SCHEMA)
        # session with error output followed by a patch
        con.execute("INSERT INTO session VALUES (?, ?, ?, ?)",
                    ("ses_fix", "C:/Users/j/Projects/demo", "fix it", 1000))
        con.execute("INSERT INTO message VALUES (?, ?, ?, ?)",
                    ("m1", "ses_fix", 1001, json.dumps(
                        {"role": "user", "time": {}})))
        con.execute("INSERT INTO part VALUES (?, ?, ?, ?, ?)",
                    ("p1", "m1", "ses_fix", 1002, json.dumps(
                        {"type": "text",
                         "text": "the importer crashes on bad rows"})))
        con.execute("INSERT INTO part VALUES (?, ?, ?, ?, ?)",
                    ("p2", "m1", "ses_fix", 1003, json.dumps(
                        {"type": "tool", "tool": "bash",
                         "state": {"status": "completed",
                                   "output": "Traceback (most recent "
                                             "call last):\nImportError: no "
                                             "module named x"}})))
        con.execute("INSERT INTO part VALUES (?, ?, ?, ?, ?)",
                    ("p3", "m1", "ses_fix", 1004, json.dumps(
                        {"type": "patch", "diff": "..."})))
        # session with error but NO patch: no resolution claim
        con.execute("INSERT INTO session VALUES (?, ?, ?, ?)",
                    ("ses_broken", "C:/Users/j/Projects/demo2", "still broken",
                     2000))
        con.execute("INSERT INTO message VALUES (?, ?, ?, ?)",
                    ("m2", "ses_broken", 2001, json.dumps(
                        {"role": "user", "time": {}})))
        con.execute("INSERT INTO part VALUES (?, ?, ?, ?, ?)",
                    ("p4", "m2", "ses_broken", 2002, json.dumps(
                        {"type": "text",
                         "text": "still crashes on import"})))
        con.execute("INSERT INTO part VALUES (?, ?, ?, ?, ?)",
                    ("p5", "m2", "ses_broken", 2003, json.dumps(
                        {"type": "tool", "tool": "bash",
                         "state": {"status": "completed",
                                   "output": "ImportError: no module named y"}})))
        con.commit()
        con.close()

    def tearDown(self):
        self._shutil.rmtree(self.tmp, ignore_errors=True)

    def test_error_then_patch_yields_resolution(self):
        miner = OpencodeMiner(self.db)
        row = next(r for r in miner.sessions() if r["id"] == "ses_fix")
        experience = miner.mine_session(row)
        self.assertIn("ImportError", (experience.failure or ""))
        self.assertEqual(experience.resolution, "fix applied via patch")

    def test_error_without_patch_makes_no_resolution_claim(self):
        miner = OpencodeMiner(self.db)
        row = next(r for r in miner.sessions() if r["id"] == "ses_broken")
        experience = miner.mine_session(row)
        self.assertIn("ImportError", (experience.failure or ""))
        self.assertIsNone(experience.resolution)


class TestBenchmarkRecords(unittest.TestCase):
    def test_success_run_records_experience(self):
        import sys
        store = ExperienceStore(Path(tempfile.mkdtemp()) / "e.jsonl")
        PY = f'"{sys.executable}"'
        provider = FakeModelProvider([
            ToolCall(name="read_file", arguments={"path": "calculator.py"}),
            ToolCall(name="run_tests", arguments={"command": f"{PY} -m unittest"}),
            ToolCall(name="edit_file", arguments={
                "path": "calculator.py",
                "old_string": "    return a - b",
                "new_string": "    return a + b"}),
            ToolCall(name="run_tests", arguments={"command": f"{PY} -m unittest"}),
            ModelResponse(text="fixed", finish_reason="stop"),
        ])
        report = run_benchmark(provider, experience_store=store)
        self.assertTrue(report.success)
        experiences = store.load()
        self.assertEqual(len(experiences), 1)
        self.assertEqual(experiences[0].outcome, "success")
        self.assertEqual(experiences[0].goal, report.goal)

    def test_recovered_run_classified_as_recovered(self):
        import sys
        store = ExperienceStore(Path(tempfile.mkdtemp()) / "e.jsonl")
        PY = f'"{sys.executable}"'
        provider = FakeModelProvider([
            ModelResponse(text="Done!", finish_reason="stop"),
            ToolCall(name="edit_file", arguments={
                "path": "calculator.py",
                "old_string": "    return a - b",
                "new_string": "    return a + b"}),
            ModelResponse(text="Now it passes.", finish_reason="stop"),
        ])
        report = run_benchmark(provider, experience_store=store)
        self.assertTrue(report.success)
        self.assertEqual(store.load()[0].outcome, "recovered")


if __name__ == "__main__":
    unittest.main()
