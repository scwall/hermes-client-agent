"""
Hermes Windows Control Plugin — remote desktop automation.

Gives Hermes Agent full control over a remote Windows/Linux machine
running the Hermes Client Agent (FastAPI HTTP server).

Tools:
  windows_health, windows_capabilities, windows_exec,
  windows_file_read, windows_file_write, windows_file_delete,
  windows_mouse_move, windows_mouse_click, windows_mouse_doubleclick,
  windows_mouse_scroll, windows_mouse_position,
  windows_keyboard_type, windows_keyboard_press, windows_keyboard_hotkey,
  windows_window_focus, windows_window_active, windows_window_list,
  windows_screenshot, windows_processes, windows_process_kill, windows_system

Multi-agent: pass agent="name" to target a specific machine.
"""

import json
import os
import base64
from pathlib import Path

import requests


# ── State ─────────────────────────────────────────────────────
STATE_PATH = Path(__file__).parent / "state.json"


def _load_state() -> dict:
    """Load agent configuration from state.json."""
    if not STATE_PATH.exists():
        return {"agents": {}}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def _get_agent(name: str | None = None) -> dict:
    """Resolve agent config by name, falling back to default."""
    state = _load_state()
    agents = state.get("agents", {})
    if not agents:
        raise RuntimeError("No agents configured in state.json")
    if name and name in agents:
        return agents[name]
    default = state.get("default") or next(iter(agents))
    return agents[default]


def _request(endpoint: str, method: str = "GET", agent: str | None = None,
             json_data: dict | None = None, timeout: int | None = None) -> dict:
    """Send an HTTP request to a remote agent."""
    cfg = _get_agent(agent)
    url = f"{cfg["url"].rstrip("/")}/{endpoint.lstrip("/")}"
    headers = {"X-Agent-Token": cfg["token"], "Content-Type": "application/json"}
    t = timeout or cfg.get("timeout", 30)
    kwargs = {"headers": headers, "timeout": t}
    if method in ("POST", "PUT") and json_data is not None:
        kwargs["json"] = json_data
    resp = requests.request(method, url, **kwargs)
    resp.raise_for_status()
    return resp.json()


# ── Hook ──────────────────────────────────────────────────────
def on_session_start(ctx):
    """Ping all configured agents on session start."""
    state = _load_state()
    agents = state.get("agents", {})
    for name, cfg in agents.items():
        try:
            url = f"{cfg["url"].rstrip("/")}/health"
            headers = {"X-Agent-Token": cfg["token"]}
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                ctx.log(f"Agent {name} healthy: {cfg["url"]}")
            else:
                ctx.log(f"Agent {name} returned {r.status_code}")
        except Exception as exc:
            ctx.log(f"Agent {name} unreachable: {exc}")


# ── Tools ─────────────────────────────────────────────────────

