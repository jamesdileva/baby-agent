"""S47.1 opencode session mining: turn the human's existing opencode
corpus into agent experience.

opencode (SST) keeps sessions in a SQLite database — sessions, messages
(role JSON), and typed parts (text / tool / reasoning / patch). The miner
opens it READ-ONLY (mode=ro URI) and converts each session into one
Experience for the S47 store: goal from the first user text part,
ordered tool names as actions, volume counts in context, the opencode
session id kept as provenance.

Two measured session shapes drive the design (docs/s47-spec.md):
- marathon projects: 1-5 sessions with thousands of messages;
- turn-spawn projects (antfarm): hundreds of tiny per-turn sessions with
  repeating goals — ExperienceStore's normalized-goal reinforcement
  merges those into few high-times_seen patterns instead of flooding.

Outcomes are honestly "partial" (confidence 0.3): the DB cannot prove
success — that refinement belongs to curation (S62), not guessing.

Pins (fixtures-first discipline):
- the suite builds a synthetic fixture DB with the real schema; the
  real database is never touched by tests;
- trivial sessions (no user text AND no tool parts) are skipped;
- every failure is a structured MiningError.
"""

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .experience import Experience, ExperienceStore
from .workspace import ProjectMetadata

MAX_ACTIONS = 50
MAX_GOAL_CHARS = 200
TRIVIAL_MIN_PARTS = 1
# antfarm injects a per-turn kickoff preamble as the "user" message — it
# is prompt template, not a task goal; sessions whose only user text is
# boilerplate have no learnable goal
BOILERPLATE_MARKERS = ("SITUATION REPORT", "PROJECT GOAL (authored by")


def _is_boilerplate(text: str) -> bool:
    return any(marker in text for marker in BOILERPLATE_MARKERS)


def _clean_goal(text: str) -> str:
    """Truncate at a word boundary, never mid-word."""
    if len(text) <= MAX_GOAL_CHARS:
        return text
    cut = text[:MAX_GOAL_CHARS]
    return cut[:cut.rfind(" ")].rstrip(",;:") + "…"
MINED_OUTCOME = "partial"
MINED_CONFIDENCE = 0.3


ERROR_SHAPE_RE = re.compile(r"Traceback \(|Error|FAIL|error:", re.IGNORECASE)


class MiningError(Exception):
    """Structured mining failure (missing DB, bad schema)."""


