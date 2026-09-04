"""S39 event stream tests: envelope, stream mechanics, full loop sequences.

Hermetic: fake providers script everything; real workspace tools only.
"""

import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from qacompanion.agent import (
    AgentConfig,
    AgentLoop,
    AgentState,
    Event,
    EventStream,
    FakeModelProvider,
    ModelResponse,
    PermissionPolicy,
    PermissionRule,
    ToolCall,
    ToolRegistry,
    Workspace,
)
from qacompanion.agent.fs_tools import FilesystemToolkit
from qacompanion.agent.registry import RegisteredTool, ToolDefinition

DENY = "DENY"


class EventTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.reg = ToolRegistry()
        for tool in FilesystemToolkit(self.ws).tools():
            self.reg.register(tool)
        self.stream = EventStream()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_scripted(self, script, **loop_kwargs):
        loop = AgentLoop(FakeModelProvider(script), self.reg, self.ws,
                         events=self.stream, **loop_kwargs)
        return loop.run("write a.txt")


class TestEventEnvelope(unittest.TestCase):
    def test_fields_and_frozen(self):
        e = Event(seq=0, event_id="abc", session_id="s", timestamp="2026-09-04T00:00:00Z",
                  event_type="session_started", payload={"goal": "g"})
        self.assertEqual(e.seq, 0)
        with self.assertRaises(Exception):
            e.seq = 5

    def test_to_dict_shape(self):
        e = Event(seq=1, event_id="abc", session_id="s", timestamp="t",
                  event_type="x", payload={"k": "v"})
        d = e.to_dict()
        self.assertEqual(
            set(d.keys()),
            {"seq", "event_id", "session_id", "timestamp", "event_type", "payload"},
        )


class TestEventStream(unittest.TestCase):
    def test_subscribe_and_delivery(self):
        stream = EventStream()
        seen = []
        stream.subscribe(seen.append)
        event = stream.emit("tool_completed", "s1", {"tool": "x"})
        self.assertEqual(seen, [event])
        self.assertEqual(stream.types(), ["tool_completed"])

    def test_multiple_subscribers_and_unsubscribe(self):
        stream = EventStream()
        a, b = [], []
        stream.subscribe(a.append)
        stream.subscribe(b.append)
        stream.emit("e", "s", {})
        stream.unsubscribe(b.append)
        stream.emit("e", "s", {})
        self.assertEqual(len(a), 2)
        self.assertEqual(len(b), 1)

    def test_seq_is_monotonic(self):
        stream = EventStream()
        e0 = stream.emit("a", "s", {})
        e1 = stream.emit("b", "s", {})
        self.assertEqual((e0.seq, e1.seq), (0, 1))

    def test_event_ids_unique(self):
        stream = EventStream()
        ids = {stream.emit("e", "s", {}).event_id for _ in range(20)}
        self.assertEqual(len(ids), 20)

    def test_history_bounded(self):
        stream = EventStream(history_maxlen=5)
        for i in range(8):
            stream.emit("e", "s", {"i": i})
        self.assertEqual(len(stream.events), 5)
        self.assertEqual(stream.events[0].payload["i"], 3)

    def test_raising_subscriber_never_breaks_emission(self):
        stream = EventStream()
        def bad(event):
            raise RuntimeError("ui exploded")
        seen = []
        stream.subscribe(bad)
        stream.subscribe(seen.append)
        stream.emit("e", "s", {})
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(stream.subscriber_errors), 1)
        self.assertIn("ui exploded", stream.subscriber_errors[0])


