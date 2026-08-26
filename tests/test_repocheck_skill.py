"""S14 repocheck skill tests: fixtures-first per rule, golden report.

ROADMAP S14 criteria: fixture repos with known states classified
correctly; non-repo dirs skipped silently. Pins frozen in the module
docstring (depth 3, 3-level scan, dot-dirs matched but not entered,
unreadable repos skipped not fatal). Units are hermetic (fake
subprocess doubles, tmp-dir fixtures only — case#9 hygiene rider);
real-git coverage is ONE temp-repo e2e pair. Exit contract
exercised: 0 clean, 1 issues found, 2 environment error.
"""

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qacompanion.__main__ import main
from qacompanion.skills import repocheck
from tests import quiet_stdout


def fake_git(branch="main", porcelain="", ahead="0", behind="0", remote="origin"):
    """_git double: receives (repo_dir, *args), returns (returncode, stdout)."""

    def _run(repo_dir, *args):
        verb = args[0] if args else ""
        if verb == "rev-parse":
            out = branch
        elif verb == "status":
            out = porcelain
        elif verb == "rev-list":
            range_str = args[2] if len(args) > 2 else ""
            out = ahead if "..HEAD" in range_str else behind
        elif verb == "remote":
            out = remote
        else:
            out = ""
        return (0, out)

    return _run


