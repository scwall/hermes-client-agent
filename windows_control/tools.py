"""Tool handlers, HTTP helper, and state management for the windows-control plugin."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

PLUGIN_DIR = Path(__file__).parent
STATE_FILE = PLUGIN_DIR / "state.json"

DEFAULT_STATE: dict[str, Any] = {
    "agent_url": "http://192.168.1.100:8765",
    "token": "hermes-windows-agent-secret-token-change-me",
    "timeout": 15,
    "enabled": True,
}


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


def _make_request(
    method: str,
    path: str,
    json_data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int | None = None,
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
            timeout=timeout or state["timeout"],
        )
        resp.raise_for_status()
        return json.dumps(resp.json())
    except requests.exceptions.ConnectionError:
        return json.dumps({"error": "agent_unreachable", "url": url})
    except requests.exceptions.Timeout:
        return json.dumps({"error": "agent_timeout", "timeout": timeout or state["timeout"]})
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        try:
            body = exc.response.text[:500] if exc.response is not None else "(no body)"
        except Exception:
            body = "(no body)"
        return json.dumps({"error": f"http_{status}", "detail": str(exc), "body": body})
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
    """POST /exec — forces UTF-8 via chcp 65001."""
    command = str(args.get("command", ""))
    shell = str(args.get("shell", "cmd"))
    if shell.lower() == "powershell":
        command = f"chcp 65001 > nul && {command}"
    else:
        command = f"chcp 65001 > nul & {command}"
    timeout = int(args.get("timeout", 15))
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
    """GET /screenshot — 10s timeout."""
    params: dict[str, Any] = {}
    region = args.get("region")
    if region:
        if isinstance(region, dict):
            region = region.get("region", "")
        params["region"] = str(region)
    return _make_request("GET", "/screenshot", params=params, timeout=10)


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


def _open_app_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """Launch an app via exec then bring its window to front."""
    executable = str(args.get("executable", ""))
    arguments = str(args.get("arguments", ""))
    wait_focus = bool(args.get("wait_focus", True))

    if not executable:
        return json.dumps({"error": "missing executable"})

    cmd = f"start '' '{executable}'"
    if arguments:
        cmd += f" {arguments}"

    exec_result = json.loads(_make_request(
        "POST", "/exec",
        json_data={"command": cmd, "shell": "cmd", "timeout": 10},
    ))

    if wait_focus:
        time.sleep(1.5)
        focus_result = json.loads(_make_request(
            "POST", "/window/focus",
            json_data={"title_substring": executable.rsplit(".", 1)[0]},
            timeout=5,
        ))
        return json.dumps({"exec": exec_result, "focus": focus_result})

    return json.dumps({"exec": exec_result})


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
