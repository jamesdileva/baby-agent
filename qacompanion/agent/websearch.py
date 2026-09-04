"""S42 web research: search as a tool capability, results as evidence.

WebSearchProvider abstraction with two implementations:
- FakeWebSearchProvider: scripted, deterministic — the test backbone;
  nothing here touches the network.
- GeminiSearchProvider: Google AI Studio generateContent with the
  google_search grounding tool — the human-directed provider ("Google
  Search with AI mode"). Activates only when GEMINI_API_KEY is present;
  the key never appears in logs or error strings.

The web_search registry tool is the first EXTERNAL-side-effect tool: the
S38 engine's default posture (EXTERNAL -> ASK) makes the constraints
amendment real — no network without permission.

Pins (fixtures-first discipline):
- every failure is a structured WebSearchError (ToolOperationError);
- sources stay attached to answers: url, title, snippet, provider,
  timestamp — provenance survives into session records;
- defensive parsing: Gemini response shape drift becomes a structured
  error, never a crash.
"""

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .registry import EXTERNAL, RegisteredTool, ToolDefinition, ToolOperationError, ToolRegistry

GEMINI_ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
                   "{model}:generateContent")
# gemini-2.0-flash was retired (live smoke 2026-09-04: 404); the
# flash-latest alias tracks the current flash generation
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"
GEMINI_TIMEOUT = 30.0
MAX_SOURCES_DEFAULT = 5


class WebSearchError(ToolOperationError):
    """Structured search failure (no provider, HTTP error, shape drift)."""


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


@dataclass
class SearchResult:
    """Search evidence: the query, its sources, and provenance."""

    query: str
    provider: str
    sources: List[Dict[str, str]] = field(default_factory=list)
    answered: Optional[str] = None
    timestamp: str = field(default_factory=_utc_stamp)

    def to_dict(self):
        return {
            "query": self.query,
            "provider": self.provider,
            "sources": [dict(source) for source in self.sources],
            "answered": self.answered,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            query=data.get("query", ""),
            provider=data.get("provider", ""),
            sources=[dict(s) for s in data.get("sources", [])],
            answered=data.get("answered"),
            timestamp=data.get("timestamp", ""),
        )


class WebSearchProvider(ABC):
    """One stable interface for web research."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def search(self, query: str, max_sources: int = MAX_SOURCES_DEFAULT
               ) -> SearchResult:
        ...


class FakeWebSearchProvider(WebSearchProvider):
    """Scripted deterministic provider for tests (never touches network)."""

    def __init__(self, results: Optional[Dict[str, SearchResult]] = None,
                 default_sources: Optional[List[Dict[str, str]]] = None,
                 answered: Optional[str] = None):
        self._results = results or {}
        self._default_sources = default_sources or [
            {"title": "Official docs", "url": "https://example.com/docs",
             "snippet": "The documented behavior."},
        ]
        self._answered = answered
        self.queries: List[str] = []

    @property
    def name(self) -> str:
        return "fake"

    def search(self, query: str, max_sources: int = MAX_SOURCES_DEFAULT
               ) -> SearchResult:
        self.queries.append(query)
        if query in self._results:
            return self._results[query]
        return SearchResult(
            query=query, provider=self.name,
            sources=self._default_sources[:max_sources],
            answered=self._answered,
        )


def _extract_grounding(data: Dict[str, Any]) -> tuple:
    """Defensively parse a grounded Gemini response into (answer, sources)."""
    answer = None
    try:
        parts = data["candidates"][0]["content"]["parts"]
        answer = "".join(str(part.get("text", "")) for part in parts).strip()
    except (KeyError, IndexError, TypeError):
        pass

    sources: List[Dict[str, str]] = []
    seen = set()
    try:
        for chunk in data["groundingMetadata"][0].get("groundingChunks", []):
            web = chunk.get("web", {})
            uri, title = web.get("uri"), web.get("title")
            if not uri or uri in seen:
                continue
            seen.add(uri)
            sources.append({"title": title or uri, "url": uri, "snippet": ""})
    except (KeyError, IndexError, TypeError):
        pass
    return answer, sources


class GeminiSearchProvider(WebSearchProvider):
    """Google AI Studio generateContent grounded with Google Search."""

    def __init__(self, api_key: Optional[str] = None,
                 model: Optional[str] = None):
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model or os.environ.get("GEMINI_MODEL") \
            or DEFAULT_GEMINI_MODEL

    @property
    def name(self) -> str:
        return "gemini-google-search"

    def search(self, query: str, max_sources: int = MAX_SOURCES_DEFAULT
               ) -> SearchResult:
        if not self._api_key:
            raise WebSearchError(
                "no search provider configured: set GEMINI_API_KEY "
                "(free key at aistudio.google.com)"
            )
        url = GEMINI_ENDPOINT.format(model=self.model)
        body = {
            "contents": [{"parts": [{"text": query}]}],
            "tools": [{"google_search": {}}],
        }
        request = urllib.request.Request(
            f"{url}?key={self._api_key}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise WebSearchError(
                f"gemini request failed: HTTP {exc.code}"
            ) from exc
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
            raise WebSearchError(f"gemini request failed: {exc}") from exc

        answer, sources = _extract_grounding(data)
        if answer is None and not sources:
            raise WebSearchError("gemini response missing usable content")
        return SearchResult(
            query=query, provider=self.name,
            sources=sources[:max_sources], answered=answer,
        )


def resolve_provider(provider: Optional[WebSearchProvider] = None
                     ) -> Optional[WebSearchProvider]:
    """Explicit injection wins; else GEMINI_API_KEY; else None."""
    if provider is not None:
        return provider
    if os.environ.get("GEMINI_API_KEY"):
        return GeminiSearchProvider()
    return None


class WebResearchToolkit:
    """Binds web_search to a provider (explicit, env-based, or absent)."""

    def __init__(self, search_provider: Optional[WebSearchProvider] = None):
        self.provider = resolve_provider(search_provider)

    def web_search(self, query: str, max_sources: int = MAX_SOURCES_DEFAULT
                   ) -> str:
        if self.provider is None:
            raise WebSearchError(
                "no search provider configured: set GEMINI_API_KEY "
                "(free key at aistudio.google.com) or inject a provider"
            )
        if not isinstance(query, str) or not query.strip():
            raise WebSearchError("query must be a non-empty string")
        result = self.provider.search(query.strip(), max_sources=max_sources)
        return json.dumps(result.to_dict(), ensure_ascii=False)

    def tools(self) -> List[RegisteredTool]:
        return [RegisteredTool(
            definition=ToolDefinition(
                name="web_search",
                description="Search the web for current information; "
                            "returns an answer (when the provider grounds "
                            "one) plus source citations. Evidence, not "
                            "truth.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_sources": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            ),
            handler=self.web_search,
            category="research",
            side_effect_level=EXTERNAL,
        )]


def update_agent_registry(registry: ToolRegistry, workspace: Workspace,
                          search_provider: Optional[WebSearchProvider] = None
                          ) -> None:
    """Register the web research tools into an existing registry."""
    for tool in WebResearchToolkit(search_provider).tools():
        registry.register(tool)
