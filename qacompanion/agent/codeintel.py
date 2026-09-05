"""S46 static code intelligence: where is it defined, who calls it, what
imports it — without reading whole files into context.

Precision is labeled, never faked. Python is parsed with the real stdlib
AST (definitions with qualified method names, precise ast.Name/Attribute
references, imports, syntax-error diagnostics). JavaScript/TypeScript use
a lightweight regex scanner (heuristic, labeled). Any other text file
falls back to common definition keywords (labeled). The index caches
parsed files by (path, mtime, size) — queries re-walk cheaply and
re-parse only what changed, so it stays correct while the agent edits.

Pins (fixtures-first discipline):
- the walk goes through PathPolicy — excluded dirs and binaries never
  enter the index (caps: 2000 files, 512 KB each);
- every failure is a structured CodeIntelError (ToolOperationError);
- diagnostics only claim what they checked: parse errors, nothing more.
"""

import ast
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .fs_tools import BINARY_EXTENSIONS
from .registry import READ_ONLY, RegisteredTool, ToolDefinition, ToolOperationError, ToolRegistry
from .workspace import PathError, Workspace

MAX_INDEX_FILES = 2000
MAX_PARSE_BYTES = 512 * 1024
MAX_RESULTS_DEFAULT = 25

PYTHON_EXTS = (".py",)
JS_EXTS = (".js", ".jsx", ".ts", ".tsx", ".mjs")
SKIP_SUFFIXES = BINARY_EXTENSIONS | {".json", ".md", ".txt", ".log",
                                     ".csv", ".yaml", ".yml", ".toml",
                                     ".cfg", ".ini", ".lock"}