class OpencodeMiner:
    """Read-only miner over an SST-opencode SQLite database."""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise MiningError(f"opencode database not found: {self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self.db_path.as_posix()}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        con.row_factory = sqlite3.Row
        return con

    def sessions(self, directory: Optional[str] = None) -> List[Dict[str, Any]]:
        con = self._connect()
        try:
            if directory:
                rows = con.execute(
                    "SELECT id, directory, title, time_created FROM session "
                    "WHERE directory = ? ORDER BY time_created",
                    (directory,),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT id, directory, title, time_created FROM session "
                    "ORDER BY time_created").fetchall()
            return [dict(row) for row in rows]
        finally:
            con.close()

    def _session_volume(self, con: sqlite3.Connection, session_id: str
                        ) -> Dict[str, int]:
        row = con.execute(
            "SELECT COUNT(*) FROM message WHERE session_id = ?",
            (session_id,)).fetchone()
        messages = row[0]
        row = con.execute(
            "SELECT COUNT(*) FROM part WHERE session_id = ?",
            (session_id,)).fetchone()
        parts = row[0]
        return {"message_count": messages, "part_count": parts}

    def _user_text(self, con: sqlite3.Connection, session_id: str
                   ) -> Optional[str]:
        """First user-authored text part (robust to JSON spacing)."""
        roles: Dict[str, str] = {}
        for row in con.execute(
                "SELECT id, data FROM message WHERE session_id = ?",
                (session_id,)).fetchall():
            try:
                roles[row["id"]] = json.loads(row["data"]).get("role", "")
            except (json.JSONDecodeError, TypeError):
                roles[row["id"]] = ""
        for row in con.execute(
                "SELECT message_id, data FROM part WHERE session_id = ? "
                "ORDER BY time_created", (session_id,)).fetchall():
            try:
                part = json.loads(row["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            if part.get("type") != "text":
                continue
            # message_id is a DB column, not a field of the part JSON
            if roles.get(row["message_id"]) != "user":
                continue
            text = (part.get("text") or "").strip()
            if text and not _is_boilerplate(text):
                return _clean_goal(text)
        return None

    def _tool_actions(self, con: sqlite3.Connection, session_id: str
                      ) -> Dict[str, Any]:
        rows = con.execute(
            "SELECT data FROM part WHERE session_id = ? ORDER BY time_created",
            (session_id,)).fetchall()
        tools: List[str] = []
        for row in rows:
            try:
                part = json.loads(row["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            if part.get("type") == "tool":
                tools.append(str(part.get("tool", "unknown")))
        return {
            "actions": tools[:MAX_ACTIONS],
            "tool_count": len(tools),
        }

    def _error_patch(self, con: sqlite3.Connection, session_id: str
                     ) -> "tuple[Optional[str], Optional[str]]":
        """Conservative error->patch correlation: when an error-shaped
        tool output is followed by a later patch part in the same
        session, report failure line + honest resolution note."""
        first_error = None
        patch_after = False
        for row in con.execute(
                "SELECT time_created, data FROM part WHERE session_id = ? "
                "ORDER BY time_created", (session_id,)).fetchall():
            try:
                part = json.loads(row["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            ptype = part.get("type")
            if ptype == "tool":
                output = str((part.get("state") or {}).get("output") or "")
                for line in output.splitlines():
                    if not ERROR_SHAPE_RE.search(line):
                        continue
                    if "Traceback (" in line:
                        # bare header: weak fallback only — keep scanning
                        # for the substantive error line past it
                        if first_error is None:
                            first_error = line.strip()[:200]
                        continue
                    first_error = line.strip()[:200]  # strong line wins
                    break
            elif ptype == "patch" and first_error is not None:
                patch_after = True
        if first_error is None:
            return None, None
        resolution = "fix applied via patch" if patch_after else None
        return first_error, resolution

    def mine_session(self, session_row: Dict[str, Any],
                     store: Optional[ExperienceStore] = None
                     ) -> Optional[Experience]:
        con = self._connect()
        try:
            session_id = session_row["id"]
            volume = self._session_volume(con, session_id)
            goal = self._user_text(con, session_id)
            tool_info = self._tool_actions(con, session_id)
            failure, resolution = self._error_patch(con, session_id)
        finally:
            con.close()

        if goal is None:
            # no non-boilerplate user text: nothing learnable yet (tool
            # actions without a goal are curation's problem, not ours)
            return None

        directory = session_row.get("directory") or ""
        project_type = None
        languages: List[str] = []
        project_root = Path(directory) if directory else None
        if project_root is not None and project_root.exists():
            metadata = ProjectMetadata.detect(project_root)
            project_type = metadata.project_type
            languages = list(metadata.languages)

        context = {
            "source": "opencode",
            "directory": directory,
            **volume,
            **tool_info,
        }
        experience = Experience(
            goal=goal or (session_row.get("title")
                          or "opencode session")[:MAX_GOAL_CHARS],
            outcome=MINED_OUTCOME,
            session_id=session_id,
            actions=tool_info["actions"],
            failure=failure,
            resolution=resolution,
            context=context,
            tags=["opencode", Path(directory).name.lower()
                  if directory else "unknown"],
            project_type=project_type,
            languages=languages,
            confidence=MINED_CONFIDENCE,
        )
        if store is not None:
            return store.record(experience)
        return experience

    def mine(self, directory: Optional[str] = None,
             store: Optional[ExperienceStore] = None,
             dry_run: bool = False) -> Dict[str, Any]:
        """Mine sessions into the store (or dry-run: no writes)."""
        stats: Dict[str, Any] = {
            "sessions_seen": 0, "mined": 0, "reinforced": 0,
            "skipped_trivial": 0, "errors": 0, "by_directory": {},
            "dry_run": dry_run,
        }
        if dry_run:
            store = None  # never write in dry-run
        for row in self.sessions(directory=directory):
            stats["sessions_seen"] += 1
            dir_key = (row.get("directory") or "?")
            stats["by_directory"].setdefault(dir_key, {"seen": 0, "mined": 0})
            stats["by_directory"][dir_key]["seen"] += 1
            try:
                experience = self.mine_session(row, store=store)
            except Exception:
                stats["errors"] += 1  # real errors are not "trivial"
                continue
            if experience is None:
                stats["skipped_trivial"] += 1
                continue
            stats["mined"] += 1
            stats["by_directory"][dir_key]["mined"] += 1
            if experience.times_seen > 1:
                stats["reinforced"] += 1
        return stats
