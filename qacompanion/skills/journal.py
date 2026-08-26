"""S15 journal skill: durable lessons ledger (workplace literacy).

Born from "VOID-L1 residuals live only in mail/memory." Append-only
markdown ledger with auto-timestamped entries, searchable, designed to
be committed alongside any repo so lessons survive resets.

Pins (fixtures-first discipline):
- entries are UTC ISO-8601 timestamps (no timezone suffix);
- each entry is one line: `## YYYY-MM-DDTHH:MM:SS <text>`;
- the ledger file is human-readable markdown;
- grep is case-insensitive substring match;
- concurrent appends are safe (append-mode file locking);
- the ledger path defaults to `JOURNAL.md` in cwd, overridable.

Exit contract (proposed spec amendment):
0 success, 1 operational failure (bad input / no grep matches /
environment error).
"""

import datetime
import os
import re
import sys
from pathlib import Path

_DEFAULT_NAME = "JOURNAL.md"


class JournalError(Exception):
    """Operational failure: bad input or unreadable ledger."""


def _timestamp():
    """Return UTC ISO-8601 without timezone suffix."""
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )


def _ledger_path(ledger=None):
    if ledger is not None:
        return Path(ledger)
    return Path(_DEFAULT_NAME)


def _lock_file(fd):
    """Acquire an exclusive lock on an open file descriptor (cross-platform)."""
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX)


def _unlock_file(fd):
    """Release a lock on an open file descriptor (cross-platform)."""
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)


def add(text, ledger=None):
    """Append a timestamped entry to the ledger. Returns the entry line."""
    if not text or not text.strip():
        raise JournalError("empty text")
    text = text.strip()
    if "\n" in text:
        raise JournalError("text must be a single line")
    ts = _timestamp()
    line = f"## {ts} {text}\n"
    path = _ledger_path(ledger)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        try:
            _lock_file(fd)
        except (OSError, ImportError):
            pass
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            try:
                _unlock_file(fd)
            except (OSError, ImportError):
                pass
    finally:
        os.close(fd)
    return line.rstrip("\n")


def grep(pattern, ledger=None):
    """Search the ledger for entries matching a case-insensitive pattern.

    Returns a list of (timestamp, text) tuples for matching entries.
    Raises JournalError if the ledger does not exist or is unreadable.
    """
    if not pattern or not pattern.strip():
        raise JournalError("empty pattern")
    path = _ledger_path(ledger)
    if not path.exists():
        raise JournalError(f"ledger not found: {path}")
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise JournalError(f"unreadable ledger: {exc}") from exc
    regex = re.compile(re.escape(pattern), re.IGNORECASE)
    results = []
    for line in content.splitlines():
        if line.startswith("## "):
            rest = line[3:]
            space_idx = rest.find(" ")
            if space_idx > 0:
                ts = rest[:space_idx]
                text = rest[space_idx + 1 :]
                if regex.search(text):
                    results.append((ts, text))
    return results


def render_add(entry_line):
    """Render an add confirmation line."""
    return entry_line


def render_grep(results, pattern):
    """Render grep results as human-readable output."""
    if not results:
        return f"no entries matching '{pattern}'"
    lines = [f"{ts}  {text}" for ts, text in results]
    return "\n".join(lines)
