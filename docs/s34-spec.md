# S34 — Filesystem Tools: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S34. Builds on S31–S33. One slice, purely additive, no CLI changes,
stdlib only.

## Overview

The seven workspace filesystem tools — the agent's ability to inspect and
modify projects. Every operation resolves through the S33 `PathPolicy`
(the policy IS the traversal filter), every failure is a structured
`ToolResult`, every mutation is atomic and ledger-tracked.

## Module layout

```text
qacompanion/agent/fs_tools.py       # tools + FilesystemToolkit + ChangeLedger
qacompanion/agent/registry.py       # + ToolOperationError seam (below)
tests/test_agent_fs_tools.py
```

## Registry amendment (additive)

`registry.ToolOperationError(Exception)`: an *expected* tool failure.
`_execute_handler` maps it to a clean structured error (`str(exc)`) instead
of the generic `"handler failed: <repr>"` reserved for unexpected
exceptions. Backward compatible; S32 suite unchanged.

## Toolkit binding

Handlers receive only validated arguments (S32 contract), so the workspace
is bound at the factory:

```text
FilesystemToolkit(workspace, change_ledger=None)
    .ledger      ChangeLedger — records every mutation:
                 (kind, path_rel, sha256_before, sha256_after, timestamp)
    .tools()     -> list[RegisteredTool]  (register into any ToolRegistry)
agent_registry(workspace, cases_path=None, digest_path=None, ledger=None)
    -> ToolRegistry preloaded with knowledge tools + filesystem tools
```

All seven tools are `requires_workspace=True` (S32 gate proven in S33),
category "filesystem", timeout 30s. Reads are READ_ONLY; write/edit are
SAFE_WRITE (in-boundary; deletion is not offered in S34). Outputs are
compact JSON strings; paths in outputs/ledger are posix-relative.

## The seven tools

- **list_directory** `{path?}` — dirs-first sorted entries
  `{name, type, size}`; caps at MAX_LIST_ENTRIES (500) with a truncated
  flag. Missing dir → structured error.
- **read_file** `{path, start_line?, max_lines?}` — UTF-8 with BOM stripped
  (repo lore: utf-8-sig); 1-based line windowing. Guards: binary sniff
  (NUL in first 8 KB), oversize (> MAX_READ_BYTES = 256 KB → error naming
  the size), invalid UTF-8 → structured error. Output: raw file content
  (window applied) — token-efficient for the model; metadata comes from
  file_metadata.
- **write_file** `{path, content, overwrite?}` — default NO-CLOBBER
  (existing target → error unless `overwrite: true`); parents auto-created;
  **atomic** (temp file + os.replace); writes BOM-less UTF-8; ledger entry;
  returns `{path, bytes, sha256, created}`.
- **edit_file** `{path, old_string, new_string}` — exact-match replace,
  `old_string` must appear EXACTLY once (0 → "not found", ≥2 → "matches N
  times — add context"), old==new rejected as a no-op. Read (utf-8 strict,
  BOM preserved in content) → modify → atomic write → ledger. Returns
  `{path, bytes, sha256}`.
- **search_code** `{query, path?, max_results?, case_sensitive?}` —
  substring search (case-insensitive default) walked through
  `policy.resolve` per candidate, so boundary + exclusions (`.git`,
  configured) apply as the traversal filter. Skips binaries (NUL sniff),
  generated/compiled extensions (`.pyc .pyo .class .o .so .dll .exe` and
  common binary/media/archive extensions), files > 1 MB. Caps at
  MAX_SEARCH_RESULTS (100) → `{matches: [{path, line_number, line}],
  truncated}`.
- **file_exists** `{path}` — `{path, exists, type}` (file/dir); never an
  error for a missing path.
- **file_metadata** `{path}` — `{path, exists, type, size, sha256, modified}`;
  missing path → `{exists: false}` (a valid answer); sha256 only for files
  within the read cap.

Read/list/search on a missing path are structured errors containing the
relative path; metadata/existence on a missing path are honest negatives.

## Scope notes (deliberate)

- No deletion/move/copy in S34 (deletion is DESTRUCTIVE — lands with the
  S38 permission work).
- Line-range editing is not offered; the unique-match edit primitive is
  the safe core. Revisit if real use demands it.
- `read_file` strips BOM (model-facing cleanliness); `edit_file` reads
  utf-8 strict so a file's BOM is preserved byte-exact outside the edited
  region — the asymmetry is deliberate and documented.
- Changed-file tracking is the toolkit ledger (session plumbing is S37/S50).

## Testing strategy (tests/test_agent_fs_tools.py)

- Registration: seven tools, categories/levels, requires_workspace flags;
  agent_registry = 3 knowledge + 7 filesystem.
- End-to-end happy path via registry.execute with a Workspace: list → read
  → create → edit → search → inspect (the roadmap verification sequence).
- read_file: content round-trip, BOM stripped, line windowing, oversize,
  binary, invalid UTF-8, missing.
- write_file: create with auto-parents, no-clobber default, overwrite flag,
  atomicity (no temp leftovers), correct sha256, ledger entries.
- edit_file: unique replace, not-found, ambiguous, no-op, ledger.
- search_code: matches, case-insensitivity, exclusion respect, binary /
  extension skips, cap, subdir filter, no-match.
- file_exists / file_metadata: positives, honest negatives, dir typing.
- Boundary: `../` escape, absolute escape, and excluded-path access all
  come back as structured ToolResult errors — never escape the workspace.
- Registry: ToolOperationError maps to clean message; unexpected exception
  keeps the "handler failed" prefix.
- ChangeLedger: entries + paths().

Expected suite growth: 979 → ~1035 OK.

## Exit criteria (from ROADMAP-agentlite.md §S34)

- A fake agent can list → read → create → edit → search → inspect inside a
  test workspace through the registry, with useful structured errors.
- Nothing escapes the workspace: traversal, absolute, symlink (S33 layer),
  and excluded paths are all enforced under the registry pipeline.
- Writes are atomic and hashed; every mutation is ledger-tracked.
- Full suite green; preflight clean.
