"""S75.11/S75.12 tests: super-audit S11 (D2/D6 — curriculum accounting,
training-gate edges) and the lab.db transcript miner (per
docs/labDB-handoff.md). Synthetic fixture DBs only — the real lab.db
and opencode.db are never touched.
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent.curriculum import CurriculumError, \
    SyntheticCurriculum
from qacompanion.agent.labdb_mine import DEFAULT_LABDB_PATH, LabDbMiner
from qacompanion.agent.training import build_records, build_training, \
    reset_runtime_catalog

LABDB_SCHEMA = """
CREATE TABLE sessions (id INTEGER PRIMARY KEY, status TEXT,
                       agent TEXT);
CREATE TABLE session_transcripts (id INTEGER PRIMARY KEY,
                                  lab_session_id INTEGER,
                                  opencode_session_id TEXT,
                                  agent TEXT, cycle INTEGER,
                                  transcript TEXT, created_at TEXT);
"""


def _msg(role, parts):
    return {"info": {"role": role}, "parts": parts}


def _tool(name, output):
    return {"type": "tool", "tool": name,
            "state": {"status": "completed", "output": output}}


class CurriculumAccountingTests(unittest.TestCase):
    """D2: silent shortfalls invalidated dataset-size comparisons."""

    def test_accounting_present_and_strict_raises(self):
        gen = SyntheticCurriculum(seed=7)
        tasks = gen.generate(5)
        self.assertEqual(5, len(tasks))
        self.assertEqual({"requested": 5, "produced": 5,
                          "skipped_duplicates": 0, "exhausted": False},
                         gen.last_run_accounting)

    def test_strict_raises_on_shortfall(self):
        gen = SyntheticCurriculum(seed=7,
                                  categories=("bug_fix",),
                                  level_range=(1, 1))
        # one category x one level has finitely many distinct goals;
        # a request far beyond the supply must raise, not whisper
        with self.assertRaises(CurriculumError) as ctx:
            gen.generate(500, strict=True)
        self.assertIn("requested 500 tasks", str(ctx.exception))


class TrainingGateEdgeTests(unittest.TestCase):
    """D6: INVALID counted, truncation marked, suffix stripped
    precisely."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def _write(self, rows):
        curated = self.tmp / "curated"
        curated.mkdir(parents=True, exist_ok=True)
        (curated / "trajectory.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return curated

    def _row(self, **kw):
        row = {
            "experience_id": "e1", "session_id": "s1", "source": "labdb",
            "goal": "g", "outcome": "success",
            "classification": "SUCCESS", "verdict": "ACCEPT",
            "score": {"overall": 0.7, "dimensions": {},
                      "unknown_dims": []},
            "hard_flags": [], "penalties": [], "reasons": [],
            "confidence": 0.9, "times_seen": 1, "diversity_score": 0.5,
            "actions": ["read_file"], "failure": None, "diagnosis": None,
            "resolution": None,
            "verification": {"attempts": [{"ok": True}]},
            "steps": [{"tool": "read_file", "args": {"path": "x"},
                       "ok": True, "result_head": "ok"}],
            "final_answer": "done", "model": "m",
            "verification_failures": [], "tags": [],
        }
        row.update(kw)
        return row

    def test_invalid_counted_in_report(self):
        curated = self._write([self._row(classification="INVALID",
                                         verdict="REJECT"),
                               self._row()])
        report = build_training(curated_dir=curated,
                                out_dir=self.tmp / "training")
        self.assertEqual(1, report["invalid_skipped"])
        self.assertEqual(1, report["trajectories"])

    def test_truncation_marked(self):
        long_steps = [{"tool": "read_file", "args": {"path": "x"},
                       "ok": True, "result_head": "ok"}] * 55
        record = build_records(curated_dir=self._write([
            self._row(steps=long_steps)]))[0]
        self.assertTrue(record.truncated)
        self.assertEqual("behavior-trace", record.capture_tier)
        self.assertTrue(record.chat["metadata"]["truncated"])

    def test_suffix_stripped_only_as_exact_trailing_pattern(self):
        record = build_records(curated_dir=self._write([
            self._row(goal="fix the widget (benchmark run 6bd97c9c)")]))[0]
        # the strip lands in the CHAT record's goal, not the
        # trajectory's provenance fields
        self.assertEqual("fix the widget",
                         record.chat["messages"][1]["content"])
        # a legitimate goal containing similar text survives
        record2 = build_records(curated_dir=self._write([
            self._row(experience_id="e2",
                      goal="a plan (benchmark run x) for later")]))[0]
        self.assertEqual("a plan (benchmark run x) for later",
                         record2.goal)

    def test_catalog_cache_resets(self):
        reset_runtime_catalog()
        from qacompanion.agent import training as t
        self.assertIsNone(t._RUNTIME_CATALOG)


class LabDbMinerTests(unittest.TestCase):
    """The lab.db transcript miner (docs/labDB-handoff.md)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = Path(self._tmp.name) / "lab.db"
        self.store = None  # set per-test via _mined()
        self._seed()

    def _mined(self):
        from qacompanion.agent.experience import ExperienceStore
        self.store = ExperienceStore(
            Path(self._tmp.name) / "exp.jsonl")
        LabDbMiner(self.db).mine(store=self.store)
        return self.store.load()

    def _seed(self):
        con = sqlite3.connect(self.db)
        con.executescript(LABDB_SCHEMA)
        transcript = json.dumps([
            _msg("user", [{"type": "text",
                           "text": "SITUATION REPORT — agent-a\n\n"
                                    "PROJECT GOAL (authored by the "
                                    "human; treat as the mission)"}]),
            _msg("user", [{"type": "text",
                           "text": "Ship the surf session tracker "
                                   "importer"}]),
            _msg("assistant", [
                _tool("read", "ok"),
                _tool("bash", "Traceback (most recent call last):\n"
                              "ValueError: bad header row"),
                {"type": "patch", "path": "importer.py"},
                _tool("bash", "all green"),
            ]),
        ])
        con.execute("INSERT INTO sessions VALUES (1, 'done', 'agent-a')")
        con.execute("INSERT INTO sessions VALUES (2, 'timed_out', "
                    "'agent-b')")
        con.execute("INSERT INTO sessions VALUES (3, 'failed', "
                    "'agent-a')")
        con.execute("INSERT INTO session_transcripts VALUES "
                    "(1, 1, 'ses_oc_done', 'agent-a', 7, ?, '2026-09-20')",
                    (transcript,))
        short = json.dumps([
            _msg("user", [{"type": "text", "text": "SITUATION REPORT"}]),
            _msg("user", [{"type": "text",
                           "text": "Finish the importer migration"}]),
            _msg("assistant", [
                _tool("read", "partial output"),
                {"type": "patch", "path": "importer.py"},
            ]),
        ])
        con.execute("INSERT INTO session_transcripts VALUES "
                    "(2, 2, 'ses_oc_to', 'agent-b', 8, ?, '2026-09-20')",
                    (short,))
        # failed session: NO transcript row (per the handoff)
        con.commit()
        con.close()

    def test_done_session_mined_with_honest_provenance(self):
        records = self._mined()
        self.assertEqual(2, len(records))  # failed: no transcript row
        record = [r for r in records if r.session_id
                  == "ses_oc_done"][0]
        self.assertEqual("labdb", record.context["source"])
        self.assertEqual("done", record.context["status"])
        self.assertEqual(7, record.context["cycle"])
        self.assertEqual(0.45, record.confidence)
        # the preamble is boilerplate; the real goal wins
        self.assertIn("surf session tracker", record.goal)
        self.assertNotIn("SITUATION", record.goal)
        # error->patch pair captured
        self.assertEqual("ValueError: bad header row",
                         record.failure)
        self.assertEqual("fix applied via patch", record.resolution)
        self.assertEqual(["read", "bash", "bash"],
                         record.actions)

    def test_timed_out_session_lower_confidence(self):
        records = self._mined()
        record = [r for r in records if r.session_id
                  == "ses_oc_to"][0]
        self.assertEqual(0.3, record.confidence)

    def test_session_id_prefers_opencode_id_for_dedupe(self):
        records = self._mined()
        self.assertTrue(all(r.session_id.startswith("ses_oc")
                            for r in records))

    def test_default_path_is_the_antfarm_store(self):
        self.assertEqual(DEFAULT_LABDB_PATH, LabDbMiner().db_path)
        self.assertIn("antfarm", str(DEFAULT_LABDB_PATH))

    def test_invalid_transcript_json_is_structured_error(self):
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO session_transcripts VALUES "
                    "(9, 1, 'ses_bad', 'agent-a', 9, '{not json', "
                    "'2026-09-20')")
        con.commit()
        con.close()
        with self.assertRaises(Exception) as ctx:
            LabDbMiner(self.db)._transcript_messages(9)
        self.assertIn("not valid JSON", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
