"""S54 computer use tests: three-gate safety model, action log, budget.

All hermetic — FakeComputerProvider records; Windows SendInput smoke is
manual-only (moving the real cursor in CI is hostile).
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import ToolCall, ToolRegistry, Workspace
from qacompanion.agent.computer import (
    ALLOWED_ACTIONS,
    ComputerError,
    ComputerProvider,
    ComputerUseConfig,
    ComputerUseToolkit,
    FakeComputerProvider,
)
from qacompanion.agent.fs_tools import agent_registry
from qacompanion.agent.registry import ALLOW_ALL_POLICY
class ComputerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.provider = FakeComputerProvider()
        # allow everything in tests: the SAFETY tests use their own configs
        self.config = ComputerUseConfig(
            allowed_actions=frozenset(ALLOWED_ACTIONS), max_actions=10,
            screen_width=1920, screen_height=1080)
        self.toolkit = ComputerUseToolkit(self.ws, self.provider, self.config)
        self.reg = ToolRegistry()
        for tool in self.toolkit.tools():
            self.reg.register(tool)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, name, confirmer=lambda call, d: True, **arguments):
        return self.reg.execute(ToolCall(name=name, arguments=arguments),
                                workspace=self.ws, policy=ALLOW_ALL_POLICY,
                                confirmer=confirmer)

    def payload(self, name, **arguments):
        out = self.call(name, **arguments)
        self.assertTrue(out.ok, f"{name} failed: {out.error}")
        return json.loads(out.output)


class TestThreeGates(ComputerBase):
    def test_unconfigured_toolkit_denies_everything(self):
        bare = ComputerUseToolkit(self.ws, self.provider)  # default config
        reg = ToolRegistry()
        for tool in bare.tools():
            reg.register(tool)
        out = reg.execute(ToolCall(name="computer_click",
                                   arguments={"x": 10, "y": 10}),
                          workspace=self.ws, policy=ALLOW_ALL_POLICY,
                          confirmer=lambda c, d: True)
        self.assertFalse(out.ok)
        self.assertIn("not in the allow-list", out.error)
        self.assertEqual(self.provider.action_log, [])

    def test_default_engine_demands_confirmation(self):
        # S38 pipeline guarantee: requires_confirmation forces ASK under
        # the default engine — no confirmer, no action (heavily
        # restricted means every single GUI action asks first)
        reg = ToolRegistry()
        for tool in self.toolkit.tools():
            reg.register(tool)
        out = reg.execute(ToolCall(name="computer_click",
                                   arguments={"x": 10, "y": 10}),
                          workspace=self.ws, confirmer=None)
        self.assertFalse(out.ok)
        self.assertIn("no confirmer", out.error)
        self.assertEqual(self.provider.action_log, [])

    def test_confirmation_gate(self):
        out = self.call("computer_click", x=10, y=10, confirmer=None)
        self.assertFalse(out.ok)
        self.assertIn("no confirmer", out.error)
        self.assertEqual(self.provider.action_log, [])

    def test_all_three_gates_pass_action_executes(self):
        payload = self.payload("computer_click", x=100, y=200)
        self.assertEqual(payload["action"], "click")
        self.assertEqual(self.provider.action_log,
                         [{"action": "click", "x": 100, "y": 200}])


class TestAllowListAndBudget(ComputerBase):
    def test_partial_allow_list_denies_unlisted(self):
        config = ComputerUseConfig(
            allowed_actions=frozenset({"click", "type"}), max_actions=10,
            screen_width=1920, screen_height=1080)
        toolkit = ComputerUseToolkit(self.ws, self.provider, config)
        reg = ToolRegistry()
        for tool in toolkit.tools():
            reg.register(tool)
        ok = reg.execute(ToolCall(name="computer_click",
                                  arguments={"x": 1, "y": 2}),
                         workspace=self.ws, policy=ALLOW_ALL_POLICY,
                         confirmer=lambda c, d: True)
        denied = reg.execute(ToolCall(name="computer_press_keys",
                                      arguments={"keys": "ctrl+s"}),
                             workspace=self.ws, policy=ALLOW_ALL_POLICY,
                             confirmer=lambda c, d: True)
        self.assertTrue(ok.ok)
        self.assertFalse(denied.ok)
        self.assertIn("not in the allow-list", denied.error)

    def test_unknown_allow_list_action_rejected_at_config(self):
        with self.assertRaises(ValueError):
            ComputerUseConfig(allowed_actions=frozenset({"format_disk"}))

    def test_budget_exhaustion_is_structured(self):
        tight = ComputerUseConfig(
            allowed_actions=frozenset(ALLOWED_ACTIONS), max_actions=2,
            screen_width=1920, screen_height=1080)
        toolkit = ComputerUseToolkit(self.ws, self.provider, tight)
        reg = ToolRegistry()
        for tool in toolkit.tools():
            reg.register(tool)
        for _ in range(2):
            out = reg.execute(ToolCall(name="computer_click",
                                       arguments={"x": 1, "y": 1}),
                              workspace=self.ws, policy=ALLOW_ALL_POLICY,
                              confirmer=lambda c, d: True)
            self.assertTrue(out.ok)
        third = reg.execute(ToolCall(name="computer_click",
                                     arguments={"x": 1, "y": 1}),
                            workspace=self.ws, policy=ALLOW_ALL_POLICY,
                            confirmer=lambda c, d: True)
        self.assertFalse(third.ok)
        self.assertIn("budget exhausted", third.error)
        self.assertEqual(len(self.provider.action_log), 2)

    def test_bounds_error_never_clamps(self):
        out = self.call("computer_click", x=99999, y=10)
        self.assertFalse(out.ok)
        self.assertIn("outside screen", out.error)
        self.assertEqual(self.provider.action_log, [])
        negative = self.call("computer_move", x=-5, y=10)
        self.assertFalse(negative.ok)
        self.assertIn("outside screen", negative.error)


class TestActionLog(ComputerBase):
    def test_action_log_ordering(self):
        self.payload("computer_click", x=5, y=6)
        self.payload("computer_type", text="hello")
        self.payload("computer_press_keys", keys="ctrl+s")
        self.payload("computer_focus_window", title="Notepad")
        self.assertEqual(
            [a["action"] for a in self.provider.action_log],
            ["click", "type", "press_keys", "focus_window"])
        self.assertEqual(self.provider.action_log[1]["text"], "hello")
        self.assertEqual(self.provider.action_log[3]["title"], "Notepad")

    def test_double_click_and_move_logged(self):
        self.payload("computer_double_click", x=7, y=8)
        self.payload("computer_move", x=9, y=10)
        self.assertEqual(
            [a["action"] for a in self.provider.action_log],
            ["double_click", "move"])


class TestRegistration(ComputerBase):
    def test_six_tools_destructive_confirm(self):
        described = {d["name"]: d for d in self.reg.describe()}
        self.assertEqual(
            set(described),
            {"computer_click", "computer_double_click", "computer_move",
             "computer_type", "computer_press_keys",
             "computer_focus_window"},
        )
        for d in described.values():
            self.assertEqual(d["side_effect_level"], "DESTRUCTIVE")
            self.assertTrue(d["requires_confirmation"])
            self.assertTrue(d["requires_workspace"])
            self.assertEqual(d["category"], "computer")

    def test_agent_registry_includes_computer_tools(self):
        reg = agent_registry(
            self.ws, computer_provider=FakeComputerProvider(),
            computer_config=ComputerUseConfig(
                allowed_actions=frozenset(ALLOWED_ACTIONS), max_actions=5,
                screen_width=1920, screen_height=1080))
        for name in ("computer_click", "computer_type",
                     "computer_focus_window"):
            self.assertIn(name, reg.names())


if __name__ == "__main__":
    unittest.main()
