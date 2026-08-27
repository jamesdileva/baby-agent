"""Tests for qacompanion.task — strict loading, add, list, validation."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from qacompanion import task

VALID_TASK = {
    "id": 0,
    "title": "Write spec",
    "status": "todo",
    "created": "2026-08-26T00:00:00Z",
    "done_at": None,
}


def write_store(tmp, text):
    path = Path(tmp) / "tasks.jsonl"
    path.write_bytes(text.encode("utf-8"))
    return path


def task_json(**overrides):
    t = dict(VALID_TASK)
    t.update(overrides)
    return json.dumps(t)


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


class LoadTests(TempDirTest):
    def test_load_valid_task(self):
        path = write_store(self.tmp, task_json() + "\n")
        tasks = task.TaskStore(path).load()
        self.assertEqual(1, len(tasks))
        self.assertEqual("Write spec", tasks[0]["title"])

    def test_missing_file_loads_empty(self):
        self.assertEqual([], task.TaskStore(self.tmp / "absent.jsonl").load())

    def test_bom_prefix_is_stripped(self):
        path = write_store(self.tmp, "\ufeff" + task_json() + "\n")
        tasks = task.TaskStore(path).load()
        self.assertEqual([0], [t["id"] for t in tasks])

    def test_crlf_line_endings_tolerated(self):
        path = write_store(self.tmp, task_json() + "\r\n" + task_json(id=1) + "\r\n")
        tasks = task.TaskStore(path).load()
        self.assertEqual([0, 1], [t["id"] for t in tasks])

    def test_missing_trailing_newline_tolerated(self):
        path = write_store(self.tmp, task_json())
        tasks = task.TaskStore(path).load()
        self.assertEqual([0], [t["id"] for t in tasks])

    def test_blank_lines_skipped(self):
        path = write_store(self.tmp, "\n" + task_json() + "\n\n")
        self.assertEqual(1, len(task.TaskStore(path).load()))

    def test_malformed_json_names_line_number(self):
        path = write_store(self.tmp, task_json() + "\n{not json}\n")
        with self.assertRaises(ValueError) as ctx:
            task.TaskStore(path).load()
        self.assertIn("line 2", str(ctx.exception))

    def test_non_object_line_rejected(self):
        path = write_store(self.tmp, "[1, 2]\n")
        with self.assertRaises(ValueError) as ctx:
            task.TaskStore(path).load()
        self.assertIn("line 1", str(ctx.exception))

    def test_non_int_id_rejected(self):
        path = write_store(self.tmp, task_json(id="7") + "\n")
        with self.assertRaises(ValueError) as ctx:
            task.TaskStore(path).load()
        self.assertIn("'id'", str(ctx.exception))

    def test_boolean_id_rejected_even_though_bool_is_int(self):
        path = write_store(self.tmp, task_json(id=True) + "\n")
        with self.assertRaises(ValueError):
            task.TaskStore(path).load()

    def test_missing_title_rejected(self):
        broken = {k: v for k, v in VALID_TASK.items() if k != "title"}
        path = write_store(self.tmp, json.dumps(broken) + "\n")
        with self.assertRaises(ValueError) as ctx:
            task.TaskStore(path).load()
        self.assertIn("title", str(ctx.exception))

    def test_empty_title_rejected(self):
        path = write_store(self.tmp, task_json(title="") + "\n")
        with self.assertRaises(ValueError) as ctx:
            task.TaskStore(path).load()
        self.assertIn("non-empty", str(ctx.exception))

    def test_invalid_status_rejected(self):
        path = write_store(self.tmp, task_json(status="pending") + "\n")
        with self.assertRaises(ValueError) as ctx:
            task.TaskStore(path).load()
        self.assertIn("todo", str(ctx.exception))

    def test_non_string_title_rejected(self):
        path = write_store(self.tmp, task_json(title=42) + "\n")
        with self.assertRaises(ValueError):
            task.TaskStore(path).load()

    def test_unparseable_created_rejected(self):
        path = write_store(self.tmp, task_json(created="yesterday") + "\n")
        with self.assertRaises(ValueError) as ctx:
            task.TaskStore(path).load()
        self.assertIn("line 1", str(ctx.exception))

    def test_done_at_non_string_rejected(self):
        path = write_store(self.tmp, task_json(status="done", done_at=123) + "\n")
        with self.assertRaises(ValueError) as ctx:
            task.TaskStore(path).load()
        self.assertIn("done_at", str(ctx.exception))

    def test_done_at_bad_format_rejected(self):
        path = write_store(self.tmp, task_json(status="done", done_at="not-a-date") + "\n")
        with self.assertRaises(ValueError) as ctx:
            task.TaskStore(path).load()
        self.assertIn("line 1", str(ctx.exception))

    def test_valid_done_task_accepted(self):
        t = dict(VALID_TASK, id=1, status="done", done_at="2026-08-26T12:00:00Z")
        path = write_store(self.tmp, json.dumps(t) + "\n")
        tasks = task.TaskStore(path).load()
        self.assertEqual("done", tasks[0]["status"])

    def test_negative_id_rejected(self):
        path = write_store(self.tmp, task_json(id=-1) + "\n")
        with self.assertRaises(ValueError) as ctx:
            task.TaskStore(path).load()
        self.assertIn(">= 0", str(ctx.exception))

    def test_ids_must_strictly_increase(self):
        path = write_store(self.tmp, task_json(id=1) + "\n" + task_json(id=1) + "\n")
        with self.assertRaises(ValueError) as ctx:
            task.TaskStore(path).load()
        self.assertIn("line 2", str(ctx.exception))


class AddTests(TempDirTest):
    def test_add_creates_task_with_todo_status(self):
        path = self.tmp / "tasks.jsonl"
        t = task.TaskStore(path).add("Buy milk")
        self.assertEqual("Buy milk", t["title"])
        self.assertEqual("todo", t["status"])
        self.assertIsNone(t["done_at"])
        self.assertEqual(0, t["id"])

    def test_add_persists_to_file(self):
        path = self.tmp / "tasks.jsonl"
        task.TaskStore(path).add("Task A")
        task.TaskStore(path).add("Task B")
        tasks = task.TaskStore(path).load()
        self.assertEqual(2, len(tasks))
        self.assertEqual("Task A", tasks[0]["title"])
        self.assertEqual("Task B", tasks[1]["title"])

    def test_add_assigns_increasing_ids(self):
        path = self.tmp / "tasks.jsonl"
        t1 = task.TaskStore(path).add("First")
        t2 = task.TaskStore(path).add("Second")
        self.assertEqual(0, t1["id"])
        self.assertEqual(1, t2["id"])

    def test_add_explicit_now_overrides_clock(self):
        path = self.tmp / "tasks.jsonl"
        fixed = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        t = task.TaskStore(path).add("Timed", now=fixed)
        self.assertEqual("2026-01-02T03:04:05Z", t["created"])

    def test_add_stamp_is_iso_utc_z(self):
        path = self.tmp / "tasks.jsonl"
        t = task.TaskStore(path).add("Check stamp")
        parsed = datetime.fromisoformat(t["created"].replace("Z", "+00:00"))
        self.assertIsNotNone(parsed.tzinfo)


class ListTests(TempDirTest):
    def test_list_empty_store(self):
        path = self.tmp / "tasks.jsonl"
        self.assertEqual([], task.TaskStore(path).list_all())

    def test_list_todo_before_done(self):
        path = self.tmp / "tasks.jsonl"
        store = task.TaskStore(path)
        store.add("Todo task")
        done_task = store.add("Done task")
        store.mark_done(done_task["id"])
        result = store.list_all()
        self.assertEqual(2, len(result))
        self.assertEqual("Todo task", result[0]["title"])
        self.assertEqual("Done task", result[1]["title"])

    def test_list_preserves_id_order_within_status(self):
        path = self.tmp / "tasks.jsonl"
        store = task.TaskStore(path)
        store.add("A")
        store.add("B")
        store.add("C")
        result = store.list_all()
        self.assertEqual(["A", "B", "C"], [t["title"] for t in result])


class MarkDoneTests(TempDirTest):
    def test_mark_done_sets_status_and_done_at(self):
        path = self.tmp / "tasks.jsonl"
        store = task.TaskStore(path)
        t = store.add("Do this")
        result = store.mark_done(t["id"])
        self.assertEqual("done", result["status"])
        self.assertIsNotNone(result["done_at"])

    def test_mark_done_persists(self):
        path = self.tmp / "tasks.jsonl"
        store = task.TaskStore(path)
        t = store.add("Persist me")
        store.mark_done(t["id"])
        tasks = task.TaskStore(path).load()
        self.assertEqual("done", tasks[0]["status"])

    def test_mark_done_already_done_raises(self):
        path = self.tmp / "tasks.jsonl"
        store = task.TaskStore(path)
        t = store.add("Double done")
        store.mark_done(t["id"])
        with self.assertRaises(ValueError) as ctx:
            store.mark_done(t["id"])
        self.assertIn("already done", str(ctx.exception))

    def test_mark_done_unknown_id_raises(self):
        path = self.tmp / "tasks.jsonl"
        store = task.TaskStore(path)
        with self.assertRaises(ValueError) as ctx:
            store.mark_done(999)
        self.assertIn("999", str(ctx.exception))


class DeleteTests(TempDirTest):
    def test_delete_removes_task(self):
        path = self.tmp / "tasks.jsonl"
        store = task.TaskStore(path)
        t = store.add("Delete me")
        store.delete(t["id"])
        self.assertEqual([], task.TaskStore(path).load())

    def test_delete_unknown_id_raises(self):
        path = self.tmp / "tasks.jsonl"
        store = task.TaskStore(path)
        with self.assertRaises(ValueError) as ctx:
            store.delete(999)
        self.assertIn("999", str(ctx.exception))


class ShowTests(TempDirTest):
    def test_show_returns_full_task(self):
        path = self.tmp / "tasks.jsonl"
        store = task.TaskStore(path)
        t = store.add("Show me")
        result = store.show(t["id"])
        self.assertEqual("Show me", result["title"])
        self.assertEqual("todo", result["status"])

    def test_show_unknown_id_raises(self):
        path = self.tmp / "tasks.jsonl"
        store = task.TaskStore(path)
        with self.assertRaises(ValueError) as ctx:
            store.show(999)
        self.assertIn("999", str(ctx.exception))


class SerializeTests(unittest.TestCase):
    def test_serialize_produces_newline_terminated_lines(self):
        tasks = [dict(VALID_TASK, id=0), dict(VALID_TASK, id=1, title="B")]
        result = task.serialize(tasks)
        lines = result.strip().split("\n")
        self.assertEqual(2, len(lines))

    def test_serialize_sorts_by_id(self):
        tasks = [dict(VALID_TASK, id=5), dict(VALID_TASK, id=1)]
        result = task.serialize(tasks)
        first_id = json.loads(result.split("\n")[0])["id"]
        self.assertEqual(1, first_id)


class AtomicWriteTests(TempDirTest):
    def test_corrupt_load_does_not_clobber_existing(self):
        good_text = task_json() + "\n"
        path = write_store(self.tmp, good_text + "{corrupt}\n")
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            task.TaskStore(path).load()
        self.assertEqual(before, path.read_bytes())


class EnvOverrideTests(TempDirTest):
    def test_default_path_prefers_env_override(self):
        override = self.tmp / "override.jsonl"
        with mock.patch.dict(os.environ, {task.ENV_OVERRIDE: str(override)}):
            self.assertEqual(override, task.default_path())
            self.assertEqual(override, task.TaskStore().path)

    def test_explicit_path_beats_env_override(self):
        override = self.tmp / "override.jsonl"
        explicit = self.tmp / "explicit.jsonl"
        with mock.patch.dict(os.environ, {task.ENV_OVERRIDE: str(override)}):
            self.assertEqual(explicit, task.TaskStore(explicit).path)


class UnicodeTests(TempDirTest):
    def test_emoji_title_round_trips(self):
        path = self.tmp / "tasks.jsonl"
        store = task.TaskStore(path)
        t = store.add("Fix the \U0001f4a9 bug")
        loaded = task.TaskStore(path).load()
        self.assertEqual("Fix the \U0001f4a9 bug", loaded[0]["title"])

    def test_cjk_title_round_trips(self):
        path = self.tmp / "tasks.jsonl"
        store = task.TaskStore(path)
        t = store.add("\u4fee\u590d\u5e03\u5c40\u9519\u8bef")
        loaded = task.TaskStore(path).load()
        self.assertEqual("\u4fee\u590d\u5e03\u5c40\u9519\u8bef", loaded[0]["title"])

    def test_rtl_title_round_trips(self):
        path = self.tmp / "tasks.jsonl"
        store = task.TaskStore(path)
        t = store.add("\u062a\u0635\u062d\u064a\u062d \u0627\u0644\u062e\u0637\u0623")
        loaded = task.TaskStore(path).load()
        self.assertEqual("\u062a\u0635\u062d\u064a\u062d \u0627\u0644\u062e\u0637\u0623", loaded[0]["title"])

    def test_mixed_scripts_title(self):
        path = self.tmp / "tasks.jsonl"
        store = task.TaskStore(path)
        t = store.add("Fix \u00e9motion \u4e16\u754c")
        loaded = task.TaskStore(path).load()
        self.assertEqual("Fix \u00e9motion \u4e16\u754c", loaded[0]["title"])


class HugeTitleTests(TempDirTest):
    def test_10k_char_title_accepted(self):
        path = self.tmp / "tasks.jsonl"
        big = "x" * 10000
        t = task.TaskStore(path).add(big)
        loaded = task.TaskStore(path).load()
        self.assertEqual(big, loaded[0]["title"])

    def test_100k_char_title_accepted(self):
        path = self.tmp / "tasks.jsonl"
        big = "y" * 100000
        t = task.TaskStore(path).add(big)
        loaded = task.TaskStore(path).load()
        self.assertEqual(big, loaded[0]["title"])


class ConcurrentWriteTests(TempDirTest):
    def test_concurrent_adds_no_corruption(self):
        import threading

        path = self.tmp / "tasks.jsonl"
        successes = []
        failures = []

        def add_task(n):
            try:
                task.TaskStore(path).add(f"task-{n}")
                successes.append(n)
            except (PermissionError, OSError):
                failures.append(n)

        threads = [threading.Thread(target=add_task, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        loaded = task.TaskStore(path).load()
        self.assertGreaterEqual(len(loaded), 1)
        ids = [t["id"] for t in loaded]
        self.assertEqual(sorted(ids), ids)

    def test_concurrent_adds_and_reads(self):
        import threading

        path = self.tmp / "tasks.jsonl"
        task.TaskStore(path).add("seed")
        read_errors = []

        def add_task(n):
            try:
                task.TaskStore(path).add(f"task-{n}")
            except (PermissionError, OSError):
                pass

        def read_tasks():
            try:
                task.TaskStore(path).load()
            except (PermissionError, OSError):
                read_errors.append(True)

        threads = []
        for i in range(10):
            threads.append(threading.Thread(target=add_task, args=(i,)))
            threads.append(threading.Thread(target=read_tasks))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        loaded = task.TaskStore(path).load()
        self.assertGreaterEqual(len(loaded), 1)


class CLIIntegrationTests(unittest.TestCase):
    """CLI exit-code and output tests through main()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = os.path.join(self.tmpdir, "tasks.jsonl")
        self.addCleanup(lambda: None)

    def _run(self, *args):
        from qacompanion.__main__ import main
        return main(["tasklite", "--file", self.store] + list(args))

    def test_add_empty_title_exit_1(self):
        ret = self._run("add", "")
        self.assertEqual(1, ret)

    def test_add_no_target_exit_1(self):
        ret = self._run("add")
        self.assertEqual(1, ret)

    def test_done_no_target_exit_1(self):
        ret = self._run("done")
        self.assertEqual(1, ret)

    def test_done_non_int_exit_1(self):
        ret = self._run("done", "abc")
        self.assertEqual(1, ret)

    def test_done_unknown_id_exit_1(self):
        ret = self._run("done", "999")
        self.assertEqual(1, ret)

    def test_delete_no_target_exit_1(self):
        ret = self._run("delete")
        self.assertEqual(1, ret)

    def test_delete_non_int_exit_1(self):
        ret = self._run("delete", "abc")
        self.assertEqual(1, ret)

    def test_delete_unknown_id_exit_1(self):
        ret = self._run("delete", "999")
        self.assertEqual(1, ret)

    def test_show_no_target_exit_1(self):
        ret = self._run("show")
        self.assertEqual(1, ret)

    def test_show_non_int_exit_1(self):
        ret = self._run("show", "abc")
        self.assertEqual(1, ret)

    def test_show_unknown_id_exit_1(self):
        ret = self._run("show", "999")
        self.assertEqual(1, ret)

    def test_done_already_done_exit_1(self):
        self._run("add", "task")
        self._run("done", "0")
        ret = self._run("done", "0")
        self.assertEqual(1, ret)

    def test_list_empty_exit_0(self):
        ret = self._run("list")
        self.assertEqual(0, ret)

    def test_list_todo_before_done(self):
        self._run("add", "todo-one")
        self._run("add", "todo-two")
        self._run("add", "will-be-done")
        self._run("done", "2")
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        from qacompanion.__main__ import main
        with redirect_stdout(buf):
            main(["tasklite", "--file", self.store, "list"])
        output = buf.getvalue()
        lines = [l for l in output.strip().splitlines() if l.strip()]
        self.assertIn("[todo] todo-one", lines[0])
        self.assertIn("[todo] todo-two", lines[1])
        self.assertIn("[done] will-be-done", lines[2])

    def test_show_json_output(self):
        self._run("add", "show me")
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        from qacompanion.__main__ import main
        with redirect_stdout(buf):
            main(["tasklite", "--file", self.store, "show", "0"])
        import json as json_mod
        data = json_mod.loads(buf.getvalue())
        self.assertEqual("show me", data["title"])
        self.assertEqual("todo", data["status"])


if __name__ == "__main__":
    unittest.main()
