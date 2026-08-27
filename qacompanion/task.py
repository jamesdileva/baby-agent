"""Task store: strict-loading JSONL persistence for tasklite.

Storage format (frozen, docs/tasklite-spec.md): one JSON object per line in
`tasks.jsonl`. Load aborts with ValueError naming the offending line number
on any malformed input; saves are atomic (temp copy + os.replace).
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = "tasks.jsonl"
ENV_OVERRIDE = "TASKLITE_FILE"

_FIELD_TYPES = {
    "id": int,
    "title": str,
    "status": str,
    "created": str,
    "done_at": (str, type(None)),
}

_VALID_STATUSES = {"todo", "done"}


def default_path():
    """Env override (TASKLITE_FILE) > repo-root default."""
    return Path(os.environ.get(ENV_OVERRIDE) or DEFAULT_PATH)


def parse_timestamp(value):
    """Parse an ISO-8601 stamp ('Z' suffix included)."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _validate_task(task, line_number):
    if not isinstance(task, dict):
        raise ValueError(f"line {line_number}: expected a JSON object")
    missing = sorted(field for field in _FIELD_TYPES if field not in task)
    if missing:
        raise ValueError(
            f"line {line_number}: missing field(s): {', '.join(missing)}"
        )
    for field, expected in _FIELD_TYPES.items():
        value = task[field]
        if isinstance(expected, tuple):
            if not isinstance(value, expected):
                raise ValueError(
                    f"line {line_number}: field '{field}' must be "
                    f"{' or '.join(e.__name__ for e in expected)}"
                )
        else:
            if isinstance(value, bool) or not isinstance(value, expected):
                raise ValueError(
                    f"line {line_number}: field '{field}' must be {expected.__name__}"
                )
    if task["id"] < 0:
        raise ValueError(f"line {line_number}: id must be >= 0")
    if task["status"] not in _VALID_STATUSES:
        raise ValueError(
            f"line {line_number}: status must be 'todo' or 'done'"
        )
    if not task["title"]:
        raise ValueError(f"line {line_number}: title must be non-empty")
    try:
        parse_timestamp(task["created"])
    except ValueError as exc:
        raise ValueError(
            f"line {line_number}: created is not ISO-8601 ({exc})"
        ) from exc
    if task["done_at"] is not None:
        try:
            parse_timestamp(task["done_at"])
        except ValueError as exc:
            raise ValueError(
                f"line {line_number}: done_at is not ISO-8601 ({exc})"
            ) from exc


def serialize(tasks):
    """Canonical frozen-format bytes (id-sorted, one JSON object per LF line)."""
    return "".join(
        json.dumps(task, ensure_ascii=False) + "\n"
        for task in sorted(tasks, key=lambda item: item["id"])
    )


def utc_now_stamp(now=None):
    moment = now or datetime.now(timezone.utc)
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


class TaskStore:
    """Reader/writer for the frozen tasks.jsonl format."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_path()

    def load(self):
        """Return all tasks ordered by strictly increasing id.

        Raises ValueError naming the first malformed line; nothing partial
        ever escapes a failed load.
        """
        if not self.path.exists():
            return []
        text = self.path.read_text(encoding="utf-8-sig")
        tasks = []
        previous_id = -1
        for line_number, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                task = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"line {line_number}: invalid JSON ({exc.msg})"
                ) from exc
            _validate_task(task, line_number)
            if task["id"] <= previous_id:
                raise ValueError(
                    f"line {line_number}: id {task['id']} does not increase "
                    f"(previous id {previous_id})"
                )
            previous_id = task["id"]
            tasks.append(task)
        return tasks

    def save(self, tasks):
        """Atomically replace the store (temp copy in the same directory)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = serialize(tasks)
        handle_fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".tasks-", suffix=".tmp"
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(handle_fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
            os.replace(tmp_path, self.path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    def add(self, title, now=None):
        """Create a new task with status=todo. Returns the new task dict."""
        stamp = utc_now_stamp(now)
        tasks = self.load()
        next_id = tasks[-1]["id"] + 1 if tasks else 0
        task = {
            "id": next_id,
            "title": title,
            "status": "todo",
            "created": stamp,
            "done_at": None,
        }
        tasks.append(task)
        self.save(tasks)
        return task

    def list_all(self):
        """Return all tasks: todo first, then done, both in id order."""
        tasks = self.load()
        todo = [t for t in tasks if t["status"] == "todo"]
        done = [t for t in tasks if t["status"] == "done"]
        return todo + done

    def _find(self, task_id):
        """Return (tasks_list, index) for the given id, or raise ValueError."""
        tasks = self.load()
        for i, t in enumerate(tasks):
            if t["id"] == task_id:
                return tasks, i
        raise ValueError(f"unknown task id: {task_id}")

    def mark_done(self, task_id, now=None):
        """Mark a task as done. Raises ValueError if already done or unknown."""
        tasks, i = self._find(task_id)
        if tasks[i]["status"] == "done":
            raise ValueError(f"task #{task_id} already done")
        stamp = utc_now_stamp(now)
        tasks[i]["status"] = "done"
        tasks[i]["done_at"] = stamp
        self.save(tasks)
        return tasks[i]

    def delete(self, task_id):
        """Remove a task by id. Raises ValueError if unknown."""
        tasks, i = self._find(task_id)
        tasks.pop(i)
        self.save(tasks)

    def show(self, task_id):
        """Return the full task dict for the given id. Raises ValueError if unknown."""
        tasks, i = self._find(task_id)
        return tasks[i]
