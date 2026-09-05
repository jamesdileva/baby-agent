"""S26/S27/S28 Ollama bridge: local model integration with retrieval + tools + escalation.

`qa ask "<question>"` retrieves relevant cases/doc-passages/skills, feeds
them as context to a local Ollama model, returns a grounded answer WITH
citations. Falls back to plain lookup when Ollama is absent.

The model may invoke research tools mid-answer by outputting tool calls
in the format [TOOL: tool_name(query="...")]. A loop guard prevents
infinite tool-calling (max 3 iterations by default).

S28 adds confidence detection: when the model's answer indicates low
confidence, the result includes a `confidence` dict with `confident: False`
and the matched markers, enabling the brain to escalate to a live agent.

Pins (fixtures-first discipline):
- Ollama endpoint is http://localhost:11434 by default (OLLAMA_URL env).
- Default model is qwen2.5-coder:1.5b (OLLAMA_MODEL env).
- Retrieval context: cases from cases.jsonl, digest entries from digest.jsonl.
- Context is formatted as a structured prompt with system instructions.
- Fallback: when Ollama unreachable, returns raw lookup results.
- generate endpoint: POST /api/generate, stream=false.
- All HTTP via stdlib urllib (no third-party deps, per spec).
- S27 tools: case_search, doc_grep, journal_read (see tools.py).
- Tool call format: [TOOL: name(query="value")] in model output.
- Loop guard: MAX_TOOL_CALLS=3 per ask() invocation.
- S28 confidence: detect_confidence() checks answer for uncertainty markers.
"""

import json
import os
import urllib.request
import urllib.error
from pathlib import Path

DEFAULT_MODEL = "qwen2.5-coder:1.5b"
DEFAULT_URL = "http://localhost:11434"


def _configured_timeout() -> float:
    """S55: per-request timeout, configurable via OLLAMA_TIMEOUT — CPU
    inference on bigger models legitimately exceeds 60s per generation.
    Call-time resolution (no reload hazards)."""
    return float(os.environ.get("OLLAMA_TIMEOUT", "60"))
DEFAULT_CASES = "cases.jsonl"
DEFAULT_DIGEST = "digest.jsonl"

MAX_CONTEXT_CHARS = 6000
DEFAULT_MAX_CASES = 10
DEFAULT_MAX_DIGEST = 10


class OllamaError(Exception):
    """Operational failure: Ollama unreachable, model error, or bad response."""


