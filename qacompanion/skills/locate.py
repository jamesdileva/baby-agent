"""S12 locate skill: repo and project finder (workplace literacy).

Born from the recurring question "where does the taskline repo live
on disk?". `qa locate QUERY [--root DIR]...` walks the common project
roots (user projects dirs, home; overridable via repeatable --root),
detects git repositories (any directory holding a .git entry, file or
dir), and matches a repo when:

- the query is a case-insensitive fragment of the repo directory
  name, or
- the query looks like a commit hash (>= MIN_HASH hex chars) and is a
  prefix of one of the COMMIT_SCAN most recent commits' hashes.

Pins (fixtures-first discipline, golden-report pattern per S10/S11):
search depth is LOCATE_DEPTH levels below each root; a detected repo
is never descended into; dot-directories are matched but not entered;
duplicate roots collapse to one search; a git query failing on an
otherwise-detected repo skips that repo as unreadable instead of
aborting (permission-error grace per ROADMAP). The report renders one
line per match - absolute path, branch, clean/dirty - then an honest
summary line counting roots searched, repos scanned and matches found.
Exit contract PROPOSED as a spec amendment (same class as preflight,
docs/DECISIONS.md): 0 at least one match, 1 no match or bad input
(missing explicit --root), 2 environment error (git executable
unusable) - rendered as ONE honest error line, never a traceback
(case#4 class).

Read-only: directory walks plus three read-only git queries per
touched repo. Units inject fake subprocess doubles for hermeticity;
real-git coverage lives in the temp-repo e2e pair (tmp dirs only,
case#9 hygiene rider).
"""

import os
import subprocess
from pathlib import Path

LOCATE_DEPTH = 3
COMMIT_SCAN = 20
MIN_HASH = 7

_GIT_ENTRY = ".git"
_HEX = set("0123456789abcdef")


class LocateEnvError(EnvironmentError):
    """Environment failure: the search cannot even run (case#4 class)."""


def default_roots():
    """Ordered, de-duplicated common project roots under home."""
    home = Path.home()
    candidates = [
        home / "Projects",
        home / "projects",
        home / "repos",
        home / "src",
        home / "dev",
        home / "code",
        home / "work",
        home / "Documents",
        home / "Desktop",
        home,
    ]
    seen = set()
    ordered = []
    for cand in candidates:
        key = str(cand).lower()
        if key not in seen:
            seen.add(key)
            ordered.append(cand)
    return ordered


def _children(directory):
    """Sorted subdirectories; unreadable directories yield nothing."""
    try:
        entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
    except OSError:
        return []
    dirs = []
    for entry in entries:
        try:
            if entry.is_dir():
                dirs.append(Path(entry.path))
        except OSError:
            continue
    return dirs


def _is_repo(candidate):
    try:
        return (candidate / _GIT_ENTRY).exists()
    except OSError:
        return False


def iter_repo_dirs(roots):
    """Yield every git repository found at/below each root, in order.

    Depth-limited DFS: a detected repo is emitted and never descended
    into; dot-directories are matched as candidates but never entered;
    unreadable directories are skipped silently (graceful degradation).
    """
    for root in roots:
        if _is_repo(root):
            yield root
            continue
        try:
            top_level = _children(root)
        except OSError:
            continue
        stack = [(child, 1) for child in reversed(top_level)]
        while stack:
            current, level = stack.pop()
            if _is_repo(current):
                yield current
                continue
            if current.name.startswith(".") or level >= LOCATE_DEPTH:
                continue
            try:
                below = _children(current)
            except OSError:
                continue
            stack.extend((child, level + 1) for child in reversed(below))


def _git(repo_dir, *argv):
    """Read-only git query; missing git binary aborts the search."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_dir), *argv],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise LocateEnvError(f"environment: git executable unusable ({exc})") from exc
    return proc.returncode, proc.stdout.strip()


def is_hash_query(query):
    lowered = query.lower()
    return len(lowered) >= MIN_HASH and set(lowered) <= _HEX


def matches_query(query, repo_dir):
    """Name-fragment match, else commit-hash prefix scan.

    Returns True/False; None means the repo is unreadable at git level
    (plumbing refused) and should be skipped, never reported.
    """
    lowered = query.lower()
    if lowered in repo_dir.name.lower():
        return True
    if not is_hash_query(lowered):
        return False
    code, out = _git(repo_dir, "rev-list", "--max-count", str(COMMIT_SCAN), "HEAD")
    if code != 0:
        return None
    return any(line.startswith(lowered) for line in out.split())


def describe(repo_dir):
    """One report row: absolute path, branch, clean/dirty state.

    None means the repo is unreadable at git level (broken HEAD).
    """
    code, branch = _git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD")
    if code != 0:
        return None
    _, porcelain = _git(repo_dir, "status", "--porcelain")
    state = "dirty" if porcelain else "clean"
    return f"{repo_dir.resolve()}  branch={branch} {state}"


def search(query, roots):
    """Walk roots, collect matching repos; graceful on unreadable ones."""
    results = {
        "roots_searched": 0,
        "repos_scanned": 0,
        "repos_skipped": 0,
        "matches": [],
    }
    seen_roots = set()
    seen_repos = set()
    for root in roots:
        root_key = str(Path(root).resolve()).lower()
        if root_key in seen_roots:
            continue
        seen_roots.add(root_key)
        results["roots_searched"] += 1
        for repo_dir in iter_repo_dirs([root]):
            key = str(repo_dir.resolve()).lower()
            if key in seen_repos:
                continue
            seen_repos.add(key)
            results["repos_scanned"] += 1
            hit = matches_query(query, repo_dir)
            if hit is None:
                results["repos_skipped"] += 1
                continue
            if not hit:
                continue
            row = describe(repo_dir)
            if row is None:
                results["repos_skipped"] += 1
                continue
            results["matches"].append(row)
    return results


def render(results, query):
    """Golden two-section report: match rows, then honest summary."""
    lines = [f"locate '{query}':"]
    lines.extend(results["matches"])
    lines.append(
        f"searched {results['roots_searched']} root(s), "
        f"scanned {results['repos_scanned']} repo(s), "
        f"skipped {results['repos_skipped']}, "
        f"found {len(results['matches'])} match(es)"
    )
    return "\n".join(lines)
