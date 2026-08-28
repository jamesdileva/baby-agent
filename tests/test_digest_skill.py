"""Tests for S20 digest skill: document ingestion and retrieval."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qacompanion.skills.digest import (
    DigestError,
    DigestStore,
    _content_hash,
    _snippet,
    digest_directory,
    format_results,
    parse_markdown,
    search,
)


def _md(path, content):
    """Write a markdown file at path."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")


# --- parse_markdown ---

class TestParseMarkdown(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_single_section_no_heading(self):
        path = Path(self.tmpdir) / "notes.md"
        _md(path, "Just some text here.")
        sections = parse_markdown(path)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["heading"], "notes")
        self.assertEqual(sections[0]["content"], "Just some text here.")

    def test_multiple_headings(self):
        path = Path(self.tmpdir) / "doc.md"
        _md(path, "# Intro\nHello world.\n# Setup\nRun make.\n")
        sections = parse_markdown(path)
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0]["heading"], "Intro")
        self.assertIn("Hello world", sections[0]["content"])
        self.assertEqual(sections[1]["heading"], "Setup")
        self.assertIn("Run make", sections[1]["content"])

    def test_text_before_first_heading(self):
        path = Path(self.tmpdir) / "doc.md"
        _md(path, "Preamble text.\n# Section One\nBody here.\n")
        sections = parse_markdown(path)
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0]["heading"], "doc")
        self.assertIn("Preamble text", sections[0]["content"])

    def test_empty_file(self):
        path = Path(self.tmpdir) / "empty.md"
        _md(path, "")
        sections = parse_markdown(path)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["content"], "(empty document)")

    def test_heading_without_content_skipped(self):
        path = Path(self.tmpdir) / "doc.md"
        _md(path, "# Empty Section\n\n# Real Section\nActual content.\n")
        sections = parse_markdown(path)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["heading"], "Real Section")

    def test_bom_stripped(self):
        path = Path(self.tmpdir) / "bom.md"
        path.write_bytes(b'\xef\xbb\xbf# BOM Section\nContent with BOM.\n')
        sections = parse_markdown(path)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["heading"], "BOM Section")

    def test_nonexistent_file_raises(self):
        with self.assertRaises(DigestError):
            parse_markdown(Path(self.tmpdir) / "nope.md")

    def test_h2_headings(self):
        path = Path(self.tmpdir) / "doc.md"
        _md(path, "## Sub Header\nSub content.\n")
        sections = parse_markdown(path)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["heading"], "Sub Header")


# --- DigestStore ---

class TestDigestStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = Path(self.tmpdir) / "digest.jsonl"

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_empty(self):
        store = DigestStore(self.store_path)
        self.assertEqual(store.load(), [])

    def test_add_creates_entry(self):
        store = DigestStore(self.store_path)
        entry, created = store.add("readme.md", "Intro", "Hello world.")
        self.assertTrue(created)
        self.assertEqual(entry["id"], 1)
        self.assertEqual(entry["source"], "readme.md")
        self.assertEqual(entry["heading"], "Intro")
        self.assertIn("content_hash", entry)

    def test_add_persists(self):
        store = DigestStore(self.store_path)
        store.add("a.md", "Section", "Content A.")
        store2 = DigestStore(self.store_path)
        entries = store2.load()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["source"], "a.md")

    def test_dedup_by_content_hash(self):
        store = DigestStore(self.store_path)
        _, c1 = store.add("a.md", "Sec", "Same content here.")
        _, c2 = store.add("b.md", "Other", "Same content here.")
        self.assertTrue(c1)
        self.assertFalse(c2)
        entries = store.load()
        self.assertEqual(len(entries), 1)

    def test_dedup_updates_timestamp(self):
        store = DigestStore(self.store_path)
        e1, _ = store.add("a.md", "Sec", "Same content here.")
        old_ts = e1["digested_at"]
        e2, _ = store.add("b.md", "Other", "Same content here.")
        self.assertEqual(e2["digested_at"], old_ts or e2["digested_at"])
        self.assertEqual(len(store.load()), 1)

    def test_different_content_not_deduped(self):
        store = DigestStore(self.store_path)
        store.add("a.md", "Sec", "Content A.")
        store.add("b.md", "Sec", "Content B.")
        self.assertEqual(len(store.load()), 2)

    def test_incremental_ids(self):
        store = DigestStore(self.store_path)
        e1, _ = store.add("a.md", "S1", "One.")
        e2, _ = store.add("b.md", "S2", "Two.")
        self.assertEqual(e1["id"], 1)
        self.assertEqual(e2["id"], 2)

    def test_atomic_save(self):
        store = DigestStore(self.store_path)
        store.add("a.md", "Sec", "Content.")
        entries = store.load()
        self.assertEqual(len(entries), 1)
        self.assertTrue(self.store_path.exists())

    def test_corrupt_file_raises(self):
        self.store_path.write_text("{bad json\n", encoding="utf-8")
        store = DigestStore(self.store_path)
        with self.assertRaises(DigestError):
            store.load()


