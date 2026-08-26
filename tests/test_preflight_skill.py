"""S11 preflight skill tests: fixtures-first per rule, golden checklist.

Reviewer TASK mail #100 criteria: exactly the three ROADMAP S11 rules,
one VIOLATION + one PASSING fixture per rule, golden output naming the
violated rule (S10 style), hermetic units (subprocess.run injected),
and real-git coverage = ONE temp-repo e2e pair plus a REAL non-repo
invocation asserting the honest environment error (case#4 class),
never a traceback. Exit contract exercised: 0 pass, 1 violation,
2 environment error.
"""

import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qacompanion.__main__ import main
from qacompanion.skills import preflight
from tests import quiet_stdout

DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def fake_run(revparse=(0, "", ""), status=(0, "", "")):
    """subprocess.run double: 'git rev-parse ...' then 'git status ...'."""

    def _run(argv, **kwargs):
        if argv[1] == "rev-parse":
            code, out, err = revparse
        else:
            code, out, err = status
        return mock.Mock(returncode=code, stdout=out, stderr=err)

    return _run


class R3RuleTests(unittest.TestCase):
    """R3 sha256-quote-ordering fixtures (seed case #3 lore)."""

    def test_passing_fixture_quote_precedes_probe(self):
        text = (
            "artifact: tool.zip\n"
            f"expected sha256: {DIGEST}\n"
            "probe: installing tool.zip\n"
        )
        status, detail = preflight.check_r3(text)
        self.assertEqual(preflight.PASS, status)
        self.assertEqual(
            "sha256 quoted on line 2 precedes probe on line 3", detail
        )

    def test_violation_fixture_quote_after_probe_begins(self):
        text = f"probe: downloading tool.zip\nsha256: {DIGEST}\n"
        status, detail = preflight.check_r3(text)
        self.assertEqual(preflight.FAIL, status)
        self.assertEqual(
            "sha256 first quoted on line 2, probe began on line 1", detail
        )

    def test_violation_fixture_never_quoted(self):
        status, detail = preflight.check_r3("probe: installing tool.zip\n")
        self.assertEqual(preflight.FAIL, status)
        self.assertEqual("probe began with no sha256 quoted anywhere", detail)

    def test_probe_free_transcript_is_honest_skip(self):
        status, detail = preflight.check_r3("nothing happened\n")
        self.assertEqual(preflight.SKIP, status)
        self.assertIn("no probe markers found", detail)


class BomRuleTests(unittest.TestCase):
    """BOM fixtures over raw first bytes (utf-8-sig lore, case #2)."""

    def test_violation_fixture_names_file(self):
        items = [
            ("configs/app.json", b"\xef\xbb\xbf{}"),
            ("plain.toml", b"[a]\n"),
        ]
        status, detail = preflight.check_no_bom(items)
        self.assertEqual(preflight.FAIL, status)
        self.assertEqual("configs/app.json starts with a UTF-8 BOM", detail)

    def test_passing_fixture_counts_scanned_files(self):
        status, detail = preflight.check_no_bom([("x.json", b"{"), ("y.ini", b";")])
        self.assertEqual(preflight.PASS, status)
        self.assertEqual(
            "2 config file(s) scanned, none starts with a BOM", detail
        )

    def test_walker_finds_configs_sorted_excluding_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            (root / "z.yaml").write_text("a: 1", encoding="utf-8")
            (root / "notes.md").write_text("x", encoding="utf-8")
            sub = root / "configs"
            sub.mkdir()
            (sub / "a.json").write_text("{}", encoding="utf-8")
            self.assertEqual(
                ["configs/a.json", "z.yaml"], preflight.iter_config_paths(root)
            )


class CleanTreeRuleTests(unittest.TestCase):
    """Clean-tree fixtures over porcelain output."""

    def test_violation_fixture_lists_change_count(self):
        text = " M qacompanion/__main__.py\n?? stray.txt\n"
        status, detail = preflight.check_clean_tree(text)
        self.assertEqual(preflight.FAIL, status)
        self.assertEqual(
            "2 uncommitted change(s) in git status --porcelain", detail
        )

    def test_passing_fixture_empty_porcelain(self):
        status, detail = preflight.check_clean_tree("")
        self.assertEqual(preflight.PASS, status)
        self.assertEqual("git status --porcelain empty", detail)


