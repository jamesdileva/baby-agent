"""S34 filesystem tools: the agent's hands inside the workspace boundary.

Seven registry tools — list_directory, read_file, write_file, edit_file,
search_code, file_exists, file_metadata — every one resolving through the
S33 PathPolicy (the policy is the traversal filter). All failures are
structured: handlers raise ToolOperationError, which the S32 registry maps
to a clean ToolResult error.

Pins (fixtures-first discipline):
- outputs are compact JSON strings; paths are posix-relative;
- writes are atomic (temp + os.replace), BOM-less UTF-8, no-clobber by
  default; every mutation lands in the ChangeLedger with sha256s;
- read_file strips BOM (utf-8-sig, repo lore) while edit_file reads utf-8
  strict so a file's BOM survives byte-exact outside the edited region;
- search walks candidates through policy.resolve, so boundary + exclusions
  apply for free; binaries, generated extensions, and >1 MB files skipped;
- no deletion/move/copy in S34 — destructive verbs wait for S38 permissions.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .registry import RegisteredTool, ToolDefinition, ToolOperationError, ToolRegistry
from .registry import READ_ONLY, SAFE_WRITE
from .workspace import PathError, Workspace

MAX_READ_BYTES = 256 * 1024
MAX_LIST_ENTRIES = 500
MAX_SEARCH_RESULTS = 100
SEARCH_MAX_FILE_BYTES = 1024 * 1024
BINARY_SNIFF_BYTES = 8192

BINARY_EXTENSIONS = frozenset({
    ".pyc", ".pyo", ".class", ".o", ".so", ".dll", ".exe", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz",
    ".tar", ".7z", ".rar", ".woff", ".woff2", ".ttf", ".db", ".sqlite",
})


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_binary_file(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return b"\x00" in fh.read(BINARY_SNIFF_BYTES)
    except OSError:
        return True


def _utc_stamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


@dataclass
class ChangeLedger:
    """Ordered record of every mutation made through the toolkit."""

    entries: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.entries is None:
            self.entries = []

    def record(self, kind: str, path_rel: str, before: Optional[str], after: str):
        self.entries.append({
            "kind": kind,
            "path": path_rel,
            "sha256_before": before,
            "sha256_after": after,
            "timestamp": _utc_stamp(datetime.now(timezone.utc).timestamp()),
        })

    def paths(self) -> List[str]:
        return [entry["path"] for entry in self.entries]


class FilesystemToolkit:
    """Binds the seven fs tools to one workspace (and one ledger)."""

    def __init__(self, workspace: Workspace, change_ledger: Optional[ChangeLedger] = None):
        self.workspace = workspace
        self.ledger = change_ledger or ChangeLedger()

    # --- helpers ---------------------------------------------------------

    def _rel(self, path: Path) -> str:
        try:
            return self.workspace.relative(path)
        except PathError:
            return str(path)

    def _resolve(self, path) -> Path:
        try:
            return self.workspace.resolve(path)
        except PathError as exc:
            raise ToolOperationError(str(exc)) from exc

    @staticmethod
    def _json(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False)

    # --- tool handlers ---------------------------------------------------

    def list_directory(self, path: str = ".") -> str:
        target = self._resolve(path)
        if not target.is_dir():
            raise ToolOperationError(f"not a directory: {self._rel(target)}")
        entries = []
        try:
            scan = list(os.scandir(target))
        except OSError as exc:
            raise ToolOperationError(f"cannot list {self._rel(target)}: {exc}") from exc
        for entry in scan:
            try:
                info = entry.stat()
                entries.append({
                    "name": entry.name,
                    "type": "dir" if entry.is_dir() else "file",
                    "size": 0 if entry.is_dir() else info.st_size,
                })
            except OSError:
                entries.append({"name": entry.name, "type": "file", "size": 0})
        entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
        truncated = len(entries) > MAX_LIST_ENTRIES
        return self._json({
            "path": self._rel(target),
            "entries": entries[:MAX_LIST_ENTRIES],
            "truncated": truncated,
        })

    def read_file(self, path: str, start_line: int = 1, max_lines: int = 2000) -> str:
        target = self._resolve(path)
        if not target.exists():
            raise ToolOperationError(f"file not found: {self._rel(target)}")
        if target.is_dir():
            raise ToolOperationError(f"is a directory: {self._rel(target)}")
        size = target.stat().st_size
        if size > MAX_READ_BYTES:
            raise ToolOperationError(
                f"file too large to read: {self._rel(target)} "
                f"({size} bytes > {MAX_READ_BYTES}); read a narrower path"
            )
        if _is_binary_file(target):
            raise ToolOperationError(f"binary file: {self._rel(target)}")
        try:
            text = target.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ToolOperationError(
                f"not valid UTF-8: {self._rel(target)} ({exc})"
            ) from exc
        # keepends: output is byte-faithful (trailing newlines preserved),
        # so edit_file old_string matching can trust exactly what was read
        lines = text.splitlines(keepends=True)
        start_index = max(int(start_line), 1) - 1
        window = lines[start_index:start_index + max(int(max_lines), 1)]
        return "".join(window)

    def write_file(self, path: str, content: str, overwrite: bool = False) -> str:
        target = self._resolve(path)
        existed = target.exists()
        if existed and not overwrite:
            raise ToolOperationError(
                f"refusing to overwrite existing file "
                f"(pass overwrite=true): {self._rel(target)}"
            )
        sha_before = _sha256_file(target) if existed else None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".tmp-write")
            tmp.write_text(content, encoding="utf-8", newline="")
            os.replace(tmp, target)
        except OSError as exc:
            raise ToolOperationError(
                f"write failed: {self._rel(target)} ({exc})"
            ) from exc
        sha_after = _sha256_file(target)
        self.ledger.record("write", self._rel(target), sha_before, sha_after)
        return self._json({
            "path": self._rel(target),
            "bytes": len(content.encode("utf-8")),
            "sha256": sha_after,
            "created": not existed,
        })

    def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        target = self._resolve(path)
        if not target.exists() or target.is_dir():
            raise ToolOperationError(f"file not found: {self._rel(target)}")
        if _is_binary_file(target):
            raise ToolOperationError(f"binary file: {self._rel(target)}")
        if old_string == new_string:
            raise ToolOperationError("edit is a no-op: old_string == new_string")
        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ToolOperationError(
                f"not valid UTF-8: {self._rel(target)} ({exc})"
            ) from exc
        count = text.count(old_string)
        if count == 0:
            raise ToolOperationError(
                f"old_string not found in {self._rel(target)}"
            )
        if count > 1:
            raise ToolOperationError(
                f"old_string matches {count} times in "
                f"{self._rel(target)} — add surrounding context"
            )
        sha_before = _sha256_file(target)
        updated = text.replace(old_string, new_string, 1)
        try:
            tmp = target.with_name(target.name + ".tmp-edit")
            tmp.write_text(updated, encoding="utf-8", newline="")
            os.replace(tmp, target)
        except OSError as exc:
            raise ToolOperationError(
                f"edit failed: {self._rel(target)} ({exc})"
            ) from exc
        sha_after = _sha256_file(target)
        self.ledger.record("edit", self._rel(target), sha_before, sha_after)
        return self._json({
            "path": self._rel(target),
            "bytes": len(updated.encode("utf-8")),
            "sha256": sha_after,
        })

    def search_code(self, query: str, path: str = ".",
                    max_results: int = MAX_SEARCH_RESULTS,
                    case_sensitive: bool = False) -> str:
        if not query:
            raise ToolOperationError("empty query")
        base = self._resolve(path)
        if not base.is_dir():
            raise ToolOperationError(f"not a directory: {self._rel(base)}")
        limit = min(int(max_results), MAX_SEARCH_RESULTS)
        needle = query if case_sensitive else query.lower()
        matches: List[Dict[str, Any]] = []
        truncated = False
        for current, dirs, files in os.walk(base):
            kept_dirs = []
            for d in dirs:
                candidate = os.path.join(current, d)
                try:
                    self.workspace.resolve(candidate)
                    kept_dirs.append(d)
                except PathError:
                    pass  # excluded or otherwise outside the boundary
            dirs[:] = kept_dirs
            for name in files:
                if Path(name).suffix.lower() in BINARY_EXTENSIONS:
                    continue
                full = os.path.join(current, name)
                try:
                    self.workspace.resolve(full)
                except PathError:
                    continue
                if Path(full).stat().st_size > SEARCH_MAX_FILE_BYTES:
                    continue
                if _is_binary_file(Path(full)):
                    continue
                try:
                    text = Path(full).read_text(encoding="utf-8-sig")
                except (UnicodeDecodeError, OSError):
                    continue
                for line_number, line in enumerate(text.splitlines(), start=1):
                    hay = line if case_sensitive else line.lower()
                    if needle in hay:
                        if len(matches) >= limit:
                            truncated = True
                            break
                        matches.append({
                            "path": self._rel(Path(full)),
                            "line_number": line_number,
                            "line": line.strip()[:200],
                        })
                if truncated:
                    break
            if truncated:
                break
        return self._json({
            "query": query,
            "matches": matches,
            "truncated": truncated,
        })

    def file_exists(self, path: str) -> str:
        target = self._resolve(path)
        exists = target.exists()
        return self._json({
            "path": self._rel(target),
            "exists": exists,
            "type": ("dir" if target.is_dir() else "file") if exists else None,
        })

    def file_metadata(self, path: str) -> str:
        target = self._resolve(path)
        exists = target.exists()
        payload: Dict[str, Any] = {
            "path": self._rel(target),
            "exists": exists,
            "type": ("dir" if target.is_dir() else "file") if exists else None,
        }
        if exists and target.is_file():
            info = target.stat()
            payload["size"] = info.st_size
            payload["modified"] = _utc_stamp(info.st_mtime)
            if info.st_size <= MAX_READ_BYTES and not _is_binary_file(target):
                payload["sha256"] = _sha256_file(target)
        return self._json(payload)

    # --- registration ------------------------------------------------------

    def tools(self) -> List[RegisteredTool]:
        def _tool(name, description, schema, handler, side_effect):
            return RegisteredTool(
                definition=ToolDefinition(
                    name=name, description=description, parameters_schema=schema
                ),
                handler=handler,
                category="filesystem",
                side_effect_level=side_effect,
                requires_workspace=True,
            )

        def _str_arg(required, optional):
            props = {name: {"type": "string"} for name in (required + optional)}
            props.update({
                name: {"type": "integer"} for name in ("start_line", "max_lines")
                if name in optional
            })
            props.update({
                name: {"type": "boolean"} for name in ("overwrite", "case_sensitive")
                if name in optional
            })
            if "max_results" in optional:
                props["max_results"] = {"type": "integer"}
            return {
                "type": "object",
                "properties": props,
                "required": required,
            }

        return [
            _tool(
                "list_directory", "List a directory inside the workspace.",
                _str_arg([], ["path"]), self.list_directory, READ_ONLY,
            ),
            _tool(
                "read_file", "Read a UTF-8 text file (BOM stripped).",
                _str_arg(["path"], ["start_line", "max_lines"]),
                self.read_file, READ_ONLY,
            ),
            _tool(
                "write_file", "Create or overwrite a file atomically.",
                _str_arg(["path", "content"], ["overwrite"]),
                self.write_file, SAFE_WRITE,
            ),
            _tool(
                "edit_file", "Replace a unique old_string with new_string.",
                _str_arg(["path", "old_string", "new_string"], []),
                self.edit_file, SAFE_WRITE,
            ),
            _tool(
                "search_code", "Substring search across workspace files.",
                _str_arg(["query"], ["path", "max_results", "case_sensitive"]),
                self.search_code, READ_ONLY,
            ),
            _tool(
                "file_exists", "Check whether a path exists.",
                _str_arg(["path"], []), self.file_exists, READ_ONLY,
            ),
            _tool(
                "file_metadata", "Size, hash, mtime, and type of a path.",
                _str_arg(["path"], []), self.file_metadata, READ_ONLY,
            ),
        ]


def agent_registry(
    workspace: Workspace,
    cases_path=None,
    digest_path=None,
    ledger=None,
    change_ledger: Optional[ChangeLedger] = None,
) -> ToolRegistry:
    """Registry preloaded with knowledge + filesystem + execution tools."""
    from .execution import ExecutionToolkit
    from .registry import default_knowledge_registry

    registry = default_knowledge_registry(
        cases_path=cases_path, digest_path=digest_path, ledger=ledger
    )
    toolkit = FilesystemToolkit(workspace, change_ledger=change_ledger)
    for tool in toolkit.tools():
        registry.register(tool)
    for tool in ExecutionToolkit(workspace).tools():
        registry.register(tool)
    return registry
