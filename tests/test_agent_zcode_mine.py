"""S62 ZCode mining tests: same SST-family schema as opencode, thin
subclass adapter. Synthetic fixture DB only — the real ZCode database is
never touched by the suite.
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent.opencode_mine import MiningError
from qacompanion.agent.zcode_mine import DEFAULT_ZCODE_DB, ZcodeMiner

SCHEMA = """
CREATE TABLE session (id TEXT PRIMARY KEY, directory TEXT, title TEXT,
                      time_created INTEGER);
CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT,
                      time_created INTEGER, data TEXT);
CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,
                   time_created INTEGER, data TEXT);
"""

NOW = 1_700_000_000_000


class ZcodeMinerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = Path(self._tmp.name) / "zcode.db"

    def _build(self):
        con = sqlite3.connect(self.db)
        con.executescript(SCHEMA)
        con.execute("INSERT INTO session VALUES (?,?,?,?)",
                    ("sess_z1", self._tmp.name, "port the dashboard", NOW))
        con.execute("INSERT INTO message VALUES (?,?,?,?)",
                    ("m0", "sess_z1", NOW, json.dumps({"role": "user"})))
        con.execute("INSERT INTO part VALUES (?,?,?,?,?)",
                    ("p0", "m0", "sess_z1", NOW + 1, json.dumps(
                        {"type": "text",
                         "text": "Port the dashboard to the new API"})))
        con.execute("INSERT INTO message VALUES (?,?,?,?)",
                    ("m1", "sess_z1", NOW + 2,
                     json.dumps({"role": "assistant"})))
        parts = [
            {"type": "step-start"},
            {"type": "tool", "tool": "edit", "callID": "c1",
             "state": {"status": "completed", "output": "ok"}},
            {"type": "tool", "tool": "bash", "callID": "c2",
             "state": {"status": "completed",
                       "output": "Error: port 8765 already in use"}},
            {"type": "patch", "path": "server.py"},
            {"type": "step-finish"},
            {"type": "timeline"},
        ]
        for i, data in enumerate(parts):
            con.execute("INSERT INTO part VALUES (?,?,?,?,?)",
                        (f"p{i + 1}", "m1", "sess_z1", NOW + 10 + i,
                         json.dumps(data)))
        con.commit()
        con.close()

    def test_mines_with_zcode_source_tag(self):
        self._build()
        exp = ZcodeMiner(self.db).mine_session(
            {"id": "sess_z1", "directory": self._tmp.name,
             "title": "port the dashboard"})
        self.assertEqual("zcode", exp.context["source"])
        self.assertEqual("zcode", exp.tags[0])
        self.assertEqual("sess_z1", exp.session_id)
        self.assertIn("Port the dashboard", exp.goal)

    def test_extra_step_and_timeline_parts_ignored(self):
        self._build()
        exp = ZcodeMiner(self.db).mine_session(
            {"id": "sess_z1", "directory": self._tmp.name,
             "title": "port the dashboard"})
        self.assertEqual(["edit", "bash"], exp.actions)
        # the error->patch cycle survived the non-opencode part types
        self.assertEqual("Error: port 8765 already in use", exp.failure)
        self.assertEqual("fix applied via patch", exp.resolution)

    def test_default_db_path_is_the_zcode_store(self):
        self.assertEqual(DEFAULT_ZCODE_DB, ZcodeMiner().db_path)
        self.assertIn(".zcode", str(ZcodeMiner().db_path))

    def test_missing_database_is_structured_error(self):
        with self.assertRaises(MiningError):
            ZcodeMiner(Path(self._tmp.name) / "nope.db")


if __name__ == "__main__":
    unittest.main()
