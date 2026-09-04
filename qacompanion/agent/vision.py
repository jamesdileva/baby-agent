"""S44 vision: acquisition tools + interpretation provider, separated.

Architecture rule (spec): vision capability != screen acquisition.
capture_* tools acquire PNGs into the workspace (SAFE_WRITE); a
VisionProvider interprets (inspect_image — EXTERNAL, the image leaves the
machine); compare_images is local pixel math (READ_ONLY). The agent
model then reasons over the observation like any other tool result.

Image format: minimal stdlib PNG (8-bit RGB, filter 0) — Gemini's
multimodal API rejects BMP and Pillow is forbidden. _decode_png only
parses our own encoder's output (foreign filters are a structured error).

Screen acquisition: ctypes GDI BitBlt (Windows); POSIX raises a
structured error rather than pretending. Window capture targets a window
title's visible rectangle on the screen (FindWindowW + GetWindowRect).

The Gemini vision adapter sends PLAIN multimodal requests (no grounding
tool) per the human ruling of 2026-09-04 — works on the free key.
"""

import base64
import ctypes
import hashlib
import json
import os
import struct
import urllib.error
import urllib.request
import zlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .registry import (
    EXTERNAL,
    READ_ONLY,
    SAFE_WRITE,
    RegisteredTool,
    ToolDefinition,
    ToolOperationError,
    ToolRegistry,
)
from .workspace import PathError, Workspace

GEMINI_ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
                   "{model}:generateContent")
# live smoke 2026-09-04: flash-latest / 3-flash-preview were 503
# (high demand); 3.1-flash-lite served free multimodal immediately
DEFAULT_VISION_MODEL = "gemini-3.1-flash-lite"
VISION_TIMEOUT = 60.0
DEFAULT_DIFF_THRESHOLD = 8
DEFAULT_INSPECT_PROMPT = ("Describe this screenshot in detail: what "
                          "application is shown, what state is it in, and "
                          "is anything visually broken?")

SRCCOPY = 0x00CC0020
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class VisionError(ToolOperationError):
    """Structured vision failure (platform, capture, provider, caps)."""


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


# --- minimal stdlib PNG codec (8-bit RGB, filter 0) ------------------------

def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def encode_png(width: int, height: int, rows: List[bytes]) -> bytes:
    """rows: top-down, each exactly width*3 RGB bytes."""
    for row in rows:
        if len(row) != width * 3:
            raise VisionError("PNG encode: bad row length")
    if len(rows) != height:
        raise VisionError("PNG encode: bad row count")
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + row for row in rows)
    return (PNG_SIGNATURE
            + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", zlib.compress(raw, 6))
            + _png_chunk(b"IEND", b""))


def decode_png(data: bytes) -> Tuple[int, int, List[bytes]]:
    """Decode our own encoder's PNGs. Foreign filters are rejected."""
    if not data.startswith(PNG_SIGNATURE):
        raise VisionError("not a PNG file")
    offset = len(PNG_SIGNATURE)
    width = height = None
    idat = b""
    while offset + 8 <= len(data):
        (length,) = struct.unpack_from(">I", data, offset)
        tag = data[offset + 4:offset + 8]
        chunk = data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if tag == b"IHDR":
            width, height, depth, color, *_ = struct.unpack(">IIBBBBB", chunk)
            if depth != 8 or color != 2:
                raise VisionError(
                    "unsupported PNG format (need 8-bit RGB from our captures)"
                )
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break
    if width is None or not idat:
        raise VisionError("PNG missing IHDR/IDAT")
    raw = zlib.decompress(idat)
    stride = width * 3
    rows = []
    for y in range(height):
        row = raw[y * (stride + 1):(y + 1) * (stride + 1)]
        if not row or row[0] != 0:
            raise VisionError("unsupported PNG filter (need filter 0)")
        rows.append(row[1:])
    return width, height, rows


