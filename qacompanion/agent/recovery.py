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

    S103: the tracker is also success-aware. The loop reports every
    successful tool result via `record_success()`, which resets the
    failing-streak counter — so `cycling()` can fire on INTERLEAVED
    thrash (many different failing paths, no success between them),
    which the consecutive-same rule can never see (live finding: a
    session cycling src/main.py / app/__init__.py / list src failed 6
    of 10 iterations with the ladder silent).
    """

    threshold: int = 3
    signatures: List[str] = field(default_factory=list)
    consec_fail_steps: int = 0

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
        self.consec_fail_steps += 1
        return len(self.signatures)

    def record_success(self) -> None:
        """S103: a successful tool result is progress by definition."""
        self.consec_fail_steps = 0

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

    def cycling(self, window: int = 5, min_distinct: int = 2) -> bool:
        """S103: non-progress across DIFFERENT failures — a streak of
        `window` failing steps with no success between them that spans
        at least `min_distinct` distinct signatures. Same-signature
        streaks are the older rule's job; this catches the model that
        cycles guessing paths."""
        if self.consec_fail_steps < window:
            return False
        recent = self.signatures[-window:]
        return len(set(recent)) >= min_distinct

    def no_progress(self, threshold: Optional[int] = None) -> bool:
        return self.consecutive_same() >= (threshold or self.threshold)

    def report(self) -> Dict[str, Any]:
        return {"total": len(self.signatures),
                "consecutive_same": self.consecutive_same(),
                "consec_fail_steps": self.consec_fail_steps,
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
               iterations_left: bool = True,
               environment_repeat: int = 0,
               cycling: bool = False) -> Decision:
        """Pick the strategy for one failure event.

        kind: "tool" | "verification" | "provider"
        repeat_count: consecutive same-signature failures
        alternate_count: alternate-approach instructions already issued
        environment_repeat: S103 — consecutive ENVIRONMENT_CHECK
            decisions already issued; after 2 the environment summary
            was requested and more of the same is not a strategy, so
            the failure falls through to the counted ladder
        cycling: S103 — the tracker sees a streak of failures across
            DIFFERENT signatures with no success between them
        """
        if not iterations_left:
            return Decision(Strategy.TERMINATE,
                            "no iterations left for another attempt")
        if repeat_count >= self.max_same_failure:
            # S103.1: the same-failure ladder outranks the environment
            # branch. S98 routed env-class failures here so blind
            # retries became environment inspections; the live finding
            # showed the residual loop — the SAME missing file re-read
            # 3x kept re-earning ENVIRONMENT_CHECK because successes
            # between failures reset the environment counter. First
            # occurrence (repeat_count 1-2) still gets the environment
            # check below; a 3rd identical failure means change
            # strategy, environment class or not.
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
        if self._is_environment(error_text) and environment_repeat < 2:
            return Decision(Strategy.ENVIRONMENT_CHECK,
                            "failure text matches environment patterns — "
                            "inspect the environment first")
        if cycling:
            if alternate_count < self.max_alternates:
                return Decision(
                    Strategy.ALTERNATE_APPROACH,
                    "different failures keep coming with no success "
                    "between them — stop guessing and change approach")
            if escalation_available:
                return Decision(Strategy.ESCALATE_MODEL,
                                "cycling failures after alternates — "
                                "escalate to a stronger brain")
            return Decision(Strategy.ASK_USER,
                            "cycling failures after alternates; no "
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
        self.environment_repeat = 0
        self.escalated = False

    def on_success(self) -> None:
        """S103: a successful tool result is progress by definition.
        Resets the failing streak AND the environment-decision counter —
        new progress means new environment context, so a later
        environment-class failure earns a fresh ENVIRONMENT_CHECK."""
        self.tracker.record_success()
        self.environment_repeat = 0

    def on_failure(self, kind: str, error_text: str, iteration: int,
                   max_iterations: int,
                   escalation_available: bool = False) -> Decision:
        signature = self.tracker.signature(kind, error_text)
        self.tracker.record(signature)
        repeat_count = self.tracker.consecutive_same()
        cycling = self.tracker.cycling()
        iterations_left = iteration < max_iterations
        if self.escalated:
            escalation_available = False  # one-way ladder: never re-escalate
        decision = self.policy.decide(
            kind=kind, error_text=error_text, repeat_count=repeat_count,
            alternate_count=self.alternate_count,
            escalation_available=escalation_available,
            iterations_left=iterations_left,
            environment_repeat=self.environment_repeat,
            cycling=cycling)
        if decision.strategy is Strategy.ALTERNATE_APPROACH:
            self.alternate_count += 1
        if decision.strategy is Strategy.ENVIRONMENT_CHECK:
            self.environment_repeat += 1
        # S103: environment_repeat deliberately does NOT reset on
        # non-environment decisions — env-class failures interleaved
        # with other failures must still fall through after 2. Only
        # on_success() (real progress) starts a fresh count.
        return decision

    def mark_escalated(self) -> None:
        self.escalated = True

    def report(self) -> Dict[str, Any]:
        return {"tracker": self.tracker.report(),
                "alternate_count": self.alternate_count,
                "environment_repeat": self.environment_repeat,
                "escalated": self.escalated}
