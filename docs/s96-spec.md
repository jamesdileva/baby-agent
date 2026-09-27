# S96 — Dashboard usefulness (the deferred S82 item)

Status: landed 2026-09-27. Server + UI only; no training, no corpus,
nothing for Colab. Electron shell, thinking toggles, and
dashboard-triggered training stay deferred per the human's call.

## The three backlog items (+1 approved extra)

Human-tested 2026-09-24, deferred until baby-agent works — it now
does (ep11 12-13/15), so the polish unblocks:

1. **Model/brain chooser (the 9B slide-in):** `GET /api/models`
   (stdlib subprocess over `ollama list`, structured 503 when
   ollama is absent) feeds a suggestion dropdown (free text kept);
   per-session `provider` (`ollama`/`gemini`) through
   `/api/session/start` into a factory that already resolved
   per-call — env default preserved, old single-arg test factories
   updated. Live smoke: real `ollama list` parses, qwen3.5 models
   appear with zero model-specific code.
2. **Folder picker:** `GET /api/browse?path=` (subdirectories,
   sorted, dot-dirs skipped; missing → 404, not-a-dir → 400) +
   picker modal defaulting at the current input. Local-only
   server; the workspace param was already arbitrary, so this is
   convenience, not new authority.
3. **Output visibility:** the feed rendered event types but dropped
   every payload — now shows model response text (capped 300 chars
   at the loop emitter, so runaway generations can't flood
   subscribers), tool failures with errors, changed paths, plus
   workspace/model/error in the session panel and visible start
   errors.
4. **Verdict decoding flags:** temperature/seed inputs on the
   Operations panel through the S93 path (empty = server default).

## Verification

- 7 new hermetic server tests (models present/absent, provider
  carry-through + invalid, browse + 404, verdict flags); real-HTTP
  loopback tests unchanged in shape.
- `npm run build` green (tsc + vite); suite 1705 OK (1698 + 7);
  pyflakes clean.
- Live smoke: `/api/models` vs real ollama, `/api/browse` vs
  real fs.
