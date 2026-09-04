"""S33 workspace abstraction: the enforced project boundary.

Every future filesystem/terminal action resolves through PathPolicy —
resolve-then-contain with independent layers (strict ".." ban, symlink-
following resolution, containment against root + allowed paths, exclusion
prefixes, protected system locations) so no single check is load-bearing
alone. ProjectMetadata detects languages / package managers / entrypoints
from one cheap non-recursive scan of the root listing.

Pins (fixtures-first discipline):
- PathPolicy.resolve never checks existence — boundary only (S34 owns
  structured missing-file errors);
- empty path / "." resolves to the root itself;
- any ".." segment is rejected outright — legitimate relative paths never
  need it, and the containment backstop catches symlink/absolute escapes;
- case-insensitive containment on Windows via os.path.normcase;
- protected-prefix matching is boundary-checked ("C:\\WindowsStuff" is not
  "C:\\Windows");
- Windows-specific test cases are skipUnless(os.name == "nt"); symlink
  tests skip honestly when the OS denies symlink creation.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .contracts import _require  # shared strictness helper (raises ValueError)


class WorkspaceError(Exception):
    """Workspace lifecycle failure (bad root, unknown in manager)."""


class PathError(WorkspaceError):
    """Path-rule violation: traversal, escape, exclusion, protected location."""


PROTECTED_PREFIXES = {
    "nt": (
        "c:\\windows",
        "c:\\program files",
        "c:\\program files (x86)",
        "c:\\programdata",
    ),
    "posix": ("/etc", "/boot", "/proc", "/sys", "/dev", "/system"),
}


def _norm(path) -> str:
    return os.path.normcase(str(path))


def _is_under(path: Path, root: Path) -> bool:
    p, r = _norm(path), _norm(root)
    return p == r or p.startswith(r + os.sep)


def _find_git_root(root: Path) -> Optional[Path]:
    for candidate in [root, *root.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


class PathPolicy:
    """The boundary check engine. Constructed with a resolved root."""

    def __init__(
        self,
        root,
        allowed_paths: Iterable = (),
        excluded_paths: Iterable = (),
    ):
        self.root = Path(root).resolve()
        self.allowed: Tuple[Path, ...] = tuple(Path(p).resolve() for p in allowed_paths)
        for candidate in [self.root, *self.allowed]:
            if self._is_protected(candidate):
                raise PathError(
                    f"workspace root inside protected system location: {candidate}"
                )
        self.excluded: Tuple[str, ...] = tuple(excluded_paths)

    def _is_protected(self, resolved: Path) -> bool:
        p = _norm(resolved)
        for prefix in PROTECTED_PREFIXES.get(os.name, ()):
            if p == prefix or p.startswith(prefix + os.sep):
                return True
        return False

    def resolve(self, path) -> Path:
        """Resolve a path against the boundary. Raises PathError on violation."""
        raw = str(path)
        if not raw or raw == ".":
            return self.root
        if "\x00" in raw:
            raise PathError("null byte in path")
        candidate = Path(raw)
        if ".." in candidate.parts:
            raise PathError("parent traversal ('..') rejected by policy")
        try:
            resolved = candidate.resolve() if candidate.is_absolute() else (
                self.root / candidate
            ).resolve()
        except OSError as exc:
            raise PathError(f"unresolvable path {raw!r}: {exc}") from exc
        matched = self.root
        for anchor in (self.root, *self.allowed):
            if _is_under(resolved, anchor):
                matched = anchor
                break
        else:
            raise PathError(f"path escapes the workspace boundary: {raw!r}")
        if self._is_protected(resolved):
            raise PathError(f"protected system location: {resolved}")
        rel = self._relative_string(resolved, matched)
        for exclusion in self.excluded:
            exc = str(exclusion).replace("\\", "/").strip("/")
            if rel == exc or rel.startswith(exc + "/"):
                raise PathError(f"path inside excluded location: {exclusion}")
        return resolved

    def _relative_string(self, resolved: Path, anchor: Path) -> str:
        p, m = _norm(resolved), _norm(anchor)
        if p == m:
            return "."
        rel = p[len(m):].lstrip("\\/").replace("\\", "/")
        return rel

    def relative(self, path) -> str:
        """Posix-normalized relative form of a resolved-inside path."""
        resolved = self.resolve(path)
        for anchor in (self.root, *self.allowed):
            if _is_under(resolved, anchor):
                return self._relative_string(resolved, anchor)
        raise PathError(f"path escapes the workspace boundary: {path!r}")  # pragma: no cover


@dataclass
class WorkspaceConfig:
    """Boundary configuration for a workspace."""

    excluded_paths: Tuple[str, ...] = (".git",)
    allowed_paths: Tuple[str, ...] = ()

    def __post_init__(self):
        _require(
            all(isinstance(e, str) and e.strip() for e in self.excluded_paths),
            "excluded_paths must be non-empty strings",
        )
        _require(
            all(isinstance(a, str) and a.strip() for a in self.allowed_paths),
            "allowed_paths must be non-empty strings",
        )

    def to_dict(self):
        return {
            "excluded_paths": list(self.excluded_paths),
            "allowed_paths": list(self.allowed_paths),
        }


@dataclass
class ProjectMetadata:
    """Detected project characteristics (root listing scan only)."""

    languages: Tuple[str, ...] = ()
    package_managers: Tuple[str, ...] = ()
    entrypoints: Tuple[str, ...] = ()
    project_type: str = "unknown"

    @classmethod
    def detect(cls, root) -> "ProjectMetadata":
        try:
            names = {entry.name for entry in Path(root).iterdir()}
        except OSError:
            names = set()

        languages: List[str] = []
        managers: List[str] = []
        if {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"} & names:
            languages.append("python")
        if "package.json" in names:
            languages.append("javascript")
        if "tsconfig.json" in names:
            languages.append("typescript")
        if "Cargo.toml" in names:
            languages.append("rust")
        if "go.mod" in names:
            languages.append("go")

        for marker, manager in (
            ("requirements.txt", "pip"),
            ("poetry.lock", "poetry"),
            ("uv.lock", "uv"),
            ("Pipfile", "pipenv"),
            ("package-lock.json", "npm"),
            ("pnpm-lock.yaml", "pnpm"),
            ("yarn.lock", "yarn"),
            ("bun.lockb", "bun"),
            ("Cargo.toml", "cargo"),
            ("go.mod", "go"),
        ):
            if marker in names:
                managers.append(manager)

        entrypoint_names = (
            "main.py", "app.py", "manage.py", "wsgi.py",
            "index.js", "index.ts", "main.ts", "server.js",
            "main.go", "main.rs",
        )
        entrypoints = []
        src_names = _src_names(root)
        for name in entrypoint_names:
            if name in names:
                entrypoints.append(name)
            elif f"src/{name}" in src_names:
                entrypoints.append(f"src/{name}")

        for lang, ptype in (
            ("python", "python"), ("javascript", "node"),
            ("rust", "rust"), ("go", "go"),
        ):
            if lang in languages:
                project_type = ptype
                break
        else:
            project_type = "unknown"

        return cls(
            languages=tuple(languages),
            package_managers=tuple(managers),
            entrypoints=tuple(entrypoints),
            project_type=project_type,
        )

    def to_dict(self):
        return {
            "languages": list(self.languages),
            "package_managers": list(self.package_managers),
            "entrypoints": list(self.entrypoints),
            "project_type": self.project_type,
        }


def _src_names(root) -> set:
    src = Path(root) / "src"
    try:
        return {f"src/{entry.name}" for entry in src.iterdir()}
    except OSError:
        return set()


class Workspace:
    """The project boundary: root, policy, git root, metadata, cwd."""

    def __init__(self, root, config: Optional[WorkspaceConfig] = None):
        resolved = Path(root).resolve()
        if not resolved.exists():
            raise WorkspaceError(f"workspace root does not exist: {resolved}")
        if not resolved.is_dir():
            raise WorkspaceError(f"workspace root is not a directory: {resolved}")
        self.root = resolved
        self.config = config or WorkspaceConfig()
        self.policy = PathPolicy(
            root=self.root,
            allowed_paths=self.config.allowed_paths,
            excluded_paths=self.config.excluded_paths,
        )
        self.git_root = _find_git_root(self.root)
        self.metadata = ProjectMetadata.detect(self.root)
        self._cwd = self.root

    @property
    def current_directory(self) -> Path:
        return self._cwd

    def set_cwd(self, path) -> Path:
        """Change the working directory (containment-checked; existence is
        checked when consumed, e.g. by S35 command execution)."""
        resolved = self.policy.resolve(path)
        self._cwd = resolved
        return resolved

    def resolve(self, path) -> Path:
        return self.policy.resolve(path)

    def relative(self, path) -> str:
        return self.policy.relative(path)

    def describe(self):
        return {
            "root": str(self.root),
            "git_root": str(self.git_root) if self.git_root else None,
            "current_directory": str(self._cwd),
            "config": self.config.to_dict(),
            "metadata": self.metadata.to_dict(),
        }


class WorkspaceManager:
    """Opens and caches workspaces; tracks the active one."""

    def __init__(self):
        self._cache = {}
        self._active: Optional[Workspace] = None

    def open(self, root, config: Optional[WorkspaceConfig] = None) -> Workspace:
        resolved = Path(root).resolve()
        key = _norm(resolved)
        if key not in self._cache:
            self._cache[key] = Workspace(resolved, config=config)
        self._active = self._cache[key]
        return self._active

    def get(self, root) -> Workspace:
        key = _norm(Path(root).resolve())
        if key not in self._cache:
            raise WorkspaceError(f"workspace not open: {root!r}")
        return self._cache[key]

    @property
    def active(self) -> Optional[Workspace]:
        return self._active
