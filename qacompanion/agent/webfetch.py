"""S43 URL context & retrieval: search results become readable knowledge.

Three EXTERNAL-side-effect tools — open_url, extract_page,
download_artifact — behind a URL safety policy that is the sprint's core:
scheme/port allowlists and resolution of EVERY host IP against loopback,
RFC1918, link-local, and unspecified ranges (SSRF hardening: localhost,
LAN, and cloud-metadata endpoints are unreachable from the agent).

Pins (fixtures-first discipline):
- no test touches the network — urllib is always mocked;
- every failure is a structured WebFetchError (ToolOperationError);
- page text is capped (20k chars) and downloads are capped (10 MB),
  written atomically into the workspace through PathPolicy;
- documented residual risk: DNS rebinding between the IP check and the
  fetch (full mitigation out of scope, recorded in the spec).
"""

import hashlib
import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

from .registry import EXTERNAL, RegisteredTool, ToolDefinition, ToolOperationError, ToolRegistry
from .workspace import PathError, Workspace

FETCH_TIMEOUT = 15.0
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 20_000
MAX_LINKS = 50
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_SCHEMES = ("http", "https")
PAGE_CONTENT_PREFIXES = ("text/", "application/json", "application/xml",
                         "+xml")
USER_AGENT = "Baby-Agent/0.1 (local research agent)"


class WebFetchError(ToolOperationError):
    """Structured fetch failure (policy rejection, HTTP error, cap)."""


