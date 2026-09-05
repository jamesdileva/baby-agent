"""S46 static code intelligence tests: AST precision, heuristics labeled,
freshness, policy, tools.

Fixture: a multi-module Python project (cross-module calls, class with
methods, variables), a broken-syntax file, a JS file, and a Go file.
"""

import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from qacompanion.agent import ToolCall, ToolRegistry, Workspace
from qacompanion.agent.codeintel import CodeIntelToolkit
from qacompanion.agent.fs_tools import agent_registry


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


UTILS = '''"""Shared helpers."""
MAX_ITEMS = 10

def clamp(value, low, high):
    if value < low:
        return low
    return min(value, high)

class Registry:
    version = 1

    def register(self, name):
        self.name = name
        return clamp(len(name), 0, MAX_ITEMS)
'''

MAIN = '''import os
from utils import Registry, clamp

def run():
    registry = Registry()
    size = registry.register("agent")
    return clamp(size, 0, 5), os.getcwd()
'''

BAD_SYNTAX = 'def broken(:\n    pass\n'

JS_FILE = '''import { helper } from "./helpers.js";
const http = require("http");
export class Server {
}
export function start(port) {
    return helper(port);
}
'''

GO_FILE = '''package main

func main() {
}
'''


class CodeIntelBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        _write(self.tmp / "utils.py", UTILS)
        _write(self.tmp / "main.py", MAIN)
        _write(self.tmp / "broken.py", BAD_SYNTAX)
        _write(self.tmp / "app.js", JS_FILE)
        _write(self.tmp / "main.go", GO_FILE)
        (self.tmp / "blob.bin").write_bytes(b"\x00\x01\x02")
        (self.tmp / ".git").mkdir()
        _write(self.tmp / ".git" / "fake.py", "def hidden():\n    pass\n")
        self.ws = Workspace(self.tmp)
        self.toolkit = CodeIntelToolkit(self.ws)
        self.reg = ToolRegistry()
        for tool in self.toolkit.tools():
            self.reg.register(tool)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, tool, **arguments):
        return self.reg.execute(ToolCall(name=tool, arguments=arguments),
                                workspace=self.ws)

    def payload(self, tool, **arguments):
        out = self.call(tool, **arguments)
        self.assertTrue(out.ok, f"{tool} failed: {out.error}")
        return json.loads(out.output)


class TestPythonSymbols(CodeIntelBase):
    def test_exact_definition_lookup(self):
        payload = self.payload("code_symbols", query="clamp", exact=True)
        self.assertEqual(payload["count"], 1)
        symbol = payload["symbols"][0]
        self.assertEqual(symbol["kind"], "function")
        self.assertEqual(symbol["file"], "utils.py")
        self.assertEqual(symbol["language"], "python")

    def test_substring_search_across_kinds(self):
        payload = self.payload("code_symbols", query="regist")
        names = {s["name"] for s in payload["symbols"]}
        self.assertIn("Registry", names)
        self.assertIn("Registry.register", names)  # qualified method
        kinds = {s["name"]: s["kind"] for s in payload["symbols"]}
        self.assertEqual(kinds["Registry"], "class")
        self.assertEqual(kinds["Registry.register"], "method")

    def test_variable_definitions(self):
        payload = self.payload("code_symbols", query="MAX_ITEMS", exact=True)
        self.assertEqual(payload["symbols"][0]["kind"], "variable")

    def test_kind_filter(self):
        payload = self.payload("code_symbols", query="r", kind="class",
                               language="python")
        self.assertEqual({s["name"] for s in payload["symbols"]}, {"Registry"})

    def test_definition_site_flagged_in_references(self):
        # AST honesty: a function's own name is a plain string, not a Name
        # node — so only VARIABLES carry is_definition at their def line
        # (MAX_ITEMS's target IS a Name node on line 3 of utils.py)
        payload = self.payload("code_references", name="MAX_ITEMS")
        def_refs = [r for r in payload["references"]
                    if r["is_definition"] and r["file"] == "utils.py"]
        self.assertEqual(len(def_refs), 1)
        self.assertEqual(def_refs[0]["line"], 2)  # MAX_ITEMS = 10
        self.assertTrue(all(r["precise"] for r in payload["references"]))

    def test_call_site_found_in_other_file(self):
        # clamp is defined in utils.py and called in main.py: the precise
        # reference machinery proves cross-file "who calls it"
        payload = self.payload("code_references", name="clamp")
        files = {r["file"] for r in payload["references"]}
        self.assertIn("utils.py", files)   # body references
        self.assertIn("main.py", files)    # the call site
        self.assertTrue(
            all(r["precise"] for r in payload["references"]))

    def test_method_reference_found(self):
        payload = self.payload("code_references", name="register")
        files = {r["file"] for r in payload["references"]}
        self.assertIn("main.py", files)