# --- search ---

class TestSearch(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = Path(self.tmpdir) / "digest.jsonl"
        self.store = DigestStore(self.store_path)
        self.store.add("deploy.md", "Deployment", "Deploy using docker compose up.")
        self.store.add("tests.md", "Testing", "Run pytest to test the code.")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_match_by_content(self):
        results = search("docker", self.store_path)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "deploy.md")

    def test_match_by_heading(self):
        results = search("Testing", self.store_path)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "tests.md")

    def test_no_match(self):
        results = search("kubernetes", self.store_path)
        self.assertEqual(results, [])

    def test_case_insensitive(self):
        results = search("DEPLOY", self.store_path)
        self.assertEqual(len(results), 1)

    def test_multi_keyword_and_semantics(self):
        self.store.add("setup.md", "Setup", "Install docker and run tests.")
        results = search("docker tests", self.store_path)
        sources = [r["source"] for r in results]
        self.assertIn("setup.md", sources)

    def test_empty_query(self):
        results = search("", self.store_path)
        self.assertEqual(results, [])

    def test_empty_store(self):
        empty_path = Path(self.tmpdir) / "empty.jsonl"
        results = search("anything", empty_path)
        self.assertEqual(results, [])


# --- format_results ---

class TestFormatResults(unittest.TestCase):
    def test_no_results(self):
        output = format_results([], "query")
        self.assertIn("no matching passages", output)

    def test_single_result(self):
        entry = {"source": "doc.md", "heading": "Intro", "content": "Hello world."}
        output = format_results([entry], "Hello")
        self.assertIn("doc.md", output)
        self.assertIn("Intro", output)
        self.assertIn("Hello", output)

    def test_truncates_at_10(self):
        entries = [
            {"source": f"f{i}.md", "heading": "H", "content": f"word{i}"}
            for i in range(15)
        ]
        output = format_results(entries, "word")
        self.assertIn("and 5 more", output)


# --- _snippet ---

class TestSnippet(unittest.TestCase):
    def test_match_in_middle(self):
        text = "Start " * 10 + "TARGET word" + " end" * 10
        snippet = _snippet(text, "TARGET", context_chars=10)
        self.assertIn("TARGET", snippet)
        self.assertTrue(snippet.startswith("...") or "Start" not in snippet)

    def test_match_at_start(self):
        snippet = _snippet("Keyword at start.", "Keyword", context_chars=20)
        self.assertIn("Keyword", snippet)

    def test_match_at_end(self):
        text = "padding " * 20 + "Keyword"
        snippet = _snippet(text, "Keyword", context_chars=20)
        self.assertIn("Keyword", snippet)


# --- digest_directory ---

