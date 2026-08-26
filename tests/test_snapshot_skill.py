"""S13 snapshot skill tests: fixtures-first per rule, golden report.

ROADMAP S13 criteria: snapshot round-trips byte-identical; manifest
hashes verified; refuses to overwrite existing stamps. Pins frozen
in the module docstring (UTC compact stamps, label gates, manifest
self-exclusion, 1 MiB chunked hashing, dirs row). Units are hermetic
(tmp-dir fixtures only - case#9 hygiene rider); the real coverage is
ONE round-trip e2e pair plus a restored-tree hash recheck. Exit
contract exercised: 0 created+verified, 1 bad source / bad label /
stamp collision, 2 copy or verify environment failure.
"""

import contextlib
import hashlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from random import Random
from unittest import mock

from qacompanion.__main__ import main
from qacompanion.skills import snapshot


STAMP_RE = r"^\d{8}T\d{6}Z$"
FIXED_STAMP = "20260826T130000Z"


def seed_tree(root):
    """Small deterministic tree: nested file, top file, empty dir."""
    root = Path(root)
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_bytes(b"hello\n")
    (root / "sub" / "b.bin").write_bytes(b"\x00\x01")
    (root / "hold").mkdir()
    return root


class StampUnitTests(unittest.TestCase):
    """The UTC stamp format and the unsafe-label gate."""

    def test_bare_stamp_is_utc_compact(self):
        self.assertRegex(snapshot.make_stamp(), STAMP_RE)

    def test_labeled_stamp_prefixes_label(self):
        with mock.patch.object(
            snapshot, "utc_now_text", return_value=FIXED_STAMP
        ):
            stamp = snapshot.make_stamp("proj")
        self.assertEqual(f"proj-{FIXED_STAMP}", stamp)

    def test_invalid_labels_rejected(self):
        for bad in ("", ".", "..", "a/b", "a\\b", "C:x"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                snapshot.normalize_label(bad)
        self.assertIsNone(snapshot.normalize_label(None))
        self.assertEqual("ok", snapshot.normalize_label("ok"))


class HashUnitTests(unittest.TestCase):
    """Known vector plus chunk-boundary equivalence."""

    def test_sha256_known_vector_abc(self):
        self.assertEqual(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            snapshot.sha256_file(self._write(b"abc")),
        )

    def test_chunked_hash_matches_direct_over_large_buffer(self):
        data = Random(7).randbytes(snapshot.HASH_CHUNK * 2 + 17)
        self.assertEqual(
            hashlib.sha256(data).hexdigest(),
            snapshot.sha256_file(self._write(data)),
        )

    def _write(self, data):
        handle = tempfile.NamedTemporaryFile(delete=False)
        self.addCleanup(os.unlink, handle.name)
        handle.write(data)
        handle.close()
        return handle.name


class ManifestUnitTests(unittest.TestCase):
    """Sorted rows, correct digests, self-exclusion, determinism."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.archive = Path(self._tmp.name) / FIXED_STAMP
        seed_tree(self.archive)
        self.manifest = snapshot.build_manifest(
            self.archive,
            source=str(Path(self._tmp.name) / "src"),
            created_utc="2026-08-26T13:00:00+00:00",
            label=None,
        )

    def test_sorted_rows_sizes_hashes_self_exclusion_dirs_row(self):
        files = self.manifest["files"]
        self.assertEqual(["a.txt", "sub/b.bin"], [f["path"] for f in files])
        by_path = {entry["path"]: entry for entry in files}
        self.assertEqual(6, by_path["a.txt"]["size"])
        self.assertEqual(hashlib.sha256(b"\x00\x01").hexdigest(),
                         by_path["sub/b.bin"]["sha256"])
        self.assertNotIn("MANIFEST.json", by_path)
        self.assertEqual(["hold", "sub"], self.manifest["dirs"])
        self.assertEqual(FIXED_STAMP, self.manifest["stamp"])

    def test_manifest_build_deterministic_for_fixed_inputs(self):
        again = snapshot.build_manifest(
            self.archive,
            source=str(Path(self._tmp.name) / "src"),
            created_utc="2026-08-26T13:00:00+00:00",
            label=None,
        )
        self.assertEqual(self._dumps(self.manifest), self._dumps(again))

    @staticmethod
    def _dumps(manifest):
        import json

        return json.dumps(manifest, indent=2, sort_keys=True)


class VerifyTests(unittest.TestCase):
    """The four verdicts: pristine, tamper, extra, missing."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.src = seed_tree(Path(self._tmp.name) / "src")
        self.dest = Path(self._tmp.name) / "archives" / FIXED_STAMP
        snapshot.create_snapshot(
            self.src, self.dest.parent,
            stamp=FIXED_STAMP, created_utc="2026-08-26T13:00:00+00:00",
        )

    def test_pristine_archive_verifies_clean(self):
        verdict = snapshot.verify_archive(self.dest)
        self.assertTrue(verdict["ok"])
        self.assertIsNone(verdict["problem"])
        self.assertEqual(2, verdict["checked"])

    def test_tampered_content_detected_as_hash_drift(self):
        target = self.dest / "a.txt"
        self.assertEqual(b"hello\n", target.read_bytes())
        target.write_bytes(b"HELL0\n")  # same length, different bytes
        verdict = snapshot.verify_archive(self.dest)
        self.assertFalse(verdict["ok"])
        self.assertIn("hash drift: a.txt", verdict["problem"])

    def test_size_change_detected_before_hashing(self):
        target = self.dest / "a.txt"
        target.write_bytes(target.read_bytes() + b"x")
        verdict = snapshot.verify_archive(self.dest)
        self.assertFalse(verdict["ok"])
        self.assertIn("size drift: a.txt", verdict["problem"])

    def test_unlisted_extra_file_detected(self):
        (self.dest / "stray.txt").write_text("sneaky", encoding="utf-8")
        verdict = snapshot.verify_archive(self.dest)
        self.assertFalse(verdict["ok"])
        self.assertIn("unlisted file(s): stray.txt", verdict["problem"])

    def test_deleted_file_detected_and_corrupt_manifest_flagged(self):
        (self.dest / "a.txt").unlink()
        verdict = snapshot.verify_archive(self.dest)
        self.assertFalse(verdict["ok"])
        self.assertIn("missing file: a.txt", verdict["problem"])
        (self.dest / "MANIFEST.json").write_text("{oops", encoding="utf-8")
        verdict = snapshot.verify_archive(self.dest)
        self.assertFalse(verdict["ok"])
        self.assertIn("manifest unreadable", verdict["problem"])


class CliGoldenTests(unittest.TestCase):
    """Golden-output CLI tests over hermetic tmp fixtures only."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.archives = self.base / "archives"

    def run_cli(self, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    @mock.patch.object(snapshot, "utc_now_text", return_value=FIXED_STAMP)
    def test_golden_happy_path_exit_zero(self, _patched):
        src = seed_tree(self.base / "proj")
        dest = self.archives / FIXED_STAMP
        expected = "\n".join(
            [
                f"snapshot '{FIXED_STAMP}':",
                f"archived 2 file(s), 8 byte(s) "
                f"from {src.resolve()} -> {dest.resolve()}",
                "manifest verified: 2/2 file(s)",
                "",
            ]
        )
        code, out, err = self.run_cli(
            ["snapshot", str(src), "--archives", str(self.archives)]
        )
        self.assertEqual(0, code)
        self.assertEqual(expected, out)
        self.assertEqual("", err)
        self.assertTrue((dest / "MANIFEST.json").is_file())

    @mock.patch.object(snapshot, "utc_now_text", return_value=FIXED_STAMP)
    def test_stamp_collision_refused_touches_nothing(self, _patched):
        src = seed_tree(self.base / "proj")
        argv = ["snapshot", str(src), "--archives", str(self.archives)]
        code, _, _ = self.run_cli(argv)
        self.assertEqual(0, code)
        before = sorted(p.name for p in (self.archives / FIXED_STAMP).iterdir())
        code, out, err = self.run_cli(argv)
        self.assertEqual(1, code)
        self.assertEqual("", out)
        self.assertIn("error: refusing to overwrite existing snapshot stamp",
                      err)
        after = sorted(p.name for p in (self.archives / FIXED_STAMP).iterdir())
        self.assertEqual(before, after)

    def test_missing_source_is_operational_error(self):
        missing = self.base / "nope"
        code, out, err = self.run_cli(
            ["snapshot", str(missing), "--archives", str(self.archives)]
        )
        self.assertEqual(1, code)
        self.assertEqual("", out)
        self.assertIn(f"error: source is not a directory: {missing}", err)

    def test_source_not_a_directory_exit_one(self):
        plain = self.base / "plain.txt"
        plain.write_text("x", encoding="utf-8")
        code, out, err = self.run_cli(
            ["snapshot", str(plain), "--archives", str(self.archives)]
        )
        self.assertEqual(1, code)
        self.assertIn("error: source is not a directory:", err)

    def test_invalid_label_exit_one_before_any_write(self):
        src = seed_tree(self.base / "proj")
        for bad in ("..", "a/b"):
            code, out, err = self.run_cli(
                ["snapshot", str(src), "--archives", str(self.archives),
                 "--label", bad]
            )
            self.assertEqual(1, code, msg=bad)
            self.assertEqual("", out, msg=bad)
            self.assertIn("error: invalid label:", err, msg=bad)
        self.assertFalse(self.archives.exists())

    def test_copy_failure_is_environment_error_exit_two(self):
        src = seed_tree(self.base / "proj")
        with mock.patch.object(
            snapshot.shutil, "copytree",
            side_effect=PermissionError("denied"),
        ):
            code, out, err = self.run_cli(
                ["snapshot", str(src), "--archives", str(self.archives)]
            )
        self.assertEqual(2, code)
        self.assertEqual("", out)
        self.assertIn("error: environment: snapshot failed", err)

    def test_archives_parent_created_on_demand(self):
        src = seed_tree(self.base / "proj")
        nested = self.base / "deep" / "nested" / "archives"
        code, _, _ = self.run_cli(
            ["snapshot", str(src), "--archives", str(nested)]
        )
        self.assertEqual(0, code)
        stamps = list(nested.iterdir())
        self.assertEqual(1, len(stamps))
        self.assertTrue((stamps[0] / "MANIFEST.json").is_file())


class RoundTripE2ETests(unittest.TestCase):
    """Real round-trip: unicode + binary + empty dir survive byte-identical."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.src = self.base / "precious"
        (self.src / "notes").mkdir(parents=True)
        (self.src / "empty").mkdir()
        (self.src / "top.txt").write_text("keep me\n", encoding="utf-8")
        (self.src / "notes" / "\u03b1\u03a9.txt").write_text(
            "\u4e16\u754c ok\n", encoding="utf-8"
        )
        (self.src / "notes" / "data.bin").write_bytes(bytes(range(256)) * 40)

    def run_snapshot(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main([
                "snapshot", str(self.src),
                "--archives", str(self.base / "archives"),
            ])
        return code, stdout.getvalue()

    def restore(self):
        stamps = list((self.base / "archives").iterdir())
        restored = self.base / "restored"
        shutil.copytree(stamps[0], restored)
        return restored

    def tree_files(self, root):
        found = set()
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                rel = (Path(dirpath) / name).relative_to(root)
                if rel.as_posix() == "MANIFEST.json":
                    continue
                found.add(rel.as_posix())
        return found

    def test_round_trip_byte_identical(self):
        code, out = self.run_snapshot()
        self.assertEqual(0, code)
        self.assertIn("manifest verified: 3/3 file(s)", out)
        restored = self.restore()
        original = {
            rel: (self.src / rel).read_bytes()
            for rel in self.tree_files(self.src)
        }
        copied = {
            rel: (restored / rel).read_bytes()
            for rel in self.tree_files(restored)
        }
        self.assertEqual(set(original), set(copied))
        for rel, payload in original.items():
            self.assertEqual(payload, copied[rel], msg=rel)

    def test_manifest_hashes_match_restored_tree(self):
        code, _ = self.run_snapshot()
        self.assertEqual(0, code)
        restored = self.restore()
        import json

        manifest = json.loads(
            (restored / "MANIFEST.json").read_text(encoding="utf-8")
        )
        self.assertEqual(str(self.src.resolve()), manifest["source"])
        for entry in manifest["files"]:
            path = restored / entry["path"]
            self.assertEqual(entry["size"], path.stat().st_size)
            self.assertEqual(
                entry["sha256"],
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
