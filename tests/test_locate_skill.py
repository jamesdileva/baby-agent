"""S12 locate skill tests: fixtures-first per rule, golden report.

ROADMAP S12 criteria: find a seeded repo by name fragment AND by a
contained commit hash; permission errors degrade gracefully. Pins are
frozen in the module docstring (depth 3, 20-commit scan, >=7-char hex,
repo roots never descended, dot-dirs matched but not entered). Units
are hermetic (fake subprocess doubles, tmp-dir fixtures only - case#9
hygiene rider); real-git coverage is ONE temp-repo e2e pair. Exit
contract exercised: 0 match, 1 no match / bad root, 2 git unusable.
"""

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qacompanion.__main__ import main
from qacompanion.skills import locate
from tests import quiet_stdout


def fake_git(branch="main", porcelain="", revlist=""):
    """subprocess.run double keyed on the first arg after 'git -C <p>'."""

    def _run(argv, **kwargs):
        verb = argv[3]
        if verb == "rev-parse":
            out = branch
        elif verb == "status":
            out = porcelain
        else:
            out = revlist
        return mock.Mock(returncode=0, stdout=out, stderr="")

    return _run


class HashQueryUnitTests(unittest.TestCase):
    """The >=7-hex gate that separates hash scans from name fragments."""

    def test_long_hex_is_hash_query(self):
        self.assertTrue(locate.is_hash_query("cafebabe123"))

    def test_short_hex_is_name_fragment_only(self):
        self.assertFalse(locate.is_hash_query("cafe"))

    def test_long_nonhex_is_name_fragment_only(self):
        self.assertFalse(locate.is_hash_query("zzzzzzz1234"))


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
        found = list(locate.iter_repo_dirs([self.root]))
        self.assertEqual([deep], found)
        self.assertNotIn(too_deep, found)

    def test_dot_dirs_matched_but_never_entered(self):
        hidden_repo = self.repo(".hidden-repo")
        buried = self.repo(".cache", "buried-repo")
        found = list(locate.iter_repo_dirs([self.root]))
        self.assertIn(hidden_repo, found)
        self.assertNotIn(buried, found)

    def test_root_itself_counts_as_candidate(self):
        repo_dir = self.repo("solo")
        self.assertEqual([repo_dir], list(locate.iter_repo_dirs([repo_dir])))

    def test_unreadable_directory_skipped_gracefully(self):
        survivor = self.repo("survivor")
        blocked = self.root / "blocked"
        blocked.mkdir()
        original = locate._children

        def guarded(directory):
            if Path(directory) == blocked:
                raise PermissionError(directory)
            return original(directory)

        with mock.patch.object(locate, "_children", side_effect=guarded):
            found = list(locate.iter_repo_dirs([self.root]))
        self.assertIn(survivor, found)


class MatcherUnitTests(unittest.TestCase):
    """Name-fragment vs commit-hash matching with an injected _git."""

    def test_name_match_short_circuits_without_git(self):
        with mock.patch.object(
            locate, "_git", side_effect=AssertionError("git must not run")
        ):
            self.assertTrue(locate.matches_query("task", Path("x/taskline")))

    def test_hash_prefix_matches_case_insensitively(self):
        hashes = "abc1234deadbeef\ndef456cafe0000\n"
        with mock.patch.object(
            locate, "_git", return_value=(0, hashes)
        ):
            self.assertTrue(locate.matches_query("ABC1234", Path("x/repo")))

    def test_non_matching_hash_scan_is_false(self):
        with mock.patch.object(locate, "_git", return_value=(0, "abc1234\n")):
            self.assertFalse(locate.matches_query("def4567", Path("x/repo")))

    def test_refused_plumbing_marks_repo_unreadable(self):
        with mock.patch.object(locate, "_git", return_value=(128, "")):
            self.assertIsNone(locate.matches_query("abc1234d", Path("x/broken")))

    def test_nonhash_long_query_never_scans_commits(self):
        with mock.patch.object(
            locate, "_git", side_effect=AssertionError("no rev-list expected")
        ):
            self.assertFalse(locate.matches_query("taskline!!", Path("x/other")))