class ChecklistGoldenTests(unittest.TestCase):
    """Golden-output CLI tests over hermetic fixtures (mocked git)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def run_cli(self, argv, revparse=None, status=None):
        kwargs = {}
        if revparse is not None:
            kwargs["revparse"] = revparse
        if status is not None:
            kwargs["status"] = status
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch("pathlib.Path.cwd", return_value=self.root), \
                mock.patch.object(
                    preflight.subprocess, "run", side_effect=fake_run(**kwargs)
                ):
            with contextlib.redirect_stdout(stdout), \
                    contextlib.redirect_stderr(stderr):
                code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_golden_all_pass_exit_zero(self):
        (self.root / "app.json").write_bytes(b"{}\n")
        transcript = self.root / "log.txt"
        transcript.write_text(
            "artifact: tool.zip\n"
            f"expected sha256: {DIGEST}\n"
            "probe: installing tool.zip\n",
            encoding="utf-8",
        )
        expected = "\n".join(
            [
                "preflight checklist:",
                "[pass] R3 sha256-quoted-before-probe: "
                "sha256 quoted on line 2 precedes probe on line 3",
                "[pass] no-BOM-in-configs: "
                "1 config file(s) scanned, none starts with a BOM",
                "[pass] clean-tree: git status --porcelain empty",
                "",
            ]
        )
        code, out, err = self.run_cli(
            ["preflight", "--transcript", str(transcript)],
            revparse=(0, str(self.root) + "\n", ""),
        )
        self.assertEqual(0, code)
        self.assertEqual(expected, out)
        self.assertEqual("", err)

    def test_golden_names_every_violated_rule_exit_one(self):
        (self.root / "bad.json").write_bytes(b"\xef\xbb\xbf{}")
        transcript = self.root / "log.txt"
        transcript.write_text(
            f"probe: downloading tool.zip\nsha256: {DIGEST}\n",
            encoding="utf-8",
        )
        expected = "\n".join(
            [
                "preflight checklist:",
                "[FAIL] R3 sha256-quoted-before-probe: "
                "sha256 first quoted on line 2, probe began on line 1",
                "[FAIL] no-BOM-in-configs: bad.json starts with a UTF-8 BOM",
                "[FAIL] clean-tree: "
                "1 uncommitted change(s) in git status --porcelain",
                "",
            ]
        )
        code, out, _ = self.run_cli(
            ["preflight", "--transcript", str(transcript)],
            revparse=(0, str(self.root) + "\n", ""),
            status=(0, "?? stray.txt\n", ""),
        )
        self.assertEqual(1, code)
        self.assertEqual(expected, out)

    def test_omitted_transcript_skips_r3_honestly_exit_zero(self):
        (self.root / "app.json").write_bytes(b"{}\n")
        code, out, _ = self.run_cli(
            ["preflight"], revparse=(0, str(self.root) + "\n", "")
        )
        self.assertEqual(0, code)
        self.assertIn(
            "[skip] R3 sha256-quoted-before-probe: "
            "no transcript supplied - rule skipped honestly",
            out,
        )

    def test_missing_explicit_transcript_is_environment_error(self):
        missing = self.root / "nope" / "log.txt"
        code, out, err = self.run_cli(["preflight", "--transcript", str(missing)])
        self.assertEqual(2, code)
        self.assertEqual("", out)
        self.assertIn("error:", err)
        self.assertIn(missing.name, err)
        self.assertIn("No such file", err)

    def test_non_repo_is_honest_environment_error_not_traceback(self):
        fatal = "fatal: not a git repository (or any of the parent directories)"
        code, out, err = self.run_cli(
            ["preflight"], revparse=(128, "", fatal + "\n")
        )
        self.assertEqual(2, code)
        self.assertEqual("", out)
        self.assertIn("error: environment: git rev-parse --show-toplevel failed", err)
        self.assertIn("not a git repository", err)

    def test_status_git_failure_is_environment_error_too(self):
        (self.root / "app.json").write_bytes(b"{}\n")
        code, _, err = self.run_cli(
            ["preflight"],
            revparse=(0, str(self.root) + "\n", ""),
            status=(128, "", "fatal: bad object HEAD"),
        )
        self.assertEqual(2, code)
        self.assertIn(
            "error: environment: git status --porcelain failed "
            "(fatal: bad object HEAD)",
            err,
        )


class RealGitE2ETests(unittest.TestCase):
    """The single real-hook e2e pair (S10 pattern): real git, temp repo."""

    def setUp(self):
        self.stdout_buf = quiet_stdout(self)
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def git(self, *argv):
        subprocess.run(
            ["git", *argv],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=True,
        )

    def run_preflight(self, *argv):
        stdout = io.StringIO()
        with mock.patch("pathlib.Path.cwd", return_value=self.root):
            with contextlib.redirect_stdout(stdout):
                code = main(["preflight", *argv])
        return code, stdout.getvalue()

    def seed_clean_repo(self):
        self.git("init", "-q")
        self.git("config", "user.name", "t")
        self.git("config", "user.email", "t@example.com")
        (self.root / "app.json").write_text("{}\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "seed")

    def test_real_repo_clean_then_dirty_flips_exit_contract(self):
        self.seed_clean_repo()
        code, out = self.run_preflight()
        self.assertEqual(0, code)
        self.assertIn("[pass] clean-tree: git status --porcelain empty", out)
        self.assertIn(
            "[skip] R3 sha256-quoted-before-probe", out
        )  # omitted transcript -> honest skip
        (self.root / "stray.txt").write_text("x", encoding="utf-8")
        code, out = self.run_preflight()
        self.assertEqual(1, code)
        self.assertIn("[FAIL] clean-tree: 1 uncommitted change(s)", out)

    def test_real_non_repo_dir_aborts_honestly(self):
        stderr = io.StringIO()
        with mock.patch("pathlib.Path.cwd", return_value=self.root):
            with contextlib.redirect_stderr(stderr):
                code = main(["preflight"])
        self.assertEqual(2, code)
        self.assertIn("not a git repository", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
