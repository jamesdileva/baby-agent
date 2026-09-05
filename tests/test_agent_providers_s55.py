"""S55 slice-1 tests: configurable bridge timeout + GeminiModelProvider."""

import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from qacompanion import ollama_bridge as bridge
from qacompanion.agent import ModelMessage, ModelRequest, ModelResponse
from qacompanion.agent.providers import GeminiModelProvider


class TestConfigurableTimeout(unittest.TestCase):
    def test_default_60s(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OLLAMA_TIMEOUT", None)
            self.assertEqual(bridge._configured_timeout(), 60.0)

    def test_env_override(self):
        with patch.dict(os.environ, {"OLLAMA_TIMEOUT": "180"}):
            self.assertEqual(bridge._configured_timeout(), 180.0)

    def test_http_post_resolves_configured_timeout(self):
        captured = {}
        def fake_urlopen(request, timeout=None):
            captured["timeout"] = timeout
            return __import__("io").BytesIO(b'{"response": "ok"}')
        with patch.dict(os.environ, {"OLLAMA_TIMEOUT": "180"}):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                bridge._http_post("http://localhost:11434/api/generate",
                                  {"prompt": "ping"})
        self.assertEqual(captured["timeout"], 180.0)


class TestGeminiModelProvider(unittest.TestCase):
    def _provider(self, **kwargs):
        return GeminiModelProvider(**kwargs)

    def test_plain_request_no_grounding(self):
        captured = {}
        class FakeResponse:
            def read(self):
                return json.dumps({"candidates": [{"content": {"parts": [
                    {"text": "cloud brain answer"}]}}]}).encode("utf-8")
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        def fake_urlopen(request, timeout=None):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()
        provider = self._provider(api_key="test-key-123")
        with patch("qacompanion.agent.providers.urllib.request.urlopen",
                   side_effect=fake_urlopen):
            resp = provider.generate(ModelRequest(
                messages=[ModelMessage(role="user", content="hello")]))
        self.assertEqual(resp.text, "cloud brain answer")
        self.assertEqual(resp.finish_reason, "stop")
        self.assertNotIn("google_search", json.dumps(captured["body"]))

    def test_missing_key_structured(self):
        provider = self._provider(api_key=None)
        with patch("qacompanion.agent.providers.urllib.request.urlopen",
                   side_effect=AssertionError("network touched")):
            with self.assertRaises(Exception) as ctx:
                provider.generate(ModelRequest(messages=[]))
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))

    def test_http_error_structured_and_key_never_leaks(self):
        provider = self._provider(api_key="test-key-123")
        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 429, "quota", {},
                                         __import__("io").BytesIO(b""))
        with patch("qacompanion.agent.providers.urllib.request.urlopen",
                   side_effect=fake_urlopen):
            with self.assertRaises(Exception) as ctx:
                provider.generate(ModelRequest(messages=[]))
        self.assertNotIn("test-key-123", str(ctx.exception))

    def test_empty_response_structured(self):
        class FakeResponse:
            def read(self):
                return json.dumps({"candidates": []}).encode("utf-8")
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        provider = self._provider(api_key="test-key-123")
        with patch("qacompanion.agent.providers.urllib.request.urlopen",
                   return_value=FakeResponse()):
            with self.assertRaises(Exception):
                provider.generate(ModelRequest(messages=[]))


if __name__ == "__main__":
    unittest.main()
