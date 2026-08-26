"""Tests for module-contract skills (S17): guarded Python skill interface."""

import importlib
import importlib.util
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from qacompanion.skills.module_contract import (
    ContractError,
    ModuleSkill,
    SkillBase,
    _load_one,
    _validate_meta,
    _validate_skill_class,
    discover_modules,
)

# Path to the real modules directory shipped with the package
_SHIPPED_MODULES = Path(__file__).resolve().parent.parent / "qacompanion" / "skills" / "modules"


# --- SkillBase contract ---


class TestSkillBase(unittest.TestCase):
    def test_cannot_instantiate_directly(self):
        base = SkillBase()
        with self.assertRaises(NotImplementedError):
            _ = base.name

    def test_cannot_run_directly(self):
        base = SkillBase()
        with self.assertRaises(NotImplementedError):
            base.run()


# --- _validate_meta ---


class TestValidateMeta(unittest.TestCase):
    def _mod(self, meta=None):
        m = type(sys)("_fake")
        if meta is not None:
            m.MODULE_meta = meta
        return m

    def test_missing_meta(self):
        m = self._mod()
        with self.assertRaises(ContractError) as ctx:
            _validate_meta(m)
        self.assertIn("missing MODULE_meta", str(ctx.exception))

    def test_not_a_dict(self):
        m = self._mod(meta="bad")
        with self.assertRaises(ContractError):
            _validate_meta(m)

    def test_missing_name(self):
        m = self._mod(meta={"version": "1.0", "description": "d"})
        with self.assertRaises(ContractError) as ctx:
            _validate_meta(m)
        self.assertIn("name", str(ctx.exception))

    def test_missing_version(self):
        m = self._mod(meta={"name": "x", "description": "d"})
        with self.assertRaises(ContractError) as ctx:
            _validate_meta(m)
        self.assertIn("version", str(ctx.exception))

    def test_missing_description(self):
        m = self._mod(meta={"name": "x", "version": "1.0"})
        with self.assertRaises(ContractError) as ctx:
            _validate_meta(m)
        self.assertIn("description", str(ctx.exception))

    def test_empty_name(self):
        m = self._mod(meta={"name": "", "version": "1.0", "description": "d"})
        with self.assertRaises(ContractError) as ctx:
            _validate_meta(m)
        self.assertIn("non-empty", str(ctx.exception))

    def test_whitespace_name(self):
        m = self._mod(meta={"name": "  ", "version": "1.0", "description": "d"})
        with self.assertRaises(ContractError) as ctx:
            _validate_meta(m)
        self.assertIn("non-empty", str(ctx.exception))

    def test_valid_meta(self):
        m = self._mod(meta={"name": "ok", "version": "1.0", "description": "good"})
        result = _validate_meta(m)
        self.assertEqual(result["name"], "ok")


# --- _validate_skill_class ---


class TestValidateSkillClass(unittest.TestCase):
    def test_not_a_class(self):
        with self.assertRaises(ContractError) as ctx:
            _validate_skill_class("notaclass", "mod")
        self.assertIn("not a class", str(ctx.exception))

    def test_does_not_inherit_skillbase(self):
        class Plain:
            pass

        with self.assertRaises(ContractError) as ctx:
            _validate_skill_class(Plain, "mod")
        self.assertIn("does not inherit SkillBase", str(ctx.exception))

    def test_is_skillbase_itself(self):
        with self.assertRaises(ContractError) as ctx:
            _validate_skill_class(SkillBase, "mod")
        self.assertIn("SkillBase itself", str(ctx.exception))

    def test_does_not_override_name(self):
        class Bad(SkillBase):
            @property
            def description(self):
                return "d"

            def run(self, **kw):
                return {}

        with self.assertRaises(ContractError) as ctx:
            _validate_skill_class(Bad, "mod")
        self.assertIn("does not override name", str(ctx.exception))

    def test_does_not_override_description(self):
        class Bad(SkillBase):
            @property
            def name(self):
                return "n"

            def run(self, **kw):
                return {}

        with self.assertRaises(ContractError) as ctx:
            _validate_skill_class(Bad, "mod")
        self.assertIn("does not override description", str(ctx.exception))

    def test_does_not_override_run(self):
        class Bad(SkillBase):
            @property
            def name(self):
                return "n"

            @property
            def description(self):
                return "d"

        with self.assertRaises(ContractError) as ctx:
            _validate_skill_class(Bad, "mod")
        self.assertIn("does not override run", str(ctx.exception))

    def test_valid_subclass(self):
        class Good(SkillBase):
            @property
            def name(self):
                return "g"

            @property
            def description(self):
                return "good"

            def run(self, **kw):
                return {"ok": True}

        _validate_skill_class(Good, "mod")


# --- discover_modules with real shipped modules ---


