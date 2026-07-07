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

    Returns a JSON string (response or error).
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
# Tool handlers
# ---------------------------------------------------------------------------

def _health_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /health"""
    return _make_request("GET", "/health")


def _capabilities_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /capabilities"""
    return _make_request("GET", "/capabilities")


def _exec_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /exec"""
    command = str(args.get("command", ""))
    shell = str(args.get("shell", "cmd"))
    timeout = int(args.get("timeout", 30))
    return _make_request(
        "POST",
        "/exec",
        json_data={
            "command": command,
            "shell": shell,
            "timeout": timeout,
        },
    )


def _file_read_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /file"""
    path = args.get("path", "")
    if isinstance(path, dict):
        path = path.get("path", "")
    return _make_request("GET", "/file", params={"path": str(path)})


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
        "POST", "/mouse/move", json_data={"x": int(args["x"]), "y": int(args["y"])}
    )


def _mouse_click_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /mouse/click"""
    body: dict[str, Any] = {"button": args.get("button", "left")}
    if args.get("x") is not None:
        body["x"] = int(args["x"])
    if args.get("y") is not None:
        body["y"] = int(args["y"])
    return _make_request("POST", "/mouse/click", json_data=body)


def _mouse_doubleclick_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /mouse/doubleclick"""
    body: dict[str, Any] = {}
    if args.get("x") is not None:
        body["x"] = int(args["x"])
    if args.get("y") is not None:
        body["y"] = int(args["y"])
    return _make_request("POST", "/mouse/doubleclick", json_data=body)


def _mouse_scroll_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /mouse/scroll"""
    return _make_request(
        "POST",
        "/mouse/scroll",
        json_data={
            "direction": str(args.get("direction", "up")),
            "clicks": int(args.get("clicks", 3)),
        },
    )


def _mouse_position_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /mouse/position"""
    return _make_request("GET", "/mouse/position")


def _keyboard_type_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /keyboard/type"""
    text = args.get("text", "")
    if isinstance(text, dict):
        text = text.get("text", "")
    return _make_request(
        "POST", "/keyboard/type", json_data={"text": str(text)}
    )


def _keyboard_press_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /keyboard/press"""
    return _make_request(
        "POST", "/keyboard/press", json_data={"key": str(args["key"])}
    )


def _keyboard_hotkey_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /keyboard/hotkey"""
    return _make_request(
        "POST", "/keyboard/hotkey", json_data={"keys": list(args["keys"])}
    )


def _window_focus_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /window/focus"""
    return _make_request(
        "POST",
        "/window/focus",
        json_data={"title_substring": str(args["title_substring"])},
    )


def _window_active_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /window/active"""
    return _make_request("GET", "/window/active")


def _window_list_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /window/list"""
    return _make_request("GET", "/window/list")


def _screenshot_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /screenshot"""
    params: dict[str, Any] = {}
    region = args.get("region")
    if region:
        if isinstance(region, dict):
            region = region.get("region", "")
        params["region"] = str(region)
    return _make_request("GET", "/screenshot", params=params)


def _processes_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /processes"""
    return _make_request("GET", "/processes")


def _process_kill_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /process/kill"""
    return _make_request(
        "POST", "/process/kill", json_data={"pid": int(args["pid"])}
    )


def _system_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /system"""
    return _make_request("GET", "/system")


# ---------------------------------------------------------------------------
# Tool schemas  (Hermes format: name + description + parameters{...})
# ---------------------------------------------------------------------------

def _s(name: str, desc: str, properties: dict[str, Any],
       required: list[str] | None = None) -> dict[str, Any]:
    """Build a Hermes-compliant tool schema."""
    schema: dict[str, Any] = {
        "name": name,
        "description": desc,
        "parameters": {
            "type": "object",
            "properties": properties,
        },
    }
    if required:
        schema["parameters"]["required"] = required
    return schema


WINDOWS_HEALTH_SCHEMA = _s(
    "windows_health",
    "Check the health status of the remote Windows agent.",
    {},
)

WINDOWS_CAPABILITIES_SCHEMA = _s(
    "windows_capabilities",
    "List available modules and endpoints on the remote Windows agent.",
    {},
)

