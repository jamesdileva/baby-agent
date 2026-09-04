"""S42 web research tests: provider abstraction, fake + Gemini (mocked).

Hermetic: NO test touches the network — urllib is always mocked for the
Gemini provider; the fake provider never sends anything.
"""

import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from qacompanion.agent import ToolCall, ToolRegistry, Workspace
from qacompanion.agent.fs_tools import agent_registry
from qacompanion.agent.websearch import (
    FakeWebSearchProvider,
    GeminiSearchProvider,
    SearchResult,
    WebResearchToolkit,
    WebSearchError,
    WebSearchProvider,
    _extract_grounding,
    resolve_provider,
)

GROUNDED_RESPONSE = {
    "candidates": [{
        "content": {"parts": [
            {"text": "The current stable version is 5.1, released this week."}
        ]},
    }],
    "groundingMetadata": [{
        "groundingChunks": [
            {"web": {"uri": "https://example.org/release",
                     "title": "Release notes"}},
            {"web": {"uri": "https://example.org/release",
                     "title": "Duplicate should be dropped"}},
            {"web": {"uri": "https://blog.example.com/launch",
                     "title": None}},
        ],
    }],
}


class TestSearchResult(unittest.TestCase):
    def test_round_trip(self):
        r = SearchResult(query="q", provider="fake",
                         sources=[{"title": "t", "url": "u", "snippet": "s"}],
                         answered="answer")
        restored = SearchResult.from_dict(json.loads(json.dumps(r.to_dict())))
        self.assertEqual(restored, r)
        self.assertTrue(r.timestamp.endswith("Z"))


class TestProviderAbstraction(unittest.TestCase):
    def test_fake_implements_interface(self):
        self.assertIsInstance(FakeWebSearchProvider(), WebSearchProvider)
        self.assertIsInstance(GeminiSearchProvider(api_key="k"),
                              WebSearchProvider)

    def test_fake_scripted_results_and_cap(self):
        custom = SearchResult(query="special", provider="fake",
                              sources=[{"title": "s", "url": "u",
                                        "snippet": ""}] * 4)
        provider = FakeWebSearchProvider(results={"special": custom},
                                         answered="grounded answer")
        result = provider.search("special")
        self.assertEqual(len(result.sources), 4)
        plain = provider.search("anything", max_sources=1)
        self.assertEqual(len(plain.sources), 1)
        self.assertEqual(plain.answered, "grounded answer")
        self.assertEqual(provider.queries, ["special", "anything"])

    def test_gemini_parsing_unit(self):
        answer, sources = _extract_grounding(GROUNDED_RESPONSE)
        self.assertIn("5.1", answer)
        self.assertEqual([s["url"] for s in sources],
                         ["https://example.org/release",
                          "https://blog.example.com/launch"])
        self.assertEqual(sources[0]["title"], "Release notes")
        # missing title falls back to the url
        self.assertEqual(sources[1]["title"],
                         "https://blog.example.com/launch")

    def test_gemini_shape_drift_is_tolerated(self):
        answer, sources = _extract_grounding({"unexpected": True})
        self.assertIsNone(answer)
        self.assertEqual(sources, [])


class TestGeminiProvider(unittest.TestCase):
    def setUp(self):
        self.provider = GeminiSearchProvider(api_key="test-key-123")

    def _mock_urlopen(self, payload):
        class FakeResponse:
            def read(self):
                return json.dumps(payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        return FakeResponse()

    def test_grounded_search_parses_sources_and_answer(self):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return self._mock_urlopen(GROUNDED_RESPONSE)

        with patch("qacompanion.agent.websearch.urllib.request.urlopen",
                   side_effect=fake_urlopen):
            result = self.provider.search("latest version of x")

        self.assertIn("5.1", result.answered)
        self.assertEqual(len(result.sources), 2)
        self.assertEqual(result.provider, "gemini:grounded")
        self.assertTrue(result.grounded)
        self.assertEqual(captured["body"]["tools"], [{"google_search": {}}])
        self.assertIn("key=test-key-123", captured["url"])

    def test_grounding_refusal_falls_back_to_plain_marked_unverified(self):
        # human ruling 2026-09-04 (no billing): 429 on the grounding tool
        # -> plain-mode retry, result honestly marked grounded=False
        attempts = []

        def fake_urlopen(request, timeout=None):
            attempts.append(json.loads(request.data.decode("utf-8")))
            if len(attempts) == 1:
                raise urllib.error.HTTPError(request.full_url, 429,
                                             "Too Many Requests", {},
                                             io.BytesIO(b""))
            return self._mock_urlopen({
                "candidates": [{"content": {"parts": [
                    {"text": "From model knowledge: 3.14"}]}}],
            })

        with patch("qacompanion.agent.websearch.urllib.request.urlopen",
                   side_effect=fake_urlopen):
            result = self.provider.search("latest python")

        self.assertFalse(result.grounded)
        self.assertEqual(result.provider, "gemini:plain")
        self.assertEqual(result.sources, [])
        self.assertIn("3.14", result.answered)
        # first attempt carried the grounding tool, second did not
        self.assertIn("google_search", attempts[0].get("tools", [{}])[0])
        self.assertNotIn("tools", attempts[1])

    def test_http_error_is_structured_and_key_never_leaks(self):
        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 403,
                                         "Forbidden", {}, io.BytesIO(b""))

        with patch("qacompanion.agent.websearch.urllib.request.urlopen",
                   side_effect=fake_urlopen):
            with self.assertRaises(WebSearchError) as ctx:
                self.provider.search("q")
        self.assertIn("HTTP 403", str(ctx.exception))
        self.assertNotIn("test-key-123", str(ctx.exception))

    def test_empty_response_is_structured_error(self):
        with patch("qacompanion.agent.websearch.urllib.request.urlopen",
                   return_value=self._mock_urlopen({"candidates": []})):
            with self.assertRaises(WebSearchError):
                self.provider.search("q")

    def test_missing_key_fails_before_any_request(self):
        provider = GeminiSearchProvider(api_key=None)
        with patch("qacompanion.agent.websearch.urllib.request.urlopen",
                   side_effect=AssertionError("network touched")):
            with self.assertRaises(WebSearchError) as ctx:
                provider.search("q")
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))


