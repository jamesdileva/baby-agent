# S33 — Workspace Abstraction: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S33. Builds on S31/S32 (`qacompanion/agent/`). One slice, purely additive,
no CLI changes, stdlib only.

## Overview

A formal, enforced concept of "the project": every future filesystem and
terminal action resolves through a boundary that cannot be escaped by
traversal, absolute paths, symlinks, or excluded/protected locations. S33
delivers the boundary and project metadata detection; the filesystem tools
that consume it land in S34.

## Module layout

```text
qacompanion/agent/workspace.py     # everything in this sprint
tests/test_agent_workspace.py
```

## Security core: PathPolicy

Resolve-then-contain, with independent layers so no single check is
load-bearing alone:

```text
1. null byte / pathological input     -> PathError
2. strict ".." ban                    -> any ".." segment is rejected outright
                                         (legitimate relative paths never need it)
3. resolve()                          -> symlinks followed, so escapes surface
4. containment                        -> resolved path must sit inside the root
                                         OR one configured allowed_path
                                         (normcase prefix check — case-insensitive
                                         on Windows)
5. exclusion                          -> relative path must not fall inside an
                                         excluded entry (prefix match, files allowed)
6. protected locations                -> defense in depth: resolved path must not
                                         sit under a protected system prefix
```

Empty / "." resolves to the root itself (legitimate: list the root).
Existence is deliberately NOT checked here — missing files are S34's
structured errors; the policy is about boundary, not existence.

Protected prefixes (normcased, boundary-checked so `C:\WindowsStuff` is not
`C:\Windows`): Windows — `C:\Windows`, `C:\Program Files`,
`C:\Program Files (x86)`, `C:\ProgramData`; POSIX — `/etc`, `/boot`,
`/proc`, `/sys`, `/dev`, `/System`. Extensible list, documented.

Exceptions: `WorkspaceError` base; `PathError(WorkspaceError)` for
path-rule violations.

## Workspace

```text
Workspace(root, config=None)
    root              resolved Path; must exist and be a directory
    config            WorkspaceConfig(excluded_paths=(".git",), allowed_paths=())
    policy            PathPolicy built from the config
    git_root          nearest ancestor (self-inclusive) containing .git, or None
    metadata          ProjectMetadata.detect(root)
    current_directory property (starts at root; set_cwd validates containment)
    resolve(path) -> Path        delegates to policy
    relative(path) -> str        posix-normalized relative form
```

Roots inside protected locations are rejected at construction.
`allowed_paths` are additional absolute directories treated as extra
containment roots (also protected-checked).

## ProjectMetadata

One cheap non-recursive scan of the root listing:

```text
languages        python (pyproject/setup/requirements), javascript (package.json),
                 typescript (tsconfig.json), rust (Cargo.toml), go (go.mod)
package_managers pip / poetry / uv / pipenv / npm / pnpm / yarn / bun / cargo / go
                 — claimed only from explicit marker files (lockfiles), never guessed
entrypoints      well-known files at root or src/: main.py, app.py, manage.py,
                 wsgi.py, index.js, index.ts, main.ts, server.js, main.go, src/main.rs
project_type     first match by priority python > node > rust > go, else "unknown"
```

## WorkspaceManager

`open(root, config=None) -> Workspace` (creates, caches by normcased root —
case-variant reopens return the same instance on Windows, sets active),
`get(root)` (cached lookup only, `WorkspaceError` if absent),
`active` property.

## Registry integration

S32's `execute(..., workspace=...)` gate treats the workspace as opaque;
S33 proves the fit: a `requires_workspace=True` tool executes once a
`Workspace` is passed (covered by test — no registry changes).

## Scope notes (deliberate)

- No file operations here (S34); no command execution (S35).
- Cancellation/permissions untouched; `set_cwd` checks containment only —
  existence is checked when the cwd is consumed.
- Symlink tests skip honestly (`skipTest`) when the OS denies symlink
  creation (Windows without Developer Mode/admin); Windows-specific cases
  are `skipUnless(os.name == "nt")` so the suite stays portable.

## Testing strategy (tests/test_agent_workspace.py)

- Containment: relative/nested/absolute-inside pass and return resolved
  absolutes; `..` anywhere rejected; absolute escape and cross-drive escape
  (Windows-guarded) rejected; empty/"." resolve to root; NUL byte rejected.
- Symlink escape into an outside temp dir rejected (privilege-skip).
- Exclusions: direct, nested, file-level; sibling non-excluded passes;
  default `.git` exclusion works.
- Windows: case-insensitive root matching; backslash relative paths;
  protected `C:\Windows` root and `C:\Windows\System32` resolves rejected
  (nt-guarded); protected-prefix boundary (`C:\WindowsStuff`) allowed as a
  plain workspace name.
- Workspace: nonexistent/file root rejected; git_root found at root and at
  an ancestor, None when absent; set_cwd containment.
- ProjectMetadata: python/node/rust/go detection, managers from lockfiles
  only, entrypoints, mixed project, empty dir → unknown.
- WorkspaceManager: caching (incl. case-variant on nt), get-unknown, active.
- Registry: `requires_workspace` tool passes the S32 gate with a Workspace.

Expected suite growth: 932 → ~980 OK.

## Exit criteria (from ROADMAP-agentlite.md §S33)

- Valid access resolves correctly (relative, absolute-in-root, allowed
  paths).
- Parent traversal, absolute escape, symlink escape, excluded-directory
  access, and protected locations are all rejected with `PathError`.
- Windows-specific pathological cases covered (case, backslashes, drives,
  protected prefixes).
- Git root / project metadata detected; manager caches correctly.
- S32 gate integrates; full suite green; preflight clean.
