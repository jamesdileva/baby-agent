"""Regression tests for super-audit S3 (C2/C3): the curation->skills handoff.

Failure modes pinned here:
- C2: skill candidates carried hyphenated names and list[dict] procedures
  (plus dict verification), so EVERY candidate failed Skill validation —
  the handoff was broken by construction. Candidates must load via
  Skill.from_dict, and procedures must preserve the demonstrated args
  (G7), not just tool names.
- C3: Skill.from_dict silently coerced — list("read_file") split a string
  into characters, str(step) hid non-string steps. The gate now rejects.
Stdlib only.
"""

import json
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent.curation import (
    TrajectoryCurator, _render_step_call, _skill_name, _skill_procedure)
from qacompanion.agent.experience import Experience, ExperienceStore
from qacompanion.agent.skills import Skill


def _exp(**kw) -> Experience:
    defaults = dict(goal="fix the login timeout bug", outcome="partial")
    defaults.update(kw)
    return Experience(**defaults)


def _accepted_candidates(experiences, tmp):
    store = ExperienceStore(Path(tmp) / "experience.jsonl")
    for exp in experiences:
        store.record(exp)
    out_dir = Path(tmp) / "curated-out"
    TrajectoryCurator(store).curate(out_dir=out_dir)
    text = (out_dir / "skills.jsonl").read_text(encoding="utf-8").strip()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


class TestCandidateLoadsAsSkillC2(unittest.TestCase):
    def test_candidate_validates_as_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills = _accepted_candidates([_exp(
                outcome="success", confidence=0.9,
                actions=["read", "edit", "run_tests"],
                verification={"ok": True})], tmp)
        self.assertEqual(1, len(skills))
        Skill.from_dict({k: v for k, v in skills[0].items()
                         if k != "provenance"})

    def test_procedure_preserves_captured_args(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills = _accepted_candidates([_exp(
                outcome="success", confidence=0.9,
                actions=["read_file", "edit_file", "run_tests"],
                context={"source": "t", "tool_calls": [
                    {"tool": "read_file", "args": {"path": "w.py"},
                     "ok": True, "result_head": "def add"},
                    {"tool": "edit_file",
                     "args": {"path": "w.py", "old_string": "a - b"},
                     "ok": True, "result_head": "edit applied"},
                    {"tool": "run_tests", "args": {"command": "pytest"},
                     "ok": True, "result_head": "OK"}]},
                verification={"ok": True})], tmp)
        self.assertEqual(1, len(skills))
        procedure = skills[0]["procedure"]
        self.assertEqual(3, len(procedure))
        self.assertIn('read_file(path="w.py")', procedure[0])
        self.assertIn('old_string="a - b"', procedure[1])
        parsed = Skill.from_dict({k: v for k, v in skills[0].items()
                                  if k != "provenance"})
        self.assertIn("read_file", parsed.required_tools)

    def test_mined_record_without_step_capture_falls_back_to_names(self):
        steps = _skill_procedure(_exp(actions=["read", "edit", "run"]))
        self.assertEqual(["read", "edit", "run"], steps)

    def test_skill_name_is_identifier_like(self):
        self.assertEqual("fix_the_login_timeout_bug",
                         _skill_name("fix the login timeout bug"))
        self.assertEqual("skill_3d_printer_fix",
                         _skill_name("3d printer fix"))
        self.assertEqual("unnamed_skill", _skill_name("!!!"))

    def test_render_step_call_dialect(self):
        self.assertEqual("read", _render_step_call("read", {}))
        self.assertEqual('f(path="a.py", k=3, force=true, limit=null)',
                         _render_step_call("f", {"path": "a.py", "k": 3,
                                                "force": True,
                                                "limit": None}))


class TestFromDictGateC3(unittest.TestCase):
    def _valid(self):
        return {"name": "ok_skill", "goal": "do the thing",
                "procedure": ["first do this", "then that"]}

    def test_string_required_tools_rejected_not_split(self):
        with self.assertRaises(ValueError):
            Skill.from_dict({**self._valid(),
                             "required_tools": "read_file"})
        # the accepted form keeps whole tool names
        skill = Skill.from_dict({**self._valid(),
                                 "required_tools": ["read_file"]})
        self.assertEqual(["read_file"], skill.required_tools)

    def test_non_string_procedure_step_rejected_not_coerced(self):
        with self.assertRaises(ValueError):
            Skill.from_dict({**self._valid(),
                             "procedure": ["fine", 42]})
        with self.assertRaises(ValueError):
            Skill.from_dict({**self._valid(), "procedure": "do it"})

    def test_non_list_scalars_rejected(self):
        for field in ("preconditions", "failure_modes", "tags"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    Skill.from_dict({**self._valid(), field: "x"})
        with self.assertRaises(ValueError):
            Skill.from_dict({**self._valid(),
                             "examples": [{"a": 1}, "nope"]})
        with self.assertRaises(ValueError):
            Skill.from_dict({**self._valid(), "description": {"x": 1}})
        with self.assertRaises(ValueError):
            Skill.from_dict({**self._valid(), "verification": ["x"]})

    def test_valid_record_round_trips(self):
        skill = Skill.from_dict(self._valid())
        restored = Skill.from_dict(
            json.loads(json.dumps(skill.to_dict())))
        self.assertEqual(skill.to_dict(), restored.to_dict())


if __name__ == "__main__":
    unittest.main()
