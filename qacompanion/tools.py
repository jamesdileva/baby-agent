"""S27 research tools: callable tools for the brain layer.

Expose case-search, doc-grep, and journal-read as simple callable tools
the model may invoke before answering. Kept deliberately few and dumb —
tiny models are unreliable orchestrators.

Pins (fixtures-first discipline):
- tool call format: [TOOL: name(arg="value")] in model output text;
- three tools: case_search, doc_grep, journal_read;
- loop guard: MAX_TOOL_CALLS per ask() invocation (default 3);
- each tool returns a string (formatted results or error message);
- tools are stateless — paths passed per call, defaults from env/cwd.
"""

import re
from pathlib import Path

from . import lookup as lookup_mod
from . import ollama_bridge as bridge
from .skills import digest, journal

MAX_TOOL_CALLS = 3

TOOL_CALL_RE = re.compile(
    r'\[\s*TOOL:\s*(\w+)\s*\(\s*(?:query|pattern)\s*=\s*["\']([^"\']*)["\']\s*\)\s*\]',
    re.IGNORECASE,
)


def case_search(query, cases_path=None):
    """Search the case base by keyword. Returns formatted matches."""
    cases_path = Path(cases_path) if cases_path else Path(bridge.DEFAULT_CASES)
    cases = bridge._load_cases(cases_path)
    matched = bridge._match_cases(cases, query)
    if not matched:
        return "no matching case"
    return lookup_mod.format_matches(matched)


def doc_grep(query, digest_path=None):
    """Search digested documents by keyword. Returns formatted results."""
    results = digest.search(query, store_path=digest_path)
    return digest.format_results(results, query)


def journal_read(pattern, ledger=None):
    """Search the journal ledger by pattern. Returns formatted entries."""
    try:
        results = journal.grep(pattern, ledger=ledger)
    except journal.JournalError as exc:
        return f"error: {exc}"
    return journal.render_grep(results, pattern)


TOOLS = {
    "case_search": case_search,
    "doc_grep": doc_grep,
    "journal_read": journal_read,
}


def parse_tool_calls(text):
    """Extract tool call instructions from model output text.

    Returns list of (tool_name, query_string) tuples.
    """
    return TOOL_CALL_RE.findall(text)


def dispatch_tool(name, query, **kwargs):
    """Execute a named tool with the given query. Returns result string."""
    fn = TOOLS.get(name)
    if fn is None:
        return f"error: unknown tool '{name}'"
    try:
        return fn(query, **kwargs)
    except Exception as exc:
        return f"error: {name} failed: {exc}"
