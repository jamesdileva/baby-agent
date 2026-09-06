# S53 — Browser Abstraction: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S53. Builds on S31–S52 + S55. One slice.

## Overview

A controlled browser interface for the agent's web applications and
documentation: launch app → open browser → navigate → interact →
screenshot → verify.

**Dependency discipline (same pattern as the Electron deferral and the
Gemini key):** the `BrowserProvider` abstraction and a hermetic
**FakeBrowserProvider** (in-memory page model) land fully tested; the
real **PlaywrightBrowserProvider** is implemented but import-gated —
it activates with `pip install playwright && playwright install
chromium` and raises a structured error naming the fix until then. No
browser binaries download as a side effect of this slice.

## Module layout

```text
qacompanion/agent/browser.py     # BrowserProvider ABC + adapters + tools
tests/test_agent_browser.py
```

## BrowserProvider interface

```text
open(url)                -> {url, title, text_len}      # navigate
back()                   -> {url}
click(selector)          -> {clicked, selector}
type(selector, text)     -> {typed}
scroll(amount)           -> {scrolled}
select(selector, value)  -> {selected}
screenshot()             -> png bytes                    # real pixels
extract()                -> {url, title, text}
```

- **FakeBrowserProvider**: an in-memory page model — register pages
  (url → title, text, elements with selectors/values), navigate between
  them with history, interact by selector. Screenshots render real PNG
  bytes via the S44 codec (deterministic color per page — compare_images
  can verify them). Fully hermetic; the demo/test path.
- **PlaywrightBrowserProvider**: sync Playwright behind an
  import guard; methods map 1:1 (goto, click, fill, go_back, screenshot
  → PNG bytes, content → text via the S43 HTML extractor). Missing
  install → structured BrowserError naming the two commands.

All provider failures are structured `BrowserError(ToolOperationError)`.

## The eight tools (category "browser", all EXTERNAL — default ASK)

```text
browser_open        {url}                       navigate + summary
browser_back        {}                          history back
browser_click       {selector}                  click an element
browser_type        {selector, text}            fill/type into a field
browser_scroll      {amount}                    scroll the page
browser_select      {selector, value}           dropdown selection
browser_screenshot  {path}                      PNG into the workspace
browser_extract     {}                          page title + text
```

`browser_download` from the roadmap is covered by
`webfetch.download_artifact` (S43) — documented deviation, no
duplicate. `browser_screenshot` is the only workspace-writing tool
(requires_workspace=True); all are EXTERNAL so the S38 engine gates
them behind ASK by default — localhost dev servers are whitelisted via
policy, exactly like every other network-touching tool.

`agent_registry()` grows to 59 tools; the benchmark's lean catalog is
unchanged (the benchmark doesn't browse).

## Testing strategy (tests/test_agent_browser.py)

- Fake provider: page registration, navigation + history, click/type/
  select by selector, extract, screenshot PNG round-trip
  (decode_png works), unregistered URL structured error.
- Playwright adapter: import-guard tested BOTH ways — mocked-absent
  import → structured error naming the fix; mocked-present module →
  method mapping verified with a fake page object (no browser).
- Tools: side-effect matrix (all EXTERNAL, screenshot requires
  workspace); through-registry runs with confirmer (ASK posture);
  escape-path rejection on screenshot.
- agent_registry membership (51 → 59); lean catalog unchanged.

Expected suite growth: 1363 → ~1385 OK.

## Exit criteria (from ROADMAP-agentlite.md §S53)

Small web app: launch (S45) → open browser → navigate → interact →
screenshot → verify — proven hermetically through the fake provider
end-to-end; the Playwright adapter mapped and import-gated. Full suite
green; preflight clean.
