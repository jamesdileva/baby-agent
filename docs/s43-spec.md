# S43 — URL Context & Retrieval: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S43. Builds on S31–S42. One slice, stdlib only, no CLI changes.

## Overview

Search results become actionable knowledge: after `web_search` finds a
page, the agent can fetch it, read the relevant section, and (rarely)
pull an artifact into the workspace. Fetching arbitrary URLs from a
model is the most dangerous surface so far — the URL safety policy is
the sprint's core, not an afterthought.

## Module layout

```text
qacompanion/agent/webfetch.py      # URL policy + fetch/extract/download tools
tests/test_agent_webfetch.py
```

## URL safety policy (checked BEFORE any request)

```text
1. scheme            http/https only
2. port              80/443 or implicit
3. host resolution   socket.getaddrinfo; EVERY resolved IP must be public
                     (loopback, private RFC1918, link-local 169.254/fe80,
                     unspecified, and IPv6 equivalents rejected — blocks
                     localhost, LAN, and cloud-metadata endpoints)
4. documented residual risk: DNS-rebinding between check and fetch
                     (full mitigation = custom connection handling; out of
                     scope, recorded honestly)
```

Violations → structured `WebFetchError` naming the rule. Both fetch tools
are **EXTERNAL** side effects (S38 default posture: ASK).

## Fetch mechanics

stdlib urllib, 15 s timeout, size cap 2 MB (truncated flag), User-Agent
identifies Baby-Agent. Content-type gate for page tools: text/*,
application/json, application/xml, +html — binary content rejected with a
hint toward download_artifact. HTML → text via a stdlib html.parser
subclass (script/style skipped, whitespace collapsed); redirects followed
with final_url reported.

## The three tools

- **open_url** `{url}` — `{url, final_url, status, content_type, title,
  text (≤20k chars, truncated), links (≤50 absolute)}`.
- **extract_page** `{url, query}` — fetch + return the lines/paragraphs
  matching the query terms with a little surrounding context — the
  "find the relevant section" step of research.
- **download_artifact** `{url, path}` — binary-capable (≤10 MB), written
  ATOMICALLY into the workspace through PathPolicy (path is
  workspace-relative; escape = structured error); returns {path, bytes,
  sha256, content_type}. Recorded in the ChangeLedger tradition via the
  returned hash.

All three: category "research", EXTERNAL, requires_workspace only for
download_artifact. `agent_registry()` grows to 27 tools.

## Testing strategy (tests/test_agent_webfetch.py)

ALL hermetic — urllib is always mocked with canned responses:
- URL policy: scheme/port rejections; mocked getaddrinfo resolving to
  loopback / RFC1918 / link-local / metadata IP each rejected; public IP
  passes.
- Fetch: HTML extraction (title, script/style stripped, whitespace
  collapsed); size-cap truncation flag; binary content-type rejection;
  HTTP error → structured error.
- extract_page: matching lines returned, non-matching page → empty with
  hint.
- download_artifact: bytes written into the workspace (sha256 verified),
  escape path rejected, oversized rejected.
- Registration metadata + through-registry runs with confirmer (EXTERNAL
  posture); agent_registry includes the three tools; exact count 27.

Expected suite growth: 1179 → ~1200 OK.

## Exit criteria (from ROADMAP-agentlite.md §S43)

Agent can search, open the official documentation, extract the relevant
section, and use it to make an implementation decision — proven hermetically;
every fetch passes the URL safety policy; nothing escapes the workspace.
Full suite green; preflight clean.
