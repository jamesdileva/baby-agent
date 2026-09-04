"""S36 git intelligence: source-control awareness inside the boundary.

Four read tools — git_status, git_diff, git_log, git_branch — over real
git invocations. Git runs as argv lists (no shell, no injection surface)
with the workspace root as cwd; path arguments resolve through PathPolicy
before reaching git. Write verbs (git_add/git_commit) are deliberately
deferred to S38, when confirmation enforcement exists — no autonomous
commits without policy controls.

Pins (fixtures-first discipline):
- --no-pager always; 30 s timeout; UTF-8 with errors="replace";
- missing git binary and non-repo directories are clean structured
  GitErrors (never raw fatal traces);
- porcelain v1 parsing: renames (orig_path), C-quoted paths unquoted,
  detached HEAD, [ahead N, behind M] upstream info (null when absent);
- git_log uses \\x1f field separators (author names can contain "|").
"""

import json
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from .registry import READ_ONLY, SAFE_WRITE, RegisteredTool, ToolDefinition, ToolOperationError, ToolRegistry
from .workspace import PathError, Workspace

GIT_TIMEOUT_SECONDS = 30.0
MAX_DIFF_BYTES = 64 * 1024
MAX_LOG_ENTRIES = 50

_FIELD_SEP = "\x1f"
_AHEAD_BEHIND_RE = re.compile(r"\[ahead (\d+)(?:, behind (\d+))?\]|(?:\[behind (\d+)\])")


class GitError(ToolOperationError):
    """Operational git failure (missing binary, non-repo, git-level error)."""


def _run_git(workspace: Workspace, *args: str) -> Tuple[int, str, str]:
    """Run git in the workspace root. Returns (rc, stdout, stderr)."""
    cmd = ["git", "--no-pager", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workspace.root),
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise GitError("git is not available") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git timed out after {GIT_TIMEOUT_SECONDS}s") from exc
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _require_repo(workspace: Workspace) -> None:
    rc, _, stderr = _run_git(workspace, "rev-parse", "--is-inside-work-tree")
    if rc != 0:
        message = stderr.strip().splitlines()[0] if stderr.strip() else "not a git repository"
        raise GitError(message)


def _unquote_path(path: str) -> str:
    """Undo git's C-style path quoting (core.quotePath).

    Git emits non-ASCII as octal UTF-8 bytes (\\303\\257); unicode_escape
    decodes those as Latin-1 codepoints, so recover the real bytes with a
    Latin-1 re-encode before decoding UTF-8.
    """
    if path.startswith('"') and path.endswith('"') and len(path) >= 2:
        body = path[1:-1]
        try:
            decoded = body.encode("ascii", "backslashreplace").decode(
                "unicode_escape"
            )
            return decoded.encode("latin-1").decode("utf-8", errors="replace")
        except (UnicodeDecodeError, UnicodeEncodeError):
            return body
    return path


def parse_branch_line(line: str) -> Dict[str, Any]:
    """Parse the '## ' header of porcelain -b output."""
    header = line[3:].strip()
    info: Dict[str, Any] = {
        "branch": None, "detached": False, "ahead": None, "behind": None,
    }
    if header.startswith("HEAD (no branch)") or header == "HEAD (no branch)":
        info["detached"] = True
        return info
    branch = header.split("...", 1)[0].split("[", 1)[0].strip()
    info["branch"] = branch or None
    match = _AHEAD_BEHIND_RE.search(header)
    if match:
        if match.group(3) is not None:
            info["behind"] = int(match.group(3))
        else:
            info["ahead"] = int(match.group(1))
            if match.group(2) is not None:
                info["behind"] = int(match.group(2))
    return info


