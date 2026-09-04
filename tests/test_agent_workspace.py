"""S33 workspace abstraction tests: boundary, metadata, manager, registry fit.

Hermetic: temp-dir fixtures only. Windows-specific cases are
skipUnless(os.name == "nt"); symlink-escape tests skip honestly when the OS
denies symlink creation (Windows without Developer Mode/admin).
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import ToolCall, ToolRegistry, RegisteredTool, ToolDefinition
from qacompanion.agent.workspace import (
    PathError,
    PathPolicy,
    ProjectMetadata,
    Workspace,
    WorkspaceConfig,
    WorkspaceError,
    WorkspaceManager,
    _is_under,
)


def _touch(path: Path, content="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestPathPolicyContainment(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.policy = PathPolicy(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_relative_path_resolves_inside(self):
        resolved = self.policy.resolve("src/app.py")
        self.assertEqual(resolved, self.tmp / "src" / "app.py")
        self.assertTrue(resolved.is_absolute())

    def test_nested_relative_path(self):
        self.assertEqual(
            self.policy.resolve("a/b/c.txt"), self.tmp / "a" / "b" / "c.txt"
        )

    def test_absolute_inside_root_passes(self):
        inside = self.tmp / "notes.md"
        self.assertEqual(self.policy.resolve(str(inside)), inside)

    def test_path_object_input_accepted(self):
        self.assertEqual(self.policy.resolve(Path("x.py")), self.tmp / "x.py")

    def test_empty_and_dot_resolve_to_root(self):
        self.assertEqual(self.policy.resolve(""), self.tmp)
        self.assertEqual(self.policy.resolve("."), self.tmp)

    def test_dotdot_rejected_anywhere(self):
        for bad in ("..", "../escape", "src/../../../etc/passwd", "a/../.."):
            with self.assertRaises(PathError, msg=bad):
                self.policy.resolve(bad)

    def test_absolute_escape_rejected(self):
        with self.assertRaises(PathError):
            self.policy.resolve(str(self.tmp.parent / "outside.txt"))

    def test_null_byte_rejected(self):
        with self.assertRaises(PathError):
            self.policy.resolve("file\0.txt")

    def test_drive_like_garbage_stays_contained(self):
        # pathlib quirk: "ZZZ:/x" is NOT a valid single-letter drive, so it
        # parses as a relative name — it must resolve INSIDE the boundary,
        # never escape (regression guard for the quirk)
        resolved = self.policy.resolve("ZZZ:/nowhere/x")
        self.assertTrue(_is_under(resolved, self.tmp))

    def test_relative_form_helper(self):
        _touch(self.tmp / "src" / "deep" / "f.txt")
        self.assertEqual(self.policy.relative("src/deep/f.txt"), "src/deep/f.txt")
        self.assertEqual(self.policy.relative(""), ".")


class TestPathPolicyExclusions(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.policy = PathPolicy(self.tmp, excluded_paths=("node_modules", "secrets.env"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_excluded_directory_rejected(self):
        with self.assertRaises(PathError):
            self.policy.resolve("node_modules/pkg/index.js")

    def test_excluded_file_rejected(self):
        with self.assertRaises(PathError):
            self.policy.resolve("secrets.env")

    def test_sibling_passes(self):
        self.assertEqual(self.policy.resolve("src/app.py"), self.tmp / "src" / "app.py")

    def test_exclusion_prefix_is_boundary_checked(self):
        # "node_modules_backup" is NOT inside "node_modules"
        self.assertEqual(
            self.policy.resolve("node_modules_backup/f.txt"),
            self.tmp / "node_modules_backup" / "f.txt",
        )


class TestPathPolicySymlink(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.outside = Path(tempfile.mkdtemp())
        self.link = self.tmp / "sneaky"
        try:
            os.symlink(str(self.outside), str(self.link), target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation denied by OS (privilege required)")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.outside, ignore_errors=True)

    def test_symlink_escape_rejected(self):
        _touch(self.outside / "secret.txt")
        with self.assertRaises(PathError):
            self.policy = PathPolicy(self.tmp)
            self.policy.resolve("sneaky/secret.txt")

    def test_symlink_into_workspace_is_allowed(self):
        inner = self.tmp / "real"
        inner.mkdir()
        os.symlink(str(inner), str(self.tmp / "alias"), target_is_directory=True)
        policy = PathPolicy(self.tmp)
        self.assertEqual(policy.resolve("alias/f.txt"), inner / "f.txt")


@unittest.skipUnless(os.name == "nt", "Windows-specific path cases")
class TestPathPolicyWindows(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_case_insensitive_containment(self):
        policy = PathPolicy(self.tmp)
        variant = str(self.tmp).lower()
        if variant == str(self.tmp):
            variant = str(self.tmp).upper()
        self.assertEqual(policy.resolve(variant + "\\f.txt"), self.tmp / "f.txt")

    def test_backslash_relative_path(self):
        policy = PathPolicy(self.tmp)
        self.assertEqual(policy.resolve("src\\app.py"), self.tmp / "src" / "app.py")

    def test_cross_drive_escape_rejected(self):
        policy = PathPolicy(self.tmp)
        with self.assertRaises(PathError):
            policy.resolve("Q:/elsewhere/x")

    def test_protected_root_rejected(self):
        with self.assertRaises(PathError):
            PathPolicy("C:/Windows")

    def test_protected_resolve_rejected(self):
        policy = PathPolicy(self.tmp)
        with self.assertRaises(PathError):
            policy.resolve("C:/Windows/System32/drivers/etc/hosts")

    def test_protected_prefix_boundary(self):
        # a directory merely NAMED like a protected prefix is not protected
        decoy = self.tmp / "Windows"
        decoy.mkdir()
        policy = PathPolicy(decoy)
        self.assertEqual(policy.resolve("f.txt"), decoy / "f.txt")

    def test_case_variant_manager_cache(self):
        mgr = WorkspaceManager()
        first = mgr.open(self.tmp)
        variant = str(self.tmp).upper()
        if variant == str(self.tmp):
            variant = str(self.tmp).lower()
        self.assertIs(mgr.open(variant), first)


class TestPathPolicyAllowedPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sibling = Path(tempfile.mkdtemp())
        self.policy = PathPolicy(self.tmp, allowed_paths=(str(self.sibling),))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.sibling, ignore_errors=True)

    def test_allowed_path_contents_pass(self):
        self.assertEqual(
            self.policy.resolve(str(self.sibling / "data.bin")),
            self.sibling / "data.bin",
        )

    def test_outside_root_and_allowed_rejected(self):
        third = Path(tempfile.mkdtemp())
        try:
            with self.assertRaises(PathError):
                self.policy.resolve(str(third / "nope.txt"))
        finally:
            shutil.rmtree(third, ignore_errors=True)


@unittest.skipUnless(os.name == "posix", "POSIX protected prefixes")
class TestPathPolicyPosixProtected(unittest.TestCase):
    def test_etc_root_rejected(self):
        with self.assertRaises(PathError):
            PathPolicy("/etc")


class TestWorkspace(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_nonexistent_root_rejected(self):
        with self.assertRaises(WorkspaceError):
            Workspace(self.tmp / "missing")

    def test_file_root_rejected(self):
        _touch(self.tmp / "afile.txt")
        with self.assertRaises(WorkspaceError):
            Workspace(self.tmp / "afile.txt")

    def test_basic_shape(self):
        ws = Workspace(self.tmp)
        self.assertEqual(ws.root, self.tmp)
        self.assertEqual(ws.current_directory, ws.root)
        self.assertIsNone(ws.git_root)
        self.assertEqual(ws.metadata.project_type, "unknown")

    def test_git_root_at_workspace_root(self):
        (self.tmp / ".git").mkdir()
        self.assertEqual(Workspace(self.tmp).git_root, self.tmp)

    def test_git_root_found_at_ancestor(self):
        (self.tmp / ".git").mkdir()
        sub = self.tmp / "sub" / "pkg"
        sub.mkdir(parents=True)
        self.assertEqual(Workspace(sub).git_root, self.tmp)

    def test_set_cwd_inside_passes(self):
        (self.tmp / "src").mkdir()
        ws = Workspace(self.tmp)
        ws.set_cwd("src")
        self.assertEqual(ws.current_directory, self.tmp / "src")

    def test_set_cwd_outside_rejected(self):
        ws = Workspace(self.tmp)
        with self.assertRaises(PathError):
            ws.set_cwd("../elsewhere")

    def test_default_git_exclusion(self):
        (self.tmp / ".git").mkdir()
        _touch(self.tmp / ".git" / "config")
        ws = Workspace(self.tmp)
        with self.assertRaises(PathError):
            ws.resolve(".git/config")

    def test_describe_is_json_serializable(self):
        line = json.dumps(Workspace(self.tmp).describe())
        self.assertIn("root", line)

    def test_config_validation(self):
        with self.assertRaises(ValueError):
            WorkspaceConfig(excluded_paths=("",))


class TestProjectMetadata(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _detect(self):
        return ProjectMetadata.detect(self.tmp)

    def test_python_project(self):
        _touch(self.tmp / "pyproject.toml")
        _touch(self.tmp / "requirements.txt")
        _touch(self.tmp / "main.py")
        meta = self._detect()
        self.assertEqual(meta.languages, ("python",))
        self.assertEqual(meta.package_managers, ("pip",))
        self.assertEqual(meta.entrypoints, ("main.py",))
        self.assertEqual(meta.project_type, "python")

    def test_node_typescript_project(self):
        _touch(self.tmp / "package.json")
        _touch(self.tmp / "package-lock.json")
        _touch(self.tmp / "tsconfig.json")
        _touch(self.tmp / "index.ts")
        meta = self._detect()
        self.assertIn("javascript", meta.languages)
        self.assertIn("typescript", meta.languages)
        self.assertEqual(meta.package_managers, ("npm",))
        self.assertEqual(meta.project_type, "node")

    def test_rust_and_go(self):
        _touch(self.tmp / "Cargo.toml")
        self.assertEqual(self._detect().project_type, "rust")
        self.assertEqual(self._detect().package_managers, ("cargo",))

        shutil.rmtree(self.tmp)
        self.tmp = Path(tempfile.mkdtemp())
        _touch(self.tmp / "go.mod")
        self.assertEqual(self._detect().project_type, "go")

    def test_poetry_claimed_only_from_lockfile(self):
        _touch(self.tmp / "pyproject.toml")
        self.assertEqual(self._detect().package_managers, ())
        _touch(self.tmp / "poetry.lock")
        self.assertEqual(self._detect().package_managers, ("poetry",))

    def test_src_entrypoint(self):
        _touch(self.tmp / "src" / "main.rs")
        self.assertEqual(self._detect().entrypoints, ("src/main.rs",))

    def test_empty_dir_is_unknown(self):
        meta = self._detect()
        self.assertEqual(meta.project_type, "unknown")
        self.assertEqual(meta.languages, ())
        self.assertEqual(meta.package_managers, ())


class TestWorkspaceManager(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mgr = WorkspaceManager()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_open_caches_and_sets_active(self):
        first = self.mgr.open(self.tmp)
        self.assertIs(self.mgr.open(self.tmp), first)
        self.assertIs(self.mgr.active, first)

    def test_get_unknown_raises(self):
        with self.assertRaises(WorkspaceError):
            self.mgr.get(self.tmp)

    def test_get_after_open(self):
        self.mgr.open(self.tmp)
        self.assertEqual(self.mgr.get(self.tmp).root, self.tmp)

    def test_different_configs_not_merged(self):
        ws = self.mgr.open(self.tmp, WorkspaceConfig(excluded_paths=("dist",)))
        self.assertEqual(ws.config.excluded_paths, ("dist",))


class TestRegistryIntegration(unittest.TestCase):
    def test_requires_workspace_tool_passes_gate_with_workspace(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            reg = ToolRegistry()
            reg.register(RegisteredTool(
                definition=ToolDefinition(
                    name="rooted",
                    description="needs a workspace",
                    parameters_schema={"type": "object", "properties": {}},
                ),
                handler=lambda **kw: "in-boundary",
                requires_workspace=True,
            ))
            denied = reg.execute(ToolCall(name="rooted", arguments={}))
            self.assertFalse(denied.ok)
            ws = Workspace(tmp)
            allowed = reg.execute(ToolCall(name="rooted", arguments={}), workspace=ws)
            self.assertTrue(allowed.ok)
            self.assertEqual(allowed.output, "in-boundary")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
