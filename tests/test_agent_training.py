"""S63 training dataset pipeline tests: curated-only source, the
verified-success eligibility gate, and the roadmap's literal
verification — a completed coding session exports as a valid structured
training record (hermetic benchmark run through the full chain).
"""

import json
import tempfile
import unittest
from pathlib import Path

from qacompanion.agent import (
    AgentSession,
    AgentState,
    FakeModelProvider,
    ModelMessage,
    ModelResponse,
    ToolCall,
    ToolResult,
)
from qacompanion.agent.benchmark import run_benchmark
from qacompanion.agent.curation import TrajectoryCurator
from qacompanion.agent.experience import ExperienceStore
from qacompanion.agent.session_learning import session_to_experience
from qacompanion.agent.training import (
    TrainingError, build_training, build_records, format_tool_call)

PY = f'"{__import__("sys").executable}"'


def _curated_row(**kw):
    row = {
        "experience_id": "exp1", "session_id": "s1", "source": "opencode",
        "goal": "fix the widget", "outcome": "partial",
        "classification": "PARTIAL", "verdict": "ACCEPT",
        "score": {"overall": 0.6, "dimensions": {}, "unknown_dims": []},
        "hard_flags": [], "penalties": [], "reasons": [],
        "confidence": 0.3, "times_seen": 1, "diversity_score": 0.5,
        "actions": ["read_file", "edit_file"],
        "failure": None, "diagnosis": None, "resolution": None,
        "verification": {}, "steps": [], "final_answer": None,
    }
    row.update(kw)
    return row


def _write_curated(tmp: Path, rows) -> Path:
    curated = Path(tmp) / "curated"
    curated.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(r) + "\n" for r in rows)
    (curated / "trajectory.jsonl").write_text(payload, encoding="utf-8")
    return curated


def _eligible_row(**kw):
    return _curated_row(
        outcome="success", classification="SUCCESS",
        verification={"attempts": [{"ok": True}]},
        steps=[{"tool": "read_file", "args": {"path": "w.py"},
                "ok": True, "result_head": "def add(a, b):"},
               {"tool": "edit_file",
                "args": {"path": "w.py", "old_string": "a - b",
                         "new_string": "a + b"},
                "ok": True, "result_head": "edit applied"}],
        actions=["read_file", "edit_file"],
        final_answer="Fixed and verified.", **kw)


class FormatToolCallTests(unittest.TestCase):
    def test_strings_numbers_and_bools(self):
        call = format_tool_call(
            "write_file", {"path": "a.py", "count": 2, "force": True})
        self.assertEqual('[TOOL: write_file(path="a.py", count=2, '
                         'force=true)]', call)

    def test_string_escaping(self):
        call = format_tool_call("write_file",
                                {"content": 'say "hi" \\ ok'})
        self.assertIn(r'"say \"hi\" \\ ok"', call)


class EligibilityGateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def _build(self, rows):
        curated = _write_curated(self.tmp, rows)
        return build_records(curated_dir=curated)

    def test_verified_success_is_eligible_and_step_trainable(self):
        record = self._build([_eligible_row()])[0]
        self.assertTrue(record.eligible, record.eligibility_reasons)
        self.assertEqual("successful", record.trajectory_class)
        self.assertIsNotNone(record.chat)

    def test_mined_partial_never_eligible(self):
        record = self._build([_curated_row()])[0]
        self.assertFalse(record.eligible)
        self.assertTrue(any("not successful" in r
                            for r in record.eligibility_reasons))
        self.assertIsNone(record.chat)

    def test_success_without_verification_evidence_excluded(self):
        record = self._build([_curated_row(
            outcome="success", classification="SUCCESS")])[0]
        self.assertFalse(record.eligible)
        self.assertTrue(any("verification evidence" in r
                            for r in record.eligibility_reasons))

    def test_review_verdict_excluded_even_when_successful(self):
        record = self._build([_eligible_row(verdict="REVIEW",
                                            confidence=0.3)])[0]
        self.assertFalse(record.eligible)
        self.assertTrue(any("REVIEW" in r
                            for r in record.eligibility_reasons))

    def test_invalid_classification_skipped_entirely(self):
        records = self._build([_curated_row(classification="INVALID",
                                            verdict="REJECT"),
                               _eligible_row()])
        self.assertEqual(1, len(records))

    def test_recovered_class_carries_failure_pair(self):
        record = self._build([_curated_row(
            outcome="recovered", classification="RECOVERED",
            failure="TypeError: x", resolution="fix applied",
            verdict="ACCEPT")])[0]
        self.assertEqual("recovered", record.trajectory_class)
        self.assertEqual("TypeError: x", record.failure)
        self.assertFalse(record.eligible)

    def test_inefficient_flag_from_efficiency_penalties(self):
        record = self._build([_eligible_row(penalties=[
            {"dimension": "efficiency", "reason": "repeated"}])])[0]
        self.assertTrue(record.inefficient)


class ChatRecordTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_chat_teaches_the_runtime_protocol(self):
        record = build_records(
            curated_dir=_write_curated(self.tmp, [_eligible_row()]))[0]
        chat = record.chat
        messages = chat["messages"]
        self.assertEqual("system", messages[0]["role"])
        self.assertIn("[TOOL: tool_name(", messages[0]["content"])
        self.assertEqual("fix the widget", messages[1]["content"])
        self.assertEqual("assistant", messages[2]["role"])
        self.assertEqual('[TOOL: read_file(path="w.py")]',
                         messages[2]["content"])
        self.assertEqual("def add(a, b):", messages[3]["content"])
        # the conversation ends with the captured final answer
        self.assertEqual("assistant", messages[-1]["role"])
        self.assertEqual("Fixed and verified.", messages[-1]["content"])

    def test_eligible_without_steps_is_not_step_trainable(self):
        record = build_records(curated_dir=_write_curated(self.tmp, [
            _curated_row(outcome="success", classification="SUCCESS",
                         verification={"attempts": [{"ok": True}]})]))[0]
        self.assertTrue(record.eligible)
        self.assertIsNone(record.chat)


class BuildTrainingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_exports_and_report(self):
        curated = _write_curated(self.tmp, [_eligible_row(),
                                            _curated_row()])
        out = self.tmp / "training"
        report = build_training(curated_dir=curated, out_dir=out)
        self.assertEqual(2, report["trajectories"])
        self.assertEqual(1, report["eligible"])
        self.assertEqual(1, report["step_trainable"])
        rows = [json.loads(l) for l in
                (out / "trajectories.jsonl").read_text(
                    encoding="utf-8").splitlines() if l]
        self.assertEqual(2, len(rows))
        chat_rows = [json.loads(l) for l in
                     (out / "training.jsonl").read_text(
                         encoding="utf-8").splitlines() if l]
        self.assertEqual(1, len(chat_rows))
        self.assertIn("messages", chat_rows[0])
        self.assertTrue((out / "report.json").exists())

    def test_dry_run_writes_nothing(self):
        curated = _write_curated(self.tmp, [_eligible_row()])
        report = build_training(curated_dir=curated,
                                out_dir=self.tmp / "training",
                                dry_run=True)
        self.assertTrue(report["dry_run"])
        self.assertFalse((self.tmp / "training").exists())

    def test_missing_curated_export_is_structured_error(self):
        with self.assertRaises(TrainingError):
            build_records(curated_dir=self.tmp / "nowhere")

    def test_honest_notes_when_nothing_eligible(self):
        curated = _write_curated(self.tmp, [_curated_row()])
        report = build_training(curated_dir=curated,
                                out_dir=self.tmp / "training")
        self.assertEqual(0, report["eligible"])
        self.assertTrue(any("no verified-success" in n
                            for n in report["notes"]))


