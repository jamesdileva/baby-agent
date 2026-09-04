"""S36 git intelligence tests: four read tools against real temp repos.

Hermetic: repos are created in temp dirs with inline git config; no network,
no global config dependence.
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qacompanion.agent import ToolCall, ToolRegistry, Workspace
from qacompanion.agent.git_tools import (
    GitError,
    GitToolkit,
    parse_branch_line,
    parse_log,
    parse_status,
)
from qacompanion.agent.fs_tools import agent_registry

GIT_CONFIG = [
    "-c", "user.name=test", "-c", "user.email=test@example.com",
    "-c", "commit.gpgsign=false",
]


class GitRepo:
    """Tiny git fixture: init -b main, commits with inline identity."""

    def __init__(self, root: Path):
        self.root = root
        self.git("init", "-b", "main")
        self.git("config", "user.name", "test")
        self.git("config", "user.email", "test@example.com")

    def git(self, *args):
        proc = subprocess.run(
            ["git", *GIT_CONFIG, *args], cwd=str(self.root),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert proc.returncode == 0, f"fixture git {args} failed: {proc.stderr}"
        return proc.stdout

    def write(self, name: str, content: str):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit_file(self, name: str, content: str, message: str):
        self.write(name, content)
        self.git("add", name)
        self.git("commit", "-m", message)


class GitTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = GitRepo(self.tmp)
        self.ws = Workspace(self.tmp)
        self.toolkit = GitToolkit(self.ws)
        self.reg = ToolRegistry()
        for tool in self.toolkit.tools():
            self.reg.register(tool)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, name, **arguments):
        return self.reg.execute(ToolCall(name=name, arguments=arguments),
                                workspace=self.ws)

    def payload(self, name, **arguments):
        out = self.call(name, **arguments)
        self.assertTrue(out.ok, f"{name} failed: {out.error}")
        return json.loads(out.output)


class TestGitStatus(GitTestBase):
    def test_clean_repo(self):
        self.repo.commit_file("README.md", "hello\n", "init")
        payload = self.payload("git_status")
        self.assertTrue(payload["clean"])
        self.assertEqual(payload["branch"], "main")
        self.assertFalse(payload["detached"])
        self.assertEqual(payload["entries"], [])

    def test_modified_tracked_file(self):
        self.repo.commit_file("app.py", "v1\n", "init")
        self.repo.write("app.py", "v2\n")
        payload = self.payload("git_status")
        self.assertFalse(payload["clean"])
        entry = next(e for e in payload["entries"] if e["path"] == "app.py")
        self.assertIn("M", entry["status"])

    def test_untracked_file(self):
        self.repo.commit_file("README.md", "x\n", "init")
        self.repo.write("new.txt", "untracked\n")
        payload = self.payload("git_status")
        entry = next(e for e in payload["entries"] if e["path"] == "new.txt")
        self.assertEqual(entry["status"], "??")

    def test_rename_entry(self):
        self.repo.commit_file("old_name.txt", "content\n", "init")
        self.repo.git("mv", "old_name.txt", "new_name.txt")
        payload = self.payload("git_status")
        entry = next(e for e in payload["entries"] if e["path"] == "new_name.txt")
        self.assertEqual(entry["orig_path"], "old_name.txt")

    def test_non_ascii_path_unquoted(self):
        self.repo.write("naïve.txt", "accent\n")
        payload = self.payload("git_status")
        paths = [e["path"] for e in payload["entries"]]
        self.assertIn("naïve.txt", paths)


class TestPorcelainParsers(unittest.TestCase):
    def test_branch_line_variants(self):
        self.assertEqual(parse_branch_line("## main")["branch"], "main")
        self.assertIsNone(parse_branch_line("## main")["ahead"])

        ahead = parse_branch_line("## main...origin/main [ahead 2]")
        self.assertEqual(ahead["ahead"], 2)
        self.assertIsNone(ahead["behind"])

        behind = parse_branch_line("## main...origin/main [behind 3]")
        self.assertEqual(behind["behind"], 3)

        both = parse_branch_line("## main...origin/main [ahead 1, behind 2]")
        self.assertEqual(both["ahead"], 1)
        self.assertEqual(both["behind"], 2)

        no_upstream = parse_branch_line("## feature")
        self.assertEqual(no_upstream["branch"], "feature")
        self.assertIsNone(no_upstream["ahead"])

        detached = parse_branch_line("## HEAD (no branch)")
        self.assertTrue(detached["detached"])
        self.assertIsNone(detached["branch"])

    def test_status_entries_and_clean(self):
        parsed = parse_status(
            "## main\n"
            " M modified.py\n"
            "?? untracked.txt\n"
            'R  "old name.txt" -> "new name.txt"\n'
        )
        self.assertFalse(parsed["clean"])
        self.assertEqual(len(parsed["entries"]), 3)
        rename = parsed["entries"][2]
        self.assertEqual(rename["path"], "new name.txt")
        self.assertEqual(rename["orig_path"], "old name.txt")


class TestGitDiff(GitTestBase):
    def test_unstaged_diff_shows_changes(self):
        self.repo.commit_file("app.py", "old line\n", "init")
        self.repo.write("app.py", "new line\n")
        out = self.call("git_diff")
        self.assertTrue(out.ok)
        self.assertIn("-old line", out.output)
        self.assertIn("+new line", out.output)

    def test_staged_diff(self):
        self.repo.commit_file("app.py", "v1\n", "init")
        self.repo.write("app.py", "v2\n")
        self.repo.git("add", "app.py")
        unstaged = self.call("git_diff")
        self.assertEqual(unstaged.output, "")
        staged = self.call("git_diff", staged=True)
        self.assertIn("+v2", staged.output)

    def test_path_scoped(self):
        self.repo.commit_file("a.txt", "a\n", "init")
        self.repo.commit_file("b.txt", "b\n", "init")
        self.repo.write("a.txt", "a2\n")
        self.repo.write("b.txt", "b2\n")
        out = self.call("git_diff", path="a.txt")
        self.assertIn("-a", out.output)
        self.assertNotIn("b.txt", out.output)

    def test_clean_repo_empty_diff(self):
        self.repo.commit_file("a.txt", "a\n", "init")
        out = self.call("git_diff")
        self.assertTrue(out.ok)
        self.assertEqual(out.output, "")

    def test_escape_path_structured_error(self):
        out = self.call("git_diff", path="../outside.txt")
        self.assertFalse(out.ok)
        self.assertTrue(out.error)


class TestGitLog(GitTestBase):
    def test_entries_newest_first(self):
        self.repo.commit_file("a.txt", "1\n", "first commit")
        self.repo.commit_file("a.txt", "2\n", "second commit")
        payload = self.payload("git_log")
        subjects = [e["subject"] for e in payload["entries"]]
        self.assertEqual(subjects, ["second commit", "first commit"])
        entry = payload["entries"][0]
        for field in ("hash", "short", "author", "date", "subject"):
            self.assertTrue(entry[field])

    def test_max_count(self):
        for i in range(3):
            self.repo.commit_file("a.txt", f"{i}\n", f"commit {i}")
        payload = self.payload("git_log", max_count=2)
        self.assertEqual(len(payload["entries"]), 2)

    def test_path_filter(self):
        self.repo.commit_file("a.txt", "1\n", "touch a")
        self.repo.commit_file("b.txt", "2\n", "touch b")
        payload = self.payload("git_log", path="a.txt")
        self.assertEqual([e["subject"] for e in payload["entries"]], ["touch a"])

    def test_empty_repository_is_structured_error(self):
        out = self.call("git_log")
        self.assertFalse(out.ok)
        self.assertIn("git log failed", out.error)

    def test_log_parser_fields(self):
        line = "abc123\x1fabc123\x1fJane Doe\x1f2026-09-04T00:00:00Z\x1ffix | the | bug"
        entries = parse_log(line)
        self.assertEqual(entries[0]["subject"], "fix | the | bug")
        self.assertEqual(entries[0]["author"], "Jane Doe")


class TestGitBranch(GitTestBase):
    def test_current_and_created_branch(self):
        self.repo.commit_file("a.txt", "1\n", "init")
        payload = self.payload("git_branch")
        self.assertEqual(payload["current"], "main")
        self.assertIn("main", payload["branches"])
        self.repo.git("checkout", "-b", "feature")
        payload = self.payload("git_branch")
        self.assertEqual(payload["current"], "feature")
        self.assertIn("feature", payload["branches"])

    def test_detached_head(self):
        self.repo.commit_file("a.txt", "1\n", "init")
        head = self.repo.git("rev-parse", "HEAD").strip()
        self.repo.git("checkout", "--detach", head)
        payload = self.payload("git_branch")
        self.assertIsNone(payload["current"])
        self.assertTrue(payload["detached"])


class TestFailureModes(unittest.TestCase):
    def test_non_repo_directory(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            out = ToolRegistry()
            reg = ToolRegistry()
            for tool in GitToolkit(Workspace(tmp)).tools():
                reg.register(tool)
            result = reg.execute(ToolCall(name="git_status", arguments={}),
                                 workspace=Workspace(tmp))
            self.assertFalse(result.ok)
            self.assertIn("not a git repository", result.error)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_git_binary(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            ws = Workspace(tmp)
            with patch("qacompanion.agent.git_tools.subprocess.run",
                       side_effect=FileNotFoundError("no git")):
                with self.assertRaises(GitError) as ctx:
                    GitToolkit(ws).git_status()
            self.assertIn("not available", str(ctx.exception))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestRegistration(unittest.TestCase):
    def test_six_git_tools(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            reg = ToolRegistry()
            for tool in GitToolkit(Workspace(tmp)).tools():
                reg.register(tool)
            self.assertEqual(
                reg.names(),
                ["git_add", "git_branch", "git_commit", "git_diff",
                 "git_log", "git_status"],
            )
            described = {d["name"]: d for d in reg.describe()}
            self.assertTrue(all(d["category"] == "git" for d in described.values()))
            for read_tool in ("git_status", "git_diff", "git_log", "git_branch"):
                self.assertEqual(described[read_tool]["side_effect_level"], "READ_ONLY")
            for write_tool in ("git_add", "git_commit"):
                self.assertEqual(described[write_tool]["side_effect_level"], "SAFE_WRITE")
            # the S36 posture: commits are the canonical ASK action
            self.assertTrue(described["git_commit"]["requires_confirmation"])
            self.assertFalse(described["git_add"]["requires_confirmation"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_agent_registry_now_twenty_one(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            reg = agent_registry(Workspace(tmp))
            self.assertEqual(len(reg.names()), 21)
            self.assertIn("git_commit", reg.names())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
