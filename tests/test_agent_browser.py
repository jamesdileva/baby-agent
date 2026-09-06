"""S53 browser abstraction tests: fake provider page model, tools,
Playwright import-guard (both ways). All hermetic."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qacompanion.agent import ToolCall, ToolRegistry, Workspace
from qacompanion.agent.browser import (
    BrowserError,
    BrowserToolkit,
    FakeBrowserProvider,
    PlaywrightBrowserProvider,
    resolve_browser_provider,
)
from qacompanion.agent.fs_tools import agent_registry
from qacompanion.agent.vision import decode_png

APP_URL = "http://127.0.0.1:8765/"
FORM_URL = "http://127.0.0.1:8765/form"

ELEMENTS = {
    "#title-input": {"tag": "input"},
    "#submit": {"tag": "button"},
    "#category": {"tag": "select", "options": ["work", "personal"]},
}


class FakeBrowserBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.provider = FakeBrowserProvider()
        self.provider.add_page(
            APP_URL, "Task Tracker",
            "Task tracker app. Create and list your tasks.",
            elements=dict(ELEMENTS), color=(30, 60, 90))
        self.provider.add_page(
            FORM_URL, "New Task", "Create a new task.",
            elements={"#task-name": {"tag": "input"}},
            color=(90, 30, 60))
        self.toolkit = BrowserToolkit(self.ws, self.provider)
        self.reg = ToolRegistry()
        for tool in self.toolkit.tools():
            self.reg.register(tool)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, name, confirmer=lambda call, d: True, **arguments):
        return self.reg.execute(ToolCall(name=name, arguments=arguments),
                                workspace=self.ws, confirmer=confirmer)

    def payload(self, name, **arguments):
        out = self.call(name, **arguments)
        self.assertTrue(out.ok, f"{name} failed: {out.error}")
        return json.loads(out.output)


class TestFakeProvider(FakeBrowserBase):
    def test_open_registered_page(self):
        summary = self.provider.open(APP_URL)
        self.assertEqual(summary["title"], "Task Tracker")
        self.assertEqual(summary["url"], APP_URL)

    def test_unregistered_url_structured_error(self):
        with self.assertRaises(BrowserError) as ctx:
            self.provider.open("https://example.com/")
        self.assertIn("unregistered URL", str(ctx.exception))

    def test_history_back(self):
        self.provider.open(FORM_URL)
        result = self.provider.back()
        self.assertEqual(result["url"], APP_URL)

    def test_back_without_history_structured_error(self):
        with self.assertRaises(BrowserError):
            self.provider.back()

    def test_click_and_type_mutate_elements(self):
        self.provider.open(FORM_URL)
        self.provider.type("#task-name", "write the spec")
        clicked = self.provider.click("#task-name")
        self.assertTrue(clicked["clicked"])
        page = self.provider.extract()
        self.assertEqual(page["title"], "New Task")

    def test_select_validates_options(self):
        self.provider.open(APP_URL)
        result = self.provider.select("#category", "work")
        self.assertEqual(result["selected"], "work")
        with self.assertRaises(BrowserError):
            self.provider.select("#category", "vacation")

    def test_selector_not_found_structured_error(self):
        self.provider.open(APP_URL)
        with self.assertRaises(BrowserError) as ctx:
            self.provider.click("#missing")
        self.assertIn("not found", str(ctx.exception))

    def test_screenshot_is_real_png(self):
        png, meta = self.provider.screenshot()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        width, height, rows = decode_png(png)
        self.assertEqual((width, height), (640, 400))
        self.assertEqual(meta["color"], [30, 60, 90])

    def test_screenshot_colors_differ_per_page(self):
        self.provider.open(APP_URL)
        png_a, _ = self.provider.screenshot()
        self.provider.open(FORM_URL)
        png_b, _ = self.provider.screenshot()
        self.assertNotEqual(png_a, png_b)

    def test_no_page_open_structured_error(self):
        bare = FakeBrowserProvider()
        with self.assertRaises(BrowserError):
            bare.extract()


class TestPlaywrightImportGuard(unittest.TestCase):
    def test_missing_playwright_names_the_fix(self):
        with patch.dict(sys.modules, {"playwright": None,
                                      "playwright.sync_api": None}):
            with self.assertRaises(BrowserError) as ctx:
                PlaywrightBrowserProvider()
        self.assertIn("pip install playwright", str(ctx.exception))
        self.assertIn("playwright install chromium", str(ctx.exception))

    def test_present_playwright_maps_methods(self):
        playwright_stub = __import__("types").ModuleType("playwright")
        sync_api = __import__("types").ModuleType("playwright.sync_api")

        class FakePage:
            def __init__(self):
                self.url = "http://127.0.0.1:9999/"
                self._title = "Fake App"

            def title(self):
                return self._title

            def goto(self, url):
                self.url = url
                self._title = "Fake App"

            def click(self, selector):
                return None

            def fill(self, selector, text):
                return None

            def go_back(self):
                return None

            def select_option(self, selector, value):
                return None

            def mouse(self):
                return None

            def content(self):
                return "<html><body><p>hello page</p></body></html>"

            def screenshot(self, type="png"):
                from qacompanion.agent.vision import encode_png
                return encode_png(2, 2, [b"\x00\x00\x00" * 2,
                                         b"\x00\x00\x00" * 2])

        fake_page = FakePage()
        fake_page.mouse = __import__(
            "types").SimpleNamespace(wheel=lambda dx, dy: None)

        class FakeBrowserHandle:
            def new_context(self):
                return __import__("types").SimpleNamespace(
                    new_page=lambda: fake_page)

        class FakePlaywright:
            def __init__(self):
                self.chromium = __import__("types").SimpleNamespace(
                    launch=lambda: FakeBrowserHandle())

            def start(self):
                return self

        sync_api.sync_playwright = lambda: FakePlaywright()
        playwright_stub.sync_api = sync_api
        sys.modules["playwright"] = playwright_stub
        sys.modules["playwright.sync_api"] = sync_api
        try:
            provider = PlaywrightBrowserProvider()
            self.assertEqual(provider.name, "playwright")
            summary = provider.open("http://127.0.0.1:9999/")
            self.assertEqual(summary["title"], "Fake App")
            extracted = provider.extract()
            self.assertIn("hello page", extracted["text"])
            png, meta = provider.screenshot()
            self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        finally:
            sys.modules.pop("playwright", None)
            sys.modules.pop("playwright.sync_api", None)

    def test_resolve_defaults_to_fake(self):
        provider = resolve_browser_provider(None, prefer_playwright=False)
        self.assertIsInstance(provider, FakeBrowserProvider)


class TestBrowserTools(FakeBrowserBase):
    def test_side_effect_matrix(self):
        described = {d["name"]: d for d in self.reg.describe()}
        self.assertEqual(
            set(described),
            {"browser_open", "browser_back", "browser_click",
             "browser_type", "browser_scroll", "browser_select",
             "browser_screenshot", "browser_extract"},
        )
        self.assertTrue(all(d["side_effect_level"] == "EXTERNAL"
                            for d in described.values()))
        self.assertTrue(described["browser_screenshot"]["requires_workspace"])
        self.assertFalse(described["browser_open"]["requires_workspace"])

    def test_default_posture_asks(self):
        out = self.call("browser_open", url=APP_URL, confirmer=None)
        self.assertFalse(out.ok)
        self.assertIn("no confirmer", out.error)

    def test_navigate_and_extract_through_registry(self):
        summary = self.payload("browser_open", url=APP_URL)
        self.assertEqual(summary["title"], "Task Tracker")
        extracted = self.payload("browser_extract")
        self.assertIn("Task tracker app", extracted["text"])

    def test_form_fill_flow(self):
        self.payload("browser_open", url=FORM_URL)
        self.payload("browser_type", selector="#task-name",
                     text="write the spec")
        self.payload("browser_click", selector="#task-name")
        extracted = self.payload("browser_extract")
        self.assertEqual(extracted["title"], "New Task")

    def test_screenshot_writes_workspace_png(self):
        payload = self.payload("browser_open", url=APP_URL)
        shot = self.payload("browser_screenshot", path="shots/app.png")
        self.assertEqual(shot["path"], "shots/app.png")
        saved = (self.tmp / "shots" / "app.png").read_bytes()
        self.assertEqual(saved[:8], b"\x89PNG\r\n\x1a\n")

    def test_screenshot_escape_rejected(self):
        self.payload("browser_open", url=APP_URL)
        out = self.call("browser_screenshot", path="../evil.png",
                        confirmer=lambda c, d: True)
        self.assertFalse(out.ok)

    def test_selector_not_found_through_registry(self):
        self.payload("browser_open", url=APP_URL)
        out = self.call("browser_click", selector="#missing")
        self.assertFalse(out.ok)
        self.assertIn("not found", out.error)


class TestAgentRegistryIncludesBrowser(unittest.TestCase):
    def test_membership(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            reg = agent_registry(Workspace(tmp),
                                 browser_provider=FakeBrowserProvider())
            for name in ("browser_open", "browser_back", "browser_click",
                         "browser_type", "browser_scroll", "browser_select",
                         "browser_screenshot", "browser_extract"):
                self.assertIn(name, reg.names())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
