"""Tests for S29 — resident digest daemon."""

import json
import os
import signal
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from qacompanion.watch import (
    LEDGER_VERSION,
    ScanLedger,
    WatchDaemon,
    WatchError,
    digest_changed,
    file_sha256,
    scan_roots,
    watch,
)


class TestFileHash(unittest.TestCase):
    def test_sha256_deterministic(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".md") as f:
            f.write(b"hello world")
            path = f.name
        try:
            h1 = file_sha256(path)
            h2 = file_sha256(path)
            self.assertEqual(h1, h2)
            self.assertEqual(len(h1), 64)
        finally:
            os.unlink(path)

    def test_sha256_differs_for_different_content(self):
        files = []
        for content in [b"aaa", b"bbb"]:
            f = tempfile.NamedTemporaryFile(delete=False, suffix=".md")
            f.write(content)
            f.close()
            files.append(f.name)
        try:
            self.assertNotEqual(file_sha256(files[0]), file_sha256(files[1]))
        finally:
            for p in files:
                os.unlink(p)


class TestScanLedger(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ledger_path = os.path.join(self.tmpdir, "scan-ledger.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_creates_empty_state(self):
        ledger = ScanLedger(self.ledger_path)
        ledger.load()
        self.assertEqual(ledger.data["version"], LEDGER_VERSION)
        self.assertIsNone(ledger.data["last_scan"])
        self.assertEqual(ledger.data["files"], {})

    def test_save_and_load_roundtrip(self):
        ledger = ScanLedger(self.ledger_path)
        ledger.set_hash("foo.md", "abc123", 100)
        ledger.save()

        ledger2 = ScanLedger(self.ledger_path)
        ledger2.load()
        self.assertEqual(ledger2.get_hash("foo.md"), "abc123")
        self.assertIsNotNone(ledger2.data["last_scan"])

    def test_corrupt_ledger_recover(self):
        Path(self.ledger_path).write_text("NOT JSON{{{", encoding="utf-8")
        ledger = ScanLedger(self.ledger_path)
        ledger.load()
        self.assertEqual(ledger.data["files"], {})

    def test_version_mismatch_resets(self):
        Path(self.ledger_path).write_text(
            json.dumps({"version": 999, "files": {"x.md": {"sha256": "y"}}}),
            encoding="utf-8",
        )
        ledger = ScanLedger(self.ledger_path)
        ledger.load()
        self.assertEqual(ledger.data["files"], {})

    def test_remove_missing(self):
        ledger = ScanLedger(self.ledger_path)
        ledger.set_hash("a.md", "h1", 10)
        ledger.set_hash("b.md", "h2", 20)
        removed = ledger.remove_missing({"a.md"})
        self.assertEqual(removed, 1)
        self.assertIsNone(ledger.get_hash("b.md"))
        self.assertIsNotNone(ledger.get_hash("a.md"))

    def test_atomic_write(self):
        ledger = ScanLedger(self.ledger_path)
        ledger.set_hash("x.md", "sha", 5)
        ledger.save()
        self.assertTrue(os.path.exists(self.ledger_path))
        tmp = Path(self.ledger_path).with_suffix(".json.tmp")
        self.assertFalse(tmp.exists())


class TestScanRoots(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ledger = ScanLedger(os.path.join(self.tmpdir, "ledger.json"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_detects_new_file(self):
        root = os.path.join(self.tmpdir, "root1")
        os.makedirs(root)
        Path(os.path.join(root, "new.md")).write_text("content", encoding="utf-8")

        changed, all_rel = scan_roots([root], self.ledger)
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0][1], "new.md")

    def test_no_changes_on_second_scan(self):
        root = os.path.join(self.tmpdir, "root2")
        os.makedirs(root)
        Path(os.path.join(root, "a.md")).write_text("content", encoding="utf-8")

        changed1, _ = scan_roots([root], self.ledger)
        self.assertEqual(len(changed1), 1)

        for _, _, _, full_key, sha in changed1:
            self.ledger.set_hash(full_key, sha, 7)
        changed2, _ = scan_roots([root], self.ledger)
        self.assertEqual(len(changed2), 0)

    def test_detects_modified_file(self):
        root = os.path.join(self.tmpdir, "root3")
        os.makedirs(root)
        fpath = os.path.join(root, "a.md")
        Path(fpath).write_text("v1", encoding="utf-8")

        changed1, _ = scan_roots([root], self.ledger)
        for _, _, _, full_key, sha in changed1:
            self.ledger.set_hash(full_key, sha, 2)

        Path(fpath).write_text("v2", encoding="utf-8")
        changed2, _ = scan_roots([root], self.ledger)
        self.assertEqual(len(changed2), 1)

    def test_skips_directories(self):
        root = os.path.join(self.tmpdir, "root4")
        os.makedirs(os.path.join(root, "subdir"))
        changed, _ = scan_roots([root], self.ledger)
        self.assertEqual(len(changed), 0)

    def test_nonexistent_root_skipped(self):
        changed, _ = scan_roots(["/no/such/dir"], self.ledger)
        self.assertEqual(len(changed), 0)

    def test_multiple_roots(self):
        r1 = os.path.join(self.tmpdir, "r1")
        r2 = os.path.join(self.tmpdir, "r2")
        os.makedirs(r1)
        os.makedirs(r2)
        Path(os.path.join(r1, "a.md")).write_text("a", encoding="utf-8")
        Path(os.path.join(r2, "b.md")).write_text("b", encoding="utf-8")

        changed, _ = scan_roots([r1, r2], self.ledger)
        self.assertEqual(len(changed), 2)

    def test_non_md_files_skipped_in_digest(self):
        root = os.path.join(self.tmpdir, "root5")
        os.makedirs(root)
        Path(os.path.join(root, "a.py")).write_text("print(1)", encoding="utf-8")

        changed, _ = scan_roots([root], self.ledger)
        self.assertEqual(len(changed), 1)
        results = digest_changed(changed, self.ledger)
        self.assertEqual(results["entries_added"], 0)
        self.assertEqual(results["files_scanned"], 1)


class TestDigestChanged(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ledger = ScanLedger(os.path.join(self.tmpdir, "ledger.json"))
        self.store_path = os.path.join(self.tmpdir, "digests.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_digests_markdown(self):
        root = os.path.join(self.tmpdir, "root")
        os.makedirs(root)
        Path(os.path.join(root, "doc.md")).write_text("# Title\n\nContent here.", encoding="utf-8")

        changed, _ = scan_roots([root], self.ledger)
        results = digest_changed(changed, self.ledger, self.store_path)
        self.assertEqual(results["entries_added"], 1)
        self.assertEqual(results["files_scanned"], 1)

    def test_skips_non_md(self):
        root = os.path.join(self.tmpdir, "root")
        os.makedirs(root)
        Path(os.path.join(root, "a.txt")).write_text("hello", encoding="utf-8")

        changed, _ = scan_roots([root], self.ledger)
        results = digest_changed(changed, self.ledger, self.store_path)
        self.assertEqual(results["entries_added"], 0)


class TestWatchDaemon(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.archives = os.path.join(self.tmpdir, "archives")
        self.roots_dir = os.path.join(self.tmpdir, "roots")
        os.makedirs(self.archives)
        os.makedirs(self.roots_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_once_mode(self):
        Path(os.path.join(self.archives, "test.md")).write_text("# Hi\n\nBody.", encoding="utf-8")
        daemon = WatchDaemon(
            archives=self.archives,
            roots=[],
            once=True,
            data_dir=self.tmpdir,
        )
        daemon.run()
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "scan-ledger.json")))

    def test_ledger_persists_across_runs(self):
        Path(os.path.join(self.archives, "a.md")).write_text("# A", encoding="utf-8")
        d1 = WatchDaemon(archives=self.archives, roots=[], once=True, data_dir=self.tmpdir)
        d1.run()

        d2 = WatchDaemon(archives=self.archives, roots=[], once=True, data_dir=self.tmpdir)
        d2.run()

        ledger = ScanLedger(os.path.join(self.tmpdir, "scan-ledger.json"))
        ledger.load()
        self.assertEqual(len(ledger.data["files"]), 1)

    def test_signal_stops_daemon(self):
        Path(os.path.join(self.archives, "a.md")).write_text("# A", encoding="utf-8")
        daemon = WatchDaemon(
            archives=self.archives,
            roots=[],
            interval=60,
            data_dir=self.tmpdir,
        )

        def signal_after_delay():
            time.sleep(0.1)
            daemon.shutdown_requested = True

        t = threading.Thread(target=signal_after_delay)
        t.start()
        daemon.run()
        t.join()
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "scan-ledger.json")))

    def test_changes_across_cycles(self):
        fpath = os.path.join(self.archives, "a.md")
        Path(fpath).write_text("# V1", encoding="utf-8")

        daemon = WatchDaemon(
            archives=self.archives, roots=[], once=True, data_dir=self.tmpdir,
        )
        daemon.run()

        Path(fpath).write_text("# V2", encoding="utf-8")
        daemon2 = WatchDaemon(
            archives=self.archives, roots=[], once=True, data_dir=self.tmpdir,
        )
        daemon2.run()

        ledger = ScanLedger(os.path.join(self.tmpdir, "scan-ledger.json"))
        ledger.load()
        sha = ledger.get_hash(f"{self.archives}:a.md")
        self.assertIsNotNone(sha)
        expected = file_sha256(fpath)
        self.assertEqual(sha, expected)


class TestWatchEntryPoint(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.archives = os.path.join(self.tmpdir, "archives")
        os.makedirs(self.archives)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_watch_once(self):
        result = watch(archives=self.archives, roots=[], once=True, data_dir=self.tmpdir)
        self.assertEqual(result["status"], "ok")

    def test_watch_invalid_archives(self):
        with self.assertRaises(WatchError):
            watch(archives="/no/such/dir", roots=[], once=True)

    def test_watch_invalid_root(self):
        with self.assertRaises(WatchError):
            watch(archives=self.archives, roots=["/no/such"], once=True)


if __name__ == "__main__":
    unittest.main()