class TestLoopEventSequence(EventTestBase):
    def test_full_sequence_for_simple_successful_run(self):
        # the roadmap verification: a test session emits the expected
        # complete event sequence
        script = [
            ToolCall(name="write_file", arguments={"path": "a.txt",
                                                   "content": "data"}),
            ModelResponse(text="wrote it", finish_reason="stop"),
        ]

        def verifier(session):
            return True, "file present"

        self.run_scripted(script, verifier=verifier)

        self.assertEqual(
            self.stream.types(),
            [
                "session_started",
                "session_state_changed",      # PLANNING
                "session_state_changed",      # RUNNING
                "model_started",              # iteration 1: tool turn
                "model_response",
                "tool_requested",
                "tool_completed",
                "file_changed",
                "model_started",              # iteration 2: final answer
                "model_response",
                "session_state_changed",      # VERIFYING
                "verification_started",
                "verification_completed",
                "session_state_changed",      # COMPLETED
                "session_completed",
            ],
        )
        started = self.stream.events[0]
        self.assertEqual(started.payload["goal"], "write a.txt")
        completed = self.stream.events[-1]
        self.assertEqual(completed.payload["termination_reason"], "goal completed")
        changed = next(e for e in self.stream.events
                       if e.event_type == "file_changed")
        self.assertEqual(changed.payload["path"], "a.txt")

    def test_denial_path_events(self):
        policy = PermissionPolicy(rules=[
            PermissionRule(tool_glob="write_file", mode=DENY, reason="no writes"),
        ])
        script = [
            ToolCall(name="write_file", arguments={"path": "a.txt",
                                                   "content": "x"}),
            ModelResponse(text="I was denied; stopping.", finish_reason="stop"),
        ]
        self.run_scripted(script, policy=policy)

        types = self.stream.types()
        self.assertIn("permission_denied", types)
        self.assertIn("tool_failed", types)
        self.assertIn("failure_detected", types)
        denied = next(e for e in self.stream.events
                      if e.event_type == "permission_denied")
        self.assertEqual(denied.payload["tool"], "write_file")
        self.assertEqual(denied.payload["rule"], "rule:write_file")

    def test_confirmation_events_granted(self):
        policy = PermissionPolicy(rules=[
            PermissionRule(tool_glob="write_file", mode="ASK", reason="ask first"),
        ])
        script = [
            ToolCall(name="write_file", arguments={"path": "a.txt",
                                                   "content": "x"}),
            ModelResponse(text="approved and written", finish_reason="stop"),
        ]
        self.run_scripted(script, policy=policy, confirmer=lambda c, d: True)

        types = self.stream.types()
        self.assertIn("permission_requested", types)
        self.assertIn("permission_granted", types)
        self.assertNotIn("permission_denied", types)

    def test_confirmation_events_denied(self):
        policy = PermissionPolicy(rules=[
            PermissionRule(tool_glob="write_file", mode="ASK", reason="ask first"),
        ])
        script = [
            ToolCall(name="write_file", arguments={"path": "a.txt",
                                                   "content": "x"}),
            ModelResponse(text="denied; stopping.", finish_reason="stop"),
        ]
        self.run_scripted(script, policy=policy, confirmer=lambda c, d: False)

        types = self.stream.types()
        self.assertIn("permission_requested", types)
        self.assertIn("permission_denied", types)
        self.assertNotIn("permission_granted", types)

    def test_recovery_path_events(self):
        attempts = {"n": 0}

        def verifier(session):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return False, "not good enough"
            return True, "good now"

        script = [
            ModelResponse(text="done?", finish_reason="stop"),
            ModelResponse(text="now done", finish_reason="stop"),
        ]
        self.run_scripted(script, verifier=verifier)

        types = self.stream.types()
        self.assertIn("verification_started", types)
        self.assertIn("verification_completed", types)
        self.assertIn("recovery_started", types)
        recovery_index = types.index("recovery_started")
        self.assertEqual(types[recovery_index - 1], "session_state_changed")
        recovering = next(e for e in self.stream.events
                          if e.event_type == "recovery_started")
        self.assertEqual(recovering.payload["attempt"], 1)

    def test_cancellation_event(self):
        event = threading.Event()

        def tripwire(**kwargs):
            event.set()
            return "tripped"

        self.reg.register(RegisteredTool(
            definition=ToolDefinition(
                name="tripwire", description="d",
                parameters_schema={"type": "object", "properties": {}}),
            handler=tripwire,
        ))
        script = [
            ToolCall(name="tripwire", arguments={}),
            ModelResponse(text="never", finish_reason="stop"),
        ]
        self.run_scripted(script, cancel_event=event)

        self.assertEqual(self.stream.types()[-1], "session_cancelled")
        self.assertEqual(
            self.stream.events[-1].payload["termination_reason"],
            "cancelled by user",
        )

    def test_subscriber_crash_does_not_break_the_run(self):
        def bad(event):
            raise ValueError("evaluator bug")

        self.stream.subscribe(bad)
        script = [
            ToolCall(name="write_file", arguments={"path": "a.txt",
                                                   "content": "x"}),
            ModelResponse(text="done", finish_reason="stop"),
        ]
        session = self.run_scripted(script)
        self.assertEqual(session.state, AgentState.COMPLETED)
        self.assertGreater(len(self.stream.subscriber_errors), 0)

    def test_tool_completed_payload(self):
        script = [
            ToolCall(name="write_file", arguments={"path": "a.txt",
                                                   "content": "x"}),
            ModelResponse(text="done", finish_reason="stop"),
        ]
        self.run_scripted(script)
        completed = next(e for e in self.stream.events
                         if e.event_type == "tool_completed")
        self.assertEqual(completed.payload["tool"], "write_file")
        self.assertIsInstance(completed.payload["duration_ms"], int)
        self.assertEqual(completed.payload["changed_path"], "a.txt")


if __name__ == "__main__":
    unittest.main()
