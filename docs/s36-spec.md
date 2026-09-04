# S36 — Git Intelligence: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S36. Builds on S31–S35. One slice, purely additive, stdlib only.

## Overview

Source-control awareness: before and after work, the agent answers
"What changed? What was already changed? What did I change? What remains?"
Four read tools over real `git` invocations, paths resolved through the
S33 boundary, every failure a structured `ToolResult`.

**Scope ruling (roadmap-letter):** only the four read tools ship in S36.
`git_add` / `git_commit` / write verbs are "later, policy-gated" — they
would be autonomous mutations, and confirmation enforcement does not exist
until S38. Deferring them is the honest reading of "no autonomous commits
without policy controls".

## Module layout

```text
qacompanion/agent/git_tools.py     # GitToolkit + parsers
tests/test_agent_git_tools.py
```

## Execution model

- Git runs as **argv lists** (`["git", "--no-pager", "status", ...]`) —
  no shell, no injection surface; cwd = workspace root; 30 s timeout;
  UTF-8 with `errors="replace"`.
- Missing git binary → `GitError("git is not available")`; "not a git
  repository" stderr → clean `GitError` (not a raw fatal trace).
- Path arguments (`git_diff`) resolve through `PathPolicy` first and are
  passed to git as workspace-relative posix paths — escapes are structured
  errors.
- `GitError(ToolOperationError)` → clean structured messages via the S34
  registry seam.

## The four tools (GitToolkit)

All: category "git", READ_ONLY, requires_workspace=True, timeout 30 s.

- **git_status** `{}` — `status --porcelain=v1 -b --no-color` parsed into
  `{branch, detached, clean, ahead, behind, entries: [{status, path,
  orig_path?}]}`. Handles: untracked (`??`), renames (`old -> new` →
  `orig_path`), C-quoted paths (non-ASCII/core.quotePath) unquoted,
  `## HEAD (no branch)` → detached, `[ahead N, behind M]` upstream info
  (null when no upstream).
- **git_diff** `{path?, staged?}` — raw unified diff (`--no-color`,
  `--cached` when staged, path-scoped after policy resolution). Raw text
  output (the model reads diffs); empty diff → empty output; capped at
  64 KB with a `[diff truncated]` marker.
- **git_log** `{max_count?, path?}` — `log --pretty=format:%H%x1f%h%x1f%an%x1f%aI%x1f%s`
  (\x1f separators — author names can contain `|`) into
  `{entries: [{hash, short, author, date, subject}]}`, newest first,
  max_count default 10 cap 50. A repository with no commits yet is a
  structured error carrying git's message.
- **git_branch** `{}` — `{current, detached, branches}` via
  `branch --show-current` + `branch --format=%(refname:short)`.

`agent_registry()` grows to 19 tools (3 knowledge + 7 filesystem +
5 execution + 4 git).

## Testing strategy (tests/test_agent_git_tools.py)

Real temporary repositories (repo precedent: S14 repocheck real-git e2e;
fixtures commit with inline `-c user.name/user.email -c commit.gpgsign=false`
for hermeticity):

- status: clean repo (branch name, clean=true); modified tracked file;
  untracked file; rename via `git mv` (orig_path); non-ASCII filename
  unquoting; detached HEAD (current null, detached true).
- porcelain parser units: ahead/behind (each, both, none), no-upstream,
  detached, quoted paths, rename lines.
- diff: unstaged modification shows -/+ lines; staged via `--cached`;
  path scoping; empty when clean; escape path → structured error.
- log: two commits newest-first, fields present, max_count, path filter,
  empty-repository structured error.
- branch: current + created branch listed.
- non-repo directory → "not a git repository" structured error; git
  binary missing (patched subprocess) → "not available".
- Boundary: path arguments resolve through PathPolicy (../escape denied).
- Registration: four tools; agent_registry = 19.

Expected suite growth: 1039 → ~1080 OK.

## Exit criteria (from ROADMAP-agentlite.md §S36)

Temporary git repository: status/diff parsing, branch detection,
clean/dirty detection, changed-file tracking, clean failure handling;
write verbs remain policy-gated (deferred to S38). Full suite green;
preflight clean.