def _utc_stamp() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def _check_url_policy(url: str) -> urllib.parse.ParseResult:
    """Validate scheme, port, and every resolved IP. Raises WebFetchError."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise WebFetchError(
            f"scheme not allowed: {parsed.scheme!r} "
            f"(allowed: {', '.join(ALLOWED_SCHEMES)})"
        )
    if not parsed.hostname:
        raise WebFetchError("URL has no hostname")
    if parsed.port is not None and parsed.port not in (80, 443):
        raise WebFetchError(f"port not allowed: {parsed.port}")
    import ipaddress
    try:
        addrinfos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise WebFetchError(f"cannot resolve host: {parsed.hostname}") from exc
    for info in addrinfos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_loopback or ip.is_private or ip.is_link_local
                or ip.is_unspecified or ip.is_reserved or ip.is_multicast):
            raise WebFetchError(
                f"host resolves to a non-public address "
                f"({ip}) — blocked by URL policy"
            )
    return parsed


class _TextExtractor(HTMLParser):
    """Collect visible text + title + links from an HTML document."""

    SKIP = {"script", "style", "noscript", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title: Optional[str] = None
        self._in_title = False
        self._skip_depth = 0
        self._chunks: List[str] = []
        self.links: List[Tuple[str, str]] = []
        self._base: Optional[str] = None

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag == "base" and self._base is None:
            for key, value in attrs:
                if key == "href":
                    self._base = value
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append((href, ""))

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title or "") + data.strip()
            return
        if self._skip_depth or not data.strip():
            return
        self._chunks.append(data.strip())
        if self.links and self.links[-1][1] == "":
            href, text = self.links[-1]
            self.links[-1] = (href, text + data.strip())

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._chunks)).strip()


def _absolute(url: str, base_url: str) -> str:
    return urllib.parse.urljoin(base_url, url)


def _fetch(url: str, max_bytes: int, strict_size: bool = False
           ) -> Tuple[bytes, str, str, str]:
    """Fetch bytes + (final_url, content_type, status). Raises WebFetchError.
    strict_size: reject (not truncate) when the payload exceeds max_bytes."""
    _check_url_policy(url)
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as resp:
            final_url = resp.geturl()
            status = resp.status
            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            data = resp.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise WebFetchError(f"HTTP {exc.code} fetching {url}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise WebFetchError(f"fetch failed for {url}: {exc}") from exc
    if strict_size and len(data) > max_bytes:
        raise WebFetchError(
            f"download exceeds {max_bytes} byte cap for {url}")
    truncated = len(data) > max_bytes
    return data[:max_bytes], final_url, content_type, str(status) + (
        " (truncated)" if truncated else "")


def _is_page_content(content_type: str) -> bool:
    return (content_type.startswith("text/")
            or any(marker in content_type for marker in
                   ("json", "xml", "+html")))


def fetch_page(url: str) -> Dict[str, Any]:
    """Fetch a page and return structured, extractable knowledge."""
    raw, final_url, content_type, status = _fetch(url, MAX_PAGE_BYTES)
    if not _is_page_content(content_type):
        raise WebFetchError(
            f"content-type {content_type!r} is not a page — "
            f"use download_artifact for binary content"
        )
    text = raw.decode("utf-8", errors="replace")
    extractor = _TextExtractor()
    try:
        extractor.feed(text)
    except Exception:
        pass  # malformed HTML: keep whatever was collected
    links = [
        {"url": _absolute(href, final_url), "text": label[:120]}
        for href, label in extractor.links[:MAX_LINKS]
    ]
    body = extractor.text()
    return {
        "url": url,
        "final_url": final_url,
        "status": status,
        "content_type": content_type,
        "title": extractor.title,
        "text": body[:MAX_TEXT_CHARS],
        "truncated": len(body) > MAX_TEXT_CHARS or status.endswith("(truncated)"),
        "links": links,
    }


def extract_relevant(page_text: str, query: str,
                     max_excerpts: int = 10) -> List[str]:
    """Return sentence-ish chunks of the page matching the query terms."""
    terms = [term.lower() for term in re.split(r"\W+", query) if term]
    if not terms:
        return []
    chunks = re.split(r"(?<=[.!?])\s+|\n+", page_text)
    matched = []
    for chunk in chunks:
        lowered = chunk.lower()
        if any(term in lowered for term in terms):
            matched.append(chunk.strip()[:400])
            if len(matched) >= max_excerpts:
                break
    return matched


def download_artifact(workspace: Workspace, url: str, path: str) -> Dict[str, Any]:
    """Fetch binary content (≤10 MB) into the workspace atomically."""
    raw, final_url, content_type, status = _fetch(
        url, MAX_DOWNLOAD_BYTES, strict_size=True)
    try:
        target = workspace.resolve(path)
    except PathError as exc:
        raise WebFetchError(str(exc)) from exc
    sha256 = hashlib.sha256(raw).hexdigest()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp-download")
        tmp.write_bytes(raw)
        os.replace(tmp, target)
    except OSError as exc:
        raise WebFetchError(f"download write failed: {exc}") from exc
    return {
        "path": workspace.relative(target),
        "bytes": len(raw),
        "sha256": sha256,
        "content_type": content_type,
        "final_url": final_url,
    }


class WebFetchToolkit:
    """Binds the three URL tools (no workspace needed except downloads)."""

    def __init__(self, workspace: Optional[Workspace] = None):
        self.workspace = workspace

    def open_url(self, url: str) -> str:
        return json.dumps(fetch_page(url), ensure_ascii=False)

    def extract_page(self, url: str, query: str) -> str:
        page = fetch_page(url)
        excerpts = extract_relevant(page["text"], query)
        return json.dumps({
            "url": url,
            "final_url": page["final_url"],
            "title": page["title"],
            "query": query,
            "excerpts": excerpts,
        }, ensure_ascii=False)

    def download_artifact(self, url: str, path: str) -> str:
        if self.workspace is None:
            raise WebFetchError("download_artifact requires a workspace")
        return json.dumps(download_artifact(self.workspace, url, path),
                          ensure_ascii=False)

    def tools(self) -> List[RegisteredTool]:
        def _tool(name, description, schema, handler, needs_workspace=False):
            return RegisteredTool(
                definition=ToolDefinition(
                    name=name, description=description,
                    parameters_schema=schema),
                handler=handler,
                category="research",
                side_effect_level=EXTERNAL,
                requires_workspace=needs_workspace,
            )

        return [
            _tool("open_url", "Fetch a web page and return its title, "
                  "text, and links.",
                  {"type": "object",
                   "properties": {"url": {"type": "string"}},
                   "required": ["url"]},
                  self.open_url),
            _tool("extract_page", "Fetch a page and return only the "
                  "passages relevant to a query.",
                  {"type": "object",
                   "properties": {
                       "url": {"type": "string"},
                       "query": {"type": "string"}},
                   "required": ["url", "query"]},
                  self.extract_page),
            _tool("download_artifact", "Download a file into the workspace "
                  "(≤10 MB, atomic).",
                  {"type": "object",
                   "properties": {
                       "url": {"type": "string"},
                       "path": {"type": "string"}},
                   "required": ["url", "path"]},
                  self.download_artifact, needs_workspace=True),
        ]


def update_agent_registry(registry: ToolRegistry, workspace: Workspace) -> None:
    """Register the URL tools into an existing registry."""
    for tool in WebFetchToolkit(workspace).tools():
        registry.register(tool)
