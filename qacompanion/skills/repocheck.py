"""S14 repocheck skill: multi-repo health report (workplace literacy).

Born from the recurring question "can I push these to GitHub eventually?"
and the 26-unpushed-commits incident. `qa repocheck [DIR]` scans a parent
directory's git repos and reports per repo: dirty files, commits ahead of
upstream, missing remotes. One glance = which projects need attention.

Pins (fixtures-first discipline):
- depth is 3 levels below the scan root (shared with locate);
  a detected repo is never descended into;
- dot-directories are matched as candidates but never entered;
- a repo whose git plumbing refuses queries is skipped as unreadable
  and counted, never fatal;
- an unreadable entry (permission denied) is skipped silently;
- the report renders one line per repo — absolute path, branch,
  dirty/clean, ahead count, behind count, missing remotes — then
  an honest summary line counting repos scanned, skipped, and needing
  attention.

Exit contract PROPOSED as a spec amendment (docs/DECISIONS.md):
0 all repos clean / caught-up, 1 issues found, 2 environment error
(git executable unusable / not a directory / missing -- directory).
"""

import os
import subprocess
from pathlib import Path

_REPO_DEPTH = 3
_GIT_ENTRY = ".git"


class RepocheckEnvError(EnvironmentError):
    """Environment failure: the scan cannot even run (case#4 class)."""


def _is_repo(candidate):
    try:
        return (candidate / _GIT_ENTRY).exists()
    except OSError:
        return False


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
            if current.name.startswith(".") or level >= _REPO_DEPTH:
                continue
            try:
                below = _children(current)
            except OSError:
                continue
            stack.extend((child, level + 1) for child in reversed(below))


def _git(repo_dir, *argv):
    """Read-only git query; missing git binary raises RepocheckEnvError."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_dir), *argv],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RepocheckEnvError(f"environment: git executable unusable ({exc})") from exc
    return proc.returncode, proc.stdout.strip()


def describe(repo_dir):
    """Build a status dict for one repo.

    Returns None when git plumbing refuses (unreadable repo) —
    counted and skipped, never fatal.
    """
    code, branch = _git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD")
    if code != 0:
        return None

    _, porcelain = _git(repo_dir, "status", "--porcelain")
    dirty = bool(porcelain)

    code_ahead, ahead_out = _git(repo_dir, "rev-list", "--count", f"origin/{branch}..HEAD")
    ahead = int(ahead_out) if code_ahead == 0 and ahead_out.isdigit() else 0

    code_behind, behind_out = _git(repo_dir, "rev-list", "--count", f"HEAD..origin/{branch}")
    behind = int(behind_out) if code_behind == 0 and behind_out.isdigit() else 0

    _, remote_out = _git(repo_dir, "remote")
    remotes = [r.strip() for r in remote_out.splitlines() if r.strip()]

    return {
        "path": str(repo_dir.resolve()),
        "branch": branch,
        "dirty": dirty,
        "ahead": ahead,
        "behind": behind,
        "missing_remotes": len(remotes) == 0,
    }


def scan(dirs):
    """Scan a list of directories for git repos and describe each.

    Returns a dict with counts and per-repo status lists.
    """
    results = {
        "repos_scanned": 0,
        "repos_skipped": 0,
        "repos_ok": [],
        "repos_dirty": [],
        "repos_ahead": [],
        "repos_missing_remote": [],
    }
    seen_repos = set()
    for directory in dirs:
        directory = Path(directory)
        if not directory.is_dir():
            continue
        for repo_dir in iter_repo_dirs([directory]):
            key = str(repo_dir.resolve()).lower()
            if key in seen_repos:
                continue
            seen_repos.add(key)
            results["repos_scanned"] += 1
            status = describe(repo_dir)
            if status is None:
                results["repos_skipped"] += 1
                continue
            has_issues = False
            if status["dirty"]:
                results["repos_dirty"].append(status)
                has_issues = True
            if status["ahead"] > 0:
                results["repos_ahead"].append(status)
                has_issues = True
            if status["missing_remotes"]:
                results["repos_missing_remote"].append(status)
                has_issues = True
            if not has_issues:
                results["repos_ok"].append(status)
    return results


def render(results, scan_dir):
    """Golden report: per-repo status lines, then honest summary."""
    lines = [f"repocheck {scan_dir}:"]
    issues = (
        results["repos_dirty"]
        + results["repos_ahead"]
        + results["repos_missing_remote"]
    )
    seen = set()
    for status in issues:
        key = status["path"]
        if key in seen:
            continue
        seen.add(key)
        parts = [key]
        parts.append("dirty" if status["dirty"] else "clean")
        if status["ahead"] > 0:
            parts.append(f"ahead={status['ahead']}")
        if status["behind"] > 0:
            parts.append(f"behind={status['behind']}")
        if status["missing_remotes"]:
            parts.append("no-remote")
        lines.append("  " + "  ".join(parts))
    lines.append(
        f"checked {results['repos_scanned']} repo(s), "
        f"skipped {results['repos_skipped']}, "
        f"{len(seen)} need(s) attention"
    )
    return "\n".join(lines)