def parse_status(raw: str) -> Dict[str, Any]:
    """Parse porcelain v1 -b output into the structured status payload."""
    lines = raw.splitlines()
    result: Dict[str, Any] = {
        "branch": None, "detached": False, "ahead": None, "behind": None,
        "clean": True, "entries": [],
    }
    entries: List[Dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        if line.startswith("## "):
            result.update(parse_branch_line(line))
            continue
        if len(line) < 4:
            continue
        status = line[:2]
        rest = line[3:]
        orig_path = None
        if " -> " in rest:
            orig, new = rest.split(" -> ", 1)
            orig_path = _unquote_path(orig)
            path = _unquote_path(new)
        else:
            path = _unquote_path(rest)
        entry: Dict[str, Any] = {"status": status, "path": path}
        if orig_path is not None:
            entry["orig_path"] = orig_path
        entries.append(entry)
    result["entries"] = entries
    result["clean"] = not entries
    return result


def parse_log(raw: str) -> List[Dict[str, Any]]:
    entries = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        fields = line.split(_FIELD_SEP)
        if len(fields) != 5:
            continue
        entries.append({
            "hash": fields[0],
            "short": fields[1],
            "author": fields[2],
            "date": fields[3],
            "subject": fields[4],
        })
    return entries


class GitToolkit:
    """Binds the four git read tools to one workspace."""

    def __init__(self, workspace: Workspace):
        self.workspace = workspace

    def git_status(self) -> str:
        _require_repo(self.workspace)
        rc, stdout, stderr = _run_git(self.workspace, "status", "--porcelain=v1", "-b")
        if rc != 0:
            raise GitError(f"git status failed: {stderr.strip()}")
        return json.dumps(parse_status(stdout), ensure_ascii=False)

    def git_diff(self, path: Optional[str] = None, staged: bool = False) -> str:
        _require_repo(self.workspace)
        args = ["diff", "--no-color"]
        if staged:
            args.append("--cached")
        if path is not None:
            try:
                resolved = self.workspace.resolve(path)
            except PathError as exc:
                raise GitError(str(exc)) from exc
            args.extend(["--", self.workspace.relative(resolved)])
        rc, stdout, stderr = _run_git(self.workspace, *args)
        if rc != 0:
            raise GitError(f"git diff failed: {stderr.strip()}")
        encoded = stdout.encode("utf-8", errors="replace")
        if len(encoded) > MAX_DIFF_BYTES:
            return encoded[:MAX_DIFF_BYTES].decode("utf-8", errors="ignore") + \
                "\n[diff truncated]"
        return stdout

    def git_log(self, max_count: int = 10, path: Optional[str] = None) -> str:
        _require_repo(self.workspace)
        limit = min(int(max_count), MAX_LOG_ENTRIES)
        args = [
            "log", f"--max-count={limit}",
            "--pretty=format:%H%x1f%h%x1f%an%x1f%aI%x1f%s",
        ]
        if path is not None:
            try:
                resolved = self.workspace.resolve(path)
            except PathError as exc:
                raise GitError(str(exc)) from exc
            args.extend(["--", self.workspace.relative(resolved)])
        rc, stdout, stderr = _run_git(self.workspace, *args)
        if rc != 0:
            raise GitError(f"git log failed: {stderr.strip()}")
        return json.dumps({"entries": parse_log(stdout)}, ensure_ascii=False)

    def git_branch(self) -> str:
        _require_repo(self.workspace)
        rc, current_raw, _ = _run_git(self.workspace, "branch", "--show-current")
        if rc != 0:
            raise GitError("git branch failed")
        rc, list_raw, stderr = _run_git(
            self.workspace, "branch", "--format=%(refname:short)"
        )
        if rc != 0:
            raise GitError(f"git branch failed: {stderr.strip()}")
        branches = [line.strip() for line in list_raw.splitlines() if line.strip()]
        current = current_raw.strip() or None
        return json.dumps({
            "current": current,
            "detached": current is None,
            "branches": branches,
        }, ensure_ascii=False)

    def git_add(self, path: str = ".") -> str:
        _require_repo(self.workspace)
        try:
            resolved = self.workspace.resolve(path)
        except PathError as exc:
            raise GitError(str(exc)) from exc
        rel = self.workspace.relative(resolved)
        rc, _, stderr = _run_git(self.workspace, "add", "--", rel)
        if rc != 0:
            raise GitError(f"git add failed: {stderr.strip()}")
        return json.dumps({"staged": rel}, ensure_ascii=False)

    def git_commit(self, message: str) -> str:
        _require_repo(self.workspace)
        if not isinstance(message, str) or not message.strip():
            raise GitError("commit message must be a non-empty string")
        rc, stdout, stderr = _run_git(self.workspace, "commit", "-m", message)
        if rc != 0:
            # git prints "nothing to commit" on STDOUT, not stderr
            combined = ((stdout or "") + (stderr or "")).lower()
            if "nothing to commit" in combined or \
                    "nothing added to commit" in combined:
                return json.dumps({
                    "committed": False,
                    "reason": "nothing to commit",
                }, ensure_ascii=False)
            raise GitError(f"git commit failed: {(stderr or stdout).strip()}")
        rc, hash_raw, _ = _run_git(self.workspace, "rev-parse", "HEAD")
        commit_hash = hash_raw.strip() if rc == 0 else None
        rc, branch_raw, _ = _run_git(self.workspace, "branch", "--show-current")
        branch = branch_raw.strip() or None
        return json.dumps({
            "committed": True,
            "hash": commit_hash,
            "branch": branch,
            "message": message,
        }, ensure_ascii=False)

    def tools(self) -> List[RegisteredTool]:
        def _tool(name, description, schema, handler,
                  side_effect=READ_ONLY, requires_confirmation=False):
            return RegisteredTool(
                definition=ToolDefinition(
                    name=name, description=description, parameters_schema=schema
                ),
                handler=handler,
                category="git",
                side_effect_level=side_effect,
                requires_workspace=True,
                requires_confirmation=requires_confirmation,
            )

        return [
            _tool("git_status", "Working-tree status: branch, clean/dirty, entries.",
                  {"type": "object", "properties": {}, "required": []},
                  self.git_status),
            _tool("git_diff", "Unified diff (optionally staged or path-scoped).",
                  {
                      "type": "object",
                      "properties": {
                          "path": {"type": "string"},
                          "staged": {"type": "boolean"},
                      },
                      "required": [],
                  },
                  self.git_diff),
            _tool("git_log", "Recent commits, newest first.",
                  {
                      "type": "object",
                      "properties": {
                          "path": {"type": "string"},
                          "max_count": {"type": "integer"},
                      },
                      "required": [],
                  },
                  self.git_log),
            _tool("git_branch", "Current branch and branch list.",
                  {"type": "object", "properties": {}, "required": []},
                  self.git_branch),
            # S38: write verbs unlocked (were deferred in S36 pending
            # confirmation enforcement). Staging is reversible -> SAFE_WRITE;
            # commits are the S36 posture's canonical ASK action.
            _tool("git_add", "Stage a file (or the whole tree) for commit.",
                  {
                      "type": "object",
                      "properties": {"path": {"type": "string"}},
                      "required": [],
                  },
                  self.git_add, side_effect=SAFE_WRITE),
            _tool("git_commit", "Create a commit with a message (requires confirmation).",
                  {
                      "type": "object",
                      "properties": {"message": {"type": "string"}},
                      "required": ["message"],
                  },
                  self.git_commit, side_effect=SAFE_WRITE,
                  requires_confirmation=True),
        ]


def update_agent_registry(registry: ToolRegistry, workspace: Workspace) -> None:
    """Register the git tools into an existing registry."""
    for tool in GitToolkit(workspace).tools():
        registry.register(tool)
