"""S55 slice 3 router tests: deterministic role routing under policy."""

import os
import unittest
from unittest.mock import patch

from qacompanion.agent.providers import GeminiModelProvider, OllamaProvider
from qacompanion.agent.router import ModelRoute, ModelRouter, default_router


def _factory(tag):
    def factory(model=None):
        return f"{tag}({model})"
    return factory


class TestModelRouter(unittest.TestCase):
    def _router(self):
        return ModelRouter(routes=[
            ModelRoute(role="escalation", provider_factory=_factory("gem"),
                       when=lambda ctx: ctx.get("failure_count", 0) >= 2
                       or ctx.get("stuck", False),
                       model="gemini-3.1-flash-lite"),
            ModelRoute(role="brain", provider_factory=_factory("local"),
                       model="qwen3:4b"),
        ], default_factory=_factory("local"), default_model="qwen3:4b")

    def test_brain_routes_to_local_by_default(self):
        provider = self._router().route("brain")
        self.assertEqual(provider, "local(qwen3:4b)")

    def test_escalation_requires_trigger(self):
        router = self._router()
        self.assertEqual(router.route("escalation", {}),
                         "local(qwen3:4b)")  # falls back to brain
        self.assertEqual(router.route("escalation",
                                      {"failure_count": 2}),
                         "gem(gemini-3.1-flash-lite)")
        self.assertEqual(router.route("escalation", {"stuck": True}),
                         "gem(gemini-3.1-flash-lite)")

    def test_first_matching_rule_wins(self):
        router = ModelRouter(routes=[
            ModelRoute(role="brain", provider_factory=_factory("first"),
                       when=lambda ctx: True),
            ModelRoute(role="brain", provider_factory=_factory("second")),
        ])
        self.assertEqual(router.route("brain"), "first(None)")

    def test_unknown_role_falls_back_to_brain(self):
        self.assertEqual(self._router().route("telepathy"),
                         "local(qwen3:4b)")

    def test_routing_is_deterministic(self):
        router = self._router()
        results = {router.route("brain", {"failure_count": n})
                   for n in range(3)}
        self.assertEqual(len(results), 1)

    def test_explain_reports_the_firing_rule(self):
        router = self._router()
        self.assertIn("qwen3:4b", router.explain("brain"))
        self.assertIn("gemini", router.explain(
            "escalation", {"failure_count": 3}))


class TestDefaultRouter(unittest.TestCase):
    def test_escalation_tier_only_when_key_present(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            router = default_router(gemini_available=False)
            routes = {r.role for r in router.routes}
            self.assertNotIn("escalation", routes)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}):
            router = default_router(gemini_available=True)
            self.assertIn("escalation", {r.role for r in router.routes})

    def test_local_fallback_is_ollama(self):
        router = default_router(gemini_available=False)
        provider = router.route("brain")
        self.assertIsInstance(provider, OllamaProvider)

    def test_gemini_escalation_provider(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}):
            router = default_router(gemini_available=True)
            provider = router.route(
                "escalation", {"failure_count": 5})
            self.assertIsInstance(provider, GeminiModelProvider)


if __name__ == "__main__":
    unittest.main()
