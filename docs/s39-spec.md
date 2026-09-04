# S39 — Event Stream & Observability: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S39. Builds on S31–S38. One slice, stdlib only, no CLI changes.

## Overview

The runtime becomes observable without anyone polling internal state: the
loop and the registry pipeline emit a typed event stream that a future UI
(S52), evaluation harness (S57), or debugger can subscribe to.

## Module layout

```text
qacompanion/agent/events.py      # Event, EventStream
qacompanion/agent/loop.py        # primary emitter
qacompanion/agent/registry.py    # permission events (additive params)
tests/test_agent_events.py
```

## Event envelope

```text
Event (frozen)
    seq         per-stream monotonic ordering number (0-based)
    event_id    uuid4 hex
    session_id  owning session
    timestamp   UTC Z stamp
    event_type  dotted-free snake_case name
    payload     dict (JSON-ready)
    to_dict()
```

## EventStream

```text
EventStream(history_maxlen=10_000)
    .subscribe(callback)          -> callback   (sync; every event delivered)
    .unsubscribe(callback)
    .emit(event_type, session_id, payload) -> Event
    .events                       -> list (bounded replay history)
    .subscriber_errors            -> list (swallowed subscriber failures)
```

Pins (fixtures-first discipline):
- subscribers are synchronous callbacks; a raising subscriber is recorded
  in `subscriber_errors` and NEVER breaks an agent run;
- history is a bounded deque — replay/inspection for tests and the future
  evaluation harness, not an unbounded log;
- emission is fire-and-forget: the emitter does not wait on subscribers.

## Emission points

**Loop** (primary emitter; `AgentLoop(events=None)`):

```text
session_started            goal, workspace_root
session_state_changed      from, to           (every transition incl. finish)
model_started              iteration
model_response             iteration, finish_reason, has_tool_calls,
                           tool_call_names
tool_requested             tool, arguments
tool_completed             tool, duration_ms, changed_path?
tool_failed                tool, error, duration_ms
file_changed               path
verification_started       attempt
verification_completed     attempt, ok, detail
recovery_started           attempt
failure_detected           message  (also on empty responses / tool crashes)
session_completed / session_cancelled / session_failed   termination_reason
```

Deliberate omissions: `tool_started` (the pipeline is synchronous —
identical to `tool_requested` until S45 adds async processes);
`session_paused` (unreachable until S45); `command_*` events (S45 —
today `tool_completed` on `run_command` carries the structured
CommandResult); PAUSED/WAITING states unchanged from S37.

**Registry** (`execute(..., event_stream=None, session_id=None)`) —
permission events are emitted where the decision actually happens:
`permission_requested` (ASK, before the confirmer), `permission_granted`
(confirmer-approved), `permission_denied` (DENY / confirmation refused /
no confirmer). ALLOW decisions stay silent — the tool_completed event
already covers the call.

## Testing strategy (tests/test_agent_events.py)

- Envelope: fields, frozen, uuid uniqueness, seq ordering, to_dict round
  shape, timestamp format.
- Stream: subscribe/unsubscribe, multi-subscriber delivery, bounded
  history, raising subscriber swallowed + recorded, emission continues.
- **The roadmap verification**: a scripted write_file → final run with a
  passing verifier emits the exact ordered event sequence (asserted as a
  list of event types), including file_changed and both state-change
  chains.
- Denial path: deny-all policy → permission_denied + tool_failed +
  failure_detected.
- Confirmation path: ASK + approve → permission_requested +
  permission_granted; ASK + refuse → permission_requested +
  permission_denied; both with the engine-level audit trail intact.
- Recovery path: verifier fails once → verification_completed(ok=False) +
  recovery_started + RECOVERING state change, then success.
- Cancellation → session_cancelled with termination_reason.
- Subscriber crash mid-run → run still COMPLETED.
- Payload spot checks (tool_completed carries call_name/duration_ms;
  file_changed carries the path).

Expected suite growth: 1109 → ~1140 OK.

## Exit criteria (from ROADMAP-agentlite.md §S39)

A test session emits the expected complete event sequence; the UI-facing
contract is callback subscription, never internal polling; subscriber
failures cannot break a run. Full suite green; preflight clean.