class WalkerTests(unittest.TestCase):
    """Depth / dot-dir / unreadable-dir fixtures over tmp dirs only."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def repo(self, *parts):
        target = self.root.joinpath(*parts)
        target.mkdir(parents=True)
        (target / ".git").mkdir()
        return target

    def test_repo_at_depth_three_found_not_four(self):
        deep = self.repo("a", "b", "c")
        too_deep = self.repo("a2", "b2", "c2", "d2", "e2")
        found = list(repocheck.iter_repo_dirs([self.root]))
        self.assertEqual([deep], found)
        self.assertNotIn(too_deep, found)

    def test_dot_dirs_matched_but_never_entered(self):
        hidden_repo = self.repo(".hidden-repo")
        buried = self.repo(".cache", "buried-repo")
        found = list(repocheck.iter_repo_dirs([self.root]))
        self.assertIn(hidden_repo, found)
        self.assertNotIn(buried, found)

    def test_root_itself_counts_as_candidate(self):
        repo_dir = self.repo("solo")
        self.assertEqual([repo_dir], list(repocheck.iter_repo_dirs([repo_dir])))

    def test_non_repo_dirs_skipped_silently(self):
        non_repo = self.root / "not-a-repo"
        non_repo.mkdir()
        found = list(repocheck.iter_repo_dirs([non_repo]))
        self.assertEqual([], found)

    def test_unreadable_directory_skipped_gracefully(self):
        survivor = self.repo("survivor")
        blocked = self.root / "blocked"
        blocked.mkdir()
        original = repocheck._children

        def guarded(directory):
            if Path(directory) == blocked:
                raise PermissionError(directory)
            return original(directory)

        with mock.patch.object(repocheck, "_children", side_effect=guarded):
            found = list(repocheck.iter_repo_dirs([self.root]))
        self.assertIn(survivor, found)


class DescribeUnitTests(unittest.TestCase):
    """describe() with injected _git double — no real git."""

    def test_clean_repo_no_remote(self):
        git = fake_git(branch="main", ahead="0", behind="0", remote="")
        with mock.patch.object(repocheck, "_git", side_effect=git):
            status = repocheck.describe(Path("fake/repo"))
        self.assertIsNotNone(status)
        self.assertFalse(status["dirty"])
        self.assertEqual(0, status["ahead"])
        self.assertEqual(0, status["behind"])
        self.assertTrue(status["missing_remotes"])

    def test_dirty_repo(self):
        git = fake_git(porcelain=" M file.txt\n")
        with mock.patch.object(repocheck, "_git", side_effect=git):
            status = repocheck.describe(Path("fake/repo"))
        self.assertTrue(status["dirty"])

    def test_ahead_repo(self):
        git = fake_git(ahead="3")
        with mock.patch.object(repocheck, "_git", side_effect=git):
            status = repocheck.describe(Path("fake/repo"))
        self.assertEqual(3, status["ahead"])

    def test_behind_repo(self):
        git = fake_git(behind="5")
        with mock.patch.object(repocheck, "_git", side_effect=git):
            status = repocheck.describe(Path("fake/repo"))
        self.assertEqual(5, status["behind"])

    def test_repo_with_remote(self):
        git = fake_git(remote="origin")
        with mock.patch.object(repocheck, "_git", side_effect=git):
            status = repocheck.describe(Path("fake/repo"))
        self.assertFalse(status["missing_remotes"])

    def test_unreadable_repo_returns_none(self):
        with mock.patch.object(repocheck, "_git", return_value=(128, "")):
            status = repocheck.describe(Path("broken/repo"))
        self.assertIsNone(status)


class ScanUnitTests(unittest.TestCase):
    """scan() over tmp-dir fixtures with injected _git."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def repo(self, *parts):
        target = self.root.joinpath(*parts)
        target.mkdir(parents=True)
        (target / ".git").mkdir()
        return target

    def test_clean_repo_counted_as_ok(self):
        self.repo("clean")
        git = fake_git(branch="main")
        with mock.patch.object(repocheck, "_git", side_effect=git):
            results = repocheck.scan([self.root])
        self.assertEqual(1, results["repos_scanned"])
        self.assertEqual(0, results["repos_skipped"])
        self.assertEqual(1, len(results["repos_ok"]))
        self.assertEqual(0, len(results["repos_dirty"]))

    def test_dirty_repo_classified(self):
        self.repo("dirty")
        git = fake_git(porcelain=" M app.py\n")
        with mock.patch.object(repocheck, "_git", side_effect=git):
            results = repocheck.scan([self.root])
        self.assertEqual(1, len(results["repos_dirty"]))
        self.assertEqual(0, len(results["repos_ok"]))

    def test_ahead_repo_classified(self):
        self.repo("ahead")
        git = fake_git(ahead="7")
        with mock.patch.object(repocheck, "_git", side_effect=git):
            results = repocheck.scan([self.root])
        self.assertEqual(1, len(results["repos_ahead"]))

    def test_no_remote_classified(self):
        self.repo("no-remote")
        git = fake_git(remote="")
        with mock.patch.object(repocheck, "_git", side_effect=git):
            results = repocheck.scan([self.root])
        self.assertEqual(1, len(results["repos_missing_remote"]))

    def test_multiple_repos_classified(self):
        self.repo("clean")
        self.repo("dirty")
        self.repo("ahead")

        def multi_git(repo_dir, *args):
            verb = args[0] if args else ""
            name = Path(repo_dir).name
            if verb == "rev-parse":
                out = "main"
            elif verb == "status":
                out = " M app.py\n" if name == "dirty" else ""
            elif verb == "rev-list":
                range_str = args[2] if len(args) > 2 else ""
                out = "3" if name == "ahead" and "..HEAD" in range_str else "0"
            elif verb == "remote":
                out = "origin"
            else:
                out = ""
            return (0, out)

        with mock.patch.object(repocheck, "_git", side_effect=multi_git):
            results = repocheck.scan([self.root])
        self.assertEqual(3, results["repos_scanned"])
        self.assertEqual(1, len(results["repos_ok"]))
        self.assertEqual(1, len(results["repos_dirty"]))
        self.assertEqual(1, len(results["repos_ahead"]))

    def test_non_repo_dirs_skipped(self):
        non_repo = self.root / "not-a-repo"
        non_repo.mkdir()
        results = repocheck.scan([non_repo])
        self.assertEqual(0, results["repos_scanned"])

    def test_unreadable_repo_counted_as_skipped(self):
        self.repo("ok-repo")
        broken = self.repo("broken-repo")

        def selective_git(repo_dir, *args):
            if Path(repo_dir).name == "broken-repo":
                return (128, "")
            verb = args[0] if args else ""
            if verb == "rev-parse":
                out = "main"
            elif verb == "status":
                out = ""
            elif verb == "rev-list":
                out = "0"
            elif verb == "remote":
                out = "origin"
            else:
                out = ""
            return (0, out)

        with mock.patch.object(repocheck, "_git", side_effect=selective_git):
            results = repocheck.scan([self.root])
        self.assertEqual(2, results["repos_scanned"])
        self.assertEqual(1, results["repos_skipped"])
        self.assertEqual(1, len(results["repos_ok"]))