class TestDiscoverModules(unittest.TestCase):
    def test_discovers_hello_skill(self):
        skills, errors = discover_modules(_SHIPPED_MODULES)
        names = [s.name for s in skills]
        self.assertIn("hello", names)
        # Broken modules are expected errors — verify only known ones
        broken_files = {"broken_no_meta.py", "broken_no_class.py", "broken_bad_meta.py"}
        for path, _ in errors:
            self.assertIn(path.name, broken_files)

    def test_rejects_broken_no_meta(self):
        _, errors = discover_modules(_SHIPPED_MODULES)
        error_names = [str(p) for p, _ in errors]
        self.assertTrue(
            any("broken_no_meta" in e for e in error_names),
            f"broken_no_meta should be in errors: {error_names}",
        )

    def test_rejects_broken_no_class(self):
        _, errors = discover_modules(_SHIPPED_MODULES)
        error_names = [str(p) for p, _ in errors]
        self.assertTrue(
            any("broken_no_class" in e for e in error_names),
            f"broken_no_class should be in errors: {error_names}",
        )

    def test_rejects_broken_bad_meta(self):
        _, errors = discover_modules(_SHIPPED_MODULES)
        error_names = [str(p) for p, _ in errors]
        self.assertTrue(
            any("broken_bad_meta" in e for e in error_names),
            f"broken_bad_meta should be in errors: {error_names}",
        )

    def test_only_broken_rejected(self):
        _, errors = discover_modules(_SHIPPED_MODULES)
        broken_files = {"broken_no_meta.py", "broken_no_class.py", "broken_bad_meta.py"}
        for path, _ in errors:
            self.assertIn(path.name, broken_files, f"unexpected error for {path.name}")

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills, errors = discover_modules(Path(tmp))
            self.assertEqual(skills, [])
            self.assertEqual(errors, [])

    def test_nonexistent_dir(self):
        skills, errors = discover_modules(Path("/nonexistent/path/xyz"))
        self.assertEqual(skills, [])
        self.assertEqual(errors, [])


# --- ModuleSkill wrapper ---


class TestModuleSkill(unittest.TestCase):
    def _get_hello(self):
        skills, _ = discover_modules(_SHIPPED_MODULES)
        for s in skills:
            if s.name == "hello":
                return s
        self.fail("hello skill not found")

    def test_name_and_description(self):
        skill = self._get_hello()
        self.assertEqual(skill.name, "hello")
        self.assertEqual(skill.description, "Example skill that returns a greeting")
        self.assertEqual(skill.version, "1.0.0")

    def test_run(self):
        skill = self._get_hello()
        result = skill.run(name="tess")
        self.assertEqual(result, {"greeting": "hello tess"})

    def test_run_default(self):
        skill = self._get_hello()
        result = skill.run()
        self.assertEqual(result, {"greeting": "hello world"})

    def test_instance_laziness(self):
        skill = self._get_hello()
        i1 = skill.get_instance()
        i2 = skill.get_instance()
        self.assertIs(i1, i2)


# --- In-temp-dir discovery (write our own module) ---


class TestDiscoverCustomModule(unittest.TestCase):
    def test_valid_module_discovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod_dir = Path(tmp)
            mod_file = mod_dir / "my_skill.py"
            mod_file.write_text(textwrap.dedent("""\
                from qacompanion.skills.module_contract import SkillBase

                MODULE_meta = {
                    "name": "custom",
                    "version": "0.1",
                    "description": "A custom skill",
                }

                class CustomSkill(SkillBase):
                    @property
                    def name(self):
                        return "custom"

                    @property
                    def description(self):
                        return "A custom skill"

                    def run(self, **kwargs):
                        return {"custom": True}
            """), encoding="utf-8")

            skills, errors = discover_modules(mod_dir)
            self.assertEqual(errors, [])
            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0].name, "custom")
            self.assertEqual(skills[0].run(), {"custom": True})

    def test_import_error_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod_dir = Path(tmp)
            mod_file = mod_dir / "bad_import.py"
            mod_file.write_text(textwrap.dedent("""\
                import nonexistent_package_xyz_12345

                MODULE_meta = {
                    "name": "bad",
                    "version": "1.0",
                    "description": "broken import",
                }
            """), encoding="utf-8")

            skills, errors = discover_modules(mod_dir)
            self.assertEqual(skills, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("import failed", errors[0][1])

    def test_syntax_error_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod_dir = Path(tmp)
            mod_file = mod_dir / "syntax_err.py"
            mod_file.write_text("def broken(:\n  pass\n", encoding="utf-8")

            skills, errors = discover_modules(mod_dir)
            self.assertEqual(skills, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("import failed", errors[0][1])


# --- Interface enforcement in isolation ---


class TestInterfaceEnforcement(unittest.TestCase):
    """Write temp modules that violate specific contract rules."""

    def _write_and_discover(self, filename, code):
        with tempfile.TemporaryDirectory() as tmp:
            mod_dir = Path(tmp)
            (mod_dir / filename).write_text(textwrap.dedent(code), encoding="utf-8")
            return discover_modules(mod_dir)

    def test_no_skillbase_subclass(self):
        skills, errors = self._write_and_discover("nobs.py", """\
            MODULE_meta = {"name": "x", "version": "1", "description": "d"}
            def helper(): return 42
        """)
        self.assertEqual(skills, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("no SkillBase subclass", errors[0][1])

    def test_name_not_overridden(self):
        skills, errors = self._write_and_discover("bad_name.py", """\
            from qacompanion.skills.module_contract import SkillBase

            MODULE_meta = {"name": "x", "version": "1", "description": "d"}

            class Bad(SkillBase):
                @property
                def description(self):
                    return "d"
                def run(self, **kw):
                    return {}
        """)
        self.assertEqual(skills, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("does not override name", errors[0][1])


if __name__ == "__main__":
    unittest.main()
