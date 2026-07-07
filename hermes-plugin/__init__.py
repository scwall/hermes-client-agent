"""Hermes native plugin: windows-control.

Remote Windows PC control via HTTP REST API.
Communicates with a FastAPI agent running on a Windows machine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

PLUGIN_DIR = Path(__file__).parent
STATE_FILE = PLUGIN_DIR / "state.json"

DEFAULT_STATE: dict[str, Any] = {
    "agent_url": "http://192.168.1.100:8765",
    "token": "hermes-windows-agent-secret-token-change-me",
    "timeout": 30,
    "enabled": True,
}


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _load_state() -> dict[str, Any]:
    """Load state from state.json, merging with defaults."""
    state = dict(DEFAULT_STATE)
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                stored = json.load(f)
            state.update(stored)
        except (json.JSONDecodeError, OSError):
            pass
    return state


def _save_state(state: dict[str, Any]) -> None:
    """Save state to disk."""
    merged = dict(DEFAULT_STATE)
    merged.update(state)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(merged, f, indent=2)


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _make_request(
    method: str,
    path: str,
    json_data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> str:
    """Make an HTTP request to the Windows agent.

    Returns the JSON response dict, or an error dict on failure.
    """
    state = _load_state()
    url = f"{state['agent_url'].rstrip('/')}{path}"
    headers = {"X-Agent-Token": state["token"]}
    try:
        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=json_data,
            params=params,
            timeout=state["timeout"],
        )
        resp.raise_for_status()
        return json.dumps(resp.json())
    except requests.exceptions.ConnectionError:
        return json.dumps({"error": "agent_unreachable", "url": url})
    except requests.exceptions.Timeout:
        return json.dumps({"error": "agent_timeout", "timeout": state["timeout"]})
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        return json.dumps({"error": f"http_{status}", "detail": str(exc)})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Tool handler signatures (all accept args: dict)
# ---------------------------------------------------------------------------

def _health_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /health"""
    return _make_request("GET", "/health")


def _capabilities_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /capabilities"""
    return _make_request("GET", "/capabilities")


def _exec_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /exec"""
    return _make_request(
        "POST",
        "/exec",
        json_data={
            "command": args["command"],
            "shell": args.get("shell", "cmd"),
            "timeout": args.get("timeout", 30),
        },
    )


def _file_read_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /file"""
    return _make_request("GET", "/file", params={"path": args["path"]})


def _file_write_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """PUT /file"""
    return _make_request(
        "PUT",
        "/file",
        json_data={"path": args["path"], "content": args["content"]},
    )


def _file_delete_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /file/delete"""
    return _make_request("POST", "/file/delete", json_data={"path": args["path"]})


def _mouse_move_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /mouse/move"""
    return _make_request(
        "POST", "/mouse/move", json_data={"x": args["x"], "y": args["y"]}
    )


def _mouse_click_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /mouse/click"""
    return _make_request(
        "POST",
        "/mouse/click",
        json_data={
            "button": args.get("button", "left"),
            "x": args.get("x"),
            "y": args.get("y"),
        },
    )


def _mouse_doubleclick_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /mouse/doubleclick"""
    return _make_request(
        "POST",
        "/mouse/doubleclick",
        json_data={"x": args.get("x"), "y": args.get("y")},
    )


def _mouse_scroll_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /mouse/scroll"""
    return _make_request(
        "POST",
        "/mouse/scroll",
        json_data={
            "direction": args.get("direction", "up"),
            "clicks": args.get("clicks", 3),
        },
    )


def _mouse_position_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /mouse/position"""
    return _make_request("GET", "/mouse/position")


def _keyboard_type_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /keyboard/type"""
    return _make_request(
        "POST", "/keyboard/type", json_data={"text": args["text"]}
    )


def _keyboard_press_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /keyboard/press"""
    return _make_request(
        "POST", "/keyboard/press", json_data={"key": args["key"]}
    )


def _keyboard_hotkey_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /keyboard/hotkey"""
    return _make_request(
        "POST", "/keyboard/hotkey", json_data={"keys": args["keys"]}
    )


def _window_focus_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /window/focus"""
    return _make_request(
        "POST",
        "/window/focus",
        json_data={"title_substring": args["title_substring"]},
    )


def _window_active_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /window/active"""
    return _make_request("GET", "/window/active")


def _window_list_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /window/list"""
    return _make_request("GET", "/window/list")


def _screenshot_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /screenshot"""
    params = {}
    if args.get("region"):
        params["region"] = args["region"]
    return _make_request("GET", "/screenshot", params=params)


def _processes_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /processes"""
    return _make_request("GET", "/processes")


def _process_kill_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /process/kill"""
    return _make_request(
        "POST", "/process/kill", json_data={"pid": args["pid"]}
    )


