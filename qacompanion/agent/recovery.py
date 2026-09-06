"""S58 failure recovery & escalation 2.0: failure as a controlled
state machine.

The loop's old behavior — feed a failed verification back and hope —
becomes a deliberate ladder: retry with advice (S49) → alternate
approach → environment check → escalate model (S55 router's escalation
tier) → ask user / terminate. Each rung is reached by COUNTED evidence
(no-progress = the same failure signature repeating), never by hope.

Pins (fixtures-first discipline):
- signatures are deterministic (first-error-line derived), so "same
  failure" is a fact, not a judgment;
- the ladder is desperate in one direction only — it never de-escalates;
- ASK_USER terminates the session honestly (the dashboard restarts
  with new instructions);
- everything is data-driven and mock-tested; recovery=None keeps the
  loop's behavior unchanged.
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RecoveryError(ValueError):
    """Invalid recovery configuration."""


class Strategy(Enum):
    RETRY_WITH_ADVICE = "retry_with_advice"
    ALTERNATE_APPROACH = "alternate_approach"
    ENVIRONMENT_CHECK = "environment_check"
    ESCALATE_MODEL = "escalate_model"
    ASK_USER = "ask_user"
    TERMINATE = "terminate"


ENVIRONMENT_MARKERS = ("no module named", "not recognized",
                       "is not recognized", "file not found",
                       "command not found", "no such file",
                       "connection refused", "address already in use",
                       "permission denied", "access is denied")


@dataclass
class Decision:
    """The chosen strategy plus the reason the model/human will see."""

    strategy: Strategy
    reason: str

    def to_dict(self):
        return {"strategy": self.strategy.value, "reason": self.reason}


@dataclass
class FailureTracker:
    """Counts consecutive identical failures (deterministic signatures).

    The loop records (kind, signature) per failure; `no_progress` fires
    when the SAME signature repeats `threshold` consecutive times.
    """

    threshold: int = 3
    signatures: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.threshold < 2:
            raise RecoveryError("threshold must be >= 2")

    def signature(self, kind: str, error_text: str) -> str:
        digest = hashlib.sha256(
            f"{kind}|{error_text.strip().lower()}".encode("utf-8")
        ).hexdigest()[:16]
        return f"{kind}:{digest}"

    def record(self, signature: str) -> int:
        self.signatures.append(signature)
        return len(self.signatures)

    def consecutive_same(self) -> int:
        if not self.signatures:
            return 0
        last = self.signatures[-1]
        count = 0
        for signature in reversed(self.signatures):
            if signature != last:
                break
            count += 1
        return count

    def no_progress(self, threshold: Optional[int] = None) -> bool:
        return self.consecutive_same() >= (threshold or self.threshold)

    def report(self) -> Dict[str, Any]:
        return {"total": len(self.signatures),
                "consecutive_same": self.consecutive_same(),
                "threshold": self.threshold}


@dataclass
class RecoveryPolicy:
    """The strategy ladder, evaluated per failure context."""

    max_same_failure: int = 3
    max_alternates: int = 2
    environment_markers: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.max_same_failure < 2:
            raise RecoveryError("max_same_failure must be >= 2")
        if self.max_alternates < 1:
            raise RecoveryError("max_alternates must be >= 1")

    def decide(self, kind: str, error_text: str, repeat_count: int,
               alternate_count: int, escalation_available: bool,
               iterations_left: bool = True) -> Decision:
        """Pick the strategy for one failure event.

        kind: "tool" | "verification" | "provider"
        repeat_count: consecutive same-signature failures
        alternate_count: alternate-approach instructions already issued
        """
        if not iterations_left:
            return Decision(Strategy.TERMINATE,
                            "no iterations left for another attempt")
        if self._is_environment(error_text):
            return Decision(Strategy.ENVIRONMENT_CHECK,
                            "failure text matches environment patterns — "
                            "inspect the environment first")
        if repeat_count >= self.max_same_failure:
            if alternate_count < self.max_alternates:
                return Decision(
                    Strategy.ALTERNATE_APPROACH,
                    f"same failure repeated {repeat_count}x — change "
                    f"strategy instead of retrying")
            if escalation_available:
                return Decision(Strategy.ESCALATE_MODEL,
                                "repeated failure after alternates — "
                                "escalate to a stronger brain")
            return Decision(Strategy.ASK_USER,
                            "repeated failure after alternates; no "
                            "escalation available — needs human decision")
        if kind == "verification":
            return Decision(Strategy.ALTERNATE_APPROACH,
                            "verification failed — attempt a different "
                            "approach")
        return Decision(Strategy.RETRY_WITH_ADVICE,
                        "first occurrence — retry with injected advice")

    def _is_environment(self, error_text: str) -> bool:
        text = (error_text or "").lower()
        for marker in self.environment_markers or ENVIRONMENT_MARKERS:
            if marker in text:
                return True
        return False


class RecoveryStateMachine:
    """Combines tracker + policy + escalation availability into the
    decision the loop acts on. Escalation swaps are one-way."""

    def __init__(self, policy: Optional[RecoveryPolicy] = None,
                 threshold: int = 3):
        self.policy = policy or RecoveryPolicy()
        self.tracker = FailureTracker(threshold=threshold)
        self.alternate_count = 0
        self.escalated = False

    def on_failure(self, kind: str, error_text: str, iteration: int,
                   max_iterations: int,
                   escalation_available: bool = False) -> Decision:
        signature = self.tracker.signature(kind, error_text)
        self.tracker.record(signature)
        repeat_count = self.tracker.consecutive_same()
        iterations_left = iteration < max_iterations
        if self.escalated:
            escalation_available = False  # one-way ladder: never re-escalate
        decision = self.policy.decide(
            kind=kind, error_text=error_text, repeat_count=repeat_count,
            alternate_count=self.alternate_count,
            escalation_available=escalation_available,
            iterations_left=iterations_left)
        if decision.strategy is Strategy.ALTERNATE_APPROACH:
            self.alternate_count += 1
        return decision

    def mark_escalated(self) -> None:
        self.escalated = True

    def report(self) -> Dict[str, Any]:
        return {"tracker": self.tracker.report(),
                "alternate_count": self.alternate_count,
                "escalated": self.escalated}