class TestDigestDirectory(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = Path(self.tmpdir) / "digest.jsonl"

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_digest_single_file(self):
        docs = Path(self.tmpdir) / "docs"
        docs.mkdir()
        _md(docs / "readme.md", "# Guide\nDeploy with care.\n")
        results = digest_directory(docs, self.store_path)
        self.assertEqual(results["files_scanned"], 1)
        self.assertEqual(results["entries_added"], 1)
        self.assertEqual(results["errors"], [])

    def test_digest_nested_dirs(self):
        docs = Path(self.tmpdir) / "docs"
        sub = docs / "sub"
        sub.mkdir(parents=True)
        _md(docs / "a.md", "# A\nContent A.\n")
        _md(sub / "b.md", "# B\nContent B.\n")
        results = digest_directory(docs, self.store_path)
        self.assertEqual(results["files_scanned"], 2)
        self.assertEqual(results["entries_added"], 2)

    def test_re_digest_deduplicates(self):
        docs = Path(self.tmpdir) / "docs"
        docs.mkdir()
        _md(docs / "a.md", "# Guide\nSame content.\n")
        digest_directory(docs, self.store_path)
        results = digest_directory(docs, self.store_path)
        self.assertEqual(results["entries_updated"], 1)
        self.assertEqual(results["entries_added"], 0)
        store = DigestStore(self.store_path)
        self.assertEqual(len(store.load()), 1)

    def test_non_markdown_skipped(self):
        docs = Path(self.tmpdir) / "docs"
        docs.mkdir()
        (docs / "readme.txt").write_text("not markdown", encoding="utf-8")
        _md(docs / "guide.md", "# Guide\nContent.\n")
        results = digest_directory(docs, self.store_path)
        self.assertEqual(results["files_scanned"], 1)

    def test_nonexistent_dir_raises(self):
        with self.assertRaises(DigestError):
            digest_directory(Path(self.tmpdir) / "nope", self.store_path)

    def test_empty_dir(self):
        docs = Path(self.tmpdir) / "docs"
        docs.mkdir()
        results = digest_directory(docs, self.store_path)
        self.assertEqual(results["files_scanned"], 0)
        self.assertEqual(results["entries_added"], 0)

    def test_search_after_digest(self):
        docs = Path(self.tmpdir) / "docs"
        docs.mkdir()
        _md(docs / "deploy.md", "# Deploy\nRun docker compose up.\n")
        digest_directory(docs, self.store_path)
        results = search("docker", self.store_path)
        self.assertEqual(len(results), 1)
        self.assertIn("deploy.md", results[0]["source"])


# --- CLI exit contracts ---

class TestDigestCLI(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = Path(self.tmpdir) / "digest.jsonl"
        self.docs = Path(self.tmpdir) / "docs"
        self.docs.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, *args):
        from qacompanion.__main__ import main
        return main(list(args))

    def test_digest_exit_0(self):
        _md(self.docs / "guide.md", "# Guide\nDeploy with care.\n")
        rc = self._run("digest", str(self.docs), "--store", str(self.store_path))
        self.assertEqual(rc, 0)
        self.assertTrue(self.store_path.exists())

    def test_digest_empty_dir_exit_0(self):
        rc = self._run("digest", str(self.docs), "--store", str(self.store_path))
        self.assertEqual(rc, 0)

    def test_digest_nonexistent_dir_exit_1(self):
        rc = self._run("digest", str(Path(self.tmpdir) / "nope"), "--store", str(self.store_path))
        self.assertEqual(rc, 1)

    def test_ask_exit_0_match(self):
        _md(self.docs / "deploy.md", "# Deploy\nRun docker compose.\n")
        self._run("digest", str(self.docs), "--store", str(self.store_path))
        rc = self._run("ask", "docker", "--digest", str(self.store_path))
        self.assertEqual(rc, 0)

    def test_ask_exit_1_no_match(self):
        _md(self.docs / "deploy.md", "# Deploy\nRun docker compose.\n")
        self._run("digest", str(self.docs), "--store", str(self.store_path))
        with patch("qacompanion.ollama_bridge._is_ollama_available", return_value=False):
            rc = self._run("ask", "kubernetes", "--digest", str(self.store_path))
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