WINDOWS_EXEC_SCHEMA = _s(
    "windows_exec",
    "Execute a command on the remote Windows PC via cmd or powershell.",
    {
        "command": {
            "type": "string",
            "description": "Command to execute on the remote PC (e.g., 'dir', 'ipconfig').",
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
    ["command"],
)

WINDOWS_FILE_READ_SCHEMA = _s(
    "windows_file_read",
    "Read a file from the remote Windows PC.",
    {
        "path": {
            "type": "string",
            "description": "Full path to the file (e.g., 'C:\\Users\\admin\\doc.txt').",
        },
    },
    ["path"],
)

WINDOWS_FILE_WRITE_SCHEMA = _s(
    "windows_file_write",
    "Write content to a file on the remote Windows PC.",
    {
        "path": {
            "type": "string",
            "description": "Full path to the file to write.",
        },
        "content": {
            "type": "string",
            "description": "Text content to write to the file.",
        },
    },
    ["path", "content"],
)

WINDOWS_FILE_DELETE_SCHEMA = _s(
    "windows_file_delete",
    "Delete a file from the remote Windows PC.",
    {
        "path": {
            "type": "string",
            "description": "Full path to the file to delete.",
        },
    },
    ["path"],
)

WINDOWS_MOUSE_MOVE_SCHEMA = _s(
    "windows_mouse_move",
    "Move the mouse cursor to absolute coordinates on the remote PC.",
    {
        "x": {"type": "integer", "description": "Absolute X coordinate (pixels)."},
        "y": {"type": "integer", "description": "Absolute Y coordinate (pixels)."},
    },
    ["x", "y"],
)

WINDOWS_MOUSE_CLICK_SCHEMA = _s(
    "windows_mouse_click",
    "Click a mouse button, optionally at specific coordinates.",
    {
        "button": {
            "type": "string",
            "description": "Mouse button: 'left' (default), 'right', or 'middle'.",
            "default": "left",
        },
        "x": {
            "type": "integer",
            "description": "X coordinate (null = click at current position).",
        },
        "y": {
            "type": "integer",
            "description": "Y coordinate (null = click at current position).",
        },
    },
)

WINDOWS_MOUSE_DOUBLECLICK_SCHEMA = _s(
    "windows_mouse_doubleclick",
    "Double-click at the current or specified coordinates.",
    {
        "x": {
            "type": "integer",
            "description": "X coordinate (null = current position).",
        },
        "y": {
            "type": "integer",
            "description": "Y coordinate (null = current position).",
        },
    },
)

WINDOWS_MOUSE_SCROLL_SCHEMA = _s(
    "windows_mouse_scroll",
    "Scroll the mouse wheel up or down.",
    {
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
)

WINDOWS_MOUSE_POSITION_SCHEMA = _s(
    "windows_mouse_position",
    "Get the current mouse cursor position (x, y) on the remote PC.",
    {},
)

WINDOWS_KEYBOARD_TYPE_SCHEMA = _s(
    "windows_keyboard_type",
    "Type a text string on the remote PC.",
    {
        "text": {
            "type": "string",
            "description": "Text to type.",
        },
    },
    ["text"],
)

WINDOWS_KEYBOARD_PRESS_SCHEMA = _s(
    "windows_keyboard_press",
    "Press a single key on the remote PC.",
    {
        "key": {
            "type": "string",
            "description": "Key to press (e.g., 'enter', 'escape', 'tab', 'f5').",
        },
    },
    ["key"],
)

WINDOWS_KEYBOARD_HOTKEY_SCHEMA = _s(
    "windows_keyboard_hotkey",
    "Press a key combination (hotkey) on the remote PC.",
    {
        "keys": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of keys (e.g., ['ctrl', 'c'] for copy).",
        },
    },
    ["keys"],
)

WINDOWS_WINDOW_FOCUS_SCHEMA = _s(
    "windows_window_focus",
    "Bring a window into focus by its title substring.",
    {
        "title_substring": {
            "type": "string",
            "description": "Substring of the window title (e.g., 'Notepad').",
        },
    },
    ["title_substring"],
)

WINDOWS_WINDOW_ACTIVE_SCHEMA = _s(
    "windows_window_active",
    "Get info about the currently active window on the remote PC.",
    {},
)

WINDOWS_WINDOW_LIST_SCHEMA = _s(
    "windows_window_list",
    "List all visible windows on the remote PC.",
    {},
)

WINDOWS_SCREENSHOT_SCHEMA = _s(
    "windows_screenshot",
    "Capture a screenshot of the remote PC's display.",
    {
        "region": {
            "type": "string",
            "description": "Optional region as 'x,y,w,h' (e.g., '0,0,800,600'). Full screen if omitted.",
        },
    },
)

WINDOWS_PROCESSES_SCHEMA = _s(
    "windows_processes",
    "List running processes on the remote PC.",
    {},
)

WINDOWS_PROCESS_KILL_SCHEMA = _s(
    "windows_process_kill",
    "Terminate a process by its PID.",
    {
        "pid": {
            "type": "integer",
            "description": "PID of the process to terminate.",
        },
    },
    ["pid"],
)

WINDOWS_SYSTEM_SCHEMA = _s(
    "windows_system",
    "Get system information from the remote PC (hostname, OS, CPU, RAM, disks, etc.).",
    {},
)


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

    tools: list[tuple[str, str, dict[str, Any], Any]] = [
        ("windows_health", "windows", WINDOWS_HEALTH_SCHEMA, _health_handler),
        ("windows_capabilities", "windows", WINDOWS_CAPABILITIES_SCHEMA, _capabilities_handler),
        ("windows_exec", "windows", WINDOWS_EXEC_SCHEMA, _exec_handler),
        ("windows_file_read", "windows", WINDOWS_FILE_READ_SCHEMA, _file_read_handler),
        ("windows_file_write", "windows", WINDOWS_FILE_WRITE_SCHEMA, _file_write_handler),
        ("windows_file_delete", "windows", WINDOWS_FILE_DELETE_SCHEMA, _file_delete_handler),
        ("windows_mouse_move", "windows", WINDOWS_MOUSE_MOVE_SCHEMA, _mouse_move_handler),
        ("windows_mouse_click", "windows", WINDOWS_MOUSE_CLICK_SCHEMA, _mouse_click_handler),
        ("windows_mouse_doubleclick", "windows", WINDOWS_MOUSE_DOUBLECLICK_SCHEMA, _mouse_doubleclick_handler),
        ("windows_mouse_scroll", "windows", WINDOWS_MOUSE_SCROLL_SCHEMA, _mouse_scroll_handler),
        ("windows_mouse_position", "windows", WINDOWS_MOUSE_POSITION_SCHEMA, _mouse_position_handler),
        ("windows_keyboard_type", "windows", WINDOWS_KEYBOARD_TYPE_SCHEMA, _keyboard_type_handler),
        ("windows_keyboard_press", "windows", WINDOWS_KEYBOARD_PRESS_SCHEMA, _keyboard_press_handler),
        ("windows_keyboard_hotkey", "windows", WINDOWS_KEYBOARD_HOTKEY_SCHEMA, _keyboard_hotkey_handler),
        ("windows_window_focus", "windows", WINDOWS_WINDOW_FOCUS_SCHEMA, _window_focus_handler),
        ("windows_window_active", "windows", WINDOWS_WINDOW_ACTIVE_SCHEMA, _window_active_handler),
        ("windows_window_list", "windows", WINDOWS_WINDOW_LIST_SCHEMA, _window_list_handler),
        ("windows_screenshot", "windows", WINDOWS_SCREENSHOT_SCHEMA, _screenshot_handler),
        ("windows_processes", "windows", WINDOWS_PROCESSES_SCHEMA, _processes_handler),
        ("windows_process_kill", "windows", WINDOWS_PROCESS_KILL_SCHEMA, _process_kill_handler),
        ("windows_system", "windows", WINDOWS_SYSTEM_SCHEMA, _system_handler),
    ]

    for name, toolset, schema, handler in tools:
        ctx.register_tool(
            name=name,
            toolset=toolset,
            schema=schema,
            handler=handler,
        )