# --- screen acquisition (ctypes GDI, Windows) ------------------------------

def _screen_size() -> Tuple[int, int]:
    user32 = ctypes.windll.user32
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def _capture_region_rgb(x: int, y: int, width: int, height: int) -> List[bytes]:
    """GDI BitBlt a screen region into top-down RGB rows."""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    screen_dc = user32.GetDC(0)
    if not screen_dc:
        raise VisionError("GetDC(0) failed")
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    gdi32.SelectObject(mem_dc, bitmap)
    gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, x, y, SRCCOPY)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
            ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
            ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
            ("biYPelsPerMeter", ctypes.c_int32),
            ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER)]

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height  # negative: top-down rows
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0  # BI_RGB

    buffer = ctypes.create_string_buffer(width * height * 4)
    copied = gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer,
                             ctypes.byref(bmi), 0)  # DIB_RGB_COLORS
    rows: List[bytes] = []
    if copied == height:
        stride = width * 4
        for y_index in range(height):
            offset = y_index * stride
            bgra = buffer.raw[offset:offset + width * 4]
            rgb = bytearray(width * 3)
            for px in range(width):
                rgb[px * 3] = bgra[px * 4 + 2]      # R
                rgb[px * 3 + 1] = bgra[px * 4 + 1]  # G
                rgb[px * 3 + 2] = bgra[px * 4]      # B
            rows.append(bytes(rgb))
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(0, screen_dc)
    if copied != height:
        raise VisionError(f"GetDIBits copied {copied}/{height} rows")
    return rows


def capture_screen_rgb() -> Tuple[int, int, List[bytes]]:
    if os.name != "nt":
        raise VisionError(
            f"screen capture unsupported on {os.name!r} (Windows GDI only)"
        )
    width, height = _screen_size()
    if width <= 0 or height <= 0:
        raise VisionError("no usable display")
    return width, height, _capture_region_rgb(0, 0, width, height)


def capture_window_rgb(title: str) -> Tuple[int, int, List[bytes], Tuple[int, int, int, int]]:
    if os.name != "nt":
        raise VisionError(
            f"screen capture unsupported on {os.name!r} (Windows GDI only)"
        )
    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        raise VisionError(f"no window with title {title!r}")
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise VisionError(f"GetWindowRect failed for {title!r}")
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise VisionError(f"window {title!r} has no visible area")
    return (width, height,
            _capture_region_rgb(rect.left, rect.top, width, height),
            (rect.left, rect.top, width, height))


# --- vision providers -------------------------------------------------------

