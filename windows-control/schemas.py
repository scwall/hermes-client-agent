"""Tool schemas for the windows-control Hermes plugin."""
from typing import Any


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
            "description": "Optional region as 'x,y,w,h' (e.g., '0,0,800,600').",
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

WINDOWS_OPEN_APP_SCHEMA = _s(
    "windows_open_app",
    "Launch an application on the remote PC and optionally bring its window to front.",
    {
        "executable": {
            "type": "string",
            "description": "Application name (e.g., 'notepad.exe', 'calc.exe', 'chrome.exe').",
        },
        "arguments": {
            "type": "string",
            "description": "Optional command-line arguments.",
            "default": "",
        },
        "wait_focus": {
            "type": "boolean",
            "description": "If true, bring the window to front after launch (default: true).",
            "default": True,
        },
    },
    ["executable"],
)
