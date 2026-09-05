"""S34 filesystem tools tests: seven tools end-to-end through the registry.

Hermetic: every test runs against a temp-dir Workspace through
registry.execute — the same pipeline the model loop will use.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import ToolCall, ToolRegistry, Workspace
from qacompanion.agent.fs_tools import (
    MAX_READ_BYTES,
    ChangeLedger,
    FilesystemToolkit,
    agent_registry,
)
from qacompanion.agent.registry import ToolOperationError, RegisteredTool, ToolDefinition


class FsTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.toolkit = FilesystemToolkit(self.ws)
        self.reg = ToolRegistry()
        for tool in self.toolkit.tools():
            self.reg.register(tool)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, name, **arguments):
        return self.reg.execute(ToolCall(name=name, arguments=arguments),
                                workspace=self.ws)

    def payload(self, name, **arguments):
        result = self.call(name, **arguments)
        self.assertTrue(result.ok, f"{name} failed: {result.error}")
        return json.loads(result.output)


class TestRegistration(unittest.TestCase):
    def test_seven_tools_registered(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            reg = ToolRegistry()
            for tool in FilesystemToolkit(Workspace(tmp)).tools():
                reg.register(tool)
            self.assertEqual(
                reg.names(),
                ["edit_file", "file_exists", "file_metadata", "list_directory",
                 "read_file", "search_code", "write_file"],
            )
            described = {d["name"]: d for d in reg.describe()}
            for read_tool in ("list_directory", "read_file", "search_code",
                              "file_exists", "file_metadata"):
                self.assertEqual(described[read_tool]["side_effect_level"], "READ_ONLY")
            for write_tool in ("write_file", "edit_file"):
                self.assertEqual(described[write_tool]["side_effect_level"], "SAFE_WRITE")
            self.assertTrue(all(d["requires_workspace"] for d in described.values()))
            self.assertTrue(all(d["category"] == "filesystem" for d in described.values()))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_agent_registry_combines_all_tool_families(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            reg = agent_registry(Workspace(tmp))
            self.assertEqual(len(reg.names()), 41)
            self.assertIn("case_search", reg.names())
            self.assertIn("write_file", reg.names())
            self.assertIn("run_command", reg.names())
            self.assertIn("git_commit", reg.names())
            self.assertIn("get_environment_summary", reg.names())
            self.assertIn("run_verification", reg.names())
            self.assertIn("web_search", reg.names())
            self.assertIn("open_url", reg.names())
            self.assertIn("extract_page", reg.names())
            self.assertIn("download_artifact", reg.names())
            self.assertIn("capture_screen", reg.names())
            self.assertIn("inspect_image", reg.names())
            self.assertIn("compare_images", reg.names())
            self.assertIn("start_process", reg.names())
            self.assertIn("health_check", reg.names())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestEndToEndSequence(FsTestBase):
    def test_list_read_create_edit_search_inspect(self):
        # the roadmap verification sequence, via the real pipeline
        self.payload("write_file", path="src/app.py", content="def main():\n    return 42\n")
        listing = self.payload("list_directory", path=".")
        names = [e["name"] for e in listing["entries"]]
        self.assertIn("src", names)

        content = self.call("read_file", path="src/app.py")
        self.assertIn("return 42", content.output)

        self.payload("edit_file", path="src/app.py",
                     old_string="return 42", new_string="return 43")
        content = self.call("read_file", path="src/app.py")
        self.assertIn("return 43", content.output)

        search = self.payload("search_code", query="return 43")
        self.assertEqual(len(search["matches"]), 1)
        self.assertEqual(search["matches"][0]["path"], "src/app.py")

        meta = self.payload("file_metadata", path="src/app.py")
        self.assertEqual(meta["type"], "file")
        self.assertTrue(meta["sha256"])

        exists = self.payload("file_exists", path="src/app.py")
        self.assertTrue(exists["exists"])
        self.assertEqual(exists["type"], "file")

    def test_never_escapes_the_workspace(self):
        for name, kwargs in (
            ("read_file", {"path": "../outside.txt"}),
            ("write_file", {"path": "../evil.txt", "content": "x"}),
            ("edit_file", {"path": "../x.txt", "old_string": "a", "new_string": "b"}),
            ("list_directory", {"path": ".."}),
            ("file_exists", {"path": "../outside.txt"}),
            ("file_metadata", {"path": str(self.tmp.parent / "nope")}),
            ("search_code", {"query": "x", "path": ".."}),
        ):
            result = self.call(name, **kwargs)
            self.assertFalse(result.ok, f"{name} escaped the boundary")
            self.assertTrue(result.error)


class TestListDirectory(FsTestBase):
    def test_entries_sorted_dirs_first(self):
        (self.tmp / "zdir").mkdir()
        (self.tmp / "adirk").mkdir()
        (self.tmp / "bfile.txt").write_text("x", encoding="utf-8")
        payload = self.payload("list_directory", path=".")
        types = [e["type"] for e in payload["entries"]]
        self.assertEqual(types[0], "dir")
        self.assertEqual(types[-1], "file")
        self.assertFalse(payload["truncated"])

    def test_missing_dir_is_structured_error(self):
        result = self.call("list_directory", path="ghost")
        self.assertFalse(result.ok)
        self.assertIn("not a directory", result.error)

    def test_truncation_flag_at_cap(self):
        for i in range(502):
            (self.tmp / f"f{i:03}.txt").write_text("x", encoding="utf-8")
        payload = self.payload("list_directory", path=".")
        self.assertTrue(payload["truncated"])
        self.assertEqual(len(payload["entries"]), 500)


class TestReadFile(FsTestBase):
    def test_content_round_trip(self):
        (self.tmp / "a.txt").write_text("héllo ✅\nsecond\n", encoding="utf-8")
        out = self.call("read_file", path="a.txt")
        self.assertEqual(out.output, "héllo ✅\nsecond\n")

    def test_bom_stripped(self):
        (self.tmp / "bom.txt").write_bytes(b"\xef\xbb\xbfBOM lore\n")
        out = self.call("read_file", path="bom.txt")
        self.assertEqual(out.output, "BOM lore\n")

    def test_line_windowing(self):
        (self.tmp / "lines.txt").write_text(
            "\n".join(f"line{i}" for i in range(1, 11)) + "\n", encoding="utf-8"
        )
        out = self.call("read_file", path="lines.txt", start_line=3, max_lines=2)
        self.assertEqual(out.output, "line3\nline4\n")

    def test_oversize_rejected(self):
        big = self.tmp / "big.log"
        big.write_text("x" * (MAX_READ_BYTES + 1), encoding="utf-8")
        result = self.call("read_file", path="big.log")
        self.assertFalse(result.ok)
        self.assertIn("too large", result.error)

    def test_binary_rejected(self):
        (self.tmp / "bin.dat").write_bytes(b"abc\x00def")
        result = self.call("read_file", path="bin.dat")
        self.assertFalse(result.ok)
        self.assertIn("binary", result.error)

    def test_invalid_utf8_rejected(self):
        (self.tmp / "bad.txt").write_bytes(b"ok\xff\xfe tail")
        result = self.call("read_file", path="bad.txt")
        self.assertFalse(result.ok)
        self.assertIn("UTF-8", result.error)

    def test_missing_rejected(self):
        result = self.call("read_file", path="ghost.txt")
        self.assertFalse(result.ok)
        self.assertIn("file not found", result.error)


class TestWriteFile(FsTestBase):
    def test_create_with_auto_parents(self):
        payload = self.payload("write_file", path="deep/nested/app.py", content="x = 1\n")
        self.assertTrue(payload["created"])
        self.assertEqual((self.tmp / "deep" / "nested" / "app.py").read_text(
            encoding="utf-8"), "x = 1\n")

    def test_no_clobber_by_default(self):
        (self.tmp / "keep.txt").write_text("original", encoding="utf-8")
        result = self.call("write_file", path="keep.txt", content="clobbered")
        self.assertFalse(result.ok)
        self.assertIn("refusing to overwrite", result.error)
        self.assertEqual((self.tmp / "keep.txt").read_text(encoding="utf-8"), "original")

    def test_overwrite_flag(self):
        (self.tmp / "keep.txt").write_text("original", encoding="utf-8")
        payload = self.payload("write_file", path="keep.txt",
                               content="replaced", overwrite=True)
        self.assertFalse(payload["created"])
        self.assertEqual((self.tmp / "keep.txt").read_text(encoding="utf-8"), "replaced")

    def test_atomic_no_temp_leftovers(self):
        self.payload("write_file", path="atomic.txt", content="data")
        leftovers = [p.name for p in self.tmp.iterdir() if "tmp-" in p.name]
        self.assertEqual(leftovers, [])

    def test_sha256_and_ledger(self):
        payload = self.payload("write_file", path="hashed.txt", content="hash me")
        self.assertEqual(payload["sha256"][:8], self.toolkit.ledger.entries[0]["sha256_after"][:8])
        self.assertIsNone(self.toolkit.ledger.entries[0]["sha256_before"])
        self.assertEqual(self.toolkit.ledger.entries[0]["kind"], "write")

    def test_escape_denied(self):
        result = self.call("write_file",
                           path=str(self.tmp.parent / "evil.txt"), content="x")
        self.assertFalse(result.ok)


class TestEditFile(FsTestBase):
    def setUp(self):
        super().setUp()
        (self.tmp / "code.py").write_text(
            "def main():\n    return 42\n", encoding="utf-8"
        )

    def test_unique_replace(self):
        payload = self.payload("edit_file", path="code.py",
                               old_string="return 42", new_string="return 43")
        self.assertEqual(
            (self.tmp / "code.py").read_text(encoding="utf-8"),
            "def main():\n    return 43\n",
        )
        self.assertEqual(self.toolkit.ledger.entries[0]["kind"], "edit")
        self.assertTrue(payload["sha256"])

    def test_not_found(self):
        result = self.call("edit_file", path="code.py",
                           old_string="return 99", new_string="return 1")
        self.assertFalse(result.ok)
        self.assertIn("not found", result.error)

    def test_ambiguous_rejected(self):
        (self.tmp / "twice.txt").write_text("same same", encoding="utf-8")
        result = self.call("edit_file", path="twice.txt",
                           old_string="same", new_string="different")
        self.assertFalse(result.ok)
        self.assertIn("2 times", result.error)

    def test_noop_rejected(self):
        result = self.call("edit_file", path="code.py",
                           old_string="42", new_string="42")
        self.assertFalse(result.ok)
        self.assertIn("no-op", result.error)


class TestSearchCode(FsTestBase):
    def test_matches_with_line_numbers(self):
        (self.tmp / "a.py").write_text("alpha\nbeta TARGET\ngamma\n", encoding="utf-8")
        (self.tmp / "b.py").write_text("TARGET here\n", encoding="utf-8")
        payload = self.payload("search_code", query="target")
        self.assertEqual(len(payload["matches"]), 2)
        paths = {m["path"] for m in payload["matches"]}
        self.assertEqual(paths, {"a.py", "b.py"})
        self.assertEqual(payload["matches"][0]["line_number"], 2)

    def test_excluded_dir_not_searched(self):
        (self.tmp / ".git").mkdir()
        (self.tmp / ".git" / "hidden.txt").write_text("TARGET", encoding="utf-8")
        (self.tmp / "visible.txt").write_text("TARGET", encoding="utf-8")
        payload = self.payload("search_code", query="TARGET", case_sensitive=True)
        self.assertEqual([m["path"] for m in payload["matches"]], ["visible.txt"])

    def test_binary_and_generated_skipped(self):
        (self.tmp / "blob.bin").write_bytes(b"TARGET\x00")
        (self.tmp / "gen.pyc").write_text("TARGET", encoding="utf-8")
        payload = self.payload("search_code", query="TARGET")
        self.assertEqual(payload["matches"], [])

    def test_no_match_is_empty_not_error(self):
        payload = self.payload("search_code", query="zzz-nothing")
        self.assertEqual(payload["matches"], [])
        self.assertFalse(payload["truncated"])

    def test_max_results_cap(self):
        for i in range(6):
            (self.tmp / f"f{i}.txt").write_text("needle", encoding="utf-8")
        payload = self.payload("search_code", query="needle", max_results=3)
        self.assertEqual(len(payload["matches"]), 3)
        self.assertTrue(payload["truncated"])

    def test_subdir_scoping(self):
        (self.tmp / "sub").mkdir()
        (self.tmp / "sub" / "in.txt").write_text("findme", encoding="utf-8")
        (self.tmp / "out.txt").write_text("findme", encoding="utf-8")
        payload = self.payload("search_code", query="findme", path="sub")
        self.assertEqual([m["path"] for m in payload["matches"]], ["sub/in.txt"])


class TestExistsAndMetadata(FsTestBase):
    def test_exists_negative_is_honest(self):
        payload = self.payload("file_exists", path="ghost.txt")
        self.assertFalse(payload["exists"])
        self.assertIsNone(payload["type"])

    def test_exists_dir_typing(self):
        (self.tmp / "d").mkdir()
        payload = self.payload("file_exists", path="d")
        self.assertTrue(payload["exists"])
        self.assertEqual(payload["type"], "dir")

    def test_metadata_positive(self):
        (self.tmp / "m.txt").write_text("metadata target", encoding="utf-8")
        payload = self.payload("file_metadata", path="m.txt")
        self.assertEqual(payload["size"], len("metadata target"))
        self.assertTrue(payload["sha256"])
        self.assertTrue(payload["modified"].endswith("Z"))

    def test_metadata_missing_is_honest_negative(self):
        payload = self.payload("file_metadata", path="ghost.txt")
        self.assertFalse(payload["exists"])
        self.assertNotIn("size", payload)

    def test_metadata_dir_no_hash(self):
        (self.tmp / "d").mkdir()
        payload = self.payload("file_metadata", path="d")
        self.assertNotIn("sha256", payload)


class TestRegistrySeam(unittest.TestCase):
    def test_tool_operation_error_gets_clean_message(self):
        reg = ToolRegistry()
        reg.register(RegisteredTool(
            definition=ToolDefinition(
                name="expected_fail", description="d",
                parameters_schema={"type": "object", "properties": {}},
            ),
            handler=lambda **kw: (_ for _ in ()).throw(
                ToolOperationError("clean structured reason")),
        ))
        result = reg.execute(ToolCall(name="expected_fail", arguments={}))
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "clean structured reason")

    def test_unexpected_exception_keeps_handler_failed_prefix(self):
        reg = ToolRegistry()
        reg.register(RegisteredTool(
            definition=ToolDefinition(
                name="unexpected_fail", description="d",
                parameters_schema={"type": "object", "properties": {}},
            ),
            handler=lambda **kw: 1 / 0,
        ))
        result = reg.execute(ToolCall(name="unexpected_fail", arguments={}))
        self.assertFalse(result.ok)
        self.assertIn("handler failed", result.error)


class TestChangeLedger(unittest.TestCase):
    def test_paths_and_ordering(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            ws = Workspace(tmp)
            toolkit = FilesystemToolkit(ws)
            reg = ToolRegistry()
            for tool in toolkit.tools():
                reg.register(tool)
            reg.execute(ToolCall(name="write_file",
                                 arguments={"path": "a.txt", "content": "1"}),
                        workspace=ws)
            reg.execute(ToolCall(name="write_file",
                                 arguments={"path": "b.txt", "content": "2"}),
                        workspace=ws)
            reg.execute(ToolCall(name="edit_file",
                                 arguments={"path": "a.txt", "old_string": "1",
                                            "new_string": "one"}),
                        workspace=ws)
            self.assertEqual(toolkit.ledger.paths(), ["a.txt", "b.txt", "a.txt"])
            kinds = [e["kind"] for e in toolkit.ledger.entries]
            self.assertEqual(kinds, ["write", "write", "edit"])
            self.assertTrue(all(e["timestamp"].endswith("Z")
                                for e in toolkit.ledger.entries))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
