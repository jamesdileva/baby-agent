"""S39 event stream & observability: the runtime, narrated.

The loop and the registry pipeline emit typed events; UIs, evaluators, and
debuggers subscribe. Nobody polls internal state.

Pins (fixtures-first discipline):
- subscribers are synchronous callbacks; a raising subscriber is recorded
  in subscriber_errors and NEVER breaks an agent run;
- history is a bounded deque — replay for tests/evaluation, not a log;
- emission is fire-and-forget; seq is a per-stream monotonic ordering
  number assigned by the stream, event_id is a uuid4 hex.
"""

import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


@dataclass(frozen=True)
class Event:
    """One observable runtime occurrence."""

    seq: int
    event_id: str
    session_id: str
    timestamp: str
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "seq": self.seq,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "payload": dict(self.payload),
        }


class EventStream:
    """Subscribe-and-emit bus with bounded replay history."""

    def __init__(self, history_maxlen: int = 10_000):
        self._subscribers: List[Callable[[Event], None]] = []
        self._history: deque = deque(maxlen=history_maxlen)
        self._seq = 0
        self.subscriber_errors: List[str] = []

    def subscribe(self, callback: Callable[[Event], None]) -> Callable[[Event], None]:
        self._subscribers.append(callback)
        return callback

    def unsubscribe(self, callback: Callable[[Event], None]) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def emit(self, event_type: str, session_id: str,
             payload: Dict[str, Any]) -> Event:
        event = Event(
            seq=self._seq,
            event_id=uuid.uuid4().hex,
            session_id=session_id,
            timestamp=_utc_stamp(),
            event_type=event_type,
            payload=dict(payload),
        )
        self._seq += 1
        self._history.append(event)
        for subscriber in list(self._subscribers):
            try:
                subscriber(event)
            except Exception as exc:
                # a broken UI/evaluator must never break an agent run
                self.subscriber_errors.append(
                    f"subscriber failed on {event_type}: {exc!r}"
                )
        return event

    @property
    def events(self) -> List[Event]:
        return list(self._history)

    def types(self) -> List[str]:
        return [event.event_type for event in self._history]