class GoldenCliTests(unittest.TestCase):
    """Golden-output CLI tests over hermetic fixtures (mocked git)."""

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
        with mock.patch.object(
            locate.subprocess, "run", side_effect=git_double
        ):
            with contextlib.redirect_stdout(stdout), \
                    contextlib.redirect_stderr(stderr):
                code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_golden_found_by_fragment_exit_zero(self):
        repo_dir = self.seed_fake_repo("taskline")
        expected = "\n".join(
            [
                "locate 'task':",
                f"{repo_dir.resolve()}  branch=main clean",
                "searched 1 root(s), scanned 1 repo(s), "
                "skipped 0, found 1 match(es)",
                "",
            ]
        )
        code, out, err = self.run_cli(
            ["locate", "task", "--root", str(self.root)], fake_git()
        )
        self.assertEqual(0, code)
        self.assertEqual(expected, out)
        self.assertEqual("", err)

    def test_golden_reports_dirty_tree(self):
        repo_dir = self.seed_fake_repo("taskline")
        code, out, _ = self.run_cli(
            ["locate", "task", "--root", str(self.root)],
            fake_git(porcelain=" M f.txt\n"),
        )
        self.assertEqual(0, code)
        self.assertIn(f"{repo_dir.resolve()}  branch=main dirty", out)

    def test_golden_no_match_exit_one(self):
        self.seed_fake_repo("taskline")
        code, out, _ = self.run_cli(
            ["locate", "nomatch", "--root", str(self.root)], fake_git()
        )
        self.assertEqual(1, code)
        self.assertIn("found 0 match(es)", out)

    def test_missing_explicit_root_is_operational_error(self):
        missing = self.root / "nope"
        code, out, err = self.run_cli(
            ["locate", "task", "--root", str(missing)], fake_git()
        )
        self.assertEqual(1, code)
        self.assertEqual("", out)
        self.assertIn(f"error: root does not exist: {missing}", err)

    def test_duplicate_roots_collapse_to_one_search(self):
        self.seed_fake_repo("taskline")
        argv = [
            "locate", "task",
            "--root", str(self.root),
            "--root", str(self.root),
        ]
        code, out, _ = self.run_cli(argv, fake_git())
        self.assertEqual(0, code)
        self.assertIn("searched 1 root(s)", out)

    def test_git_unusable_is_environment_error_exit_two(self):
        self.seed_fake_repo("taskline")

        def explode(argv, **kwargs):
            raise FileNotFoundError("git")

        code, out, err = self.run_cli(
            ["locate", "task", "--root", str(self.root)], explode
        )
        self.assertEqual(2, code)
        self.assertEqual("", out)
        self.assertIn("error: environment: git executable unusable", err)

    def test_default_roots_dedupe_preserving_order(self):
        home = self.root / "home"
        (home / "Projects").mkdir(parents=True)
        with mock.patch.object(locate.Path, "home", return_value=home):
            roots = locate.default_roots()
        lowered = [str(root).lower() for root in roots]
        self.assertEqual(home / "Projects", roots[0])
        self.assertEqual(len(lowered), len(set(lowered)))
        self.assertEqual(home, roots[-1])


class RealGitE2ETests(unittest.TestCase):
    """The single real-git e2e pair: fragment find + hash find, dirty."""

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

    def seed_repo(self, name):
        repo_dir = self.root / name
        repo_dir.mkdir()
        self.git("init", "-q", cwd=repo_dir)
        self.git("config", "user.name", "t", cwd=repo_dir)
        self.git("config", "user.email", "t@example.com", cwd=repo_dir)
        (repo_dir / "app.txt").write_text("seed\n", encoding="utf-8")
        self.git("add", "-A", cwd=repo_dir)
        self.git("commit", "-qm", "seed", cwd=repo_dir)
        self.git("branch", "-m", "main", cwd=repo_dir)
        return repo_dir

    def run_locate(self, query):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["locate", query, "--root", str(self.root)])
        return code, stdout.getvalue()

    def test_find_by_fragment_then_by_head_hash_prefix(self):
        repo_dir = self.seed_repo("skunkworks-repo")
        code, out = self.run_locate("skunk")
        self.assertEqual(0, code)
        self.assertIn("branch=main clean", out)
        head = self.git("rev-parse", "HEAD", cwd=repo_dir)
        code, out = self.run_locate(head[:8])
        self.assertEqual(0, code)
        self.assertIn("skunkworks-repo", out)
        code, out = self.run_locate("deadbeef00")
        self.assertEqual(1, code)
        self.assertIn("found 0 match(es)", out)

    def test_dirty_status_reported_on_real_repo(self):
        self.seed_repo("skunkworks-repo")
        (self.root / "skunkworks-repo" / "stray.txt").write_text(
            "x", encoding="utf-8"
        )
        code, out = self.run_locate("skunkworks")
        self.assertEqual(0, code)
        self.assertIn("branch=main dirty", out)


if __name__ == "__main__":
    unittest.main()
