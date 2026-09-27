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

## S96.1 repair (user-tested same day)

Four live findings, all fixed:

1. **White/vanilla UI — root cause: `main.tsx` never imported
   `./styles.css`.** The dark stylesheet existed since S52 but was
   never wired in: the dashboard was ALWAYS unstyled. One-line
   fix; the build now emits a real CSS asset (verified present).
2. **Up-button KeyError** (`C%3A%5C…`): the hand-rolled query
   parser never URL-decoded params. Decode centrally + regression
   test with an encoded Windows path; live smoke browses the real
   repo root through the encoded URL.
3. **`qa` not recognized:** `qa` was never installed anywhere —
   docs assumed it. New `qa.bat` shim (PYTHONPATH-based, keeps
   caller CWD for per-project stores) + quick-reference line;
   verified `qa --help` works.
4. **Stylesheet completed** (every class in use: picker modal,
   error, rows, history affordance) + picker path display and
   empty-state; "auto-picks baby-agent" was the modal opening at
   the server cwd, now explicit.
- Suite 1706 OK (1705 + 1); pyflakes clean; npm build green;
  live smoke re-run (CSS link present, encoded browse, 20 models).

## S96.2 protocol fix + honesty badge (user-tested same day)

The user's dashboard sessions (`Can you read the documents…`,
ep11-q4) recorded `partial` with **0 tool calls**: the dashboard
was the only consumer of the NATIVE tool path, while every
verdict runs the TEXTUAL shim — ep11 emitted a JSON-shaped text
blob that parsed to zero calls, and with no verifier the loop
accepted it as final. Fix: `default_provider_factory` builds
ollama sessions with `native_tools=False` (gemini stays native —
its proven path). UI: UNVERIFIED badge + hint on verifier-less
completions, plus a verify-command input plumbed end to end.
Live re-run of the exact goal: 25 tool calls (list/reads/tests),
document read — fix proven; session ran to max-iters on the
vague goal (open-ended goals thrash without a verifier — noted,
not this slice). Suite 1707 OK. `qa drip` 429s confirmed as
spent free-tier quota (working as designed, no change).