JS_DEF_PATTERNS = [
    (re.compile(r"^\s*export\s+default\s+function\s+(\w+)"), "function"),
    (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"), "function"),
    (re.compile(r"^\s*(?:export\s+)?class\s+(\w+)"), "class"),
    (re.compile(r"^\s*(?:export\s+)?const\s+(\w+)\s*="), "variable"),
    (re.compile(r"^\s*(?:export\s+)?let\s+(\w+)\s*="), "variable"),
    (re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)"), "interface"),
    (re.compile(r"^\s*(?:export\s+)?type\s+(\w+)\s*="), "type"),
]
JS_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?from\s+|require\(\s*)['"]([^'"]+)['"]""")
FALLBACK_DEF_RE = re.compile(
    r"^\s*(?:pub\s+)?(?:def|function|class|interface|struct|func|fn)\s+(\w+)")
WORD_RE = re.compile(r"\w+")


class CodeIntelError(ToolOperationError):
    """Structured code-intelligence failure."""


@dataclass
class Symbol:
    name: str
    kind: str
    file: str          # posix-relative to the workspace
    line: int
    language: str

    def to_dict(self):
        return {"name": self.name, "kind": self.kind, "file": self.file,
                "line": self.line, "language": self.language}


@dataclass
class Reference:
    name: str
    file: str
    line: int
    language: str
    precise: bool
    is_definition: bool = False

    def to_dict(self):
        return {"name": self.name, "file": self.file, "line": self.line,
                "language": self.language, "precise": self.precise,
                "is_definition": self.is_definition}


@dataclass
class FileEntry:
    file: str
    language: str
    precise: bool
    definitions: List[Symbol] = field(default_factory=list)
    references: List[Reference] = field(default_factory=list)
    imports: List[Dict[str, Any]] = field(default_factory=list)
    diagnostic: Optional[str] = None  # parse failure reason


def language_for(path: Path) -> Optional[str]:
    suffix = path.suffix.lower()
    if suffix in PYTHON_EXTS:
        return "python"
    if suffix in JS_EXTS:
        return "javascript"
    if suffix in SKIP_SUFFIXES or suffix in BINARY_EXTENSIONS:
        return None
    return "text-fallback"


def _parse_python(rel: str, source: str) -> FileEntry:
    entry = FileEntry(file=rel, language="python", precise=True)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        entry.diagnostic = f"syntax error line {exc.lineno}: {exc.msg}"
        return entry

    def visit(node, class_name=None, in_function=False):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{class_name}.{child.name}" if class_name else child.name
                kind = "method" if class_name else "function"
                entry.definitions.append(
                    Symbol(name=name, kind=kind, file=rel,
                           line=child.lineno, language="python"))
                visit(child, class_name=class_name, in_function=True)
            elif isinstance(child, ast.ClassDef):
                entry.definitions.append(
                    Symbol(name=child.name, kind="class", file=rel,
                           line=child.lineno, language="python"))
                visit(child, class_name=child.name, in_function=in_function)
            elif isinstance(child, (ast.Assign, ast.AnnAssign)):
                # module-level variables only (spec); the value subtree is
                # still walked for references either way
                if class_name is None and not in_function:
                    targets = child.targets if isinstance(child, ast.Assign) \
                        else [child.target]
                    for target in targets:
                        if isinstance(target, ast.Name):
                            entry.definitions.append(
                                Symbol(name=target.id, kind="variable",
                                       file=rel, line=child.lineno,
                                       language="python"))
                visit(child, class_name=class_name, in_function=in_function)
            elif isinstance(child, ast.Import):
                for alias in child.names:
                    entry.imports.append({
                        "module": alias.name,
                        "names": [alias.asname or alias.name],
                    })
            elif isinstance(child, ast.ImportFrom):
                module = child.module or ""
                entry.imports.append({
                    "module": module,
                    "names": [alias.name for alias in child.names],
                })
            elif isinstance(child, (ast.Name, ast.Attribute)):
                name = child.attr if isinstance(child, ast.Attribute) \
                    else child.id
                entry.references.append(
                    Reference(name=name, file=rel, line=child.lineno,
                              language="python", precise=True))
            else:
                visit(child, class_name=class_name, in_function=in_function)

    visit(tree)
    # Definition-site flagging: match (name, line) against collected
    # definitions. Honest AST reality: a function's own name is a plain
    # string, not a Name node — so functions get no self-reference at the
    # def line; only variables (whose targets ARE Name nodes) can appear
    # at their definition site.
    def_sites = {(d.name.split(".")[-1], d.line) for d in entry.definitions}
    for reference in entry.references:
        reference.is_definition = (reference.name, reference.line) in def_sites
    return entry


def _parse_javascript(rel: str, source: str) -> FileEntry:
    entry = FileEntry(file=rel, language="javascript", precise=False)
    for line_number, line in enumerate(source.splitlines(), start=1):
        for pattern, kind in JS_DEF_PATTERNS:
            match = pattern.match(line)
            if match:
                entry.definitions.append(
                    Symbol(name=match.group(1), kind=kind, file=rel,
                           line=line_number, language="javascript"))
                entry.references.append(
                    Reference(name=match.group(1), file=rel,
                              line=line_number, language="javascript",
                              precise=False, is_definition=True))
                break
        for match in JS_IMPORT_RE.finditer(line):
            entry.imports.append({"module": match.group(1), "names": []})
        for token in WORD_RE.findall(line):
            entry.references.append(
                Reference(name=token, file=rel, line=line_number,
                          language="javascript", precise=False))
    return entry


def _parse_fallback(rel: str, source: str) -> FileEntry:
    entry = FileEntry(file=rel, language="text-fallback", precise=False)
    for line_number, line in enumerate(source.splitlines(), start=1):
        match = FALLBACK_DEF_RE.match(line)
        if match:
            entry.definitions.append(
                Symbol(name=match.group(1), kind="definition", file=rel,
                       line=line_number, language="text-fallback"))
            entry.references.append(
                Reference(name=match.group(1), file=rel, line=line_number,
                          language="text-fallback", precise=False,
                          is_definition=True))
        for token in WORD_RE.findall(line):
            entry.references.append(
                Reference(name=token, file=rel, line=line_number,
                          language="text-fallback", precise=False))
    return entry


_PARSERS = {"python": _parse_python, "javascript": _parse_javascript}


class CodeIndex:
    """Workspace-scoped, mtime-fresh index of definitions/references/imports."""

    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self._cache: Dict[str, Tuple[float, int, FileEntry]] = {}

    def scan(self, max_files: int = MAX_INDEX_FILES) -> Dict[str, Any]:
        """Walk + parse (only changed files re-parse). Returns scan stats."""
        root = self.workspace.root
        scanned = errors = 0
        seen = set()
        for current, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs
                       if self._indexable(os.path.join(current, d))]
            for name in files:
                path = Path(current) / name
                language = language_for(path)
                if language is None:
                    continue
                try:
                    resolved = self.workspace.resolve(path)
                except PathError:
                    continue  # excluded or escaped: not indexable
                rel = self.workspace.relative(resolved)
                seen.add(rel)
                if len(seen) > max_files:
                    raise CodeIntelError(
                        f"workspace exceeds the {max_files}-file index cap")
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if stat.st_size > MAX_PARSE_BYTES:
                    continue
                cached = self._cache.get(rel)
                if cached and cached[0] == stat.st_mtime \
                        and cached[1] == stat.st_size:
                    scanned += 1
                    continue
                try:
                    source = path.read_text(encoding="utf-8-sig")
                except (UnicodeDecodeError, OSError):
                    continue
                parser = _PARSERS.get(language, _parse_fallback)
                entry = parser(rel, source)
                self._cache[rel] = (stat.st_mtime, stat.st_size, entry)
                scanned += 1
        # drop files that vanished
        for gone in set(self._cache) - seen:
            del self._cache[gone]
        for entry in self._cache.values():
            if entry[2].diagnostic:
                errors += 1
        return {"scanned": scanned, "indexed": len(self._cache),
                "parse_errors": errors}

    def _indexable(self, dir_path: str) -> bool:
        try:
            self.workspace.resolve(dir_path)
            return True
        except PathError:
            return False

    def entries(self) -> List[FileEntry]:
        return [cached[2] for cached in self._cache.values()]

    def definitions(self, query: Optional[str] = None, exact: bool = False,
                    kind: Optional[str] = None,
                    language: Optional[str] = None) -> List[Symbol]:
        found = []
        for entry in self.entries():
            for symbol in entry.definitions:
                if exact:
                    if symbol.name != query:
                        continue
                elif query and query.lower() not in symbol.name.lower():
                    continue
                if kind and symbol.kind != kind:
                    continue
                if language and symbol.language != language:
                    continue
                found.append(symbol)
        found.sort(key=lambda s: (s.name, s.file, s.line))
        return found

    def references(self, name: str) -> List[Reference]:
        found = []
        for entry in self.entries():
            for reference in entry.references:
                if reference.name == name:
                    found.append(reference)
        found.sort(key=lambda r: (r.file, r.line))
        return found

    def importers(self, module: str) -> List[Dict[str, Any]]:
        found = []
        for entry in self.entries():
            for imported in entry.imports:
                target = imported["module"]
                if target == module or target.endswith("." + module) \
                        or target.startswith(module + "."):
                    found.append({"file": entry.file, "module": target,
                                  "names": imported["names"],
                                  "language": entry.language})
        return found

    def diagnostics(self) -> List[Dict[str, Any]]:
        return [{"file": entry.file, "error": entry.diagnostic}
                for entry in self.entries() if entry.diagnostic]


class CodeIntelToolkit:
    """Binds the five code-intelligence tools to one workspace."""

    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self.index = CodeIndex(workspace)

    def code_symbols(self, query: str = "", exact: bool = False,
                     kind: Optional[str] = None,
                     language: Optional[str] = None,
                     max_results: int = MAX_RESULTS_DEFAULT) -> str:
        self.index.scan()
        found = self.index.definitions(
            query=query, exact=exact, kind=kind, language=language)
        return json.dumps({
            "query": query, "count": len(found),
            "symbols": [s.to_dict() for s in found[:max_results]],
        }, ensure_ascii=False)

    def code_references(self, name: str,
                        max_results: int = MAX_RESULTS_DEFAULT) -> str:
        self.index.scan()
        found = self.index.references(name)
        return json.dumps({
            "name": name, "count": len(found),
            "references": [r.to_dict() for r in found[:max_results]],
        }, ensure_ascii=False)

    def code_imports(self, path: str) -> str:
        self.index.scan()
        try:
            rel = self.workspace.relative(self.workspace.resolve(path))
        except PathError as exc:
            raise CodeIntelError(str(exc)) from exc
        for entry in self.index.entries():
            if entry.file == rel:
                return json.dumps({
                    "file": rel, "language": entry.language,
                    "imports": entry.imports,
                }, ensure_ascii=False)
        raise CodeIntelError(f"file not indexed: {rel}")

    def code_importers(self, module: str,
                       max_results: int = MAX_RESULTS_DEFAULT) -> str:
        self.index.scan()
        found = self.index.importers(module)
        return json.dumps({
            "module": module, "count": len(found),
            "importers": found[:max_results],
        }, ensure_ascii=False)

    def code_diagnostics(self) -> str:
        stats = self.index.scan()
        return json.dumps({
            "scan": stats,
            "problems": self.index.diagnostics(),
        }, ensure_ascii=False)

    def tools(self) -> List[RegisteredTool]:
        def _tool(name, description, schema, handler):
            return RegisteredTool(
                definition=ToolDefinition(
                    name=name, description=description,
                    parameters_schema=schema),
                handler=handler,
                category="code",
                side_effect_level=READ_ONLY,
                requires_workspace=True,
            )

        return [
            _tool("code_symbols", "Search code definitions (functions, "
                  "classes, methods, variables) by name.",
                  {"type": "object",
                   "properties": {
                       "query": {"type": "string"},
                       "exact": {"type": "boolean"},
                       "kind": {"type": "string"},
                       "language": {"type": "string"},
                       "max_results": {"type": "integer"}},
                   "required": []},
                  self.code_symbols),
            _tool("code_references", "Find every reference to a symbol "
                  "name, with file and line.",
                  {"type": "object",
                   "properties": {"name": {"type": "string"},
                                  "max_results": {"type": "integer"}},
                   "required": ["name"]},
                  self.code_references),
            _tool("code_imports", "List what a file imports.",
                  {"type": "object",
                   "properties": {"path": {"type": "string"}},
                   "required": ["path"]},
                  self.code_imports),
            _tool("code_importers", "Find the files that import a module.",
                  {"type": "object",
                   "properties": {"module": {"type": "string"},
                                  "max_results": {"type": "integer"}},
                   "required": ["module"]},
                  self.code_importers),
            _tool("code_diagnostics", "Scan stats and files that fail to "
                  "parse.",
                  {"type": "object", "properties": {}, "required": []},
                  self.code_diagnostics),
        ]


def update_agent_registry(registry: ToolRegistry, workspace: Workspace) -> None:
    """Register the code-intelligence tools into an existing registry."""
    for tool in CodeIntelToolkit(workspace).tools():
        registry.register(tool)
