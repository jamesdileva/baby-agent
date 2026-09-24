"""S75.12 lab.db session mining: the antfarm colony's saved cycle
transcripts (docs/labDB-handoff.md).

Every colony cycle saves its full OpenCode transcript (messages +
parts JSON, same part vocabulary opencode.db uses) into lab.db's
session_transcripts table — and session GC then DELETES the session
from opencode.db, so lab.db is the only copy. 99 live transcripts
(82 done / 17 timed_out), pre-filtered to genuine cycles: no
SITUATION-REPORT-only sessions, no resume loops.

Outcome mapping is honest: the transcript proves the cycle's SHAPE,
not its success — `done` keeps the miner's partial outcome with
confidence raised to 0.45 (a completed cycle is stronger evidence
than a blanket partial), `timed_out` stays at 0.3. Curation stays the
judge. session_id prefers the opencode id so the store's
normalized-goal reinforcement merges with opencode-mined sessions
instead of double-counting them.

Pins (fixtures-first discipline): synthetic fixture DBs only; the real
lab.db is never touched by tests (read-only live smokes excepted);
every failure a structured MiningError; the boilerplate policy matches
the base miner (SITUATION REPORT preambles are skipped for goal
extraction).
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .experience import Experience
from .opencode_mine import (
    ERROR_SHAPE_RE, MAX_ACTIONS, MAX_FAILURE_PAIRS, MINED_OUTCOME,
    SUBSTANTIAL_GOAL_LESS_PARTS, MiningError, OpencodeMiner,
    _clean_goal, _is_boilerplate,
)

DEFAULT_LABDB_PATH = (Path.home() / "AppData" / "Roaming" / "@antfarm"
                      / "shell" / "antfarm-home" / "project" / "lab.db")

# handoff F3: done = the cycle completed its move (stronger than a
# blanket partial); timed_out = partial work
_STATUS_CONFIDENCE = {"done": 0.45, "timed_out": 0.3}


class LabDbMiner(OpencodeMiner):
    """Read-only miner over the antfarm lab.db transcript store."""

    SOURCE_NAME = "labdb"

    def __init__(self, db_path=None):
        super().__init__(db_path or DEFAULT_LABDB_PATH)

    def sessions(self, directory: Optional[str] = None
                 ) -> List[Dict[str, Any]]:
        """Transcript rows joined to their cycle status. `directory`
        filters by agent (the labdb equivalent of a project directory)."""
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT t.id, t.opencode_session_id, t.agent, t.cycle, "
                "s.status FROM session_transcripts t "
                "JOIN sessions s ON s.id = t.lab_session_id "
                "ORDER BY t.id").fetchall()
        finally:
            con.close()
        out = []
        for row in rows:
            agent = row["agent"] or "unknown"
            if directory and agent != directory:
                continue
            out.append({
                "id": row["id"],
                "directory": agent,
                "opencode_session_id": row["opencode_session_id"],
                "cycle": row["cycle"],
                "status": row["status"],
            })
        return out

    def _transcript_messages(self, transcript_id: int) -> List[Dict[str, Any]]:
        con = self._connect()
        try:
            row = con.execute(
                "SELECT transcript FROM session_transcripts WHERE id = ?",
                (transcript_id,)).fetchone()
        finally:
            con.close()
        if row is None:
            raise MiningError(f"transcript {transcript_id} not found")
        try:
            data = json.loads(row["transcript"])
        except (json.JSONDecodeError, TypeError) as exc:
            raise MiningError(
                f"transcript {transcript_id} is not valid JSON: {exc}"
            ) from exc
        if not isinstance(data, list):
            raise MiningError(
                f"transcript {transcript_id}: expected a JSON array")
        return data

    @staticmethod
    def _iter_parts(messages: List[Dict[str, Any]]):
        for message in messages:
            role = (message.get("info") or {}).get("role", "")
            for part in message.get("parts") or []:
                if isinstance(part, dict):
                    yield role, part

    def mine_session(self, session_row: Dict[str, Any],
                     store=None) -> Optional[Experience]:
        transcript_id = session_row["id"]
        messages = self._transcript_messages(transcript_id)

        # goal: first non-boilerplate user text part (the SITUATION
        # REPORT preamble is boilerplate by the base miner's rules)
        goal: Optional[str] = None
        actions: List[str] = []
        part_count = 0
        failure_pairs: List[List[Optional[str]]] = []
        current_error: Optional[str] = None
        patch_since = False
        for role, part in self._iter_parts(messages):
            part_count += 1
            ptype = part.get("type")
            if ptype == "text" and role == "user" and goal is None:
                text = (part.get("text") or "").strip()
                if text and not _is_boilerplate(text):
                    goal = _clean_goal(text)
            elif ptype == "tool":
                actions.append(str(part.get("tool", "unknown")))
                output = str((part.get("state") or {}).get("output") or "")
                for line in output.splitlines():
                    if not ERROR_SHAPE_RE.search(line):
                        continue
                    if "Traceback (" in line:
                        continue  # weak fallback only; lab pairs want strong lines
                    if line.strip()[:200] != current_error:
                        if current_error is not None and \
                                len(failure_pairs) >= MAX_FAILURE_PAIRS:
                            break
                        if current_error is not None:
                            failure_pairs.append([
                                current_error,
                                "fix applied via patch" if patch_since
                                else None])
                        current_error = line.strip()[:200]
                        patch_since = False
                    break
            elif ptype == "patch" and current_error is not None:
                patch_since = True
        if current_error is not None and \
                len(failure_pairs) < MAX_FAILURE_PAIRS:
            failure_pairs.append([current_error,
                                  "fix applied via patch" if patch_since
                                  else None])
        tool_count = len(actions)
        actions = actions[:MAX_ACTIONS]

        goal is None
        if goal is None:
            if part_count < SUBSTANTIAL_GOAL_LESS_PARTS:
                return None
            goal = "continued prior work (session had no stated goal)"

        status = str(session_row.get("status") or "unknown")
        directory = session_row.get("directory") or "unknown"
        context: Dict[str, Any] = {
            "source": self.SOURCE_NAME,
            "directory": f"antfarm/{directory}",
            "message_count": len(messages),
            "part_count": part_count,
            "tool_count": tool_count,
            "status": status,
            "cycle": session_row.get("cycle"),
        }
        if failure_pairs:
            context["failure_pairs"] = failure_pairs
        failure = failure_pairs[0][0] if failure_pairs else None
        resolution = (failure_pairs[0][1] if failure_pairs else None)

        experience = Experience(
            goal=goal,
            outcome=MINED_OUTCOME,
            session_id=session_row.get("opencode_session_id")
            or f"labdb-{transcript_id}",
            actions=actions,
            failure=failure,
            resolution=resolution,
            context=context,
            tags=["labdb", str(directory).lower()],
            confidence=_STATUS_CONFIDENCE.get(status, 0.3),
        )
        if store is not None:
            return store.record(experience)
        return experience
