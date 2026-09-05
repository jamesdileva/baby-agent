"""S49 QA brain integration: the accumulated QA intelligence answers
automatically when commands fail.

Failure path: failed ToolResult -> failure signature (S2 normalization)
-> layered lookup (exact case signature -> keyword case match ->
S47 MemoryLayer fallback) -> advice injected into the loop as a
system-role message BEFORE the model's next action. Honest silence when
nothing matches; a degraded store never crashes the loop.

Recording is deliberately out of scope: no case auto-creation without
confirmation (case-#10 lore) — this brain reads, S50 writes.
"""

import json
import re
from typing import Any, Dict, Optional

from .. import lookup as lookup_mod
from .. import ollama_bridge as bridge
from ..signatures import canonical, normalize
from .contracts import ToolResult
from .experience import ExperienceStore, MemoryLayer

STOPWORD_THRESHOLD = 3  # words shorter than this are weak query terms


def derive_signature(call_name: str, output_text: str) -> str:
    """Canonical S2 signature for one failed tool call."""
    lines = [line.strip() for line in (output_text or "").splitlines()
             if line.strip()]
    first_error_line = lines[0] if lines else "no output"
    return canonical(normalize(call_name, first_error_line))


def _query_terms(output_text: str) -> str:
    """Distinctive word tokens from the error output for the keyword
    matcher — punctuation-free, so `ZeroDivisionError:` matches stored
    text containing `ZeroDivisionError`."""
    lines = [line.strip() for line in (output_text or "").splitlines()
             if line.strip()]
    words: list = []
    seen: set = set()
    for line in reversed(lines):
        for token in re.findall(r"\w+", line):
            key = token.lower()
            if key in seen or len(key) < STOPWORD_THRESHOLD:
                continue
            seen.add(key)
            words.append(key)
            if len(words) >= 12:
                return " ".join(words)
    return " ".join(words)


def failure_text(result: ToolResult) -> Optional[str]:
    """Extract failure substance, or None when nothing failed.

    Two failure shapes: a failed ToolResult itself, and the S35
    convention where run_command-family results are ok=True with the
    embedded CommandResult carrying the nonzero exit code. Module-level
    since S50 (session harvesting reuses it).
    """
    if not result.ok:
        return (result.error or "") + "\n" + (result.output or "")
    try:
        payload = json.loads(result.output)
    except (ValueError, TypeError):
        return None
    if isinstance(payload, dict) \
            and payload.get("exit_code") not in (0, None):
        return (payload.get("stderr") or "") + "\n" \
            + (payload.get("stdout") or "")
    return None


class QABrain:
    """Layered failure advice from the colony's accumulated memory."""

    def __init__(self, cases_path=None,
                 experience_store: Optional[ExperienceStore] = None,
                 memory_layer: Optional[MemoryLayer] = None):
        self.cases_path = cases_path
        self.memory_layer = memory_layer or MemoryLayer(
            experience_store=experience_store or ExperienceStore(),
            cases_path=cases_path,
        )

    def advise(self, result: ToolResult) -> Optional[Dict[str, Any]]:
        failure_text = self._failure_text(result)
        if failure_text is None:
            return None
        signature = derive_signature(result.call_name, failure_text)
        return self._lookup_cases(signature, failure_text)

    def _failure_text(self, result: ToolResult) -> Optional[str]:
        """Extract failure substance, or None when nothing failed.

        Two failure shapes: a failed ToolResult itself, and the S35
        convention where run_command-family results are ok=True with the
        embedded CommandResult carrying the nonzero exit code.
        """
        if not result.ok:
            return (result.error or "") + "\n" + (result.output or "")
        try:
            payload = json.loads(result.output)
        except (ValueError, TypeError):
            return None
        if isinstance(payload, dict) \
                and payload.get("exit_code") not in (0, None):
            return (payload.get("stderr") or "") + "\n" \
                + (payload.get("stdout") or "")
        return None

    def _lookup_cases(self, signature: str,
                      output_text: str) -> Optional[Dict[str, Any]]:
        try:
            from pathlib import Path
            cases_path = Path(self.cases_path) if self.cases_path \
                else Path(bridge.DEFAULT_CASES)
            if cases_path.exists():
                cases = bridge._load_cases(cases_path)
                exact = lookup_mod.select(cases, signature)
                if exact:
                    case = exact[0]
                    return self._case_advice(case, "exact-signature")
                query = _query_terms(output_text)
                if query:
                    keyword_hits = bridge._match_cases(cases, query)
                    if keyword_hits:
                        return self._case_advice(keyword_hits[0],
                                                 "keyword-match")
        except Exception:
            pass  # degraded store: fall through to memory
        return self._lookup_memory(output_text)

    def _case_advice(self, case: Dict[str, Any], how: str
                     ) -> Optional[Dict[str, Any]]:
        diagnosis = case.get("diagnosis")
        if not diagnosis:
            return None
        return {
            "source": "case",
            "how": how,
            "case_id": case.get("id"),
            "signature": case.get("signature"),
            "diagnosis": diagnosis,
            "times_seen": case.get("times_seen"),
        }

    def _lookup_memory(self, output_text: str) -> Optional[Dict[str, Any]]:
        try:
            query = _query_terms(output_text)
            if not query:
                return None
            results = self.memory_layer.search(query, k_per_source=2)
            for item in results:
                text = item.get("diagnosis") or item.get("resolution") \
                    or item.get("text") or ""
                if text:
                    return {
                        "source": item["source"],
                        "how": "memory-search",
                        "diagnosis": text[:400],
                        "score": item.get("score"),
                    }
        except Exception:
            pass  # a failing memory layer degrades to honest silence
        return None


def format_advice(advice: Dict[str, Any]) -> str:
    """The system-message form the model sees."""
    return json.dumps({"qa_memory": advice}, ensure_ascii=False)