class TestImports(CodeIntelBase):
    def test_imports_of_file(self):
        payload = self.payload("code_imports", path="main.py")
        modules = {i["module"] for i in payload["imports"]}
        self.assertIn("os", modules)
        self.assertIn("utils", modules)
        utils_import = next(i for i in payload["imports"]
                            if i["module"] == "utils")
        self.assertIn("Registry", utils_import["names"])
        self.assertIn("clamp", utils_import["names"])

    def test_importers_via_suffix_match(self):
        payload = self.payload("code_importers", module="utils")
        files = {i["file"] for i in payload["importers"]}
        self.assertIn("main.py", files)

    def test_imports_of_unindexed_path(self):
        out = self.call("code_imports", path="ghost.py")
        self.assertFalse(out.ok)
        self.assertIn("not indexed", out.error)

    def test_imports_escape_rejected(self):
        out = self.call("code_imports", path="../outside.py")
        self.assertFalse(out.ok)


class TestDiagnosticsAndFreshness(CodeIntelBase):
    def test_diagnostics_report_broken_file(self):
        payload = self.payload("code_diagnostics")
        problems = {p["file"]: p["error"] for p in payload["problems"]}
        self.assertIn("broken.py", problems)
        self.assertIn("syntax error", problems["broken.py"])
        # everything else still parsed
        self.assertNotIn("utils.py", problems)

    def test_scan_stats(self):
        payload = self.payload("code_diagnostics")
        self.assertGreaterEqual(payload["scan"]["indexed"], 5)
        self.assertEqual(payload["scan"]["parse_errors"], 1)

    def test_freshness_after_edit(self):
        before = self.payload("code_symbols", query="brand_new", exact=True)
        self.assertEqual(before["count"], 0)
        time.sleep(0.01)  # mtime resolution
        _write(self.tmp / "utils.py", UTILS + "\ndef brand_new():\n    pass\n")
        after = self.payload("code_symbols", query="brand_new", exact=True)
        self.assertEqual(after["count"], 1)

    def test_git_dir_excluded_and_binary_skipped(self):
        payload = self.payload("code_symbols", query="hidden", exact=True)
        self.assertEqual(payload["count"], 0)
        # binary blob never entered the index (no crash, no symbols)
        diag = self.payload("code_diagnostics")
        self.assertNotIn("blob.bin", json.dumps(diag))


class TestJsAndFallback(CodeIntelBase):
    def test_js_heuristic_extraction(self):
        payload = self.payload("code_symbols", query="Server", exact=True)
        self.assertEqual(payload["symbols"][0]["language"], "javascript")
        self.assertEqual(payload["symbols"][0]["kind"], "class")

        imports = self.payload("code_imports", path="app.js")
        modules = {i["module"] for i in imports["imports"]}
        self.assertIn("./helpers.js", modules)
        self.assertIn("http", modules)

    def test_js_references_labeled_imprecise(self):
        payload = self.payload("code_references", name="start")
        refs = [r for r in payload["references"] if r["file"] == "app.js"]
        self.assertTrue(refs)
        self.assertFalse(all(r["precise"] for r in refs))

    def test_go_fallback_labeled(self):
        payload = self.payload("code_symbols", query="main", language="text-fallback")
        symbols = [s for s in payload["symbols"] if s["file"] == "main.go"]
        self.assertTrue(symbols)
        self.assertEqual(symbols[0]["language"], "text-fallback")


class TestRegistration(CodeIntelBase):
    def test_five_tools_read_only(self):
        described = {d["name"]: d for d in self.reg.describe()}
        self.assertEqual(
            set(described),
            {"code_symbols", "code_references", "code_imports",
             "code_importers", "code_diagnostics"},
        )
        self.assertTrue(all(d["side_effect_level"] == "READ_ONLY"
                            for d in described.values()))
        self.assertTrue(all(d["category"] == "code"
                            for d in described.values()))

    def test_agent_registry_includes_code_tools(self):
        reg = agent_registry(self.ws)
        self.assertEqual(len(reg.names()), 46)
        self.assertIn("code_symbols", reg.names())


if __name__ == "__main__":
    unittest.main()
