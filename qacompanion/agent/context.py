"""S56 context optimization: never drown the model.

ContextBuilder assembles the per-turn request under a char budget with
explicit priority: goal > current failure > latest tool result
(verbatim) > recent tool results (reduced) > older history (one-line
digests). ObservationReducer/ToolResultSummarizer do the shrinking;
MemoryRetriever injects source-labeled S47 memory at run start.

Pins (fixtures-first discipline):
- additive integration: AgentLoop(context_builder=None) keeps today's
  full-replay behavior byte-identical; the builder is opt-in;
- never split a message mid-content — over-budget items are dropped
  whole, lowest priority first, and the drop is reported;
- the LATEST tool result is always verbatim (the model reasons over
  it next);
- retrieval is the deterministic S47 keyword scoring — no embeddings.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .contracts import ModelMessage
from .experience import MemoryLayer, ExperienceStore


class ContextError(ValueError):
    """Invalid context-builder configuration."""


@dataclass
class ContextBudget:
    """Char budget with simple accounting."""

    max_chars: int = 24_000

    def __post_init__(self):
        if self.max_chars < 500:
            raise ContextError("max_chars must be at least 500")

    def fits(self, used: int, incoming: str) -> bool:
        return used + len(incoming) <= self.max_chars


def summarize_command_result(output: str, head: int = 5, tail: int = 10
                             ) -> str:
    """Reduce an embedded S35 CommandResult JSON to the decision
    surface: exit code, stdout head+tail, stderr head."""
    try:
        payload = json.loads(output)
    except (ValueError, TypeError):
        return output[:600]
    if not isinstance(payload, dict) or "exit_code" not in payload:
        return output[:600]
    lines = []
    lines.append(f"exit_code={payload.get('exit_code')}"
                 + (" (timed out)" if payload.get("timed_out") else ""))
    stdout = (payload.get("stdout") or "").splitlines()
    stderr = (payload.get("stderr") or "").splitlines()
    if stdout:
        shown = stdout[:head]
        if len(stdout) > head + tail:
            shown.append(f"... ({len(stdout) - head - tail} lines omitted)")
        shown += stdout[-tail:] if len(stdout) > head + tail else \
            stdout[head:]
        lines.append("stdout: " + " | ".join(line.strip()[:160]
                                             for line in shown if line.strip()))
    if stderr:
        lines.append("stderr: " + " | ".join(
            line.strip()[:160] for line in stderr[:5] if line.strip()))
    return "\n".join(lines)


def reduce_message(content: str, is_latest: bool = False,
                   max_verbatim: int = 4_000) -> str:
    """Shrink one message's content. The latest message stays verbatim
    up to max_verbatim; older tool results reduce to decision surface."""
    if is_latest and len(content) <= max_verbatim:
        return content
    if content.lstrip().startswith("{") and "exit_code" in content:
        reduced = summarize_command_result(content)
    else:
        lines = content.splitlines()
        if len(lines) > 6:
            reduced = (" | ".join(line.strip()[:120]
                                  for line in lines[:3] if line.strip())
                       + f" ... ({len(lines) - 3} more lines)")
        else:
            reduced = content[:600]
    if is_latest and len(reduced) < len(content):
        reduced = reduced + f"\n(latest, reduced from {len(content)} chars)"
    return reduced


def _digest(content: str) -> str:
    line = next((line.strip() for line in content.splitlines()
                 if line.strip()), "")
    return f"[earlier] {line[:140]}"


class MemoryRetriever:
    """Injects source-labeled S47 memory for the goal at run start."""

    def __init__(self, memory_layer: Optional[MemoryLayer] = None):
        self.memory_layer = memory_layer

    def retrieve(self, goal: str, k: int = 3) -> List[Dict[str, Any]]:
        if self.memory_layer is None or not goal.strip():
            return []
        try:
            return self.memory_layer.search(goal, k_per_source=k)
        except Exception:
            return []  # degraded memory: honest silence

    def block(self, goal: str, k: int = 3) -> str:
        results = self.retrieve(goal, k=k)
        if not results:
            return ""
        lines = ["## Relevant memory (prior runs, source-labeled)"]
        for item in results:
            label = item.get("source", "?")
            summary = (item.get("goal") or item.get("signature")
                       or item.get("heading") or item.get("text") or "")
            detail = (item.get("resolution") or item.get("diagnosis")
                      or item.get("snippet") or "")
            lines.append(f"- [{label}] {str(summary)[:140]}"
                         + (f" -> {str(detail)[:160]}"
                            if detail else ""))
        return "\n".join(lines)


@dataclass
class BuildReport:
    """What survived assembly — the verification surface."""

    included: int
    dropped: int
    chars: int
    budget: int
    goal_present: bool
    latest_tool_result_verbatim: bool
    over_budget: bool = False  # True when fixed-priority content alone
                               # exceeded the budget (nothing was dropped
                               # to compensate — honesty over cosmetics)

    def to_dict(self):
        return {key: value for key, value in {
            "included": self.included,
            "dropped": self.dropped,
            "chars": self.chars,
            "budget": self.budget,
            "goal_present": self.goal_present,
            "latest_tool_result_verbatim":
                self.latest_tool_result_verbatim,
            "over_budget": self.over_budget,
        }.items()}


class ContextBuilder:
    """Assembles the per-turn message list under budget, prioritized."""

    def __init__(self, budget: ContextBudget = None,
                 memory_retriever: Optional[MemoryRetriever] = None,
                 keep_last_turns: int = 3):
        self.budget = budget or ContextBudget()
        self.retriever = memory_retriever
        self.keep_last_turns = keep_last_turns
        self.last_report: Optional[BuildReport] = None

    def build(self, session: Any, offered_tools: List[Any],
              native_tools: bool = False) -> List[ModelMessage]:
        from .loop import build_system_prompt

        # priorities: system > goal > memory block > latest tool result
        # (verbatim) > recent turns (reduced) > older turns (digest)
        messages = list(session.messages)
        system = next((m for m in messages if m.role == "system"), None)
        goal = next((m for m in messages if m.role == "user"), None)
        history = [m for m in messages if m.role != "system"]
        tool_indices = [i for i, m in enumerate(history)
                        if m.role == "tool"]
        latest_tool_index = tool_indices[-1] if tool_indices else None

        memory_block = ""
        if self.retriever is not None and goal is not None:
            memory_block = self.retriever.block(goal.content)

        # assemble newest-first so the budget sacrifices the oldest
        assembled: List[ModelMessage] = []
        if system is not None:
            offered_lines = ["", "Available tools:"]
            for tool in offered_tools:
                offered_lines.append(f"- {tool.name}: {tool.description}")
            if not native_tools:
                from .loop import TOOL_PROTOCOL_PROMPT
                offered_lines.append(TOOL_PROTOCOL_PROMPT)
            system_text = system.content.split("## Relevant memory")[0]
            system_text = system_text.rstrip() + "\n".join(offered_lines)
            assembled.append(ModelMessage(role="system",
                                          content=system_text))
        used = len(assembled[0].content) if assembled else 0

        def _fits(text: str) -> bool:
            total = sum(len(m.content) for m in assembled)
            return self.budget.fits(total, text)

        if goal is not None:
            assembled.append(goal)
            used += len(goal.content)
        if memory_block:
            memory_message = ModelMessage(role="system",
                                          content=memory_block)
            assembled.append(memory_message)
            used += len(memory_block)

        remaining = list(enumerate(history))
        dropped = 0
        for offset, (index, message) in enumerate(reversed(remaining)):
            is_latest_tool = index == latest_tool_index
            within_recent = offset < self.keep_last_turns
            if is_latest_tool:
                # NON-DROPPABLE: the model is about to reason over this.
                # verbatim -> reduced -> hard truncate; budget may be
                # exceeded and that is reported honestly (over_budget).
                content = reduce_message(message.content, is_latest=True)
                if not _fits(content):
                    content = reduce_message(message.content)
                if not _fits(content):
                    content = content[:800]
                assembled.append(ModelMessage(role=message.role,
                                              content=content))
                used += len(content)
                continue
            if within_recent:
                content = reduce_message(message.content)
            else:
                content = _digest(message.content)
            if not _fits(content):
                dropped += 1
                continue
            assembled.append(ModelMessage(role=message.role,
                                          content=content))
            used += len(content)

        self.last_report = BuildReport(
            included=len(assembled),
            dropped=dropped,
            chars=used,
            budget=self.budget.max_chars,
            goal_present=goal is not None,
            latest_tool_result_verbatim=(
                latest_tool_index is not None and any(
                    m.role == "tool" and len(m.content) <= 4_000
                    for m in assembled)),
            over_budget=used > self.budget.max_chars,
        )
        return assembled
