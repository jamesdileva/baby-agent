"""S47.1 opencode mining tests: synthetic fixture DB with the real schema.

The REAL opencode database is never touched by the suite.
"""

import hashlib
import json
import sqlite3
import unittest
from pathlib import Path

from qacompanion.agent.experience import ExperienceStore
from qacompanion.agent.opencode_mine import MiningError, OpencodeMiner

SCHEMA = """
CREATE TABLE session (id TEXT PRIMARY KEY, directory TEXT, title TEXT,
                      time_created INTEGER);
CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT,
                      time_created INTEGER, data TEXT);
CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,
                   time_created INTEGER, data TEXT);
"""

NOW = 1_700_000_000_000


def _write_db(path: Path) -> dict:
    """Build the synthetic fixture. Returns useful ids."""
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    ids = {}

    def session(sid, directory, title):
        con.execute("INSERT INTO session VALUES (?,?,?,?)",
                    (sid, directory, title, NOW))

    def message(mid, sid, role, offset=0):
        con.execute("INSERT INTO message VALUES (?,?,?,?)",
                    (mid, sid, NOW + offset, json.dumps({
                        "role": role, "time": {"created": NOW + offset}})))

    def part(pid, mid, sid, data, offset=0):
        con.execute("INSERT INTO part VALUES (?,?,?,?,?)",
                    (pid, mid, sid, NOW + offset, json.dumps(data)))

    # marathon session: goal text, tools, more text
    session("ses_marathon", "C:/Users/j/Projects/surfhop",
            "Build the surf session tracker")
    message("m1", "ses_marathon", "user")
    part("p1", "m1", "ses_marathon",
         {"type": "text", "text": "Build a surf session tracker with maps"},
         1)
    message("m2", "ses_marathon", "assistant", 2)
    part("p2", "m2", "ses_marathon", {"type": "step-start"}, 3)
    part("p3", "m2", "ses_marathon",
         {"type": "tool", "tool": "write",
          "state": {"status": "completed"}}, 4)
    message("m3", "ses_marathon", "user", 5)
    part("p4", "m3", "ses_marathon",
         {"type": "tool", "tool": "bash", "state": {"status": "completed"}}, 6)
    part("p5", "m3", "ses_marathon",
         {"type": "text", "text": "why did the build fail?"}, 7)
    ids["marathon"] = "ses_marathon"

    # turn-spawn pair: identical goals -> reinforcement
    for i, sid in enumerate(("ses_turn1", "ses_turn2")):
        session(sid, "C:/Users/j/AppData/Roaming/@antfarm/shell/antfarm-home",
                "Continue the migration task")
        message(f"tm{i}a", sid, "user")
        part(f"tp{i}a", f"tm{i}a", sid,
             {"type": "text", "text": "Continue the migration task"}, i * 10)
        message(f"tm{i}b", sid, "assistant", i * 10 + 1)
        part(f"tp{i}b", f"tm{i}b", sid,
             {"type": "tool", "tool": "read", "state": {"status": "completed"}},
             i * 10 + 2)
    ids["turns"] = ["ses_turn1", "ses_turn2"]

    # trivial session: no user text, no tools
    session("ses_trivial", "C:/Users/j/Projects/surfhop", "New session")
    message("m_triv", "ses_trivial", "user")
    part("p_triv", "m_triv", "ses_trivial", {"type": "step-start"}, 1)
    ids["trivial"] = "ses_trivial"

    # boilerplate-only session: antfarm kickoff preamble, no real goal
    session("ses_boiler", "C:/Users/j/AppData/Roaming/@antfarm/shell",
            "SITUATION REPORT turn")
    message("m_boil", "ses_boiler", "user")
    part("p_boil1", "m_boil", "ses_boiler",
         {"type": "text",
          "text": "SITUATION REPORT - agent-a  PROJECT GOAL (authored by"
                  " the human; treat as context)"}, 1)
    part("p_boil2", "m_boil", "ses_boiler",
         {"type": "tool", "tool": "read", "state": {"status": "completed"}}, 2)
    ids["boilerplate"] = "ses_boiler"

    # goal-less but SUBSTANTIAL session: crash-and-continue sprint chunk
    session("ses_nogoal", "C:/Users/j/Projects/surfhop", "New session - 2026")
    con.execute("INSERT INTO message VALUES (?, ?, ?, ?)",
                ("m_ng", "ses_nogoal", 3000, json.dumps(
                    {"role": "user", "time": {}})))
    part("p_ng0", "m_ng", "ses_nogoal",
         {"type": "text", "text": "continue"}, 3001)
    for i in range(120):
        con.execute("INSERT INTO part VALUES (?, ?, ?, ?, ?)",
                    (f"p_ng{i+1}", "m_ng", "ses_nogoal", 3002 + i, json.dumps(
                        {"type": "tool", "tool": "edit",
                         "state": {"status": "completed"}})))

    # missing-directory session (project gone)
    session("ses_ghost", "C:/Users/j/VanishedProject", "fix the thing")
    message("m_ghost", "ses_ghost", "user")
    part("p_ghost1", "m_ghost", "ses_ghost",
         {"type": "text", "text": "fix the vanished project"}, 1)
    part("p_ghost2", "m_ghost", "ses_ghost",
         {"type": "tool", "tool": "edit", "state": {"status": "completed"}}, 2)
    ids["ghost"] = "ses_ghost"

    con.commit()
    con.close()
    return ids