def _system_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /system"""
    return _make_request("GET", "/system")


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

WINDOWS_HEALTH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "description": "Check the health status of the remote Windows agent.",
}

WINDOWS_CAPABILITIES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "description": "List available modules and endpoints on the remote Windows agent.",
}

WINDOWS_EXEC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": "Command to execute on the remote Windows PC (e.g., 'dir', 'ipconfig', 'whoami').",
        },
        "shell": {
            "type": "string",
            "description": "Shell to use: 'cmd' (default) or 'powershell'.",
            "default": "cmd",
        },
        "timeout": {
            "type": "integer",
            "description": "Command timeout in seconds (default: 30).",
            "default": 30,
        },
    },
    "required": ["command"],
}

WINDOWS_FILE_READ_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Full path to the file on the remote Windows PC (e.g., 'C:\\\\Users\\\\admin\\\\doc.txt').",
        }
    },
    "required": ["path"],
}

WINDOWS_FILE_WRITE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Full path to the file to write on the remote Windows PC.",
        },
        "content": {
            "type": "string",
            "description": "Text content to write to the file.",
        },
    },
    "required": ["path", "content"],
}

WINDOWS_FILE_DELETE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Full path to the file to delete on the remote Windows PC.",
        }
    },
    "required": ["path"],
}

WINDOWS_MOUSE_MOVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "x": {
            "type": "integer",
            "description": "Absolute X coordinate (screen pixel).",
        },
        "y": {
            "type": "integer",
            "description": "Absolute Y coordinate (screen pixel).",
        },
    },
    "required": ["x", "y"],
}

WINDOWS_MOUSE_CLICK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "button": {
            "type": "string",
            "description": "Mouse button: 'left' (default), 'right', or 'middle'.",
            "default": "left",
        },
        "x": {
            "type": "integer",
            "description": "X coordinate to move to before clicking (null = click at current position).",
        },
        "y": {
            "type": "integer",
            "description": "Y coordinate to move to before clicking (null = click at current position).",
        },
    },
}

WINDOWS_MOUSE_DOUBLECLICK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "x": {
            "type": "integer",
            "description": "X coordinate (null = current position).",
        },
        "y": {
            "type": "integer",
            "description": "Y coordinate (null = current position).",
        },
    },
}

WINDOWS_MOUSE_SCROLL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "direction": {
            "type": "string",
            "description": "Scroll direction: 'up' (default) or 'down'.",
            "default": "up",
        },
        "clicks": {
            "type": "integer",
            "description": "Number of scroll clicks (default: 3).",
            "default": 3,
        },
    },
}

WINDOWS_MOUSE_POSITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "description": "Get the current mouse cursor position (x, y) on the remote Windows PC.",
}

WINDOWS_KEYBOARD_TYPE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "Text string to type on the remote Windows PC.",
        }
    },
    "required": ["text"],
}

WINDOWS_KEYBOARD_PRESS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "key": {
            "type": "string",
            "description": "Key to press (e.g., 'enter', 'escape', 'tab', 'a', 'f5', 'shift', 'ctrl').",
        }
    },
    "required": ["key"],
}

WINDOWS_KEYBOARD_HOTKEY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "keys": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of keys for the hotkey combination (e.g., ['ctrl', 'c'] for copy, ['alt', 'tab']).",
        }
    },
    "required": ["keys"],
}

WINDOWS_WINDOW_FOCUS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title_substring": {
            "type": "string",
            "description": "Substring of the window title to bring to focus (e.g., 'Notepad', 'Chrome').",
        }
    },
    "required": ["title_substring"],
}

WINDOWS_WINDOW_ACTIVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "description": "Get information about the currently active window on the remote Windows PC.",
}

WINDOWS_WINDOW_LIST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "description": "List all visible windows on the remote Windows PC.",
}

WINDOWS_SCREENSHOT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "region": {
            "type": "string",
            "description": "Optional screenshot region as 'x,y,w,h' (e.g., '0,0,800,600'). Captures full screen if omitted.",
        }
    },
}

WINDOWS_PROCESSES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "description": "List running processes on the remote Windows PC.",
}

WINDOWS_PROCESS_KILL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pid": {
            "type": "integer",
            "description": "PID of the process to terminate.",
        }
    },
    "required": ["pid"],
}

WINDOWS_SYSTEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "description": "Get system information (hostname, OS version, CPU count, RAM, etc.) from the remote Windows PC.",
}


# ---------------------------------------------------------------------------
# Hook: on_session_start
# ---------------------------------------------------------------------------

def on_session_start(**kwargs: Any) -> None:
    """Check agent health when a Hermes session starts."""
    state = _load_state()
    if state.get("enabled", True):
        result_raw = _make_request("GET", "/health")
        try:
            result = json.loads(result_raw)
        except (json.JSONDecodeError, TypeError):
            print(
                f"[windows-control] Agent unreachable at {state['agent_url']} "
                f"- invalid response: {result_raw[:200]}"
            )
            return
        if "error" in result:
            print(
                f"[windows-control] Agent unreachable at {state['agent_url']} "
                f"- error: {result['error']}"
            )
        else:
            print(
                f"[windows-control] Agent healthy at {state['agent_url']} "
                f"- status: {result.get('status', 'unknown')}"
            )
    else:
        print("[windows-control] Plugin is disabled in state.json. Skipping health check.")


# ---------------------------------------------------------------------------
# Plugin entry point
# ---------------------------------------------------------------------------

def register(ctx: Any) -> None:
    """Register the windows-control plugin with the Hermes runtime."""
    ctx.register_hook("on_session_start", on_session_start)

    ctx.register_tool(
        "windows_health",
        "windows",
        WINDOWS_HEALTH_SCHEMA,
        _health_handler,
    )
    ctx.register_tool(
        "windows_capabilities",
        "windows",
        WINDOWS_CAPABILITIES_SCHEMA,
        _capabilities_handler,
    )
    ctx.register_tool(
        "windows_exec",
        "windows",
        WINDOWS_EXEC_SCHEMA,
        _exec_handler,
    )
    ctx.register_tool(
        "windows_file_read",
        "windows",
        WINDOWS_FILE_READ_SCHEMA,
        _file_read_handler,
    )
    ctx.register_tool(
        "windows_file_write",
        "windows",
        WINDOWS_FILE_WRITE_SCHEMA,
        _file_write_handler,
    )
    ctx.register_tool(
        "windows_file_delete",
        "windows",
        WINDOWS_FILE_DELETE_SCHEMA,
        _file_delete_handler,
    )
    ctx.register_tool(
        "windows_mouse_move",
        "windows",
        WINDOWS_MOUSE_MOVE_SCHEMA,
        _mouse_move_handler,
    )
    ctx.register_tool(
        "windows_mouse_click",
        "windows",
        WINDOWS_MOUSE_CLICK_SCHEMA,
        _mouse_click_handler,
    )
    ctx.register_tool(
        "windows_mouse_doubleclick",
        "windows",
        WINDOWS_MOUSE_DOUBLECLICK_SCHEMA,
        _mouse_doubleclick_handler,
    )
    ctx.register_tool(
        "windows_mouse_scroll",
        "windows",
        WINDOWS_MOUSE_SCROLL_SCHEMA,
        _mouse_scroll_handler,
    )
    ctx.register_tool(
        "windows_mouse_position",
        "windows",
        WINDOWS_MOUSE_POSITION_SCHEMA,
        _mouse_position_handler,
    )
    ctx.register_tool(
        "windows_keyboard_type",
        "windows",
        WINDOWS_KEYBOARD_TYPE_SCHEMA,
        _keyboard_type_handler,
    )
    ctx.register_tool(
        "windows_keyboard_press",
        "windows",
        WINDOWS_KEYBOARD_PRESS_SCHEMA,
        _keyboard_press_handler,
    )
    ctx.register_tool(
        "windows_keyboard_hotkey",
        "windows",
        WINDOWS_KEYBOARD_HOTKEY_SCHEMA,
        _keyboard_hotkey_handler,
    )
    ctx.register_tool(
        "windows_window_focus",
        "windows",
        WINDOWS_WINDOW_FOCUS_SCHEMA,
        _window_focus_handler,
    )
    ctx.register_tool(
        "windows_window_active",
        "windows",
        WINDOWS_WINDOW_ACTIVE_SCHEMA,
        _window_active_handler,
    )
    ctx.register_tool(
        "windows_window_list",
        "windows",
        WINDOWS_WINDOW_LIST_SCHEMA,
        _window_list_handler,
    )
    ctx.register_tool(
        "windows_screenshot",
        "windows",
        WINDOWS_SCREENSHOT_SCHEMA,
        _screenshot_handler,
    )
    ctx.register_tool(
        "windows_processes",
        "windows",
        WINDOWS_PROCESSES_SCHEMA,
        _processes_handler,
    )
    ctx.register_tool(
        "windows_process_kill",
        "windows",
        WINDOWS_PROCESS_KILL_SCHEMA,
        _process_kill_handler,
    )
    ctx.register_tool(
        "windows_system",
        "windows",
        WINDOWS_SYSTEM_SCHEMA,
        _system_handler,
    )
