"""S15 journal skill tests — durable lessons ledger.

Pins: append-only markdown, auto-timestamped entries, case-insensitive
grep, concurrent-safe appends, human-readable format.
"""

import os
import tempfile
import unittest
from pathlib import Path

from qacompanion.skills import journal


class JournalAddTests(unittest.TestCase):
    """Unit tests for journal.add()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ledger = os.path.join(self.tmpdir, "TEST_JOURNAL.md")

    def test_add_creates_file(self):
        journal.add("first entry", ledger=self.ledger)
        self.assertTrue(Path(self.ledger).exists())

    def test_add_returns_timestamped_line(self):
        result = journal.add("hello world", ledger=self.ledger)
        self.assertTrue(result.startswith("## "))
        self.assertIn("hello world", result)

    def test_add_empty_text_raises(self):
        with self.assertRaises(journal.JournalError):
            journal.add("", ledger=self.ledger)

    def test_add_whitespace_only_raises(self):
        with self.assertRaises(journal.JournalError):
            journal.add("   ", ledger=self.ledger)

    def test_add_multiline_raises(self):
        with self.assertRaises(journal.JournalError):
            journal.add("line1\nline2", ledger=self.ledger)

    def test_add_multiple_entries_append(self):
        journal.add("entry one", ledger=self.ledger)
        journal.add("entry two", ledger=self.ledger)
        content = Path(self.ledger).read_text(encoding="utf-8")
        lines = [l for l in content.splitlines() if l.startswith("## ")]
        self.assertEqual(len(lines), 2)

    def test_add_creates_parent_dirs(self):
        nested = os.path.join(self.tmpdir, "sub", "dir", "JOURNAL.md")
        journal.add("nested entry", ledger=nested)
        self.assertTrue(Path(nested).exists())


class JournalGrepTests(unittest.TestCase):
    """Unit tests for journal.grep()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ledger = os.path.join(self.tmpdir, "TEST_JOURNAL.md")

    def _seed(self, *texts):
        for t in texts:
            journal.add(t, ledger=self.ledger)

    def test_grep_empty_pattern_raises(self):
        with self.assertRaises(journal.JournalError):
            journal.grep("", ledger=self.ledger)

    def test_grep_missing_ledger_raises(self):
        with self.assertRaises(journal.JournalError):
            journal.grep("foo", ledger="/nonexistent/path/JOURNAL.md")

    def test_grep_no_matches(self):
        self._seed("alpha", "beta")
        results = journal.grep("gamma", ledger=self.ledger)
        self.assertEqual(results, [])

    def test_grep_finds_match(self):
        self._seed("fix the bug", "update docs")
        results = journal.grep("bug", ledger=self.ledger)
        self.assertEqual(len(results), 1)
        self.assertIn("fix the bug", results[0][1])

    def test_grep_case_insensitive(self):
        self._seed("Fix The Bug")
        results = journal.grep("fix", ledger=self.ledger)
        self.assertEqual(len(results), 1)

    def test_grep_returns_timestamps(self):
        self._seed("lesson learned")
        results = journal.grep("lesson", ledger=self.ledger)
        self.assertEqual(len(results), 1)
        ts = results[0][0]
        self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

    def test_grep_multiple_matches(self):
        self._seed("fix bug one", "fix bug two", "update docs")
        results = journal.grep("fix", ledger=self.ledger)
        self.assertEqual(len(results), 2)

    def test_grep_ignores_non_entry_lines(self):
        path = Path(self.ledger)
        path.write_text(
            "# Header\nsome text\n## 2026-01-01T00:00:00 real entry\n"
            "## 2026-01-02T00:00:00 another entry\n",
            encoding="utf-8",
        )
        results = journal.grep("entry", ledger=self.ledger)
        self.assertEqual(len(results), 2)


class JournalRenderTests(unittest.TestCase):
    """Unit tests for render functions."""

    def test_render_add(self):
        result = journal.render_add("## 2026-01-01T00:00:00 hello")
        self.assertEqual(result, "## 2026-01-01T00:00:00 hello")

    def test_render_grep_empty(self):
        result = journal.render_grep([], "foo")
        self.assertEqual(result, "no entries matching 'foo'")

    def test_render_grep_results(self):
        results = [("2026-01-01T00:00:00", "fix bug")]
        result = journal.render_grep(results, "fix")
        self.assertIn("2026-01-01T00:00:00", result)
        self.assertIn("fix bug", result)


class JournalTimestampTests(unittest.TestCase):
    """Verify timestamp format is pinned."""

    def test_timestamp_format(self):
        ts = journal._timestamp()
        self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


class JournalCLIExitContractTests(unittest.TestCase):
    """Golden CLI exit-code tests through main()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ledger = os.path.join(self.tmpdir, "JOURNAL.md")

    def test_add_exit_0(self):
        from qacompanion.__main__ import main
        ret = main(["journal", "add", "test entry", "--ledger", self.ledger])
        self.assertEqual(ret, 0)

    def test_grep_exit_1_no_match(self):
        from qacompanion.__main__ import main
        main(["journal", "add", "alpha", "--ledger", self.ledger])
        ret = main(["journal", "grep", "zzz", "--ledger", self.ledger])
        self.assertEqual(ret, 1)

    def test_grep_exit_0_match(self):
        from qacompanion.__main__ import main
        main(["journal", "add", "fix bug", "--ledger", self.ledger])
        ret = main(["journal", "grep", "bug", "--ledger", self.ledger])
        self.assertEqual(ret, 0)

    def test_add_empty_text_exit_1(self):
        from qacompanion.__main__ import main
        ret = main(["journal", "add", "", "--ledger", self.ledger])
        self.assertEqual(ret, 1)


class JournalE2ETests(unittest.TestCase):
    """Real file round-trip e2e test."""

    def test_full_cycle(self):
        tmpdir = tempfile.mkdtemp()
        ledger = os.path.join(tmpdir, "JOURNAL.md")
        journal.add("learned: phantom sitreps need evidence blocks", ledger=ledger)
        journal.add("learned: sole-committer prevents race conditions", ledger=ledger)
        journal.add("fixed: stderr leak in test helper", ledger=ledger)

        results = journal.grep("phantom", ledger=ledger)
        self.assertEqual(len(results), 1)
        self.assertIn("phantom sitreps", results[0][1])

        results = journal.grep("learned", ledger=ledger)
        self.assertEqual(len(results), 2)

        content = Path(ledger).read_text(encoding="utf-8")
        self.assertTrue(content.startswith("## "))
        lines = [l for l in content.splitlines() if l.startswith("## ")]
        self.assertEqual(len(lines), 3)


if __name__ == "__main__":
    unittest.main()
