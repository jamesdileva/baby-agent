"""S53 browser abstraction: a controlled browser interface for the
agent's web apps and documentation.

BrowserProvider is the abstraction; two adapters:
- FakeBrowserProvider: an in-memory page model (registered pages,
  selector-addressable elements, history) — fully hermetic; the test
  and demo path. Screenshots render REAL PNG bytes via the S44 codec
  (deterministic color per page, so compare_images can verify them).
- PlaywrightBrowserProvider: sync Playwright behind an import guard —
  activates with `pip install playwright && playwright install
  chromium`; before that it raises a structured error naming the fix.
  No browser binaries download as a side effect of this module.

All failures are structured BrowserError(ToolOperationError). All
browser tools are EXTERNAL (untrusted page content + possible network)
— the S38 engine gates them behind ASK by default; localhost dev
servers are whitelisted via policy like every other network tool.

`browser_download` from the roadmap is covered by
webfetch.download_artifact (S43) — documented deviation.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .registry import EXTERNAL, RegisteredTool, ToolDefinition, ToolOperationError, ToolRegistry
from .workspace import PathError, Workspace
from .vision import decode_png, encode_png


class BrowserError(ToolOperationError):
    """Structured browser failure (provider missing, page missing,
    selector not found)."""


class BrowserProvider(ABC):
    """One controlled browser session behind a stable surface."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def open(self, url: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    def back(self) -> Dict[str, Any]:
        ...

    @abstractmethod
    def click(self, selector: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    def type(self, selector: str, text: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    def scroll(self, amount: int) -> Dict[str, Any]:
        ...

    @abstractmethod
    def select(self, selector: str, value: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    def screenshot(self) -> Tuple[bytes, Dict[str, Any]]:
        """Return (png_bytes, metadata)."""

    @abstractmethod
    def extract(self) -> Dict[str, Any]:
        ...


@dataclass
class FakePage:
    """One registered page in the fake browser."""

    url: str
    title: str
    text: str
    color: Tuple[int, int, int] = (40, 44, 52)
    elements: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class FakeBrowserProvider(BrowserProvider):
    """In-memory page model — register pages, then browse them.

    Pages are looked up by exact URL. Elements are addressed by
    selector key; type/select mutate the element's value so extract()
    reflects form state. History supports back().
    """

    def __init__(self, start_color: Tuple[int, int, int] = (40, 44, 52)):
        self._pages: Dict[str, FakePage] = {}
        self._history: List[str] = []
        self._current: Optional[FakePage] = None
        self._scroll = 0
        self._color = start_color

    @property
    def name(self) -> str:
        return "fake"

    def add_page(self, url: str, title: str, text: str,
                 elements: Optional[Dict[str, Dict[str, Any]]] = None,
                 color: Optional[Tuple[int, int, int]] = None) -> None:
        page = FakePage(url=url, title=title, text=text,
                        elements=elements or {},
                        color=color or self._color)
        self._pages[url] = page
        if self._current is None:
            self._current = page

    def _page(self) -> FakePage:
        if self._current is None:
            raise BrowserError(
                "no page open — call browser_open with a URL first")
        return self._current

    def open(self, url: str) -> Dict[str, Any]:
        page = self._pages.get(url)
        if page is None:
            raise BrowserError(
                f"unregistered URL {url!r} — register it on the fake "
                f"provider or use the Playwright adapter for real pages")
        if self._current is not None:
            self._history.append(self._current.url)
        self._current = page
        self._scroll = 0
        return {"url": page.url, "title": page.title,
                "text_len": len(page.text)}

    def back(self) -> Dict[str, Any]:
        if not self._history:
            raise BrowserError("no history to go back to")
        url = self._history.pop()
        self._current = self._pages[url]
        return {"url": self._current.url}

    def _element(self, selector: str) -> Dict[str, Any]:
        page = self._page()
        element = page.elements.get(selector)
        if element is None:
            raise BrowserError(
                f"selector {selector!r} not found on {page.url}")
        return element

    def click(self, selector: str) -> Dict[str, Any]:
        element = self._element(selector)
        element["clicked"] = element.get("clicked", 0) + 1
        return {"clicked": True, "selector": selector}

    def type(self, selector: str, text: str) -> Dict[str, Any]:
        element = self._element(selector)
        element["value"] = text
        return {"typed": True, "selector": selector, "value": text}

    def scroll(self, amount: int) -> Dict[str, Any]:
        self._scroll += amount
        return {"scrolled": self._scroll}

    def select(self, selector: str, value: str) -> Dict[str, Any]:
        element = self._element(selector)
        allowed = element.get("options")
        if allowed is not None and value not in allowed:
            raise BrowserError(
                f"value {value!r} not in options for {selector!r}")
        element["value"] = value
        return {"selected": value, "selector": selector}

    def screenshot(self) -> Tuple[bytes, Dict[str, Any]]:
        page = self._page()
        width, height = 640, 400
        row = bytes(page.color) * width
        rows = [row for _ in range(height)]
        png = encode_png(width, height, rows)
        return png, {"url": page.url, "title": page.title,
                     "width": width, "height": height,
                     "color": list(page.color)}

    def extract(self) -> Dict[str, Any]:
        page = self._page()
        return {"url": page.url, "title": page.title, "text": page.text,
                "scroll": self._scroll}


class PlaywrightBrowserProvider(BrowserProvider):
    """Sync Playwright behind an import guard. Activates with:
    pip install playwright && playwright install chromium"""

    def __init__(self):
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as exc:
            raise BrowserError(
                "playwright is not installed — run: "
                "pip install playwright && playwright install chromium"
            ) from exc
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch()
        self._context = self._browser.new_context()
        self._page = self._context.new_page()

    @property
    def name(self) -> str:
        return "playwright"

    def open(self, url: str) -> Dict[str, Any]:
        self._page.goto(url)
        return {"url": self._page.url, "title": self._page.title(),
                "text_len": len(self._extract_text())}

    def back(self) -> Dict[str, Any]:
        self._page.go_back()
        return {"url": self._page.url}

    def click(self, selector: str) -> Dict[str, Any]:
        self._page.click(selector)
        return {"clicked": True, "selector": selector}

    def type(self, selector: str, text: str) -> Dict[str, Any]:
        self._page.fill(selector, text)
        return {"typed": True, "selector": selector, "value": text}

    def scroll(self, amount: int) -> Dict[str, Any]:
        self._page.mouse.wheel(0, amount)
        return {"scrolled": amount}

    def select(self, selector: str, value: str) -> Dict[str, Any]:
        self._page.select_option(selector, value)
        return {"selected": value, "selector": selector}

    def screenshot(self) -> Tuple[bytes, Dict[str, Any]]:
        png = self._page.screenshot(type="png")
        return png, {"url": self._page.url, "title": self._page.title()}

    def _extract_text(self) -> str:
        from .webfetch import _TextExtractor

        extractor = _TextExtractor()
        try:
            extractor.feed(self._page.content())
        except Exception:
            pass
        return extractor.text()

    def extract(self) -> Dict[str, Any]:
        return {"url": self._page.url, "title": self._page.title(),
                "text": self._extract_text()[:20_000]}


def resolve_browser_provider(
        provider: Optional[BrowserProvider] = None,
        prefer_playwright: bool = False) -> Optional[BrowserProvider]:
    """Explicit injection wins; else Playwright when preferred (and
    installed); else the hermetic fake."""
    if provider is not None:
        return provider
    if prefer_playwright:
        try:
            return PlaywrightBrowserProvider()
        except BrowserError:
            return None
    return FakeBrowserProvider()


class BrowserToolkit:
    """Binds the eight browser tools to one provider (+ workspace for
    the screenshot file output)."""

    def __init__(self, workspace: Workspace,
                 provider: Optional[BrowserProvider] = None):
        self.workspace = workspace
        self.provider = resolve_browser_provider(provider)

    def browser_open(self, url: str) -> str:
        if self.provider is None:
            raise BrowserError("no browser provider configured")
        return json.dumps(self.provider.open(url), ensure_ascii=False)

    def browser_back(self) -> str:
        if self.provider is None:
            raise BrowserError("no browser provider configured")
        return json.dumps(self.provider.back(), ensure_ascii=False)

    def browser_click(self, selector: str) -> str:
        if self.provider is None:
            raise BrowserError("no browser provider configured")
        return json.dumps(self.provider.click(selector), ensure_ascii=False)

    def browser_type(self, selector: str, text: str) -> str:
        if self.provider is None:
            raise BrowserError("no browser provider configured")
        return json.dumps(self.provider.type(selector, text),
                          ensure_ascii=False)

    def browser_scroll(self, amount: int) -> str:
        if self.provider is None:
            raise BrowserError("no browser provider configured")
        return json.dumps(self.provider.scroll(int(amount)),
                          ensure_ascii=False)

    def browser_select(self, selector: str, value: str) -> str:
        if self.provider is None:
            raise BrowserError("no browser provider configured")
        return json.dumps(self.provider.select(selector, value),
                          ensure_ascii=False)

    def browser_screenshot(self, path: str) -> str:
        if self.provider is None:
            raise BrowserError("no browser provider configured")
        try:
            target = self.workspace.resolve(path)
        except PathError as exc:
            raise BrowserError(str(exc)) from exc
        png, meta = self.provider.screenshot()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(png)
        except OSError as exc:
            raise BrowserError(f"screenshot write failed: {exc}") from exc
        meta["path"] = self.workspace.relative(target)
        meta["bytes"] = len(png)
        meta["sha256"] = __import__("hashlib").sha256(png).hexdigest()
        return json.dumps(meta, ensure_ascii=False)

    def browser_extract(self) -> str:
        if self.provider is None:
            raise BrowserError("no browser provider configured")
        return json.dumps(self.provider.extract(), ensure_ascii=False)

    def tools(self) -> List[RegisteredTool]:
        def _tool(name, description, schema, handler,
                  needs_workspace=False):
            return RegisteredTool(
                definition=ToolDefinition(
                    name=name, description=description,
                    parameters_schema=schema),
                handler=handler,
                category="browser",
                side_effect_level=EXTERNAL,
                requires_workspace=needs_workspace,
            )

        return [
            _tool("browser_open", "Open a URL in the controlled browser "
                  "and return title + summary.",
                  {"type": "object",
                   "properties": {"url": {"type": "string"}},
                   "required": ["url"]},
                  self.browser_open),
            _tool("browser_back", "Go back in browser history.",
                  {"type": "object", "properties": {}, "required": []},
                  self.browser_back),
            _tool("browser_click", "Click an element by CSS selector.",
                  {"type": "object",
                   "properties": {"selector": {"type": "string"}},
                   "required": ["selector"]},
                  self.browser_click),
            _tool("browser_type", "Type text into an element (fills the "
                  "field).",
                  {"type": "object",
                   "properties": {"selector": {"type": "string"},
                                  "text": {"type": "string"}},
                   "required": ["selector", "text"]},
                  self.browser_type),
            _tool("browser_scroll", "Scroll the page (positive = down).",
                  {"type": "object",
                   "properties": {"amount": {"type": "integer"}},
                   "required": ["amount"]},
                  self.browser_scroll),
            _tool("browser_select", "Select a dropdown option by value.",
                  {"type": "object",
                   "properties": {"selector": {"type": "string"},
                                  "value": {"type": "string"}},
                   "required": ["selector", "value"]},
                  self.browser_select),
            _tool("browser_screenshot", "Screenshot the page into a "
                  "workspace PNG.",
                  {"type": "object",
                   "properties": {"path": {"type": "string"}},
                   "required": ["path"]},
                  self.browser_screenshot, needs_workspace=True),
            _tool("browser_extract", "Extract the current page title and "
                  "visible text.",
                  {"type": "object", "properties": {}, "required": []},
                  self.browser_extract),
        ]


def update_agent_registry(registry: ToolRegistry, workspace: Workspace,
                          provider: Optional[BrowserProvider] = None
                          ) -> None:
    """Register the browser tools into an existing registry."""
    for tool in BrowserToolkit(workspace, provider).tools():
        registry.register(tool)
