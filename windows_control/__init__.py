"""Hermes native plugin: windows-control.

Remote Windows PC control via HTTP REST API.
Communicates with a FastAPI agent running on a Windows machine.
"""

from __future__ import annotations

from typing import Any

from .schemas import (
    WINDOWS_ACP_SCHEMA,
    WINDOWS_CAPABILITIES_SCHEMA,
    WINDOWS_EXEC_BATCH_SCHEMA,
    WINDOWS_EXEC_SCHEMA,
    WINDOWS_FILE_DELETE_SCHEMA,
    WINDOWS_FILE_READ_SCHEMA,
    WINDOWS_FILE_WRITE_SCHEMA,
    WINDOWS_HEALTH_SCHEMA,
    WINDOWS_KEYBOARD_HOTKEY_SCHEMA,
    WINDOWS_KEYBOARD_PRESS_SCHEMA,
    WINDOWS_KEYBOARD_TYPE_SCHEMA,
    WINDOWS_MOUSE_CLICK_SCHEMA,
    WINDOWS_MOUSE_DOUBLECLICK_SCHEMA,
    WINDOWS_MOUSE_MOVE_SCHEMA,
    WINDOWS_MOUSE_POSITION_SCHEMA,
    WINDOWS_MOUSE_SCROLL_SCHEMA,
    WINDOWS_OPEN_APP_SCHEMA,
    WINDOWS_PROCESS_KILL_SCHEMA,
    WINDOWS_PROCESSES_SCHEMA,
    WINDOWS_SCREENSHOT_SCHEMA,
    WINDOWS_SYSTEM_SCHEMA,
    WINDOWS_WINDOW_ACTIVE_SCHEMA,
    WINDOWS_WINDOW_FOCUS_SCHEMA,
    WINDOWS_WINDOW_LIST_SCHEMA,
)
from .tools import (
    _acp_handler,
    _capabilities_handler,
    _exec_batch_handler,
    _exec_handler,
    _file_delete_handler,
    _file_read_handler,
    _file_write_handler,
    _health_handler,
    _keyboard_hotkey_handler,
    _keyboard_press_handler,
    _keyboard_type_handler,
    _mouse_click_handler,
    _mouse_doubleclick_handler,
    _mouse_move_handler,
    _mouse_position_handler,
    _mouse_scroll_handler,
    _open_app_handler,
    _process_kill_handler,
    _processes_handler,
    _screenshot_handler,
    _system_handler,
    _window_active_handler,
    _window_focus_handler,
    _window_list_handler,
    set_plugin_context,
)


def register(ctx: Any) -> None:
    """Register the windows-control plugin with the Hermes runtime."""
    set_plugin_context(ctx)

    try:
        from .tools import _load_config as _lc
        config, source = _lc()
        agents = config.get("agents", {})
        names = ", ".join(agents.keys()) if agents else "(none)"
        print(f"[windows_control] Loaded {len(agents)} agent(s) from {source}: {names}")
    except RuntimeError as exc:
        print(f"[windows_control] {exc}")

    tools: list[tuple[str, str, dict[str, Any], Any]] = [
        ("windows_health", "windows", WINDOWS_HEALTH_SCHEMA, _health_handler),
        ("windows_capabilities", "windows", WINDOWS_CAPABILITIES_SCHEMA, _capabilities_handler),
        ("windows_acp", "windows", WINDOWS_ACP_SCHEMA, _acp_handler),
        ("windows_exec", "windows", WINDOWS_EXEC_SCHEMA, _exec_handler),
        ("windows_exec_batch", "windows", WINDOWS_EXEC_BATCH_SCHEMA, _exec_batch_handler),
        ("windows_file_read", "windows", WINDOWS_FILE_READ_SCHEMA, _file_read_handler),
        ("windows_file_write", "windows", WINDOWS_FILE_WRITE_SCHEMA, _file_write_handler),
        ("windows_file_delete", "windows", WINDOWS_FILE_DELETE_SCHEMA, _file_delete_handler),
        ("windows_mouse_move", "windows", WINDOWS_MOUSE_MOVE_SCHEMA, _mouse_move_handler),
        ("windows_mouse_click", "windows", WINDOWS_MOUSE_CLICK_SCHEMA, _mouse_click_handler),
        ("windows_mouse_doubleclick", "windows",
         WINDOWS_MOUSE_DOUBLECLICK_SCHEMA, _mouse_doubleclick_handler),
        ("windows_mouse_scroll", "windows",
         WINDOWS_MOUSE_SCROLL_SCHEMA, _mouse_scroll_handler),
        ("windows_mouse_position", "windows",
         WINDOWS_MOUSE_POSITION_SCHEMA, _mouse_position_handler),
        ("windows_open_app", "windows",
         WINDOWS_OPEN_APP_SCHEMA, _open_app_handler),
        ("windows_keyboard_type", "windows",
         WINDOWS_KEYBOARD_TYPE_SCHEMA, _keyboard_type_handler),
        ("windows_keyboard_press", "windows",
         WINDOWS_KEYBOARD_PRESS_SCHEMA, _keyboard_press_handler),
        ("windows_keyboard_hotkey", "windows",
         WINDOWS_KEYBOARD_HOTKEY_SCHEMA, _keyboard_hotkey_handler),
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
