"""S55 slice-1 tests: configurable bridge timeout + GeminiModelProvider."""

import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from qacompanion import ollama_bridge as bridge
from qacompanion.agent import ModelMessage, ModelRequest, ToolCall, ToolResult
from qacompanion.agent.providers import GeminiModelProvider, ProviderError


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


class TestOllamaNativeToolCalling(unittest.TestCase):
    def test_native_chat_with_tools(self):
        from qacompanion.agent import OllamaProvider
        from qacompanion.agent.contracts import ToolDefinition
        from qacompanion import ollama_bridge as bridge
        captured = {}
        def fake_post(url, data, timeout=None):
            captured["url"] = url
            captured["data"] = data
            return {"message": {"role": "assistant", "content": "",
                                "tool_calls": [{"function": {
                                    "name": "read_file",
                                    "arguments": {"path": "a.py"}}}]}}
        provider = OllamaProvider()
        with patch.object(bridge, "_http_post", side_effect=fake_post):
            resp = provider.generate(ModelRequest(
                messages=[ModelMessage(role="user", content="read a.py")],
                tools=[ToolDefinition(name="read_file",
                                      description="read a file",
                                      parameters_schema={"type": "object"})]))
        self.assertIn("/api/chat", captured["url"])
        self.assertEqual(captured["data"]["tools"][0]["function"]["name"],
                         "read_file")
        self.assertEqual(resp.finish_reason, "tool_calls")
        self.assertEqual(resp.tool_calls[0].name, "read_file")
        self.assertEqual(resp.tool_calls[0].arguments, {"path": "a.py"})

    def test_think_flag_applies_to_chat(self):
        from qacompanion.agent import OllamaProvider
        from qacompanion.agent.contracts import ToolDefinition
        from qacompanion import ollama_bridge as bridge
        captured = {}
        def fake_post(url, data, timeout=None):
            captured["data"] = data
            return {"message": {"content": "done"}}
        provider = OllamaProvider()
        with patch.object(bridge, "_http_post", side_effect=fake_post):
            with patch.dict(os.environ, {"OLLAMA_THINK": "false"}):
                with patch.object(bridge, "_think_flag",
                                  return_value=False):
                    provider.generate(ModelRequest(
                        messages=[ModelMessage(role="user", content="hi")],
                        tools=[ToolDefinition(
                            name="t", description="d",
                            parameters_schema={"type": "object"})]))
        self.assertIn("think", captured["data"])
        self.assertFalse(captured["data"]["think"])

    def test_native_chat_timeout_floor_and_knob(self):
        """S64 finding: the native path hardcoded a 300s ceiling and
        ignored OLLAMA_TIMEOUT. Floor stays 300; the knob raises it."""
        from unittest.mock import patch
        captured = {}

        def fake_post(url, data, timeout=None):
            captured["timeout"] = timeout
            return {"message": {"content": "ok"}}

        with patch.object(bridge, "_http_post", side_effect=fake_post):
            bridge._ollama_chat([{"role": "user", "content": "hi"}])
            self.assertEqual(300, captured["timeout"])  # floor
            with patch.dict(os.environ, {"OLLAMA_TIMEOUT": "600"}):
                bridge._ollama_chat([{"role": "user", "content": "hi"}])
                self.assertEqual(600, captured["timeout"])


    def test_textual_path_preserved_without_tools(self):
        # the 1.5B-era shim: no tools declared -> /api/generate textual
        from qacompanion.agent import OllamaProvider
        from qacompanion import ollama_bridge as bridge
        captured = {}
        def fake_generate(prompt, model=None, url=None, **kwargs):
            captured["prompt"] = prompt
            return "plain answer"
        provider = OllamaProvider()
        with patch.object(bridge, "_ollama_generate",
                          side_effect=fake_generate):
            resp = provider.generate(ModelRequest(
                messages=[ModelMessage(role="user", content="hi")]))
        self.assertEqual(resp.finish_reason, "stop")
        self.assertEqual(resp.text, "plain answer")
        self.assertNotIn("/api/chat", json.dumps(captured))


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
        # 429 now retries with a minute-long wait (free-tier rate limit);
        # patch sleep so the structured-error assertion stays instant
        with patch("qacompanion.agent.providers.time.sleep"),              patch("qacompanion.agent.providers.urllib.request.urlopen",
                   side_effect=fake_urlopen):
            with self.assertRaises(Exception) as ctx:
                provider.generate(ModelRequest(messages=[]))
        self.assertNotIn("test-key-123", str(ctx.exception))

    def test_native_function_calling(self):
        captured = {}
        class FakeResponse:
            def read(self):
                return json.dumps({"candidates": [{"content": {"parts": [
                    {"functionCall": {"name": "read_file",
                                      "args": {"path": "a.py"}}}]}}]
                }).encode("utf-8")
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        def fake_urlopen(request, timeout=None):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()
        from qacompanion.agent import ToolDefinition
        provider = self._provider(api_key="test-key-123")
        with patch("qacompanion.agent.providers.urllib.request.urlopen",
                   side_effect=fake_urlopen):
            resp = provider.generate(ModelRequest(
                messages=[ModelMessage(role="user", content="read a.py")],
                tools=[ToolDefinition(name="read_file",
                                      description="read a file",
                                      parameters_schema={"type": "object"})]))
        self.assertEqual(resp.finish_reason, "tool_calls")
        self.assertEqual(resp.tool_calls[0].name, "read_file")
        self.assertEqual(resp.tool_calls[0].arguments, {"path": "a.py"})
        decls = captured["body"]["tools"][0]["function_declarations"]
        self.assertEqual(decls[0]["name"], "read_file")

    def test_native_no_function_call_is_stop(self):
        class FakeResponse:
            def read(self):
                return json.dumps({"candidates": [{"content": {"parts": [
                    {"text": "plain answer"}]}}]}).encode("utf-8")
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        provider = self._provider(api_key="test-key-123")
        from qacompanion.agent import ToolDefinition
        with patch("qacompanion.agent.providers.urllib.request.urlopen",
                   return_value=FakeResponse()):
            resp = provider.generate(ModelRequest(
                messages=[ModelMessage(role="user", content="hi")],
                tools=[ToolDefinition(name="read_file",
                                      description="read",
                                      parameters_schema={"type": "object"})]))
        self.assertEqual(resp.finish_reason, "stop")
        self.assertEqual(resp.tool_calls, [])

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