class TestResolveProvider(unittest.TestCase):
    def test_injection_wins_over_env(self):
        fake = FakeWebSearchProvider()
        with patch.dict("os.environ", {"GEMINI_API_KEY": "env-key"}):
            self.assertIs(resolve_provider(fake), fake)

    def test_env_creates_gemini(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "env-key"}):
            provider = resolve_provider(None)
        self.assertIsInstance(provider, GeminiSearchProvider)

    def test_none_without_key(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("GEMINI_API_KEY", None)
            self.assertIsNone(resolve_provider(None))


class TestWebSearchTool(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _registry(self, provider):
        reg = ToolRegistry()
        for tool in WebResearchToolkit(provider).tools():
            reg.register(tool)
        return reg

    def test_registration_is_external(self):
        reg = self._registry(FakeWebSearchProvider())
        described = reg.describe()[0]
        self.assertEqual(described["name"], "web_search")
        self.assertEqual(described["side_effect_level"], "EXTERNAL")

    def test_search_through_registry_with_fake(self):
        provider = FakeWebSearchProvider(answered="the grounded answer")
        reg = self._registry(provider)
        result = reg.execute(ToolCall(name="web_search",
                                      arguments={"query": "current api"}),
                             workspace=self.ws,
                             confirmer=lambda call, d: True)
        self.assertTrue(result.ok, result.error)
        payload = json.loads(result.output)
        self.assertEqual(payload["answered"], "the grounded answer")
        self.assertTrue(payload["sources"])
        self.assertTrue(payload["timestamp"].endswith("Z"))

    def test_no_provider_is_structured_error(self):
        from qacompanion.agent.registry import ALLOW_ALL_POLICY
        reg = self._registry(None)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            result = reg.execute(ToolCall(name="web_search",
                                          arguments={"query": "q"}),
                                 workspace=self.ws, policy=ALLOW_ALL_POLICY)
        self.assertFalse(result.ok)
        self.assertIn("GEMINI_API_KEY", result.error)

    def test_empty_query_rejected(self):
        from qacompanion.agent.registry import ALLOW_ALL_POLICY
        reg = self._registry(FakeWebSearchProvider())
        result = reg.execute(ToolCall(name="web_search", arguments={"query": " "}),
                             workspace=self.ws, policy=ALLOW_ALL_POLICY)
        self.assertFalse(result.ok)
        self.assertIn("non-empty", result.error)

    def test_default_policy_asks_before_network(self):
        # the constraints amendment made real: EXTERNAL -> ASK, no
        # confirmer -> no network call happens
        calls = []
        provider = FakeWebSearchProvider()
        original = provider.search
        provider.search = lambda *a, **k: calls.append(1) or original(*a, **k)
        reg = self._registry(provider)
        result = reg.execute(ToolCall(name="web_search",
                                      arguments={"query": "q"}),
                             workspace=self.ws)
        self.assertFalse(result.ok)
        self.assertIn("no confirmer", result.error)
        self.assertEqual(calls, [])


class TestAgentRegistryIncludesWebSearch(unittest.TestCase):
    def test_membership(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            reg = agent_registry(Workspace(tmp))
            self.assertIn("web_search", reg.names())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
