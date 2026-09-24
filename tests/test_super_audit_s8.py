"""S75.8 super-audit S8 regression tests: timeout enforcement (A2/F4),
bounded permission audit trail (F14), Retry-After-aware bounded retry
delays (F13). All hermetic — the wall-clock test uses an event-based
hang, generous margins, and no live providers.
"""

import io
import threading
import time
import unittest
import urllib.error

from qacompanion.agent import ToolCall, ToolRegistry
from qacompanion.agent.permissions import PermissionPolicy
from qacompanion.agent.providers import _MAX_RETRY_WAIT, _retry_delay
from qacompanion.agent.registry import RegisteredTool, ToolDefinition


def _tool(name, handler, timeout=1.0):
    return RegisteredTool(
        definition=ToolDefinition(
            name=name, description="test tool",
            parameters_schema={"type": "object", "properties": {}}),
        handler=handler,
        timeout_seconds=timeout,
    )


class TimeoutEnforcementTests(unittest.TestCase):
    """A2: the old per-call `with ThreadPoolExecutor` form blocked on
    shutdown(wait=True) after a timeout — wall time equaled handler
    time while claiming timed_out. The caller must now return on time."""

    def test_timed_out_call_returns_before_the_handler_finishes(self):
        release = threading.Event()
        registry = ToolRegistry()

        def hung_handler():
            release.wait(timeout=30)  # never released in this test
            return "late"

        registry.register(_tool("hang", hung_handler, timeout=0.3))
        begin = time.monotonic()
        result = registry.execute(ToolCall(name="hang", arguments={}))
        elapsed = time.monotonic() - begin
        release.set()  # let the lingering thread end promptly

        self.assertFalse(result.ok)
        self.assertTrue(result.timed_out)
        self.assertIn("timed out", result.error)
        self.assertLess(elapsed, 2.0,
                        f"timeout did not bound wall clock: {elapsed:.2f}s")

    def test_fast_call_still_succeeds(self):
        registry = ToolRegistry()
        registry.register(_tool("quick", lambda: "ok", timeout=1.0))
        result = registry.execute(ToolCall(name="quick", arguments={}))
        self.assertTrue(result.ok)
        self.assertEqual("ok", result.output)


class BoundedAuditTrailTests(unittest.TestCase):
    """F14: the decisions list grew unbounded across a long session."""

    def test_decisions_trim_to_the_recent_window(self):
        policy = PermissionPolicy()
        for i in range(1200):
            policy.decide(f"tool_{i}", {})
        self.assertLessEqual(len(policy.decisions),
                             PermissionPolicy.MAX_DECISIONS)
        # the most recent decisions survive the trim
        self.assertEqual("tool_1199", policy.decisions[-1].tool_name)


class RetryDelayTests(unittest.TestCase):
    """F13: the 429/503 retry sleep was a blind 60s block."""

    def _http_error(self, retry_after=None):
        headers = {} if retry_after is None else {"Retry-After": retry_after}
        return urllib.error.HTTPError(
            "url", 429, "quota", headers, io.BytesIO(b""))

    def test_retry_after_header_honored(self):
        self.assertEqual(7.0, _retry_delay(self._http_error("7"), 0))

    def test_retry_after_capped(self):
        self.assertEqual(_MAX_RETRY_WAIT,
                         _retry_delay(self._http_error("999"), 0))

    def test_heuristic_fallback_scales_with_attempt(self):
        self.assertEqual(5.0, _retry_delay(self._http_error(), 0))
        self.assertEqual(10.0, _retry_delay(self._http_error(), 1))

    def test_http_date_form_falls_back_to_heuristic(self):
        delay = _retry_delay(
            self._http_error("Wed, 21 Oct 2026 07:28:00 GMT"), 0)
        self.assertEqual(5.0, delay)


if __name__ == "__main__":
    unittest.main()
