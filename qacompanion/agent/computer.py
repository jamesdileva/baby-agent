"""S54 computer use: the roadmap's heavily restricted GUI capability.

Three gates must agree before ANY action executes:
1. the action type is in ComputerUseConfig.allowed_actions (default
   EMPTY — an unconfigured computer-use toolkit is a no-op),
2. every tool is DESTRUCTIVE + requires_confirmation (the S38 pipeline
   guarantee: default engine policy DENIES, permissive policies still
   ASK),
3. the confirmer approves the specific action.

Screen observation is S44 capture_screen; application launching is S45
start_process — deliberately NOT duplicated here.

Pins (fixtures-first discipline):
- FakeComputerProvider records an action log (hermetic tests assert on
  the log; nothing moves);
- WindowsComputerProvider (ctypes SendInput) is skipped on non-Windows
  with a structured error;
- coordinates out of screen bounds are a structured error, never
  silently clamped;
- max_actions budget: runaway-clicking protection, exhaustion is a
  structured error.
"""

import ctypes
import json
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .registry import DESTRUCTIVE, RegisteredTool, ToolDefinition, ToolOperationError, ToolRegistry
from .workspace import Workspace

ALLOWED_ACTIONS = ("click", "double_click", "move", "type", "press_keys",
                   "focus_window")


class ComputerError(ToolOperationError):
    """Structured computer-use failure (not allowed, budget, bounds)."""


@dataclass
class ComputerUseConfig:
    """The explicit allow-list and runaway protection."""

    allowed_actions: frozenset = frozenset()
    max_actions: int = 50
    screen_width: Optional[int] = None   # None = query the OS
    screen_height: Optional[int] = None

    def __post_init__(self):
        unknown = set(self.allowed_actions) - set(ALLOWED_ACTIONS)
        if unknown:
            raise ValueError(
                f"unknown allowed actions: {sorted(unknown)} "
                f"(known: {', '.join(ALLOWED_ACTIONS)})")
        if self.max_actions < 1:
            raise ValueError("max_actions must be >= 1")

    def allows(self, action: str) -> bool:
        return action in self.allowed_actions


def _screen_size() -> Tuple[int, int]:
    if os.name == "nt":
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    raise ComputerError(
        f"computer use unsupported on {os.name!r} (Windows SendInput only)")


