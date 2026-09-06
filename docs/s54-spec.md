# S54 — Computer Use: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S54. Builds on S31–S53. One slice, stdlib only, no CLI changes.

## Overview

General GUI interaction — explicitly the roadmap's "heavily restricted,
only after screenshots, browser automation, and permissions are
reliable" capability, and explicitly NOT needed for ordinary coding
tasks. The design center is therefore the SAFETY MODEL, not the action
surface:

```text
nothing happens unless THREE gates agree:
1. the action type is in an EXPLICIT allow-list (default: EMPTY)
2. the S38 engine's verdict is DENY-resistant: every tool is
   DESTRUCTIVE-level + requires_confirmation (pipeline guarantee)
3. the confirmer approves the specific action
```

**Reuse over duplication (documented deviations):** screen observation
is S44 `capture_screen`; application launching is S45 `start_process`.
Computer use adds only the truly new primitives: mouse, keyboard,
window focus.

## Module layout

```text
qacompanion/agent/computer.py    # ComputerProvider ABC + adapters + tools
tests/test_agent_computer.py
```

## Actions (the full surface — six tools)

```text
computer_click         {x, y}              left click at coordinates
computer_double_click  {x, y}
computer_move          {x, y}              cursor move (hover)
computer_type          {text}              keyboard text input
computer_press_keys    {keys}              key combo, e.g. "ctrl+s"
computer_focus_window  {title}             find + foreground a window
```

All six: category "computer", DESTRUCTIVE, requires_confirmation=True —
the S38 pipeline guarantee makes them DENIED under the default engine
policy (Part 6: DESTRUCTIVE→DENY) and ASK-gated under any policy that
allows them, with the confirmer seeing the exact action.

## ComputerUseConfig (the explicit allow-list)

```text
ComputerUseConfig(allowed_actions=frozenset(), max_actions=50,
                  screen_width=auto, screen_height=auto)
```

- `allowed_actions`: subset of {click, double_click, move, type,
  press_keys, focus_window}. Default EMPTY — configuring an empty
  computer-use toolkit is a no-op by construction.
- `max_actions`: per-provider action budget; exhausted → structured
  error (runaway-clicking protection).
- Coordinates outside screen bounds → structured error (never clamped
  silently — clicks must go where the agent says).

## Providers

- **FakeComputerProvider**: records every allowed action in an
  `.actions` log (hermetic — tests assert on the log, nothing moves).
- **WindowsComputerProvider**: ctypes user32 SendInput for
  mouse/keyboard, FindWindowW + SetForegroundWindow for focus;
  `os.name != "nt"` → structured error. Coordinates from
  GetSystemMetrics.

## Testing strategy (tests/test_agent_computer.py)

- Config: default empty allow-list denies everything; explicit grants;
  budget exhaustion; bounds errors.
- Fake provider: action log ordering (click → type → press_keys);
  denial of non-allow-listed actions.
- Windows adapter: guarded by os.name (skipped on POSIX); action
  construction verified through the fake log on Windows — real SendInput
  smoke is manual-only (moving the real cursor in CI is hostile).
- Tools: DESTRUCTIVE + confirmation matrix; default-engine DENY;
  explicit-allow policy + confirmer → action executes and is logged;
  budget exhaustion mid-sequence.
- Registry membership (59 → 65); benchmark lean catalog unchanged.

Expected suite growth: 1384 → ~1400 OK.

## Exit criteria (from ROADMAP-agentlite.md §S54)

Sandboxed benchmark with an explicit allow-list: actions execute only
when all three gates agree; every action is logged; runaway protection
works. Full suite green; preflight clean.