class TestGeminiNativeContents(unittest.TestCase):
    """S63 live finding: tool results are USER-turn functionResponse
    parts. Model-role text made requests "end with a model turn" and
    Gemini 400'd the whole conversation."""

    def _provider(self):
        return GeminiModelProvider(api_key="test-key-123")

    def _generate(self, request):
        captured = {}

        class FakeResponse:
            def read(self):
                return json.dumps({"candidates": [{"content": {"parts": [
                    {"functionCall": {"name": "list_directory",
                                      "args": {"path": "."}}}]}}]}
                    ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout=None):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with patch("qacompanion.agent.providers.urllib.request.urlopen",
                   side_effect=fake_urlopen):
            response = self._provider().generate(request)
        return captured["body"], response

    def test_tool_result_is_user_turn_function_response(self):
        result = ToolResult(call_name="read_file", ok=True,
                            output="def add(): ...")
        body, response = self._generate(ModelRequest(
            messages=[
                ModelMessage(role="system", content="be terse"),
                ModelMessage(role="user", content="read the file"),
                ModelMessage(role="assistant", content="",
                             tool_calls=[ToolCall(
                                 name="read_file",
                                 arguments={"path": "a.py"})]),
                ModelMessage(role="tool",
                             content=json.dumps(result.to_dict())),
            ],
            tools=[_simple_definition()]))
        contents = body["contents"]
        self.assertEqual(["user", "user", "model", "user"],
                         [c["role"] for c in contents])
        function_call = contents[2]["parts"][0]["functionCall"]
        self.assertEqual("read_file", function_call["name"])
        self.assertEqual({"path": "a.py"}, function_call["args"])
        function_response = contents[3]["parts"][0]["functionResponse"]
        self.assertEqual("read_file", function_response["name"])
        self.assertIn("def add", function_response["response"]["result"])
        # the request never ends with a model turn
        self.assertEqual("user", contents[-1]["role"])
        # no empty text parts anywhere
        for content in contents:
            for part in content["parts"]:
                if "text" in part:
                    self.assertTrue(part["text"].strip(), content)
        self.assertEqual(response.finish_reason, "tool_calls")

    def test_assistant_text_replayed_alongside_calls(self):
        body, _ = self._generate(ModelRequest(
            messages=[
                ModelMessage(role="user", content="go"),
                ModelMessage(role="assistant", content="Checking.",
                             tool_calls=[ToolCall(
                                 name="read_file",
                                 arguments={"path": "a.py"})]),
                ModelMessage(role="tool", content="not json output"),
            ],
            tools=[_simple_definition()]))
        parts = body["contents"][1]["parts"]
        self.assertEqual("Checking.", parts[0]["text"])
        self.assertEqual("read_file", parts[1]["functionCall"]["name"])
        # unparseable tool content still yields a named functionResponse
        self.assertEqual("tool",
                         body["contents"][2]["parts"][0]
                         ["functionResponse"]["name"])

    def test_thought_signature_round_trip(self):
        captured = {}

        class FakeResponse:
            def read(self):
                return json.dumps({"candidates": [{"content": {"parts": [
                    {"functionCall": {"name": "run_tests", "args": {}},
                     "thoughtSignature": "sig-abc123"}]}}]}).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout=None):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        provider = GeminiModelProvider(api_key="test-key-123")
        with patch("qacompanion.agent.providers.urllib.request.urlopen",
                   side_effect=fake_urlopen):
            first = provider.generate(ModelRequest(
                messages=[ModelMessage(role="user", content="run tests")],
                tools=[_simple_definition()]))
        self.assertEqual("sig-abc123",
                         first.tool_calls[0].thought_signature)
        # replay the captured call as history: signature must survive
        with patch("qacompanion.agent.providers.urllib.request.urlopen",
                   side_effect=fake_urlopen):
            provider.generate(ModelRequest(
                messages=[
                    ModelMessage(role="user", content="run tests"),
                    ModelMessage(role="assistant", content="",
                                 tool_calls=first.tool_calls),
                    ModelMessage(role="tool", content='{"call_name": '
                                                     '"read_file"}'),
                ],
                tools=[_simple_definition()]))
        part = captured["body"]["contents"][1]["parts"][0]
        self.assertEqual("sig-abc123", part["thoughtSignature"])
        self.assertEqual("run_tests", part["functionCall"]["name"])
        self.assertNotIn("thoughtSignature", part["functionCall"])

    def test_error_body_surfaced(self):
        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                "url", 400, "Bad", {},
                io.BytesIO(b'{"error": {"message": "boom: bad part"}}'))

        with patch("qacompanion.agent.providers.urllib.request.urlopen",
                   side_effect=fake_urlopen):
            with self.assertRaises(ProviderError) as ctx:
                self._provider().generate(ModelRequest(
                    messages=[ModelMessage(role="user", content="hi")]))
        self.assertIn("boom: bad part", str(ctx.exception))
        self.assertIn("HTTP 400", str(ctx.exception))


def _simple_definition():
    from qacompanion.agent.contracts import ToolDefinition
    return ToolDefinition(
        name="read_file", description="Read a file",
        parameters_schema={"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]})