class VisionProvider(ABC):
    """Interprets image bytes into a text observation."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def inspect(self, png_bytes: bytes, prompt: str) -> str:
        ...


class FakeVisionProvider(VisionProvider):
    """Scripted interpretation for tests (never touches network)."""

    def __init__(self, observation: str = "a login form with a red button"):
        self._observation = observation
        self.calls: List[Tuple[bytes, str]] = []

    @property
    def name(self) -> str:
        return "fake"

    def inspect(self, png_bytes: bytes, prompt: str) -> str:
        self.calls.append((png_bytes, prompt))
        return self._observation


class GeminiVisionProvider(VisionProvider):
    """Gemini multimodal (plain request — no grounding tool)."""

    def __init__(self, api_key: Optional[str] = None,
                 model: Optional[str] = None):
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model or os.environ.get("GEMINI_VISION_MODEL") \
            or DEFAULT_VISION_MODEL

    @property
    def name(self) -> str:
        return "gemini"

    def inspect(self, png_bytes: bytes, prompt: str) -> str:
        if not self._api_key:
            raise VisionError(
                "no vision provider configured: set GEMINI_API_KEY "
                "(free key at aistudio.google.com)"
            )
        encoded = base64.b64encode(png_bytes).decode("ascii")
        body = {
            "contents": [{"parts": [
                {"inline_data": {"mime_type": "image/png", "data": encoded}},
                {"text": prompt},
            ]}],
        }
        request = urllib.request.Request(
            f"{GEMINI_ENDPOINT.format(model=self.model)}?key={self._api_key}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=VISION_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            raise VisionError(
                f"gemini vision request failed: HTTP {exc.code} {detail}"
            ) from exc
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
            raise VisionError(f"gemini vision request failed: {exc}") from exc
        try:
            parts = data["candidates"][0]["content"]["parts"]
            observation = "".join(str(p.get("text", "")) for p in parts).strip()
        except (KeyError, IndexError, TypeError):
            observation = ""
        if not observation:
            raise VisionError("gemini vision response missing usable content")
        return observation


def resolve_vision_provider(provider: Optional[VisionProvider] = None
                            ) -> Optional[VisionProvider]:
    if provider is not None:
        return provider
    if os.environ.get("GEMINI_API_KEY"):
        return GeminiVisionProvider()
    return None


# --- toolkit ----------------------------------------------------------------

def _diff_pixels(rows_a: List[bytes], rows_b: List[bytes],
                 threshold: int) -> Tuple[int, int]:
    total = len(rows_a) * (len(rows_a[0]) // 3) if rows_a else 0
    differing = 0
    for row_a, row_b in zip(rows_a, rows_b):
        for offset in range(0, len(row_a), 3):
            if (abs(row_a[offset] - row_b[offset]) > threshold
                    or abs(row_a[offset + 1] - row_b[offset + 1]) > threshold
                    or abs(row_a[offset + 2] - row_b[offset + 2]) > threshold):
                differing += 1
    return differing, total


class VisionToolkit:
    """Binds the five vision tools (workspace required for file output)."""

    def __init__(self, workspace: Workspace,
                 vision_provider: Optional[VisionProvider] = None):
        self.workspace = workspace
        self.provider = resolve_vision_provider(vision_provider)

    def _save_capture(self, path: str, width: int, height: int,
                      rows: List[bytes]) -> Dict[str, Any]:
        try:
            target = self.workspace.resolve(path)
        except PathError as exc:
            raise VisionError(str(exc)) from exc
        png = encode_png(width, height, rows)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".tmp-capture")
            tmp.write_bytes(png)
            os.replace(tmp, target)
        except OSError as exc:
            raise VisionError(f"capture write failed: {exc}") from exc
        return {
            "path": self.workspace.relative(target),
            "width": width,
            "height": height,
            "bytes": len(png),
            "sha256": hashlib.sha256(png).hexdigest(),
            "format": "png",
            "captured_at": _utc_stamp(),
        }

    def capture_screen(self, path: str) -> str:
        width, height, rows = capture_screen_rgb()
        return json.dumps(self._save_capture(path, width, height, rows),
                          ensure_ascii=False)

    def capture_window(self, path: str, title: str) -> str:
        width, height, rows, _rect = capture_window_rgb(title)
        return json.dumps(self._save_capture(path, width, height, rows),
                          ensure_ascii=False)

    def capture_region(self, path: str, x: int, y: int,
                       width: int, height: int) -> str:
        if os.name != "nt":
            raise VisionError(
                f"screen capture unsupported on {os.name!r} (Windows GDI only)"
            )
        screen_w, screen_h = _screen_size()
        if min(x, y, width, height) < 0 or width == 0 or height == 0:
            raise VisionError("invalid capture region")
        if x + width > screen_w or y + height > screen_h:
            raise VisionError(
                f"capture region exceeds screen ({screen_w}x{screen_h})")
        rows = _capture_region_rgb(x, y, width, height)
        return json.dumps(self._save_capture(path, width, height, rows),
                          ensure_ascii=False)

    def _load_png(self, path: str) -> bytes:
        try:
            target = self.workspace.resolve(path)
        except PathError as exc:
            raise VisionError(str(exc)) from exc
        if not target.exists():
            raise VisionError(f"image not found: {path}")
        return target.read_bytes()

    def inspect_image(self, path: str, prompt: str = DEFAULT_INSPECT_PROMPT
                      ) -> str:
        png = self._load_png(path)
        if self.provider is None:
            raise VisionError(
                "no vision provider configured: set GEMINI_API_KEY "
                "(free key at aistudio.google.com) or inject a provider"
            )
        observation = self.provider.inspect(png, prompt)
        return json.dumps({
            "image": path,
            "observation": observation,
            "provider": self.provider.name,
            "model": getattr(self.provider, "model", None),
        }, ensure_ascii=False)

    def compare_images(self, path_a: str, path_b: str,
                       threshold: int = DEFAULT_DIFF_THRESHOLD) -> str:
        width_a, height_a, rows_a = decode_png(self._load_png(path_a))
        width_b, height_b, rows_b = decode_png(self._load_png(path_b))
        if (width_a, height_a) != (width_b, height_b):
            raise VisionError(
                f"dimension mismatch: {width_a}x{height_a} vs "
                f"{width_b}x{height_b}"
            )
        differing, total = _diff_pixels(rows_a, rows_b, threshold)
        return json.dumps({
            "path_a": path_a,
            "path_b": path_b,
            "width": width_a,
            "height": height_a,
            "diff_count": differing,
            "diff_ratio": round(differing / total, 6) if total else 0.0,
            "threshold": threshold,
            "identical": differing == 0,
        }, ensure_ascii=False)

    def tools(self) -> List[RegisteredTool]:
        def _tool(name, description, schema, handler, side_effect,
                  needs_workspace=True):
            return RegisteredTool(
                definition=ToolDefinition(
                    name=name, description=description,
                    parameters_schema=schema),
                handler=handler,
                category="vision",
                side_effect_level=side_effect,
                requires_workspace=needs_workspace,
            )

        path_schema = {"type": "object",
                       "properties": {"path": {"type": "string"}},
                       "required": ["path"]}
        return [
            _tool("capture_screen", "Capture the whole screen as a PNG in "
                  "the workspace.", path_schema, self.capture_screen,
                  SAFE_WRITE),
            _tool("capture_window", "Capture a named window's visible "
                  "rectangle as a PNG.",
                  {"type": "object",
                   "properties": {"path": {"type": "string"},
                                  "title": {"type": "string"}},
                   "required": ["path", "title"]},
                  self.capture_window, SAFE_WRITE),
            _tool("capture_region", "Capture a screen region as a PNG.",
                  {"type": "object",
                   "properties": {
                       "path": {"type": "string"}, "x": {"type": "integer"},
                       "y": {"type": "integer"},
                       "width": {"type": "integer"},
                       "height": {"type": "integer"}},
                   "required": ["path", "x", "y", "width", "height"]},
                  self.capture_region, SAFE_WRITE),
            _tool("inspect_image", "Send a workspace image to the vision "
                  "provider and return its text observation (EXTERNAL: "
                  "the image leaves the machine).",
                  {"type": "object",
                   "properties": {"path": {"type": "string"},
                                  "prompt": {"type": "string"}},
                   "required": ["path"]},
                  self.inspect_image, EXTERNAL),
            _tool("compare_images", "Local pixel comparison of two PNGs "
                  "(no model, no network).",
                  {"type": "object",
                   "properties": {"path_a": {"type": "string"},
                                  "path_b": {"type": "string"},
                                  "threshold": {"type": "integer"}},
                   "required": ["path_a", "path_b"]},
                  self.compare_images, READ_ONLY),
        ]


def update_agent_registry(registry: ToolRegistry, workspace: Workspace,
                          vision_provider: Optional[VisionProvider] = None
                          ) -> None:
    """Register the vision tools into an existing registry."""
    for tool in VisionToolkit(workspace, vision_provider).tools():
        registry.register(tool)