def register(register_tool):
    TS = "windows"  # toolset

    # ── Health & capabilities ─────────────────────────────────

    register_tool(
        name="windows_health", toolset=TS,
        schema={"properties": {"agent": {"type": "string"}}},
        handler=lambda agent=None: _request("health", agent=agent))

    register_tool(
        name="windows_capabilities", toolset=TS,
        schema={"properties": {"agent": {"type": "string"}}},
        handler=lambda agent=None: _request("capabilities", agent=agent))

    # ── Shell ─────────────────────────────────────────────────

    register_tool(
        name="windows_exec", toolset=TS,
        schema={
            "properties": {
                "command": {"type": "string"},
                "shell": {"type": "string", "enum": ["powershell", "cmd"], "default": "powershell"},
                "timeout": {"type": "integer", "default": 30},
                "agent": {"type": "string"},
            },
            "required": ["command"],
        },
        handler=lambda command, shell="powershell", timeout=30, agent=None: _request(
            "exec", method="POST", agent=agent,
            json_data={"command": command, "shell": shell, "timeout": timeout}))

    # ── Files ─────────────────────────────────────────────────

    register_tool(
        name="windows_file_read", toolset=TS,
        schema={
            "properties": {"path": {"type": "string"}, "agent": {"type": "string"}},
            "required": ["path"],
        },
        handler=lambda path, agent=None: _request(
            f"file?path={requests.utils.quote(path, safe="")}", agent=agent))

    register_tool(
        name="windows_file_write", toolset=TS,
        schema={
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "agent": {"type": "string"},
            },
            "required": ["path", "content"],
        },
        handler=lambda path, content, agent=None: _request(
            "file", method="PUT", agent=agent,
            json_data={"path": path, "content": content}))

    register_tool(
        name="windows_file_delete", toolset=TS,
        schema={
            "properties": {"path": {"type": "string"}, "agent": {"type": "string"}},
            "required": ["path"],
        },
        handler=lambda path, agent=None: _request(
            "file/delete", method="POST", agent=agent,
            json_data={"path": path}))

    # ── Mouse ─────────────────────────────────────────────────

    register_tool(
        name="windows_mouse_move", toolset=TS,
        schema={
            "properties": {
                "x": {"type": "integer"}, "y": {"type": "integer"},
                "agent": {"type": "string"},
            },
            "required": ["x", "y"],
        },
        handler=lambda x, y, agent=None: _request(
            "mouse/move", method="POST", agent=agent,
            json_data={"x": x, "y": y}))

    register_tool(
        name="windows_mouse_click", toolset=TS,
        schema={
            "properties": {
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "x": {"type": "integer"}, "y": {"type": "integer"},
                "agent": {"type": "string"},
            },
        },
        handler=lambda button="left", x=None, y=None, agent=None: _request(
            "mouse/click", method="POST", agent=agent,
            json_data={"button": button, "x": x, "y": y}))

    register_tool(
        name="windows_mouse_doubleclick", toolset=TS,
        schema={
            "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "agent": {"type": "string"}},
        },
        handler=lambda x=None, y=None, agent=None: _request(
            "mouse/doubleclick", method="POST", agent=agent,
            json_data={"x": x, "y": y}))

    register_tool(
        name="windows_mouse_scroll", toolset=TS,
        schema={
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down"], "default": "down"},
                "clicks": {"type": "integer", "default": 3},
                "agent": {"type": "string"},
            },
        },
        handler=lambda direction="down", clicks=3, agent=None: _request(
            "mouse/scroll", method="POST", agent=agent,
            json_data={"direction": direction, "clicks": clicks}))

    register_tool(
        name="windows_mouse_position", toolset=TS,
        schema={"properties": {"agent": {"type": "string"}}},
        handler=lambda agent=None: _request("mouse/position", agent=agent))

    # ── Keyboard ──────────────────────────────────────────────

    register_tool(
        name="windows_keyboard_type", toolset=TS,
        schema={
            "properties": {"text": {"type": "string"}, "agent": {"type": "string"}},
            "required": ["text"],
        },
        handler=lambda text, agent=None: _request(
            "keyboard/type", method="POST", agent=agent,
            json_data={"text": text}))

    register_tool(
        name="windows_keyboard_press", toolset=TS,
        schema={
            "properties": {
                "key": {"type": "string"},
                "agent": {"type": "string"},
            },
            "required": ["key"],
        },
        handler=lambda key, agent=None: _request(
            "keyboard/press", method="POST", agent=agent,
            json_data={"key": key}))

    register_tool(
        name="windows_keyboard_hotkey", toolset=TS,
        schema={
            "properties": {
                "keys": {"type": "array", "items": {"type": "string"}},
                "agent": {"type": "string"},
            },
            "required": ["keys"],
        },
        handler=lambda keys, agent=None: _request(
            "keyboard/hotkey", method="POST", agent=agent,
            json_data={"keys": keys}))

    # ── Windows ───────────────────────────────────────────────

    register_tool(
        name="windows_window_focus", toolset=TS,
        schema={
            "properties": {"title_substring": {"type": "string"}, "agent": {"type": "string"}},
            "required": ["title_substring"],
        },
        handler=lambda title_substring, agent=None: _request(
            "window/focus", method="POST", agent=agent,
            json_data={"title_substring": title_substring}))

    register_tool(
        name="windows_window_active", toolset=TS,
        schema={"properties": {"agent": {"type": "string"}}},
        handler=lambda agent=None: _request("window/active", agent=agent))

    register_tool(
        name="windows_window_list", toolset=TS,
        schema={"properties": {"agent": {"type": "string"}}},
        handler=lambda agent=None: _request("window/list", agent=agent))

    # ── Screenshot ────────────────────────────────────────────

    register_tool(
        name="windows_screenshot", toolset=TS,
        schema={
            "properties": {
                "region": {"type": "string", "description": "x,y,w,h or empty for full screen"},
                "agent": {"type": "string"},
            },
        },
        handler=lambda region=None, agent=None: _request(
            f"screenshot{?region= + region if region else }", agent=agent))

    # ── Processes ─────────────────────────────────────────────

    register_tool(
        name="windows_processes", toolset=TS,
        schema={"properties": {"agent": {"type": "string"}}},
        handler=lambda agent=None: _request("processes", agent=agent))

    register_tool(
        name="windows_process_kill", toolset=TS,
        schema={
            "properties": {"pid": {"type": "integer"}, "agent": {"type": "string"}},
            "required": ["pid"],
        },
        handler=lambda pid, agent=None: _request(
            "process/kill", method="POST", agent=agent,
            json_data={"pid": pid}))

    # ── System ────────────────────────────────────────────────

    register_tool(
        name="windows_system", toolset=TS,
        schema={"properties": {"agent": {"type": "string"}}},
        handler=lambda agent=None: _request("system", agent=agent))
