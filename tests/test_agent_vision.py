"""S44 vision tests: PNG codec, comparison, capture, providers, tools.

Hermetic: no network (Gemini always mocked); capture tests run only on
Windows with real GDI — pixel content never asserted (the screen is
nondeterministic), structure only.
"""

import base64
import hashlib
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
from qacompanion.agent.registry import ALLOW_ALL_POLICY
from qacompanion.agent.vision import (
    DEFAULT_DIFF_THRESHOLD,
    FakeVisionProvider,
    GeminiVisionProvider,
    VisionError,
    VisionProvider,
    VisionToolkit,
    _diff_pixels,
    decode_png,
    encode_png,
    resolve_vision_provider,
)


def _solid(width, height, rgb):
    row = bytes(rgb) * width
    return [row for _ in range(height)]


def _with_pixels(rows, positions):
    """positions: {(x, y): (r, g, b)} — returns new row list."""
    height = len(rows)
    width = len(rows[0]) // 3
    mutable = [bytearray(row) for row in rows]
    for (x, y), (r, g, b) in positions.items():
        offset = x * 3
        mutable[y][offset] = r
        mutable[y][offset + 1] = g
        mutable[y][offset + 2] = b
    return [bytes(row) for row in mutable]


class TestPngCodec(unittest.TestCase):
    def test_round_trip(self):
        rows = _with_pixels(_solid(4, 3, (10, 20, 30)),
                            {(1, 1): (255, 0, 128), (3, 2): (0, 255, 0)})
        png = encode_png(4, 3, rows)
        out_w, out_h, out_rows = decode_png(png)
        self.assertEqual((out_w, out_h), (4, 3))
        self.assertEqual(out_rows, rows)

    def test_png_signature_and_nonempty(self):
        png = encode_png(2, 2, _solid(2, 2, (1, 2, 3)))
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(png), 50)

    def test_foreign_filter_rejected(self):
        png = bytearray(encode_png(2, 1, _solid(2, 1, (0, 0, 0))))
        # flip a filter byte inside the decompressed stream: easiest is to
        # re-zlib a tampered stream — instead just corrupt the file
        png[40] ^= 0xFF
        with self.assertRaises(Exception):
            decode_png(bytes(png))

    def test_bad_signature_rejected(self):
        with self.assertRaises(VisionError):
            decode_png(b"not a png at all")


class TestCompare(unittest.TestCase):
    def test_identical_images_zero_diff(self):
        rows = _solid(3, 2, (7, 8, 9))
        differing, total = _diff_pixels(rows, rows, DEFAULT_DIFF_THRESHOLD)
        self.assertEqual((differing, total), (0, 6))

    def test_small_difference(self):
        rows_a = _solid(3, 2, (0, 0, 0))
        rows_b = _with_pixels(rows_a, {(0, 0): (200, 200, 200)})
        differing, total = _diff_pixels(rows_a, rows_b,
                                        DEFAULT_DIFF_THRESHOLD)
        self.assertEqual(differing, 1)
        self.assertEqual(total, 6)

    def test_threshold_respected(self):
        rows_a = _solid(1, 1, (100, 100, 100))
        rows_b = _with_pixels(rows_a, {(0, 0): (105, 100, 100)})  # +5 <= 8
        differing, _ = _diff_pixels(rows_a, rows_b, DEFAULT_DIFF_THRESHOLD)
        self.assertEqual(differing, 0)
        differing, _ = _diff_pixels(rows_a, rows_b, threshold=2)
        self.assertEqual(differing, 1)