class RenderTests(unittest.TestCase):
    """Golden output rendering."""

    def test_all_clean_report(self):
        results = {
            "repos_scanned": 2,
            "repos_skipped": 0,
            "repos_ok": [
                {"path": "/p/a", "branch": "main", "dirty": False,
                 "ahead": 0, "behind": 0, "missing_remotes": False},
                {"path": "/p/b", "branch": "dev", "dirty": False,
                 "ahead": 0, "behind": 0, "missing_remotes": False},
            ],
            "repos_dirty": [],
            "repos_ahead": [],
            "repos_missing_remote": [],
        }
        out = repocheck.render(results, "/p")
        self.assertIn("checked 2 repo(s)", out)
        self.assertIn("0 need(s) attention", out)
        self.assertNotIn("dirty", out)

    def test_mixed_issues_report(self):
        results = {
            "repos_scanned": 3,
            "repos_skipped": 0,
            "repos_ok": [
                {"path": "/p/clean", "branch": "main", "dirty": False,
                 "ahead": 0, "behind": 0, "missing_remotes": False},
            ],
            "repos_dirty": [
                {"path": "/p/dirty", "branch": "main", "dirty": True,
                 "ahead": 0, "behind": 0, "missing_remotes": False},
            ],
            "repos_ahead": [
                {"path": "/p/ahead", "branch": "main", "dirty": False,
                 "ahead": 5, "behind": 0, "missing_remotes": False},
            ],
            "repos_missing_remote": [],
        }
        out = repocheck.render(results, "/p")
        self.assertIn("dirty", out)
        self.assertIn("ahead=5", out)
        self.assertIn("2 need(s) attention", out)

    def test_no_remote_flagged(self):
        results = {
            "repos_scanned": 1,
            "repos_skipped": 0,
            "repos_ok": [],
            "repos_dirty": [],
            "repos_ahead": [],
            "repos_missing_remote": [
                {"path": "/p/noremote", "branch": "main", "dirty": False,
                 "ahead": 0, "behind": 0, "missing_remotes": True},
            ],
        }
        out = repocheck.render(results, "/p")
        self.assertIn("no-remote", out)
        self.assertIn("1 need(s) attention", out)


