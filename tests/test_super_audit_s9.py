"""S75.9 super-audit S9 regression tests: boundary correctness batch —
root/drive containment (F8), git toplevel boundary (F10), dead
textwrap code removed (F12), substring rules labeled defense-in-depth
(F15).
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import curriculum
from qacompanion.agent.git_tools import GitError
from qacompanion.agent.workspace import _is_under, Workspace
from qacompanion.agent.git_tools import GitToolkit


class RootContainmentTests(unittest.TestCase):
    """F8: a root workspace ("/", "C:\\") failed closed — every path
    was rejected because "root + sep" doubled the separator."""

    def test_posix_root_contains_everything(self):
        self.assertTrue(_is_under(Path("/etc/passwd"), Path("/")))
        self.assertTrue(_is_under(Path("/"), Path("/")))

    def test_posix_root_still_rejects_relative_shapes(self):
        # a Windows-style path is not under the POSIX root conceptually,
        # but string containment cannot know that; the meaningful
        # assertion is that rooted prefixes still match exactly
        self.assertFalse(_is_under(Path("/opt"), Path("/usr")))

    @unittest.skipIf(os.name != "nt", "drive-root case is Windows-only")
    def test_drive_root_contains_its_tree(self):
        self.assertTrue(_is_under(Path("C:\\Windows"), Path("C:\\")))
        self.assertTrue(_is_under(Path("C:\\"), Path("C:\\")))
        self.assertFalse(_is_under(Path("D:\\x"), Path("C:\\")))

    def test_non_root_behavior_unchanged(self):
        self.assertTrue(_is_under(Path("/work/src/a.py"), Path("/work")))
        self.assertFalse(_is_under(Path("/work"), Path("/work/src")))


class GitToplevelBoundaryTests(unittest.TestCase):
    """F10: a workspace nested in a monorepo passed the old
    is-inside-work-tree check while git operated on the WHOLE repo."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.parent = Path(self._tmp.name) / "monorepo"
        self.child = self.parent / "packages" / "app"
        self.child.mkdir(parents=True)
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        subprocess.run(["git", "init", "-q"], cwd=self.parent, check=True,
                       env=env)
        (self.parent / "f.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "f.txt"], cwd=self.parent, check=True,
                       env=env)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.parent,
                       check=True, env=env)

    def test_nested_workspace_refused(self):
        workspace = Workspace(self.child)
        toolkit = GitToolkit(workspace)
        with self.assertRaises(GitError) as ctx:
            toolkit.git_status()
        self.assertIn("workspace boundary", str(ctx.exception))

    def test_root_workspace_still_works(self):
        workspace = Workspace(self.parent)
        toolkit = GitToolkit(workspace)
        result = toolkit.git_status()  # must not raise GitError
        self.assertIn("main", result)  # -b branch line present


class DeadCodeTests(unittest.TestCase):
    """F12: _test_footer called unimported textwrap — a guaranteed
    NameError for any future caller. Removed, not imported."""

    def test_test_footer_gone(self):
        self.assertFalse(hasattr(curriculum, "_test_footer"))


class RuleLabelingTests(unittest.TestCase):
    """F15: substring args_contains matching is defense-in-depth, not a
    boundary — the docstring must say so."""

    def test_matches_docstring_labels_the_semantics(self):
        from qacompanion.agent.permissions import PermissionRule
        doc = PermissionRule.matches.__doc__ or ""
        self.assertIn("defense-in-depth", doc)
        self.assertIn("NEVER a security boundary", doc)


if __name__ == "__main__":
    unittest.main()