def _http_post(url, data, timeout=None):
    """POST JSON to url, return parsed response. Raises OllamaError on failure.
    timeout=None falls back to OLLAMA_TIMEOUT (default 60s)."""
    if timeout is None:
        timeout = _configured_timeout()
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise OllamaError(f"Ollama request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise OllamaError(f"Ollama returned invalid JSON: {exc}") from exc
    except OSError as exc:
        raise OllamaError(f"Ollama connection error: {exc}") from exc


def _ollama_generate(prompt, model=None, url=None):
    """Send a prompt to Ollama and return the response text."""
    model = model or os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL
    base_url = url or os.environ.get("OLLAMA_URL") or DEFAULT_URL
    endpoint = f"{base_url}/api/generate"
    data = {"model": model, "prompt": prompt, "stream": False}
    result = _http_post(endpoint, data)
    return result.get("response", "") or ""


def _is_ollama_available(model=None, url=None):
    """Ping Ollama with a trivial prompt; return True if it responds."""
    try:
        _ollama_generate("ping", model=model, url=url)
        return True
    except OllamaError:
        return False


# --- Retrieval context builder ---

def _load_cases(cases_path):
    """Load cases from JSONL, return list of dicts."""
    path = Path(cases_path)
    if not path.exists():
        return []
    cases = []
    try:
        text = path.read_text(encoding="utf-8-sig")
        for raw in text.splitlines():
            if not raw.strip():
                continue
            cases.append(json.loads(raw))
    except (json.JSONDecodeError, OSError):
        return []
    return cases


def _load_digest(digest_path):
    """Load digest entries from JSONL, return list of dicts."""
    path = Path(digest_path)
    if not path.exists():
        return []
    entries = []
    try:
        text = path.read_text(encoding="utf-8-sig")
        for raw in text.splitlines():
            if not raw.strip():
                continue
            entries.append(json.loads(raw))
    except (json.JSONDecodeError, OSError):
        return []
    return entries


def _match_cases(cases, query):
    """Return cases whose signature or diagnosis contains any query keyword."""
    keywords = query.lower().split()
    matched = []
    for case in cases:
        text = (case.get("signature", "") + " " + case.get("diagnosis", "")).lower()
        if any(kw in text for kw in keywords):
            matched.append(case)
    matched.sort(key=lambda c: (-c.get("times_seen", 0), c.get("id", 0)))
    return matched


def _match_digest(entries, query):
    """Return digest entries whose content or heading contains any query keyword."""
    keywords = query.lower().split()
    matched = []
    for entry in entries:
        text = (
            entry.get("content", "") + " " + entry.get("heading", "")
        ).lower()
        if any(kw in text for kw in keywords):
            matched.append(entry)
    return matched


def build_retrieval_context(
    query, cases_path=None, digest_path=None,
    max_cases=DEFAULT_MAX_CASES, max_digest=DEFAULT_MAX_DIGEST,
):
    """Gather relevant cases and digest entries for the query.

    Returns dict with keys: cases, digest, total_items.
    """
    cases_path = Path(cases_path) if cases_path else Path(DEFAULT_CASES)
    digest_path = Path(digest_path) if digest_path else Path(DEFAULT_DIGEST)

    all_cases = _load_cases(cases_path)
    all_digest = _load_digest(digest_path)

    matched_cases = _match_cases(all_cases, query)[:max_cases]
    matched_digest = _match_digest(all_digest, query)[:max_digest]

    return {
        "cases": matched_cases,
        "digest": matched_digest,
        "total_items": len(matched_cases) + len(matched_digest),
    }


# --- Context formatting ---

def _format_cases_context(cases):
    """Format matched cases into a context string."""
    if not cases:
        return ""
    lines = []
    for case in cases:
        lines.append(
            f"case #{case['id']} times_seen={case.get('times_seen', '?')}"
        )
        lines.append(f"signature: {case.get('signature', '?')}")
        lines.append(f"diagnosis: {case.get('diagnosis', '?')}")
        lines.append("")
    return "\n".join(lines)


def _format_digest_context(entries):
    """Format matched digest entries into a context string."""
    if not entries:
        return ""
    lines = []
    for entry in entries:
        src = entry.get("source", "?")
        heading = entry.get("heading", "?")
        content = entry.get("content", "")
        lines.append(f"[{src}] #{heading}")
        lines.append(f"  {content[:500]}")
        lines.append("")
    return "\n".join(lines)


TOOL_INSTRUCTIONS = (
    "\n\n## Research Tools\n"
    "If you need more information before answering, you may call a tool by "
    "outputting exactly one of these lines:\n"
    '  [TOOL: case_search(query="search terms")]  -- search past failure cases\n'
    '  [TOOL: doc_grep(query="search terms")]  -- search digested documentation\n'
    '  [TOOL: journal_read(pattern="search terms")]  -- search the journal ledger\n'
    "Tool results will be injected as additional context. You may call at most "
    "3 tools per answer. After receiving tool results, give your final answer "
    "without any more [TOOL: ...] lines."
)


def _build_prompt(query, context, use_tools=False):
    """Build the full prompt with system instruction and retrieval context."""
    parts = [
        "You are a QA companion assistant. Answer the question using ONLY "
        "the provided context (past failure cases and documentation). "
        "Always cite which case or document section supports your answer. "
        "If the context does not contain enough information, say so honestly "
        "rather than guessing.",
        "",
    ]
    if use_tools:
        parts[0] += TOOL_INSTRUCTIONS

    cases_text = _format_cases_context(context["cases"])
    digest_text = _format_digest_context(context["digest"])

    if cases_text or digest_text or context.get("tool_results"):
        parts.append("## Retrieved Context")
        parts.append("")
        if cases_text:
            parts.append("### Past Failure Cases")
            parts.append(cases_text)
        if digest_text:
            parts.append("### Documentation")
            parts.append(digest_text)
        if context.get("tool_results"):
            parts.append("### Tool Results")
            for tr in context["tool_results"]:
                parts.append(tr)
            parts.append("")
        parts.append("")
    else:
        parts.append("No relevant context found in the case base or documentation.")
        parts.append("")

    parts.append(f"## Question")
    parts.append(query)

    prompt = "\n".join(parts)
    if len(prompt) > MAX_CONTEXT_CHARS:
        prompt = prompt[:MAX_CONTEXT_CHARS] + "\n... (context truncated)"
    return prompt


# --- Main ask orchestration ---

def ask(query, cases_path=None, digest_path=None, model=None, url=None):
    """Orchestrate: check Ollama, build context, ask or fallback.

    Supports a tool-calling loop: if the model outputs [TOOL: ...] calls,
    they are dispatched and results injected as context, up to MAX_TOOL_CALLS.

    Returns dict with keys: answer, used_ollama, citations, model, context_used.
    """
    from . import tools as tools_mod

    model = model or os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL
    context = build_retrieval_context(query, cases_path, digest_path)

    used_ollama = False
    answer = ""
    context_used = ""

    if _is_ollama_available(model=model, url=url):
        try:
            tool_results_extra = []
            for _tool_step in range(tools_mod.MAX_TOOL_CALLS + 1):
                # Build extended context with any tool results
                ctx_for_prompt = dict(context)
                if tool_results_extra:
                    ctx_for_prompt["tool_results"] = tool_results_extra
                prompt = _build_prompt(query, ctx_for_prompt, use_tools=True)
                answer = _ollama_generate(prompt, model=model, url=url)

                # Parse tool calls from response
                tool_calls = tools_mod.parse_tool_calls(answer)
                if not tool_calls or _tool_step == tools_mod.MAX_TOOL_CALLS:
                    break

                # Dispatch each tool, collect results
                for tool_name, tool_query in tool_calls:
                    kwargs = {}
                    if tool_name == "case_search":
                        kwargs["cases_path"] = cases_path
                    elif tool_name == "doc_grep":
                        kwargs["digest_path"] = digest_path
                    result = tools_mod.dispatch_tool(tool_name, tool_query, **kwargs)
                    tool_results_extra.append(
                        f"[{tool_name}({tool_query})] => {result}"
                    )

            used_ollama = True
            context_used = _format_cases_context(
                context["cases"]
            ) + _format_digest_context(context["digest"])
        except OllamaError:
            used_ollama = False

    if not used_ollama:
        from . import lookup as lookup_mod
        if context["cases"]:
            answer = lookup_mod.format_matches(context["cases"])
        elif context["digest"]:
            answer = _format_digest_context(context["digest"]).strip()
        else:
            answer = "no matching case"

    # S28: detect confidence in the answer
    from . import escalation as esc_mod
    confidence = esc_mod.detect_confidence(answer)

    return {
        "answer": answer,
        "used_ollama": used_ollama,
        "citations": {
            "cases": len(context["cases"]),
            "digest": len(context["digest"]),
        },
        "model": model if used_ollama else None,
        "context_used": context_used,
        "confidence": confidence,
    }


def format_ask_output(result):
    """Render the ask result for CLI output."""
    lines = []
    if result["used_ollama"]:
        total = result["citations"]["cases"] + result["citations"]["digest"]
        lines.append(f"[{result['model']}] ({total} sources)")
        lines.append("")
        lines.append(result["answer"])
    else:
        lines.append("[fallback: no Ollama — raw lookup]")
        lines.append("")
        lines.append(result["answer"])

    # S28: flag low confidence
    confidence = result.get("confidence", {})
    if confidence and not confidence.get("confident", True):
        lines.append("")
        lines.append("[low confidence — consider escalation]")
        lines.append(
            "Run 'qa escalate' to draft a question for a live agent, "
            "or 'qa record' to add the answer manually."

        )

    return "\n".join(lines)