class GoldenCliTests(unittest.TestCase):
    """Golden-output CLI tests over hermetic fixtures (mocked _git)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def seed_fake_repo(self, name):
        repo_dir = self.root / name
        (repo_dir / ".git").mkdir(parents=True)
        return repo_dir

    def run_cli(self, argv, git_double):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(repocheck, "_git", side_effect=git_double):
            with contextlib.redirect_stdout(stdout), \
                    contextlib.redirect_stderr(stderr):
                code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_golden_clean_repo_exit_zero(self):
        self.seed_fake_repo("myproject")
        expected = "\n".join(
            [
                f"repocheck {self.root.resolve()}:",
                "checked 1 repo(s), skipped 0, 0 need(s) attention",
                "",
            ]
        )
        code, out, err = self.run_cli(
            ["repocheck", str(self.root)], fake_git()
        )
        self.assertEqual(0, code)
        self.assertEqual(expected, out)
        self.assertEqual("", err)

    def test_golden_dirty_repo_exit_one(self):
        self.seed_fake_repo("myproject")
        code, out, _ = self.run_cli(
            ["repocheck", str(self.root)],
            fake_git(porcelain=" M file.txt\n"),
        )
        self.assertEqual(1, code)
        self.assertIn("dirty", out)
        self.assertIn("1 need(s) attention", out)

    def test_golden_ahead_repo_exit_one(self):
        self.seed_fake_repo("myproject")
        code, out, _ = self.run_cli(
            ["repocheck", str(self.root)],
            fake_git(ahead="7"),
        )
        self.assertEqual(1, code)
        self.assertIn("ahead=7", out)

    def test_golden_no_remote_repo_exit_one(self):
        self.seed_fake_repo("myproject")
        code, out, _ = self.run_cli(
            ["repocheck", str(self.root)],
            fake_git(remote=""),
        )
        self.assertEqual(1, code)
        self.assertIn("no-remote", out)

    def test_golden_non_repo_dir_exit_zero(self):
        non_repo = self.root / "empty-dir"
        non_repo.mkdir()
        code, out, err = self.run_cli(
            ["repocheck", str(non_repo)], fake_git()
        )
        self.assertEqual(0, code)
        self.assertIn("checked 0 repo(s)", out)

    def test_missing_dir_is_environment_error_exit_two(self):
        missing = self.root / "nope"
        code, out, err = self.run_cli(
            ["repocheck", str(missing)], fake_git()
        )
        self.assertEqual(2, code)
        self.assertIn("error:", err)

    def test_git_unusable_is_environment_error_exit_two(self):
        self.seed_fake_repo("myproject")

        def explode(repo_dir, *args):
            raise repocheck.RepocheckEnvError("environment: git executable unusable")

        code, out, err = self.run_cli(
            ["repocheck", str(self.root)], explode
        )
        self.assertEqual(2, code)
        self.assertIn("error: environment: git executable unusable", err)


class RealGitE2ETests(unittest.TestCase):
    """The single real-git e2e pair: clean + dirty + ahead + no-remote."""

    def setUp(self):
        self.stdout_buf = quiet_stdout(self)
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def git(self, *argv, cwd=None):
        result = subprocess.run(
            ["git", *argv],
            cwd=str(cwd or self.root),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def seed_repo(self, name, dirty=False, ahead=0, has_remote=True):
        repo_dir = self.root / name
        repo_dir.mkdir()
        self.git("init", "-q", cwd=repo_dir)
        self.git("config", "user.name", "t", cwd=repo_dir)
        self.git("config", "user.email", "t@example.com", cwd=repo_dir)
        (repo_dir / "app.txt").write_text("seed\n", encoding="utf-8")
        self.git("add", "-A", cwd=repo_dir)
        self.git("commit", "-qm", "seed", cwd=repo_dir)
        self.git("branch", "-m", "main", cwd=repo_dir)

        if has_remote:
            bare = self.root / f"{name}-bare"
            bare.mkdir()
            self.git("init", "--bare", "-q", cwd=bare)
            self.git("remote", "add", "origin", str(bare), cwd=repo_dir)
            self.git("push", "-q", "origin", "main", cwd=repo_dir)

        if ahead > 0:
            for i in range(ahead):
                (repo_dir / f"file{i}.txt").write_text(f"commit {i}\n", encoding="utf-8")
                self.git("add", "-A", cwd=repo_dir)
                self.git("commit", "-qm", f"commit {i}", cwd=repo_dir)

        if dirty:
            (repo_dir / "stray.txt").write_text("dirty\n", encoding="utf-8")

        return repo_dir

    def run_repocheck(self, directory=None):
        target = str(directory or self.root)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["repocheck", target])
        return code, stdout.getvalue()

    def test_clean_repo_exit_zero(self):
        self.seed_repo("clean-project")
        code, out = self.run_repocheck(self.root / "clean-project")
        self.assertEqual(0, code)
        self.assertIn("0 need(s) attention", out)

    def test_dirty_repo_exit_one(self):
        self.seed_repo("dirty-project", dirty=True)
        code, out = self.run_repocheck(self.root / "dirty-project")
        self.assertEqual(1, code)
        self.assertIn("dirty", out)

    def test_ahead_repo_exit_one(self):
        self.seed_repo("ahead-project", ahead=3)
        code, out = self.run_repocheck(self.root / "ahead-project")
        self.assertEqual(1, code)
        self.assertIn("ahead=3", out)

    def test_no_remote_repo_exit_one(self):
        self.seed_repo("noremote-project", has_remote=False)
        code, out = self.run_repocheck(self.root / "noremote-project")
        self.assertEqual(1, code)
        self.assertIn("no-remote", out)

    def test_mixed_repos_scan(self):
        self.seed_repo("clean-project")
        self.seed_repo("dirty-project", dirty=True)
        code, out = self.run_repocheck()
        self.assertEqual(1, code)
        self.assertIn("dirty", out)
        self.assertIn("checked 2 repo(s)", out)

    def test_non_repo_dir_skipped(self):
        empty = self.root / "empty"
        empty.mkdir()
        code, out = self.run_repocheck(empty)
        self.assertEqual(0, code)
        self.assertIn("checked 0 repo(s)", out)


if __name__ == "__main__":
    unittest.main()
