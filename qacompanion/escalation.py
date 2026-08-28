"""S28 escalation handshake: brain drafts question for live agent.

When the local model's answer indicates low confidence, the brain formats
the question (with retrieval context) for a LIVE agent session. The agent's
answer is then distilled back into the case base after parent confirmation,
closing the loop: novel questions today, free lookups tomorrow.

Pins (fixtures-first discipline):
- confidence detection via regex markers on answer text;
- escalation question includes original query + retrieval context;
- answer recording uses CaseStore.record() (atomic, validated);
- no auto-record without human/agent confirmation (--by required);
- all stdlib, no third-party deps.
"""

import re
from pathlib import Path

from . import store as store_mod

CONFIDENCE_MARKERS = [
    r"\b(?:i'm not sure|i am not sure)\b",
    r"\b(?:i don't know|do not know|don't know)\b",
    r"\b(?:uncertain|unclear|ambiguous)\b",
    r"\b(?:no relevant|no matching|not found)\b",
    r"\b(?:cannot determine|can't determine)\b",
    r"\b(?:unable to|not able to)\b",
    r"\b(?:no information|no data|no context)\b",
    r"\b(?:i cannot find|cannot locate)\b",
    r"\b(?:i was unable|was not able)\b",
    r"\b(?:no diagnosis|no answer)\b",
]

_CONFIDENCE_RE = re.compile(
    "|".join(CONFIDENCE_MARKERS), re.IGNORECASE
)

ESCALATION_TEMPLATE = """\
=== ESCALATION QUESTION ===

The local model was unable to answer this confidently.

Original question:
  {query}

{context_section}
{answer_section}
Please answer this question. If the answer teaches a new lesson,
provide: signature, error excerpt, and diagnosis so it can be recorded.
============================"""


class EscalationError(Exception):
    """Operational failure in the escalation handshake."""


def detect_confidence(answer_text):
    """Detect whether the model's answer indicates low confidence.

    Returns dict with:
      confident: bool — True if answer seems grounded
      markers: list of matched confidence marker strings
    """
    if not answer_text:
        return {"confident": True, "markers": []}
    matches = _CONFIDENCE_RE.findall(answer_text)
    markers = list(set(matches))
    return {
        "confident": len(markers) == 0,
        "markers": markers,
    }


def format_escalation_question(query, context, answer=None):
    """Format a question for escalation to a live agent.

    Includes the original query, retrieval context, and any low-confidence
    answer the model produced.
    """
    context_section = ""
    if context:
        context_section = f"Retrieved context:\n  {context}"

    answer_section = ""
    if answer:
        answer_section = f"Model's low-confidence answer:\n  {answer}\n"

    return ESCALATION_TEMPLATE.format(
        query=query,
        context_section=context_section,
        answer_section=answer_section,
    )


def record_escalated_answer(
    question, answer, signature, error_excerpt, diagnosis,
    by=None, cases_path=None,
):
    """Record an escalated answer into the case base.

    Uses CaseStore.record() for atomic, validated persistence.
    Requires a 'by' value to prevent silent auto-creation.

    Returns (case, created) tuple.
    """
    cs = store_mod.CaseStore(cases_path)
    return cs.record(
        signature=signature,
        error_excerpt=error_excerpt,
        diagnosis=diagnosis,
        by=by,
    )


def format_escalation_output(question_text):
    """Render escalation output for the CLI."""
    lines = [
        question_text,
        "",
        "To record the answer, run:",
        '  qa record --sig "SIGNATURE" --err "ERROR" --diag "DIAGNOSIS"',
    ]
    return "\n".join(lines)
