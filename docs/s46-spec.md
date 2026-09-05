# S46 — Static Code Intelligence: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S46. Builds on S31–S45. One slice, stdlib only, no CLI changes.

## Overview

Answer "where is this defined / who calls it / what imports this" without
reading the whole repository. Honesty about precision is the design
pillar: every result says HOW it was derived.

## Module layout

```text
qacompanion/agent/codeintel.py    # CodeIndex + the five tools
tests/test_agent_codeintel.py
```

## Language tiers (precision labeled, never faked)

1. **Python — real AST** (stdlib `ast`):
   definitions: functions/async functions (kind `function`, `method` with
   qualified `Class.method` names), classes, module-level variables
   (`AnnAssign`/`Assign` with Name targets); references: every `ast.Name`
   id + `ast.Attribute` attr with file/line (precise); imports:
   `Import`/`ImportFrom` (module + names); parse failures become
   diagnostics (syntax errors), never crashes.
2. **JavaScript/TypeScript — lightweight regex scanner** (documented
   heuristic): definitions for `function name(`, `class name`,
   `const/let name =`, `interface name`, `type name =`; imports for
   `import ... from 'mod'` and `require('mod')`; references are
   word-boundary text matches (imprecise, labeled).
3. **Generic fallback** (any other text file): common definition keywords
   (`def`, `function`, `class`, `interface`, `struct`, `fn`) — labeled
   imprecise.

Language is picked by extension: .py → python; .js/.jsx/.ts/.tsx/.mjs →
javascript; everything else non-binary → text-fallback.

## CodeIndex

- Walks the workspace through `PathPolicy` (excluded dirs like `.git`
  never enter; binary/asset extensions skipped; caps: 2000 files, 512 KB
  per file).
- **Freshness**: parsed files cached by (path, mtime, size) — a query
  re-walks (cheap) and re-parses only what changed, so the index stays
  correct while the agent edits code.

## The five tools (all READ_ONLY, requires_workspace=True, category "code")

```text
code_symbols     {query, exact?, kind?, language?, max_results?}
                 definition search; exact=true is the "where is X defined"
                 lookup
code_references  {name, max_results?}     who references it (precise for
                                          python, word-boundary otherwise;
                                          definition sites flagged)
code_imports     {path}                   what this file imports
code_importers   {module, max_results?}   what imports this module (exact
                                          or dotted-suffix match)
code_diagnostics {}                       files that fail to parse + scan
                                          stats
```

LSP integration stays the documented future upgrade; the tool surface
above is stable against it.

## Testing strategy (tests/test_agent_codeintel.py)

Fixture: a multi-module Python project (functions, class with methods,
module variables, cross-module calls and imports), an intentionally
broken-syntax .py, a .js file, a .go file, and a junk binary.

- Python: exact/substring symbol search; qualified method names; variable
  definitions; references point at the calling file/line with the
  definition site flagged; imports extraction (module + names); importers
  find the caller via dotted-suffix match; diagnostics report the broken
  file without crashing the index.
- JS heuristic: function/import extraction; word-boundary references.
- Fallback: go func definition found, labeled text-fallback.
- Freshness: append a function to a fixture file → next query sees it.
- Policy: `.git` excluded; binary skipped; escape path rejected.
- Tools: registration (READ_ONLY, workspace-gated); through-registry
  runs; agent_registry membership; exact count 41 → 46.

Expected suite growth: 1238 → ~1265 OK.

## Exit criteria (from ROADMAP-agentlite.md §S46)

A multi-module project yields correct symbol and reference discovery
through registry tools, without reading whole files into context. Full
suite green; preflight clean.