class CaptureUpgradeTests(unittest.TestCase):
    """S63 additive capture: step data + final answer, actions unchanged."""

    def _session(self):
        session = AgentSession(goal="fix the widget")
        session.tool_calls = [
            ToolCall(name="read_file", arguments={"path": 'a b"c'}),
            ToolCall(name="run_tests", arguments={"command": PY}),
        ]
        session.observations = [
            ToolResult(call_name="read_file", ok=True,
                       output="def add(a, b):\n    return a + b"),
            ToolResult(call_name="run_tests", ok=True, output="OK"),
        ]
        session.messages = [
            ModelMessage(role="system", content="sys"),
            ModelMessage(role="assistant",
                         content='[TOOL: read_file(path="a b\\"c")]'),
            ModelMessage(role="assistant", content="All tests pass."),
        ]
        session.verification_results = [{"ok": True}]
        session.state = AgentState.COMPLETED
        return session

    def test_step_capture_with_json_safe_args(self):
        exp = session_to_experience(self._session(), model="fake")
        steps = exp.context["tool_calls"]
        self.assertEqual(2, len(steps))
        self.assertEqual({"path": 'a b"c'}, steps[0]["args"])
        self.assertEqual("def add(a, b):", steps[0]["result_head"])
        self.assertTrue(steps[1]["ok"])
        self.assertEqual("All tests pass.", exp.context["final_answer"])
        # S50 compatibility: actions stay tool NAMES
        self.assertEqual(["read_file", "run_tests"], exp.actions)
        # verified first attempt: honest success outcome
        self.assertEqual("success", exp.outcome)

    def test_final_answer_prefers_session_final_result(self):
        session = self._session()
        session.final_result = "Done: widget fixed and verified."
        exp = session_to_experience(session, model="fake")
        self.assertEqual("Done: widget fixed and verified.",
                         exp.context["final_answer"])

    def test_final_answer_skips_tool_call_messages(self):
        session = self._session()
        session.final_result = None
        session.messages = session.messages[:-1] + [
            ModelMessage(role="assistant",
                         content='[TOOL: run_tests(command="x")]')]
        exp = session_to_experience(session, model="fake")
        self.assertIsNone(exp.context["final_answer"])


class EndToEndTests(unittest.TestCase):
    """The roadmap's literal S63 verification: a completed coding
    session exports as a valid structured training record — hermetic
    benchmark run through record -> curate -> build-training."""

    def _success_script(self):
        return [
            ToolCall(name="read_file", arguments={"path": "calculator.py"}),
            ToolCall(name="run_tests",
                     arguments={"command": f"{PY} -m unittest"}),
            ToolCall(name="edit_file", arguments={
                "path": "calculator.py",
                "old_string": "    return a - b",
                "new_string": "    return a + b",
            }),
            ToolCall(name="run_tests",
                     arguments={"command": f"{PY} -m unittest"}),
            ModelResponse(text="The add() function subtracted instead of "
                               "adding. Fixed and verified: 2 tests pass.",
                          finish_reason="stop"),
        ]

    def test_benchmark_session_becomes_training_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ExperienceStore(Path(tmp) / "exp.jsonl")
            report = run_benchmark(FakeModelProvider(self._success_script()),
                                   experience_store=store)
            self.assertTrue(report.success, report.termination_reason)
            curated = Path(tmp) / "curated"
            TrajectoryCurator(store).curate(out_dir=curated)
            training = build_training(curated_dir=curated,
                                      out_dir=Path(tmp) / "training")
            self.assertEqual(1, training["eligible"])
            self.assertEqual(1, training["step_trainable"])
            chat = json.loads((Path(tmp) / "training" / "training.jsonl")
                              .read_text(encoding="utf-8"))
            messages = chat["messages"]
            self.assertIn("[TOOL:", messages[0]["content"])
            assistants = [m for m in messages if m["role"] == "assistant"]
            self.assertIn("[TOOL: read_file(", assistants[0]["content"])
            self.assertTrue(any("Fixed and verified" in m["content"]
                                for m in assistants))


if __name__ == "__main__":
    unittest.main()