class TestProviders(unittest.TestCase):
    def test_fake_implements_interface_and_records(self):
        provider = FakeVisionProvider("a red square")
        self.assertIsInstance(provider, VisionProvider)
        observation = provider.inspect(b"pngbytes", "what is this?")
        self.assertEqual(observation, "a red square")
        self.assertEqual(provider.calls, [(b"pngbytes", "what is this?")])

    def test_gemini_sends_inline_data_and_prompt(self):
        provider = GeminiVisionProvider(api_key="test-key-123")
        captured = {}

        class FakeResponse:
            def read(self):
                return json.dumps({
                    "candidates": [{"content": {"parts": [
                        {"text": "a screenshot of a code editor"}]}}],
                }).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with patch("qacompanion.agent.vision.urllib.request.urlopen",
                   side_effect=fake_urlopen):
            observation = provider.inspect(b"png-bytes-here", "describe")

        self.assertEqual(observation, "a screenshot of a code editor")
        inline = captured["body"]["contents"][0]["parts"][0]["inline_data"]
        self.assertEqual(inline["mime_type"], "image/png")
        self.assertEqual(
            base64.b64decode(inline["data"]), b"png-bytes-here")
        self.assertEqual(captured["body"]["contents"][0]["parts"][1]["text"],
                         "describe")
        self.assertNotIn("google_search", json.dumps(captured["body"]))

    def test_gemini_http_error_structured_and_key_never_leaks(self):
        provider = GeminiVisionProvider(api_key="test-key-123")

        def error_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 429,
                                         "Too Many Requests", {},
                                         io.BytesIO(b""))

        with patch("qacompanion.agent.vision.urllib.request.urlopen",
                   side_effect=error_urlopen):
            with self.assertRaises(VisionError) as ctx:
                provider.inspect(b"x", "p")
        self.assertIn("HTTP 429", str(ctx.exception))
        self.assertNotIn("test-key-123", str(ctx.exception))

    def test_missing_key_fails_before_request(self):
        provider = GeminiVisionProvider(api_key=None)
        with patch("qacompanion.agent.vision.urllib.request.urlopen",
                   side_effect=AssertionError("network touched")):
            with self.assertRaises(VisionError) as ctx:
                provider.inspect(b"x", "p")
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))

    def test_resolve_provider(self):
        fake = FakeVisionProvider()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}):
            self.assertIs(resolve_vision_provider(fake), fake)
            self.assertIsInstance(resolve_vision_provider(None),
                                  GeminiVisionProvider)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            self.assertIsNone(resolve_vision_provider(None))


