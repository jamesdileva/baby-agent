"""S55 slice 3: deterministic model routing under policy.

The human role sketch (validated by the S55 bake-off): a capable brain
for real tasks, cheap local models for routine work, a vision model,
and an escalation tier when stuck. ModelRouter turns that sketch into
an ordered, deterministic rule list — no LLM judgment about which model
to use, ever.

Pins (fixtures-first discipline):
- rules are data: ModelRoute(role, provider_factory, when) evaluated in
  order, first match wins, explicit default for the brain role;
- routing is pure policy: `route()` never calls a model, never guesses;
- escalation is trigger-driven (failure_count, stuck) — the S49 brain
  supplies the signals, the router supplies the model;
- unknown roles fall back to brain, never raise.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ModelRoute:
    """One routing rule. First matching rule wins (order = priority)."""

    role: str
    provider_factory: Callable[..., Any]
    when: Optional[Callable[[Dict[str, Any]], bool]] = None
    model: Optional[str] = None
    reason: str = ""

    def matches(self, context: Dict[str, Any]) -> bool:
        if self.when is None:
            return True
        return bool(self.when(context))


class ModelRouter:
    """Deterministic role -> provider routing under policy."""

    def __init__(self, routes: List[ModelRoute],
                 default_factory: Optional[Callable[..., Any]] = None,
                 default_model: Optional[str] = None):
        self.routes = list(routes)
        self.default_factory = default_factory
        self.default_model = default_model

    def route(self, role: str = "brain",
              context: Optional[Dict[str, Any]] = None) -> Any:
        """Return the provider instance for a role under the current
        context (e.g. {'failure_count': 2, 'stuck': True})."""
        context = context or {}
        for route in self.routes:
            if route.role != role:
                continue
            if route.matches(context):
                return route.provider_factory(model=route.model)
        if role == "brain":
            factory = self.default_factory or _default_ollama
            return factory(model=self.default_model)
        # unknown role falls back to brain, never raises
        return self.route("brain", context)

    def explain(self, role: str = "brain",
                context: Optional[Dict[str, Any]] = None) -> str:
        """Which rule would fire — for dashboards and debugging."""
        context = context or {}
        for route in self.routes:
            if route.role == role and route.matches(context):
                return (f"{role}: {route.model or route.provider_factory}"
                        f" ({route.reason or 'rule'})")
        if role == "brain" and self.default_factory is not None:
            return f"{role}: default ({self.default_model or 'local'})"
        return f"{role}: default brain"


def _default_ollama(model: Optional[str] = None):
    from .providers import OllamaProvider

    return OllamaProvider(model=model)


def default_router(gemini_available: Optional[bool] = None) -> ModelRouter:
    """The human-validated role sketch as policy:
    - brain: the local bake-off winner by default; escalate to the free
      Gemini cloud brain when the loop reports repeated failures
    - escalation: Gemini plain mode (quota-limited on purpose)
    - local: cheap/routine work on the local coder
    """
    if gemini_available is None:
        gemini_available = bool(os.environ.get("GEMINI_API_KEY"))

    def _gemini(model: Optional[str] = None):
        from .providers import GeminiModelProvider

        return GeminiModelProvider(model=model)

    def _ollama_qwen(model: Optional[str] = None):
        return _default_ollama(model or "qwen3:4b")

    routes: List[ModelRoute] = []
    if gemini_available:
        routes.append(ModelRoute(
            role="escalation", provider_factory=_gemini,
            model="gemini-3.1-flash-lite",
            when=lambda ctx: ctx.get("failure_count", 0) >= 2
            or ctx.get("stuck", False),
            reason="stuck/escalation -> free cloud brain",
        ))
        routes.append(ModelRoute(
            role="brain",
            provider_factory=_gemini,
            model="gemini-3.1-flash-lite",
            when=lambda ctx: ctx.get("prefer_cloud", False),
            reason="cloud brain when explicitly preferred",
        ))
    routes.append(ModelRoute(
        role="brain", provider_factory=_ollama_qwen,
        model="qwen3:4b", reason="local brain (bake-off primary)",
    ))
    routes.append(ModelRoute(
        role="local", provider_factory=_ollama_qwen,
        model="qwen2.5-coder:3b", reason="cheap local coder",
    ))
    return ModelRouter(routes=routes, default_factory=_ollama_qwen,
                       default_model="qwen3:4b")