class ComputerProvider(ABC):
    """One controlled GUI session behind the allow-list."""

    action_log: List[Dict[str, Any]]

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def click(self, x: int, y: int) -> Dict[str, Any]:
        ...

    @abstractmethod
    def double_click(self, x: int, y: int) -> Dict[str, Any]:
        ...

    @abstractmethod
    def move(self, x: int, y: int) -> Dict[str, Any]:
        ...

    @abstractmethod
    def type_text(self, text: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    def press_keys(self, keys: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    def focus_window(self, title: str) -> Dict[str, Any]:
        ...


class FakeComputerProvider(ComputerProvider):
    """Records every allowed action; hermetic."""

    def __init__(self):
        self.action_log: List[Dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "fake"

    def _log(self, action: str, **details) -> Dict[str, Any]:
        record = {"action": action, **details}
        self.action_log.append(record)
        return {"performed": True, **details}

    def click(self, x: int, y: int) -> Dict[str, Any]:
        return self._log("click", x=x, y=y)

    def double_click(self, x: int, y: int) -> Dict[str, Any]:
        return self._log("double_click", x=x, y=y)

    def move(self, x: int, y: int) -> Dict[str, Any]:
        return self._log("move", x=x, y=y)

    def type_text(self, text: str) -> Dict[str, Any]:
        return self._log("type", text=text)

    def press_keys(self, keys: str) -> Dict[str, Any]:
        return self._log("press_keys", keys=keys)

    def focus_window(self, title: str) -> Dict[str, Any]:
        return self._log("focus_window", title=title)


class WindowsComputerProvider(ComputerProvider):
    """ctypes SendInput adapter (Windows)."""

    def __init__(self):
        if os.name != "nt":
            raise ComputerError(
                f"computer use unsupported on {os.name!r} (Windows only)")
        self.user32 = ctypes.windll.user32
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "windows"

    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    VK_MAP = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "enter": 0x0D,
              "esc": 0x1B, "tab": 0x09, "space": 0x20, "backspace": 0x08,
              "delete": 0x2E, "win": 0x5B}

    def _vk_for(self, char: str) -> int:
        if char.lower() in self.VK_MAP:
            return self.VK_MAP[char.lower()]
        vk = self.user32.VkKeyScanW(ord(char))
        if vk == -1:
            raise ComputerError(f"cannot type character: {char!r}")
        return vk & 0xFF

    def _send_key(self, vk: int, up: bool = False) -> None:
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort),
                        ("wScan", ctypes.c_ushort),
                        ("dwFlags", ctypes.c_uint32),
                        ("time", ctypes.c_uint32),
                        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        class INPUT(ctypes.Structure):
            class _I(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]
            _anonymous_ = ("i",)
            _fields_ = [("type", ctypes.c_uint32), ("i", _I)]

        inp = INPUT()
        inp.type = self.INPUT_KEYBOARD
        inp.ki.wVk = vk
        inp.ki.dwFlags = self.KEYEVENTF_KEYUP if up else 0
        self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def click(self, x: int, y: int) -> Dict[str, Any]:
        with self._lock:
            self.user32.SetCursorPos(x, y)
            time.sleep(0.01)
            self.user32.mouse_event(self.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            self.user32.mouse_event(self.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        return {"performed": True, "x": x, "y": y}

    def double_click(self, x: int, y: int) -> Dict[str, Any]:
        self.click(x, y)
        time.sleep(0.05)
        return self.click(x, y)

    def move(self, x: int, y: int) -> Dict[str, Any]:
        self.user32.SetCursorPos(x, y)
        return {"performed": True, "x": x, "y": y}

    def type_text(self, text: str) -> Dict[str, Any]:
        with self._lock:
            for char in text:
                vk = self._vk_for(char)
                self._send_key(vk)
                self._send_key(vk, up=True)
                time.sleep(0.005)
        return {"performed": True, "chars": len(text)}

    def press_keys(self, keys: str) -> Dict[str, Any]:
        combo = [part.strip() for part in keys.split("+") if part.strip()]
        vks = [self._vk_for(part) for part in combo]
        with self._lock:
            for vk in vks:
                self._send_key(vk)
            for vk in reversed(vks):
                self._send_key(vk, up=True)
        return {"performed": True, "keys": keys}

    def focus_window(self, title: str) -> Dict[str, Any]:
        hwnd = self.user32.FindWindowW(None, title)
        if not hwnd:
            raise ComputerError(f"no window with title {title!r}")
        self.user32.SetForegroundWindow(hwnd)
        return {"performed": True, "title": title}


class ComputerUseToolkit:
    """Binds the six GUI tools behind the three-gate safety model."""

    def __init__(self, workspace: Workspace,
                 provider: Optional[ComputerProvider] = None,
                 config: Optional[ComputerUseConfig] = None):
        self.workspace = workspace
        self.config = config or ComputerUseConfig()
        if provider is not None:
            self.provider = provider
        elif os.name == "nt":
            self.provider = WindowsComputerProvider()
        else:
            raise ComputerError(
                f"computer use unsupported on {os.name!r} (Windows only)")
        self._action_count = 0
        self._lock = threading.Lock()

    def _gate(self, action: str) -> None:
        if not self.config.allows(action):
            raise ComputerError(
                f"action {action!r} is not in the allow-list "
                f"(configured: {sorted(self.config.allowed_actions) or '[]'})")
        with self._lock:
            if self._action_count >= self.config.max_actions:
                raise ComputerError(
                    f"computer-use action budget exhausted "
                    f"({self.config.max_actions})")
            self._action_count += 1

    def _bounds_check(self, x: int, y: int) -> Tuple[int, int]:
        width = self.config.screen_width
        height = self.config.screen_height
        if width is None or height is None:
            width, height = _screen_size()
        if not (0 <= x < width and 0 <= y < height):
            raise ComputerError(
                f"coordinates ({x}, {y}) outside screen "
                f"({width}x{height})")
        return x, y

    def _execute(self, action: str, method_name: str, **kwargs) -> str:
        self._gate(action)
        method = getattr(self.provider, method_name)
        if action in ("click", "double_click", "move"):
            x, y = self._bounds_check(kwargs["x"], kwargs["y"])
            kwargs["x"], kwargs["y"] = x, y
        result = method(**kwargs)
        return json.dumps({"action": action, **result}, ensure_ascii=False)

    def computer_click(self, x: int, y: int) -> str:
        return self._execute("click", "click", x=int(x), y=int(y))

    def computer_double_click(self, x: int, y: int) -> str:
        return self._execute("double_click", "double_click",
                             x=int(x), y=int(y))

    def computer_move(self, x: int, y: int) -> str:
        return self._execute("move", "move", x=int(x), y=int(y))

    def computer_type(self, text: str) -> str:
        return self._execute("type", "type_text", text=text)

    def computer_press_keys(self, keys: str) -> str:
        return self._execute("press_keys", "press_keys", keys=keys)

    def computer_focus_window(self, title: str) -> str:
        return self._execute("focus_window", "focus_window", title=title)

    def tools(self) -> List[RegisteredTool]:
        def _tool(name, description, schema, handler):
            return RegisteredTool(
                definition=ToolDefinition(
                    name=name, description=description,
                    parameters_schema=schema),
                handler=handler,
                category="computer",
                side_effect_level=DESTRUCTIVE,
                requires_confirmation=True,
                requires_workspace=True,
            )

        xy = {"type": "object",
              "properties": {"x": {"type": "integer"},
                             "y": {"type": "integer"}},
              "required": ["x", "y"]}
        return [
            _tool("computer_click", "Left-click at screen coordinates.",
                  xy, self.computer_click),
            _tool("computer_double_click", "Double-click at screen "
                  "coordinates.", xy, self.computer_double_click),
            _tool("computer_move", "Move the cursor (hover).",
                  xy, self.computer_move),
            _tool("computer_type", "Type text via the keyboard.",
                  {"type": "object",
                   "properties": {"text": {"type": "string"}},
                   "required": ["text"]},
                  self.computer_type),
            _tool("computer_press_keys", "Press a key combo, e.g. "
                  '"ctrl+s".',
                  {"type": "object",
                   "properties": {"keys": {"type": "string"}},
                   "required": ["keys"]},
                  self.computer_press_keys),
            _tool("computer_focus_window", "Bring a window to the "
                  "foreground by title.",
                  {"type": "object",
                   "properties": {"title": {"type": "string"}},
                   "required": ["title"]},
                  self.computer_focus_window),
        ]


def update_agent_registry(registry: ToolRegistry, workspace: Workspace,
                          provider: Optional[ComputerProvider] = None,
                          config: Optional[ComputerUseConfig] = None
                          ) -> None:
    """Register the computer-use tools into an existing registry."""
    for tool in ComputerUseToolkit(workspace, provider, config).tools():
        registry.register(tool)