@unittest.skipUnless(os.name == "nt", "GDI screen capture is Windows-only")
class TestCaptureReal(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.toolkit = VisionToolkit(self.ws, FakeVisionProvider())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_capture_screen_structure(self):
        out = self.toolkit.capture_screen("shots/full.png")
        payload = json.loads(out)
        self.assertGreater(payload["width"], 0)
        self.assertGreater(payload["height"], 0)
        self.assertEqual(payload["format"], "png")
        self.assertTrue(payload["sha256"])
        saved = (self.tmp / "shots" / "full.png").read_bytes()
        self.assertEqual(hashlib.sha256(saved).hexdigest(), payload["sha256"])
        width, height, rows = decode_png(saved)
        self.assertEqual((width, height),
                         (payload["width"], payload["height"]))
        self.assertEqual(len(rows), height)

    def test_capture_region_exact_dimensions(self):
        out = self.toolkit.capture_region("shots/region.png", 0, 0, 320, 200)
        payload = json.loads(out)
        self.assertEqual((payload["width"], payload["height"]), (320, 200))

    def test_capture_region_bounds_validated(self):
        with self.assertRaises(VisionError):
            self.toolkit.capture_region("shots/big.png", 0, 0, 999999, 100)
        with self.assertRaises(VisionError):
            self.toolkit.capture_region("shots/neg.png", -1, 0, 10, 10)

    def test_capture_window_unknown_title(self):
        with self.assertRaises(VisionError) as ctx:
            self.toolkit.capture_window("shots/w.png",
                                        "Definitely Not A Real Window 12345")
        self.assertIn("no window", str(ctx.exception))


class TestVisionTools(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.provider = FakeVisionProvider("a login form with a red button")
        self.toolkit = VisionToolkit(self.ws, self.provider)
        self.reg = ToolRegistry()
        for tool in self.toolkit.tools():
            self.reg.register(tool)
        # seed a real PNG through the encoder (no screen needed)
        self.png = encode_png(2, 1, _solid(2, 1, (5, 5, 5)))
        (self.tmp / "shot.png").write_bytes(self.png)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_side_effect_matrix(self):
        described = {d["name"]: d for d in self.reg.describe()}
        self.assertEqual(
            set(described),
            {"capture_screen", "capture_window", "capture_region",
             "inspect_image", "compare_images"},
        )
        for name in ("capture_screen", "capture_window", "capture_region"):
            self.assertEqual(described[name]["side_effect_level"], "SAFE_WRITE")
        self.assertEqual(described["inspect_image"]["side_effect_level"],
                         "EXTERNAL")
        self.assertEqual(described["compare_images"]["side_effect_level"],
                         "READ_ONLY")

    def test_inspect_through_registry(self):
        result = self.reg.execute(
            ToolCall(name="inspect_image",
                     arguments={"path": "shot.png", "prompt": "what?"}),
            workspace=self.ws, confirmer=lambda call, d: True)
        self.assertTrue(result.ok, result.error)
        payload = json.loads(result.output)
        self.assertEqual(payload["observation"], "a login form with a red button")
        self.assertEqual(payload["image"], "shot.png")
        # the provider received the exact file bytes
        self.assertEqual(self.provider.calls[0][0], self.png)

    def test_inspect_default_posture_asks(self):
        # EXTERNAL: denied without confirmer — no accidental cloud call
        result = self.reg.execute(
            ToolCall(name="inspect_image", arguments={"path": "shot.png"}),
            workspace=self.ws)
        self.assertFalse(result.ok)
        self.assertIn("no confirmer", result.error)
        self.assertEqual(self.provider.calls, [])

    def test_inspect_without_provider_structured_error(self):
        import os
        bare = VisionToolkit(self.ws, None)
        reg = ToolRegistry()
        for tool in bare.tools():
            reg.register(tool)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            result = reg.execute(
                ToolCall(name="inspect_image", arguments={"path": "shot.png"}),
                workspace=self.ws, policy=ALLOW_ALL_POLICY)
        self.assertFalse(result.ok)
        self.assertIn("GEMINI_API_KEY", result.error)

    def test_compare_through_registry(self):
        rows = _solid(2, 1, (5, 5, 5))
        (self.tmp / "b.png").write_bytes(
            encode_png(2, 1, _with_pixels(rows, {(1, 0): (250, 5, 5)})))
        result = self.reg.execute(
            ToolCall(name="compare_images",
                     arguments={"path_a": "shot.png", "path_b": "b.png"}),
            workspace=self.ws)
        self.assertTrue(result.ok, result.error)
        payload = json.loads(result.output)
        self.assertFalse(payload["identical"])
        self.assertEqual(payload["diff_count"], 1)
        self.assertAlmostEqual(payload["diff_ratio"], 0.5)

    def test_compare_dimension_mismatch(self):
        (self.tmp / "tall.png").write_bytes(encode_png(2, 2, _solid(2, 2, (0, 0, 0))))
        result = self.reg.execute(
            ToolCall(name="compare_images",
                     arguments={"path_a": "shot.png", "path_b": "tall.png"}),
            workspace=self.ws)
        self.assertFalse(result.ok)
        self.assertIn("dimension mismatch", result.error)

    def test_missing_image_structured_error(self):
        result = self.reg.execute(
            ToolCall(name="compare_images",
                     arguments={"path_a": "ghost.png", "path_b": "shot.png"}),
            workspace=self.ws)
        self.assertFalse(result.ok)
        self.assertIn("not found", result.error)


class TestAgentRegistryIncludesVision(unittest.TestCase):
    def test_membership(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            reg = agent_registry(Workspace(tmp), vision_provider=FakeVisionProvider())
            for name in ("capture_screen", "capture_window", "capture_region",
                         "inspect_image", "compare_images"):
                self.assertIn(name, reg.names())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