class MineTestBase(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "opencode.db"
        self.ids = _write_db(self.db)
        self.store = ExperienceStore(self.tmp / "experience.jsonl")
        self.miner = OpencodeMiner(self.db)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestMinerBasics(MineTestBase):
    def test_missing_db_is_structured_error(self):
        with self.assertRaises(MiningError):
            OpencodeMiner(self.tmp / "nope.db")

    def test_sessions_listing_and_filter(self):
        self.assertEqual(len(self.miner.sessions()), 7)
        surf = self.miner.sessions(directory="C:/Users/j/Projects/surfhop")
        self.assertEqual([r["id"] for r in surf],
                         ["ses_marathon", "ses_trivial", "ses_nogoal"])

    def test_goal_from_first_user_text(self):
        row = next(r for r in self.miner.sessions()
                   if r["id"] == "ses_marathon")
        experience = self.miner.mine_session(row)
        self.assertEqual(experience.goal,
                         "Build a surf session tracker with maps")
        self.assertEqual(experience.outcome, "partial")
        self.assertEqual(experience.session_id, "ses_marathon")

    def test_actions_ordered_and_volume_recorded(self):
        row = next(r for r in self.miner.sessions()
                   if r["id"] == "ses_marathon")
        experience = self.miner.mine_session(row)
        self.assertEqual(experience.actions, ["write", "bash"])
        context = experience.context
        self.assertEqual(context["source"], "opencode")
        self.assertEqual(context["message_count"], 3)
        self.assertEqual(context["part_count"], 5)
        self.assertEqual(context["tool_count"], 2)

    def test_missing_project_directory_omits_metadata(self):
        row = next(r for r in self.miner.sessions()
                   if r["id"] == "ses_ghost")
        experience = self.miner.mine_session(row)
        self.assertEqual(experience.project_type, None)
        self.assertEqual(experience.languages, [])
        self.assertIsNotNone(experience.goal)

    def test_trivial_session_skipped(self):
        row = next(r for r in self.miner.sessions()
                   if r["id"] == "ses_trivial")
        self.assertIsNone(self.miner.mine_session(row))

    def test_boilerplate_only_session_skipped(self):
        # antfarm's injected preamble is template, not a task goal
        row = next(r for r in self.miner.sessions()
                   if r["id"] == "ses_boiler")
        self.assertIsNone(self.miner.mine_session(row))

    def test_goal_less_substantial_session_mined_with_placeholder(self):
        # crash-and-continue chunks with real work are worth keeping even
        # without a stated goal (the "continue" itself is boilerplate)
        row = next(r for r in self.miner.sessions()
                   if r["id"] == "ses_nogoal")
        experience = self.miner.mine_session(row)
        self.assertIsNotNone(experience)
        self.assertEqual(experience.goal,
                         "continued prior work (session had no stated goal)")
        self.assertIn("goal-less", experience.tags)
        self.assertEqual(experience.context["part_count"], 121)


class TestMineRun(MineTestBase):
    def test_dry_run_writes_nothing(self):
        stats = self.miner.mine(store=self.store, dry_run=True)
        self.assertTrue(stats["dry_run"])
        self.assertEqual(stats["sessions_seen"], 7)
        self.assertEqual(stats["skipped_trivial"], 2)
        self.assertEqual(len(self.store.load()), 0)

    def test_full_run_reinforces_turn_spawn_pattern(self):
        stats = self.miner.mine(store=self.store)
        self.assertEqual(stats["sessions_seen"], 7)
        self.assertEqual(stats["mined"], 5)
        self.assertEqual(stats["skipped_trivial"], 2)
        self.assertEqual(stats["errors"], 0)
        # the two identical turn-goals reinforced into ONE experience:
        # 5 mined - 1 reinforcement = 4 stored goals
        self.assertEqual(stats["reinforced"], 1)
        goals = [e.goal for e in self.store.load()]
        self.assertEqual(len(goals), 4)
        self.assertIn("Continue the migration task", goals)

    def test_directory_filter(self):
        stats = self.miner.mine(store=self.store,
                                directory="C:/Users/j/Projects/surfhop")
        self.assertEqual(stats["sessions_seen"], 3)
        self.assertEqual(stats["mined"], 2)

    def test_read_only_database(self):
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.miner.mine(store=self.store)
        after = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
