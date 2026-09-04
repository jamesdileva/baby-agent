"""S38 permission & safety tests: rule engine, confirmation flow, git verbs.

Hermetic: git verbs run against real temp repositories; the confirmation
flow uses scripted confirmer callables (the CLI/UI confirmer arrives with
S52).
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import (
    ALLOW,
    ASK,
    DENY,
    AgentLoop,
    AgentState,
    FakeModelProvider,
    ModelResponse,
    PermissionDecision,
    PermissionPolicy,
    PermissionRule,
    ToolCall,
    ToolRegistry,
    Workspace,
)
from qacompanion.agent.execution import ExecutionToolkit
from qacompanion.agent.fs_tools import FilesystemToolkit
from qacompanion.agent.git_tools import GitToolkit
from qacompanion.agent.registry import RegisteredTool, ToolDefinition
from qacompanion.agent.permissions import DEFAULT_LEVEL_DEFAULTS

GIT_CONFIG = [
    "-c", "user.name=test", "-c", "user.email=test@example.com",
    "-c", "commit.gpgsign=false",
]


def _tool(name="sample", side_effect_level="READ_ONLY", requires_confirmation=False):
    return RegisteredTool(
        definition=ToolDefinition(
            name=name, description=f"{name} test tool",
            parameters_schema={"type": "object", "properties": {}},
        ),
        handler=lambda **kw: "ok",
        side_effect_level=side_effect_level,
        requires_confirmation=requires_confirmation,
    )


class TestRuleResolution(unittest.TestCase):
    def test_exact_rule_wins_over_defaults(self):
        policy = PermissionPolicy(rules=[
            PermissionRule(tool_glob="write_file", mode=DENY, reason="no writes"),
        ])
        d = policy.decide("write_file", {}, tool=_tool("write_file"))
        self.assertEqual(d.mode, DENY)
        self.assertEqual(d.rule, "rule:write_file")
        self.assertEqual(d.reason, "no writes")

    def test_glob_rule(self):
        policy = PermissionPolicy(rules=[
            PermissionRule(tool_glob="git_*", mode=ASK, reason="git is asked"),
        ])
        self.assertEqual(policy.check("git_commit", {}, tool=_tool("git_commit")), ASK)
        self.assertEqual(policy.check("git_push", {}, tool=_tool("git_push")), ASK)
        self.assertEqual(policy.check("read_file", {}), ALLOW)

    def test_first_matching_rule_wins(self):
        policy = PermissionPolicy(rules=[
            PermissionRule(tool_glob="run_*", mode=ALLOW, reason="first"),
            PermissionRule(tool_glob="run_command", mode=DENY, reason="second"),
        ])
        d = policy.decide("run_command", {})
        self.assertEqual(d.mode, ALLOW)
        self.assertEqual(d.rule, "rule:run_*")

    def test_args_contains_rule(self):
        policy = PermissionPolicy(rules=[
            PermissionRule(tool_glob="run_command", mode=ASK,
                           reason="package installs are asked",
                           args_contains={"command": "npm install"}),
        ])
        self.assertEqual(
            policy.check("run_command", {"command": "npm install left-pad"}),
            ASK)
        self.assertEqual(
            policy.check("run_command", {"command": "npm test"}),
            ALLOW)

    def test_requires_confirmation_declares_ask(self):
        policy = PermissionPolicy()
        d = policy.decide("git_commit", {}, tool=_tool("git_commit",
                                                       requires_confirmation=True))
        self.assertEqual(d.mode, ASK)
        self.assertEqual(d.rule, "confirmation-required")

    def test_destructive_defaults_to_deny(self):
        policy = PermissionPolicy()
        d = policy.decide("delete_file", {}, tool=_tool("delete_file",
                                                        side_effect_level="DESTRUCTIVE"))
        self.assertEqual(d.mode, DENY)
        self.assertEqual(d.rule, "level:DESTRUCTIVE")

    def test_external_defaults_to_ask(self):
        policy = PermissionPolicy()
        d = policy.decide("web_search", {}, tool=_tool("web_search",
                                                       side_effect_level="EXTERNAL"))
        self.assertEqual(d.mode, ASK)

    def test_reads_default_to_allow(self):
        policy = PermissionPolicy()
        self.assertEqual(policy.check("read_file", {},
                                      tool=_tool("read_file")), ALLOW)

    def test_level_defaults_override(self):
        paranoid = PermissionPolicy(level_defaults=dict(DEFAULT_LEVEL_DEFAULTS,
                                                        EXECUTION=DENY))
        d = paranoid.decide("run_tests", {}, tool=_tool("run_tests",
                                                        side_effect_level="EXECUTION"))
        self.assertEqual(d.mode, DENY)

    def test_deny_by_default_mode(self):
        policy = PermissionPolicy(default_mode=DENY)
        self.assertEqual(policy.check("anything", {}), DENY)
        self.assertEqual(policy.check("read_file", {}, tool=_tool("read_file")),
                          ALLOW)  # level default still applies

    def test_invalid_rule_rejected(self):
        with self.assertRaises(ValueError):
            PermissionRule(tool_glob="x", mode="MAYBE")

    def test_audit_trail_records_every_decision(self):
        policy = PermissionPolicy(rules=[
            PermissionRule(tool_glob="a_*", mode=ALLOW, reason="open"),
        ])
        policy.check("a_thing", {})
        policy.check("b_thing", {}, tool=_tool("b_thing",
                                               requires_confirmation=True))
        self.assertEqual(len(policy.decisions), 2)
        self.assertEqual([d.mode for d in policy.decisions], [ALLOW, ASK])
        self.assertTrue(all(d.timestamp.endswith("Z") for d in policy.decisions))
        dumped = json.dumps(policy.audit_dicts())
        self.assertIn("rule:a_*", dumped)

    def test_decision_is_frozen_and_serializable(self):
        policy = PermissionPolicy()
        d = policy.decide("x", {})
        with self.assertRaises(Exception):
            d.mode = DENY
        self.assertEqual(d.to_dict()["tool_name"], "x")


class TestRegistryConfirmation(unittest.TestCase):
    def setUp(self):
        self.reg = ToolRegistry()
        self.reg.register(_tool("asker", requires_confirmation=True))

    def test_ask_without_confirmer_denied(self):
        result = self.reg.execute(ToolCall(name="asker", arguments={}))
        self.assertFalse(result.ok)
        self.assertIn("no confirmer", result.error)

    def test_ask_confirmer_approved_executes(self):
        seen = []
        def confirmer(call, decision):
            seen.append((call.name, decision.mode))
            return True
        result = self.reg.execute(ToolCall(name="asker", arguments={}),
                                  confirmer=confirmer)
        self.assertTrue(result.ok)
        self.assertEqual(seen, [("asker", ASK)])

    def test_ask_confirmer_denied(self):
        result = self.reg.execute(ToolCall(name="asker", arguments={}),
                                  confirmer=lambda call, d: False)
        self.assertFalse(result.ok)
        self.assertIn("denied by confirmation", result.error)

    def test_confirmer_not_called_on_allow(self):
        calls = []
        reg = ToolRegistry()
        reg.register(_tool("plain"))
        reg.execute(ToolCall(name="plain", arguments={}),
                    confirmer=lambda c, d: calls.append(1))
        self.assertEqual(calls, [])


class TestGitWriteVerbs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self._git("init", "-b", "main")
        self._git("config", "user.name", "test")
        self._git("config", "user.email", "test@example.com")
        self.reg = ToolRegistry()
        for tool in GitToolkit(self.ws).tools():
            self.reg.register(tool)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _git(self, *args):
        proc = subprocess.run(["git", *GIT_CONFIG, *args], cwd=str(self.tmp),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        return proc

    def _write(self, name, content):
        (self.tmp / name).write_text(content, encoding="utf-8")

    def call(self, name, confirmer=lambda call, d: True, **arguments):
        return self.reg.execute(ToolCall(name=name, arguments=arguments),
                                workspace=self.ws, confirmer=confirmer)

    def payload(self, name, **kwargs):
        out = self.call(name, **kwargs)
        self.assertTrue(out.ok, f"{name} failed: {out.error}")
        return json.loads(out.output)

    def test_add_stages_file(self):
        self._git("add", ".")
        self._git("commit", "-m", "init")
        self._write("app.py", "v2\n")
        payload = self.payload("git_add", path="app.py")
        self.assertEqual(payload["staged"], "app.py")
        status = json.loads(self.call("git_status").output)
        self.assertFalse(status["clean"])

    def test_commit_requires_confirmation(self):
        out = self.call("git_commit", confirmer=None, message="x")
        self.assertFalse(out.ok)
        self.assertIn("no confirmer", out.error)

    def test_commit_with_approval(self):
        self._write("a.txt", "one\n")
        self._git("add", ".")
        payload = self.payload("git_commit", message="first commit")
        self.assertTrue(payload["committed"])
        self.assertTrue(payload["hash"])
        self.assertEqual(payload["branch"], "main")
        log = json.loads(self.call("git_log").output)
        self.assertEqual(log["entries"][0]["subject"], "first commit")
        status = json.loads(self.call("git_status").output)
        self.assertTrue(status["clean"])

    def test_commit_denied_by_confirmer(self):
        self._write("a.txt", "one\n")
        self._git("add", ".")
        out = self.call("git_commit", confirmer=lambda c, d: False,
                        message="should not happen")
        self.assertFalse(out.ok)
        self.assertIn("denied by confirmation", out.error)
        # no commit exists: rev-parse HEAD fails in a repo without commits
        self.assertNotEqual(self._git("rev-parse", "HEAD").returncode, 0)

    def test_commit_nothing_to_commit_is_honest(self):
        self._git("add", ".")
        self._git("commit", "-m", "empty init")
        payload = self.payload("git_commit", message="nothing?")
        self.assertFalse(payload["committed"])
        self.assertIn("nothing", payload["reason"])

    def test_commit_missing_message_rejected(self):
        out = self.call("git_commit", message="   ")
        self.assertFalse(out.ok)
        self.assertIn("non-empty", out.error)

    def test_add_escape_rejected(self):
        out = self.call("git_add", path="../outside.txt")
        self.assertFalse(out.ok)
        self.assertTrue(out.error)


class TestLoopConfirmation(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.reg = ToolRegistry()
        for tool in GitToolkit(self.ws).tools():
            self.reg.register(tool)
        for tool in FilesystemToolkit(self.ws).tools():
            self.reg.register(tool)
        for tool in ExecutionToolkit(self.ws).tools():
            self.reg.register(tool)
        self._git("init", "-b", "main")
        self._git("config", "user.name", "test")
        self._git("config", "user.email", "test@example.com")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _git(self, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                               *args], cwd=str(self.tmp), capture_output=True)

    def call(self, name, confirmer=lambda call, d: True, **arguments):
        return self.reg.execute(ToolCall(name=name, arguments=arguments),
                                workspace=self.ws, confirmer=confirmer)

    def test_confirmed_commit_through_the_loop(self):
        approvals = []

        def confirmer(call, decision):
            approvals.append(call.name)
            return True

        provider = FakeModelProvider([
            ToolCall(name="write_file", arguments={"path": "note.txt",
                                                   "content": "v1"}),
            ToolCall(name="git_add", arguments={"path": "note.txt"}),
            ToolCall(name="git_commit", arguments={"message": "add note"}),
            ModelResponse(text="Committed the note.", finish_reason="stop"),
        ])
        loop = AgentLoop(provider, self.reg, self.ws, confirmer=confirmer)
        session = loop.run("write a note and commit it")

        self.assertEqual(session.state, AgentState.COMPLETED)
        self.assertEqual(approvals, ["git_commit"])  # only the ASK verb
        self.assertEqual(len(session.tool_calls), 3)
        commit_obs = session.observations[2]
        self.assertIn('"committed": true', commit_obs.output)
        log = json.loads(self.call("git_log").output)
        self.assertEqual(log["entries"][0]["subject"], "add note")

    def test_denied_commit_feeds_back_to_model(self):
        provider = FakeModelProvider([
            ToolCall(name="write_file", arguments={"path": "note.txt",
                                                   "content": "v1"}),
            ToolCall(name="git_add", arguments={"path": "note.txt"}),
            ToolCall(name="git_commit", arguments={"message": "sneak in"}),
            ModelResponse(text="The commit was denied; stopping.",
                          finish_reason="stop"),
        ])
        loop = AgentLoop(provider, self.reg, self.ws,
                         confirmer=lambda call, d: False)
        session = loop.run("write and commit")
        self.assertEqual(session.state, AgentState.COMPLETED)
        self.assertIn("denied by confirmation", session.observations[2].error)
        # no commit exists: rev-parse HEAD fails in a repo without commits
        self.assertNotEqual(self._git("rev-parse", "HEAD").returncode, 0)


if __name__ == "__main__":
    unittest.main()
