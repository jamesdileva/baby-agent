# S97 — Eyes for dashboard sessions + blank-screen detector

Status: landed 2026-09-27. Server + vision only; benchmark/harness
catalogs untouched (hermetic); Colab ep15 untouched.

## Why

User-tested: "screenshot my PC" was correctly declined — the
dashboard session registry (coding families only) never offered
vision tools. Nothing about executables matters (capture is GDI);
the fix is offering the tools. The white-screen idea becomes a
deterministic loading-hang detector from owned primitives.

## Changes

1. **Vision wiring for dashboard sessions** (`dashboard_registry`
   helper in server.py, used by `run()`): coding families + all
   vision tools. Captures land as workspace PNGs the human opens;
   compare runs locally; inspect_image works iff GEMINI_API_KEY
   is set, else raises naming the fix (EXTERNAL stays
   confirmer-denied — no silent exfiltration, ever).
2. **New `detect_blank_screen` tool** (READ_ONLY): white-pixel
   ratio + `blank` verdict over a workspace PNG
   (`white_threshold` default 240, `min_white_percent` default
   95; validated ranges). Loading hang vs rendered app; pairs
   with compare_images for before/after-load checks.
3. Registry exact-count pin 65/59 → 66/60 with membership.

## Verification

- 6 new hermetic tests (blank true/false/threshold/args/missing,
  dashboard registry membership); suite 1713 OK (1707 + 6);
  pyflakes clean.
- **Live proof:** real dashboard session ("screenshot my PC",
  ep11-q4) COMPLETED with shot.png (119KB) in the workspace —
  capture_screen called and reported; the refusal mode is gone.
