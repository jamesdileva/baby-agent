"""S38 permission & safety: the real policy engine for untrusted automation.

Every model-generated tool call passes the S32 pipeline's permission stage.
The engine decides and records — it never executes and never touches the
filesystem.

Resolution order (first match wins):
    1. explicit rules      PermissionRule(tool_glob, mode, reason,
                           args_contains) — fnmatch on tool name;
                           args_contains {arg: substring} must all match
    2. tool declaration    tool.requires_confirmation -> ASK
    3. level defaults      READ_ONLY/SAFE_WRITE/EXECUTION -> ALLOW,
                           DESTRUCTIVE -> DENY, EXTERNAL -> ASK
    4. fallback            default_mode ("DENY" = paranoid mode)

ASK resolution is the confirmer seam (registry.execute, additive): a
confirmer callable approves or denies; absent confirmer = structured
denial, preserving the S32 safe default. Every decision — including
confirmation outcomes — lands in the policy's audit trail.

Pins (fixtures-first discipline):
- check(tool_name, arguments, tool=None) is the S32 compat seam: mode
  string only; decide() carries the full PermissionDecision;
- the engine duck-types the tool (side_effect_level, requires_confirmation)
  to avoid a registry<->permissions import cycle;
- rules are data, not code — teaching the agent new permissions is
  constructing PermissionRule lists, exactly like the S16 declarative
  skills tradition.
"""

import fnmatch
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

ALLOW = "ALLOW"
ASK = "ASK"
DENY = "DENY"
MODES = (ALLOW, ASK, DENY)

READ_ONLY = "READ_ONLY"
SAFE_WRITE = "SAFE_WRITE"
EXECUTION = "EXECUTION"
DESTRUCTIVE = "DESTRUCTIVE"
EXTERNAL = "EXTERNAL"

DEFAULT_LEVEL_DEFAULTS = {
    READ_ONLY: ALLOW,
    SAFE_WRITE: ALLOW,
    EXECUTION: ALLOW,
    DESTRUCTIVE: DENY,
    EXTERNAL: ASK,
}


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


@dataclass(frozen=True)
class PermissionRule:
    """One explicit rule. First matching rule wins (order = priority)."""

    tool_glob: str
    mode: str
    reason: str = ""
    args_contains: Optional[Dict[str, str]] = None

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"rule mode must be one of {MODES}: {self.mode!r}")
        if not self.tool_glob:
            raise ValueError("rule tool_glob required")
        if self.args_contains is not None and not isinstance(self.args_contains, dict):
            raise ValueError("args_contains must be a dict of {arg: substring}")

    def matches(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        if not fnmatch.fnmatchcase(tool_name, self.tool_glob):
            return False
        if self.args_contains:
            for key, needle in self.args_contains.items():
                haystack = str(arguments.get(key, ""))
                if needle.lower() not in haystack.lower():
                    return False
        return True


@dataclass(frozen=True)
class PermissionDecision:
    """The outcome of one permission resolution (one audit-trail entry)."""

    tool_name: str
    mode: str
    rule: str
    reason: str
    timestamp: str = ""

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"decision mode must be one of {MODES}: {self.mode!r}")

    def to_dict(self):
        return {
            "tool_name": self.tool_name,
            "mode": self.mode,
            "rule": self.rule,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


@dataclass
class PermissionPolicy:
    """The canonical S38 policy engine (replaces the S32 minimal seam)."""

    rules: List[PermissionRule] = field(default_factory=list)
    level_defaults: Optional[Dict[str, str]] = None
    default_mode: str = ALLOW
    name: str = "policy"

    def __post_init__(self):
        if self.default_mode not in MODES:
            raise ValueError(f"default_mode must be one of {MODES}: {self.default_mode!r}")
        if self.level_defaults is None:
            self.level_defaults = dict(DEFAULT_LEVEL_DEFAULTS)
        self.decisions: List[PermissionDecision] = []

    # -- resolution -------------------------------------------------------

    def decide(self, tool_name: str, arguments: Dict[str, Any],
               tool: Any = None) -> PermissionDecision:
        decision = self._resolve(tool_name, arguments, tool)
        self.decisions.append(decision)
        return decision

    def check(self, tool_name: str, arguments: Dict[str, Any],
              tool: Any = None) -> str:
        """S32 compat seam: mode string only (decision still audited)."""
        return self.decide(tool_name, arguments, tool).mode

    def _resolve(self, tool_name: str, arguments: Dict[str, Any],
                 tool: Any) -> PermissionDecision:
        def _decide(mode, rule, reason):
            return PermissionDecision(
                tool_name=tool_name, mode=mode, rule=rule, reason=reason,
                timestamp=_utc_stamp(),
            )

        for rule in self.rules:
            if rule.matches(tool_name, arguments):
                return _decide(rule.mode, f"rule:{rule.tool_glob}",
                               rule.reason or "explicit rule")

        if tool is not None:
            if getattr(tool, "requires_confirmation", False):
                return _decide(
                    ASK, "confirmation-required",
                    f"{tool_name} declares requires_confirmation",
                )
            level = getattr(tool, "side_effect_level", None)
            if level in self.level_defaults:
                mode = self.level_defaults[level]
                # the level default IS the decision, even when it is ALLOW —
                # a DENY-by-default policy must still allow reads
                return _decide(mode, f"level:{level}",
                               f"side_effect_level {level} defaults to {mode}")

        return _decide(self.default_mode, "fallback",
                       f"no rule matched; default_mode={self.default_mode}")

    # -- helpers ------------------------------------------------------------

    def audit_dicts(self) -> List[dict]:
        return [d.to_dict() for d in self.decisions]


ALLOW_ALL_POLICY = PermissionPolicy(name="allow-all")
