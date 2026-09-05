"""S51 skills 2.0 tests: schema, tolerant library, tools, resume seed.

Hermetic: fixture skill dirs in temp paths (plus the real S50 resume
seed, loaded read-only).
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import ToolCall, ToolRegistry, Workspace
from qacompanion.agent.fs_tools import agent_registry
from qacompanion.agent.skills import (
    Skill,
    SkillError,
    SkillLibrary,
    SkillToolkit,
)

VALID = {
    "name": "debug_build_failure",
    "goal": "diagnose and repair a failing build",
    "description": "read the error, locate the code, fix, rebuild",
    "required_tools": ["read_file", "run_build", "edit_file"],
    "preconditions": ["the project has a build command"],
    "procedure": ["run the build", "read the first error",
                  "locate the code", "fix", "rebuild"],
    "verification": "the build exits 0",
    "failure_modes": ["fixing symptoms not causes"],
    "examples": [{"goal": "npm run build fails", "source": "test"}],
    "confidence": 0.7,
    "tags": ["build"],
}

RESUME_SEED = Path("skills") / "agent" / "resume_interrupted_task.json"


class SkillsBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.skill_dir = self.tmp / "skills" / "agent"
        self.library = SkillLibrary(self.skill_dir)
        self.toolkit = SkillToolkit(self.library)
        self.reg = ToolRegistry()
        for tool in self.toolkit.tools():
            self.reg.register(tool)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, name, **arguments):
        return self.reg.execute(ToolCall(name=name, arguments=arguments),
                                workspace=None)

    def payload(self, name, **arguments):
        out = self.call(name, **arguments)
        self.assertTrue(out.ok, f"{name} failed: {out.error}")
        return json.loads(out.output)


class TestSkillSchema(unittest.TestCase):
    def test_round_trip_non_ascii(self):
        # names stay identifier-like (they map to filenames); content is
        # free UTF-8
        skill = Skill(name="reparer_fichier", goal="réparer ✅",
                      procedure=["étape un"])
        restored = Skill.from_dict(json.loads(json.dumps(skill.to_dict())))
        self.assertEqual(restored.goal, skill.goal)

    def test_validation_rejections(self):
        with self.assertRaises(ValueError):
            Skill(name="BadName", goal="g", procedure=["s"])
        with self.assertRaises(ValueError):
            Skill(name="ok", goal="  ", procedure=["s"])
        with self.assertRaises(ValueError):
            Skill(name="ok", goal="g", procedure=[])
        with self.assertRaises(ValueError):
            Skill(name="ok", goal="g", procedure=["s"], confidence=2.0)
        with self.assertRaises(ValueError):
            Skill.from_dict(["not", "an", "object"])
        with self.assertRaises(ValueError):
            Skill.from_dict({"name": "ok", "goal": "g"})


class TestSkillLibrary(SkillsBase):
    def _write(self, name, data):
        self.skill_dir.mkdir(parents=True, exist_ok=True)
        (self.skill_dir / f"{name}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_load_list_get(self):
        self._write("debug_build_failure", VALID)
        skills = self.library.list_skills()
        self.assertEqual([s.name for s in skills],
                         ["debug_build_failure"])
        self.assertEqual(self.library.get("debug_build_failure").goal,
                         VALID["goal"])
        self.assertIsNone(self.library.get("nope"))

    def test_missing_dir_is_empty(self):
        self.assertEqual(self.library.list_skills(), [])
        self.assertEqual(self.library.find("anything"), [])

    def test_malformed_file_skipped_and_recorded(self):
        self.skill_dir.mkdir(parents=True, exist_ok=True)
        (self.skill_dir / "broken.json").write_text("{nope", encoding="utf-8")
        self._write("good_skill", dict(VALID, name="good_skill"))
        skills = self.library.list_skills()
        self.assertEqual([s.name for s in skills], ["good_skill"])
        self.assertEqual(len(self.library.errors), 1)
        self.assertIn("broken.json", self.library.errors[0])

    def test_find_ranks_by_keyword_overlap(self):
        self._write("debug_build_failure", VALID)
        self._write("resume_task", dict(VALID, name="resume_task",
                                        goal="continue interrupted work",
                                        tags=["resume"]))
        matches = self.library.find("build is failing")
        self.assertEqual(matches[0].name, "debug_build_failure")
        matches = self.library.find("interrupted continue")
        self.assertEqual(matches[0].name, "resume_task")

    def test_teach_persists_atomically(self):
        skill = Skill.from_dict(VALID)
        target = self.library.teach(skill)
        self.assertTrue(target.exists())
        leftovers = [p.name for p in self.skill_dir.iterdir()
                     if "tmp-" in p.name]
        self.assertEqual(leftovers, [])
        self.assertIsNotNone(self.library.get("debug_build_failure"))


class TestResumeSeedIntegration(unittest.TestCase):
    def test_s50_seed_loads_and_is_findable(self):
        # the S50 -> S51 loop: the resume skill seed is real knowledge now
        library = SkillLibrary(RESUME_SEED.parent)
        skill = library.get("resume_interrupted_task")
        self.assertIsNotNone(skill)
        self.assertIn("interrupted", skill.goal)
        self.assertTrue(skill.procedure)
        matches = library.find("resume interrupted task")
        self.assertEqual(matches[0].name, "resume_interrupted_task")


class TestSkillTools(SkillsBase):
    def test_side_effect_matrix(self):
        described = {d["name"]: d for d in self.reg.describe()}
        self.assertEqual(set(described), {"skill_find", "skill_teach"})
        self.assertEqual(described["skill_find"]["side_effect_level"],
                         "READ_ONLY")
        self.assertEqual(described["skill_teach"]["side_effect_level"],
                         "SAFE_WRITE")
        self.assertTrue(all(not d["requires_workspace"]
                            for d in described.values()))

    def test_teach_then_find_through_registry(self):
        out = self.call("skill_teach", skill=VALID)
        self.assertTrue(out.ok, out.error)
        payload = json.loads(out.output)
        self.assertTrue(payload["taught"])

        found = self.payload("skill_find", query="failing build repair")
        self.assertEqual(found["count"], 1)
        skill = found["skills"][0]
        self.assertEqual(skill["name"], "debug_build_failure")
        self.assertIn("rebuild", skill["procedure"][0] + "".join(
            skill["procedure"]))

    def test_invalid_teach_structured_error(self):
        out = self.call("skill_teach", skill={"name": "x"})
        self.assertFalse(out.ok)
        self.assertIn("invalid skill record", out.error)

    def test_find_no_match_is_empty_not_error(self):
        payload = self.payload("skill_find", query="quantum chromodynamics")
        self.assertEqual(payload["count"], 0)


class TestAgentRegistryIncludesSkills(unittest.TestCase):
    def test_membership(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        try:
            reg = agent_registry(Workspace(tmp),
                                 skill_dir=tmp / "skills" / "agent")
            for name in ("skill_find", "skill_teach"):
                self.assertIn(name, reg.names())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
