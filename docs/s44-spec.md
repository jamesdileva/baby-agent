# S44 — Vision / Screenshot Analysis: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S44. Builds on S31–S43. One slice, stdlib only, no CLI changes.

## Overview

Visual perception, with the architecture rule enforced by the module
boundary: **vision capability ≠ screen acquisition**. Capture tools
acquire; a VisionProvider interprets; the agent model decides; action
tools act. A screenshot becomes an ordinary observation the model can
reason over — "what does the app look like" is then just a tool result.

## Module layout

```text
qacompanion/agent/vision.py    # PNG codec, GDI capture, VisionProvider, 5 tools
tests/test_agent_vision.py
```

## Image format: stdlib PNG

Gemini's multimodal API does not accept BMP, and Pillow is not allowed —
so vision.py carries a minimal PNG codec (~50 lines): `_encode_png`
(8-bit RGB, filter 0, zlib IDAT) and `_decode_png` (parses our own
encoder's output; foreign filters → structured error — compare only
needs our captures). Captures are saved as PNG files in the workspace.

## Acquisition (Windows via ctypes GDI; POSIX = structured error)

```text
capture_screen  {path}                      whole screen
capture_window  {path, title}               FindWindowW + GetWindowRect region
                                            (visible content; unknown title
                                            -> structured error)
capture_region  {path, x, y, width, height} bounds-validated against screen
```

All three: SAFE_WRITE (workspace writes through PathPolicy, atomic),
category "vision", PNG output {path, width, height, bytes, sha256}.

## Interpretation + comparison

- **inspect_image** `{path, prompt?}` — **EXTERNAL** (the image leaves the
  machine). `VisionProvider` abstraction: `FakeVisionProvider` (scripted)
  + `GeminiVisionProvider` (generateContent with inline_data base64 PNG +
  text prompt — PLAIN request, no grounding tool: works on the human's
  free key per the 2026-09-04 ruling; model from GEMINI_VISION_MODEL env,
  default gemini-flash-latest). Missing key → structured error before any
  request. Returns {image, observation, provider, model} — the
  ImageObservation the loop's model reasons over.
- **compare_images** `{path_a, path_b, threshold?}` — local pixel math
  (READ_ONLY): identical → diff_ratio 0; per-channel threshold defaults to
  8; dimension mismatch → structured error. This is what verifies "the
  layout improved" without a model.

`agent_registry()` grows to 32 tools.

## Testing strategy (tests/test_agent_vision.py)

- PNG codec: encode→decode round trip on synthetic pixels; foreign-filter
  rejection; corrupt signature rejection.
- Compare: identical → 0.0; synthetic difference → 0 < ratio < 1; per-
  channel threshold respected; dimension mismatch error.
- Capture (skipUnless Windows, display present): screen PNG has screen
  dimensions and valid sha256; region PNG has exact requested
  dimensions; unknown window title → structured error. Pixel content is
  never asserted (screen is nondeterministic) — structure only.
- VisionProvider: fake scripted; Gemini mocked (inline_data carries the
  exact base64; prompt present; HTTP/429 errors structured; missing key
  fails before any request).
- Tools: registration + side-effect matrix (SAFE_WRITE ×3, EXTERNAL,
  READ_ONLY); through-registry runs; default ASK posture for
  inspect_image (denied without confirmer — no accidental cloud calls);
  agent_registry membership.

Expected suite growth: 1198 → ~1220 OK.

## Exit criteria (from ROADMAP-agentlite.md §S44)

Capture → inspect → identify → modify → relaunch → compare → verify is
mechanically possible through registry tools (the full benchmark is an
S48 concern). Live smoke: capture this screen and inspect it with the
human's free Gemini key. Full suite green; preflight clean.
