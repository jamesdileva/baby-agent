"""Tests for skill registry (S16): rule packs, validation, matching, teach."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from qacompanion.skills.registry import (
    MAX_PATTERN_LEN,
    RegistryError,
    _match_one_pattern,
    _validate_pack,
    _validate_rule,
    format_rule_matches,
    load_all,
    load_pack,
    match_rules,
)
from qacompanion.teach import teach_rule, render_teach


def _make_rule(
    pattern="^Error: .*",
    classification="test-failure",
    diagnosis_hint="generic error",
    exit_code=None,
    action_hint=None,
    rule_id=None,
):
    rule = {
        "pattern": pattern,
        "classification": classification,
        "diagnosis_hint": diagnosis_hint,
    }
    if exit_code is not None:
        rule["exit_code"] = exit_code
    if action_hint is not None:
        rule["action_hint"] = action_hint
    if rule_id is not None:
        rule["id"] = rule_id
    return rule


def _make_pack(rules=None, name="test-pack", version="1.0"):
    return {"name": name, "version": version, "rules": rules or []}


# --- Rule validation ---

class TestValidateRule(unittest.TestCase):
    def test_valid_minimal(self):
        _validate_rule(_make_rule(), "test", 1)

    def test_valid_full(self):
        rule = _make_rule(rule_id="r1", exit_code=1, action_hint="fix it")
        _validate_rule(rule, "test", 1)

    def test_missing_pattern(self):
        rule = _make_rule()
        del rule["pattern"]
        with self.assertRaises(RegistryError):
            _validate_rule(rule, "test", 1)

    def test_missing_classification(self):
        rule = _make_rule()
        del rule["classification"]
        with self.assertRaises(RegistryError):
            _validate_rule(rule, "test", 1)

    def test_missing_diagnosis_hint(self):
        rule = _make_rule()
        del rule["diagnosis_hint"]
        with self.assertRaises(RegistryError):
            _validate_rule(rule, "test", 1)

    def test_unknown_field(self):
        rule = _make_rule()
        rule["bogus"] = True
        with self.assertRaises(RegistryError):
            _validate_rule(rule, "test", 1)

    def test_invalid_regex(self):
        with self.assertRaises(RegistryError):
            _validate_rule(_make_rule(pattern="[invalid"), "test", 1)

    def test_empty_pattern(self):
        with self.assertRaises(RegistryError):
            _validate_rule(_make_rule(pattern=""), "test", 1)

    def test_non_string_pattern(self):
        with self.assertRaises(RegistryError):
            _validate_rule(_make_rule(pattern=123), "test", 1)

    def test_unknown_classification(self):
        with self.assertRaises(RegistryError):
            _validate_rule(_make_rule(classification="bogus"), "test", 1)

    def test_empty_diagnosis(self):
        with self.assertRaises(RegistryError):
            _validate_rule(_make_rule(diagnosis_hint=""), "test", 1)

    def test_exit_code_out_of_range(self):
        with self.assertRaises(RegistryError):
            _validate_rule(_make_rule(exit_code=256), "test", 1)

    def test_exit_code_negative(self):
        with self.assertRaises(RegistryError):
            _validate_rule(_make_rule(exit_code=-1), "test", 1)

    def test_exit_code_not_int(self):
        with self.assertRaises(RegistryError):
            _validate_rule(_make_rule(exit_code="1"), "test", 1)

    def test_action_hint_empty(self):
        with self.assertRaises(RegistryError):
            _validate_rule(_make_rule(action_hint=""), "test", 1)

    def test_rule_not_dict(self):
        with self.assertRaises(RegistryError):
            _validate_rule("not a dict", "test", 1)

    def test_valid_classifications(self):
        for cls in ("test-failure", "environment-error", "build-failure",
                     "configuration-error", "dependency-error", "flaky-test",
                     "unknown"):
            _validate_rule(_make_rule(classification=cls), "test", 1)

    def test_pattern_exceeds_size_cap(self):
        long_pat = "a" * (MAX_PATTERN_LEN + 1)
        with self.assertRaises(RegistryError):
            _validate_rule(_make_rule(pattern=long_pat), "test", 1)

    def test_pattern_at_size_cap_ok(self):
        pat = "a" * MAX_PATTERN_LEN
        _validate_rule(_make_rule(pattern=pat), "test", 1)


# --- Pack validation ---

class TestValidatePack(unittest.TestCase):
    def test_valid_pack(self):
        pack = _make_pack(rules=[_make_rule()])
        _validate_pack(pack, "test")

    def test_empty_rules(self):
        pack = _make_pack(rules=[])
        _validate_pack(pack, "test")

    def test_not_dict(self):
        with self.assertRaises(RegistryError):
            _validate_pack([], "test")

    def test_missing_rules(self):
        with self.assertRaises(RegistryError):
            _validate_pack({"name": "x"}, "test")

    def test_rules_not_array(self):
        with self.assertRaises(RegistryError):
            _validate_pack({"rules": "not a list"}, "test")

    def test_unknown_top_level_field(self):
        pack = _make_pack(rules=[_make_rule()])
        pack["bogus"] = True
        with self.assertRaises(RegistryError):
            _validate_pack(pack, "test")

    def test_invalid_rule_in_pack(self):
        pack = _make_pack(rules=[_make_rule(pattern="")])
        with self.assertRaises(RegistryError):
            _validate_pack(pack, "test")


# --- File loading ---

class TestLoadPack(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.pack_path = Path(self.tmpdir) / "test.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, obj):
        self.pack_path.write_text(json.dumps(obj), encoding="utf-8")

    def test_load_valid(self):
        self._write(_make_pack(rules=[_make_rule()]))
        pack = load_pack(self.pack_path)
        self.assertEqual(len(pack["rules"]), 1)
        self.assertIsNotNone(pack["rules"][0]["_compiled"])

    def test_malformed_json(self):
        self.pack_path.write_text("{bad json", encoding="utf-8")
        with self.assertRaises(RegistryError):
            load_pack(self.pack_path)

    def test_invalid_pack_content(self):
        self._write({"not_rules": True})
        with self.assertRaises(RegistryError):
            load_pack(self.pack_path)

    def test_missing_file(self):
        with self.assertRaises(RegistryError):
            load_pack(Path(self.tmpdir) / "nope.json")


class TestLoadAll(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.skills_dir = Path(self.tmpdir) / "skills"
        self.skills_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name, obj):
        (self.skills_dir / name).write_text(json.dumps(obj), encoding="utf-8")

    def test_empty_dir(self):
        packs, errors = load_all(self.skills_dir)
        self.assertEqual(packs, [])
        self.assertEqual(errors, [])

    def test_nonexistent_dir(self):
        packs, errors = load_all(Path(self.tmpdir) / "nope")
        self.assertEqual(packs, [])
        self.assertEqual(errors, [])

    def test_one_good_pack(self):
        self._write("a.json", _make_pack(rules=[_make_rule()]))
        packs, errors = load_all(self.skills_dir)
        self.assertEqual(len(packs), 1)
        self.assertEqual(errors, [])

    def test_multiple_packs_sorted(self):
        self._write("b.json", _make_pack(name="b", rules=[_make_rule()]))
        self._write("a.json", _make_pack(name="a", rules=[_make_rule()]))
        packs, errors = load_all(self.skills_dir)
        self.assertEqual(len(packs), 2)
        self.assertEqual(packs[0]["name"], "a")
        self.assertEqual(packs[1]["name"], "b")

    def test_bad_pack_collected(self):
        self._write("good.json", _make_pack(rules=[_make_rule()]))
        self._write("bad.json", {"not": "a pack"})
        packs, errors = load_all(self.skills_dir)
        self.assertEqual(len(packs), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("bad.json", str(errors[0][0]))

    def test_non_json_skipped(self):
        (self.skills_dir / "readme.txt").write_text("hello", encoding="utf-8")
        packs, errors = load_all(self.skills_dir)
        self.assertEqual(packs, [])
        self.assertEqual(errors, [])


# --- Matching ---

class TestMatchRules(unittest.TestCase):
    def _pack(self, rules):
        return _make_pack(rules=rules)

    def test_no_rules_no_match(self):
        result = match_rules([], "Error: something", exit_code=1)
        self.assertEqual(result, [])

    def test_regex_match(self):
        rule = _make_rule(pattern="^Error: .*", rule_id="r1")
        rule["_compiled"] = __import__("re").compile(rule["pattern"])
        pack = self._pack([rule])
        result = match_rules([pack], "Error: boom")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "r1")

    def test_no_match(self):
        rule = _make_rule(pattern="^SyntaxError", rule_id="r1")
        rule["_compiled"] = __import__("re").compile(rule["pattern"])
        pack = self._pack([rule])
        result = match_rules([pack], "Error: boom")
        self.assertEqual(result, [])

    def test_exit_code_filter(self):
        rule = _make_rule(pattern="Error", exit_code=1, rule_id="r1")
        rule["_compiled"] = __import__("re").compile(rule["pattern"])
        pack = self._pack([rule])
        self.assertEqual(len(match_rules([pack], "Error: x", exit_code=1)), 1)
        self.assertEqual(len(match_rules([pack], "Error: x", exit_code=2)), 0)

    def test_exit_code_none_matches_any(self):
        rule = _make_rule(pattern="Error", rule_id="r1")
        rule["_compiled"] = __import__("re").compile(rule["pattern"])
        pack = self._pack([rule])
        self.assertEqual(len(match_rules([pack], "Error: x", exit_code=99)), 1)

    def test_multiple_packs(self):
        r1 = _make_rule(pattern="Error", rule_id="r1")
        r1["_compiled"] = __import__("re").compile(r1["pattern"])
        r2 = _make_rule(pattern="Error", rule_id="r2")
        r2["_compiled"] = __import__("re").compile(r2["pattern"])
        p1 = self._pack([r1])
        p2 = self._pack([r2])
        result = match_rules([p1, p2], "Error: x")
        self.assertEqual(len(result), 2)

    def test_pack_name_attached(self):
        rule = _make_rule(pattern="Error", rule_id="r1")
        rule["_compiled"] = __import__("re").compile(rule["pattern"])
        pack = _make_pack(name="mypack", rules=[rule])
        result = match_rules([pack], "Error: x")
        self.assertEqual(result[0]["_pack"], "mypack")


# --- Format ---

class TestFormatRuleMatches(unittest.TestCase):
    def test_no_matches(self):
        self.assertEqual(format_rule_matches([]), "no matching rules")

    def test_single_match(self):
        result = format_rule_matches([
            {"id": "r1", "_pack": "p", "classification": "test-failure",
             "diagnosis_hint": "oops"}
        ])
        self.assertIn("r1", result)
        self.assertIn("oops", result)

    def test_ambiguous(self):
        result = format_rule_matches([
            {"id": "r1", "_pack": "p", "classification": "test-failure",
             "diagnosis_hint": "a"},
            {"id": "r2", "_pack": "p", "classification": "test-failure",
             "diagnosis_hint": "b"},
        ])
        self.assertIn("AMBIGUOUS", result)


# --- Teach ---

class TestTeach(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.pack_path = Path(self.tmpdir) / "taught.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_teach_creates_pack(self):
        rule = _make_rule(rule_id="t1")
        pack = teach_rule(rule, self.pack_path)
        self.assertTrue(self.pack_path.exists())
        self.assertEqual(len(pack["rules"]), 1)
        self.assertEqual(pack["rules"][0]["id"], "t1")

    def test_teach_appends_to_existing(self):
        rule1 = _make_rule(rule_id="t1")
        rule2 = _make_rule(rule_id="t2")
        teach_rule(rule1, self.pack_path)
        pack = teach_rule(rule2, self.pack_path)
        self.assertEqual(len(pack["rules"]), 2)

    def test_teach_validates_rejects_bad(self):
        rule = _make_rule(pattern="")  # invalid
        with self.assertRaises(RegistryError):
            teach_rule(rule, self.pack_path)
        self.assertFalse(self.pack_path.exists())

    def test_teach_round_trips_through_load(self):
        rule = _make_rule(rule_id="t1")
        teach_rule(rule, self.pack_path)
        pack = load_pack(self.pack_path)
        self.assertEqual(len(pack["rules"]), 1)
        self.assertIsNotNone(pack["rules"][0]["_compiled"])

    def test_render_teach_created(self):
        rule = _make_rule(rule_id="t1")
        result = render_teach(rule, self.pack_path, created=True)
        self.assertIn("created", result)
        self.assertIn("t1", result)

    def test_render_teach_appended(self):
        rule = _make_rule(rule_id="t1")
        result = render_teach(rule, self.pack_path, created=False)
        self.assertIn("appended", result)


# --- CLI exit contracts (e2e) ---

class TestTeachCLI(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.pack_path = Path(self.tmpdir) / "taught.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, *args):
        from qacompanion.__main__ import main
        return main(list(args))

    def test_teach_exit_0(self):
        rule = json.dumps(_make_rule(rule_id="t1"))
        rc = self._run("teach", "--rule", rule, "--pack", str(self.pack_path))
        self.assertEqual(rc, 0)
        self.assertTrue(self.pack_path.exists())

    def test_teach_bad_json_exit_1(self):
        rc = self._run("teach", "--rule", "not json", "--pack", str(self.pack_path))
        self.assertEqual(rc, 1)

    def test_teach_invalid_rule_exit_1(self):
        rule = json.dumps({"pattern": "", "classification": "test-failure", "diagnosis_hint": "x"})
        rc = self._run("teach", "--rule", rule, "--pack", str(self.pack_path))
        self.assertEqual(rc, 1)


# --- S19: Pack-file I/O robustness ---

class TestPackFileRobustness(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.pack_path = Path(self.tmpdir) / "test.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_raw(self, data):
        self.pack_path.write_bytes(data)

    def test_bom_prefix_stripped(self):
        obj = _make_pack(rules=[_make_rule()])
        raw = json.dumps(obj).encode("utf-8")
        self._write_raw(b'\xef\xbb\xbf' + raw)
        pack = load_pack(self.pack_path)
        self.assertEqual(len(pack["rules"]), 1)

    def test_crlf_line_endings_ok(self):
        obj = _make_pack(rules=[_make_rule()])
        raw = json.dumps(obj).encode("utf-8").replace(b'\n', b'\r\n')
        self._write_raw(raw)
        pack = load_pack(self.pack_path)
        self.assertEqual(len(pack["rules"]), 1)

    def test_no_trailing_newline_ok(self):
        obj = _make_pack(rules=[_make_rule()])
        raw = json.dumps(obj).encode("utf-8").rstrip(b'\n')
        self._write_raw(raw)
        pack = load_pack(self.pack_path)
        self.assertEqual(len(pack["rules"]), 1)

    def test_bom_crlf_combined(self):
        obj = _make_pack(rules=[_make_rule()])
        raw = json.dumps(obj).encode("utf-8").replace(b'\n', b'\r\n')
        self._write_raw(b'\xef\xbb\xbf' + raw)
        pack = load_pack(self.pack_path)
        self.assertEqual(len(pack["rules"]), 1)

    def test_non_utf8_bytes_rejected(self):
        self._write_raw(b'\xff\xfe')
        with self.assertRaises(RegistryError) as ctx:
            load_pack(self.pack_path)
        self.assertIn("non-UTF-8", str(ctx.exception))


# --- S19: Regex timeout guard ---

class TestRegexTimeout(unittest.TestCase):
    def test_hostile_regex_does_not_hang(self):
        import re as _re
        compiled = _re.compile("(a+)+$")
        text = "a" * 25 + "!"
        t0 = __import__("time").time()
        result = _match_one_pattern(compiled, text, timeout=0.5)
        elapsed = __import__("time").time() - t0
        self.assertFalse(result)
        self.assertLess(elapsed, 5.0)

    def test_normal_regex_still_matches(self):
        import re as _re
        compiled = _re.compile("^Error: .*")
        self.assertTrue(_match_one_pattern(compiled, "Error: boom", timeout=0.5))

    def test_normal_regex_no_match(self):
        import re as _re
        compiled = _re.compile("^SyntaxError")
        self.assertFalse(_match_one_pattern(compiled, "Error: boom", timeout=0.5))

    def test_match_rules_with_hostile_pattern_completes(self):
        hostile_rule = _make_rule(
            pattern="(a+)+$",
            rule_id="hostile",
        )
        hostile_rule["_compiled"] = __import__("re").compile(hostile_rule["pattern"])
        pack = _make_pack(name="bad", rules=[hostile_rule])
        t0 = __import__("time").time()
        result = match_rules([pack], "a" * 25 + "!")
        elapsed = __import__("time").time() - t0
        self.assertEqual(result, [])
        self.assertLess(elapsed, 5.0)

    def test_match_rules_normal_pattern_still_works(self):
        import re as _re
        rule = _make_rule(pattern="^Error: .*", rule_id="r1")
        rule["_compiled"] = _re.compile(rule["pattern"])
        pack = _make_pack(name="good", rules=[rule])
        result = match_rules([pack], "Error: boom")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "r1")


if __name__ == "__main__":
    unittest.main()
