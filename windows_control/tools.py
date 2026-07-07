"""Tool handlers, HTTP helper, and state management for the windows-control plugin."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

PLUGIN_DIR = Path(__file__).parent
STATE_FILE = PLUGIN_DIR / "state.json"

_ctx = None


def set_plugin_context(ctx: Any) -> None:
    """Store the Hermes plugin context for config resolution."""
    global _ctx
    _ctx = ctx


def _load_state_fallback() -> dict[str, Any]:
    """Load agent configuration from state.json (flat or multi-agent format)."""
    if not STATE_FILE.exists():
        return _default_agents()
    try:
        with open(STATE_FILE) as f:
            stored = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _default_agents()

    # Auto-convert flat format to multi-agent format
    if "agents" not in stored:
        stored = {
            "agents": {
                "default": {
                    "url": stored.get("agent_url", "http://192.168.1.100:8765"),
                    "token": stored.get("token", "hermes-windows-agent-secret-token-change-me"),
                    "timeout": stored.get("timeout", 15),
                }
            },
            "default_agent": "default",
        }

    return stored


def _default_agents() -> dict[str, Any]:
    return {
        "agents": {
            "default": {
                "url": "http://192.168.1.100:8765",
                "token": "hermes-windows-agent-secret-token-change-me",
                "timeout": 15,
            }
        },
        "default_agent": "default",
    }


def _load_config_from_ctx() -> dict[str, Any] | None:
    """Try to load config via ctx.config() (config.yaml)."""
    if _ctx is not None and hasattr(_ctx, "config") and callable(_ctx.config):
        try:
            cfg = _ctx.config()
            if "windows_control" in cfg:
                return _clean_config(cfg["windows_control"])
        except Exception:
            pass
    return None


def _clean_config(config: dict[str, Any]) -> dict[str, Any]:
    """Ensure the config has the expected structure."""
    if "agents" not in config:
        config["agents"] = {}
    return config


def _load_config() -> tuple[dict[str, Any], str]:
    """Load configuration, trying ctx.config first, falling back to state.json."""
    cfg = _load_config_from_ctx()
    if cfg:
        return cfg, "config.yaml"
    return _load_state_fallback(), "state.json"


def _get_agent_config(config: dict[str, Any], agent: str | None = None) -> dict[str, Any]:
    """Resolve agent config by name, falling back to default_agent."""
    agents = config.get("agents", {})
    if not agents:
        raise RuntimeError(
            "No agents configured. Add a windows_control section to config.yaml or check state.json."
        )
    if agent and agent in agents:
        return agents[agent]
    default_name = config.get("default_agent") or next(iter(agents))
    return agents[default_name]


def _mask_token(token: str) -> str:
    """Return a masked version of a token for logging."""
    if not token or token.startswith("${"):
        return token
    if len(token) <= 8:
        return token[:3] + "***"
    return token[:6] + "***" + token[-4:]


def _make_request(
    method: str,
    path: str,
    json_data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int | None = None,
    agent: str | None = None,
) -> str:
    """Make an HTTP request to a Windows agent.

    Returns a JSON string (response or error).
    Supports multi-agent targeting via the ``agent`` parameter.
    """
    config, _ = _load_config()
    cfg = _get_agent_config(config, agent)
    url = f"{cfg['url'].rstrip('/')}{path}"
    headers = {"X-Agent-Token": cfg["token"]}
    try:
        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=json_data,
            params=params,
            timeout=timeout or cfg.get("timeout", 15),
        )
        resp.raise_for_status()
        return json.dumps(resp.json())
    except requests.exceptions.ConnectionError:
        return json.dumps({"error": "agent_unreachable", "url": url})
    except requests.exceptions.Timeout:
        return json.dumps({"error": "agent_timeout", "timeout": timeout or cfg.get("timeout", 15)})
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
# Tool handlers (unchanged — they accept **kwargs which includes agent)
# ---------------------------------------------------------------------------

def _health_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request("GET", "/health", agent=args.get("agent"))


def _capabilities_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request("GET", "/capabilities", agent=args.get("agent"))


def _exec_handler(args: dict[str, Any], **kwargs: Any) -> str:
    command = str(args.get("command", ""))
    shell = str(args.get("shell", "cmd"))
    if shell.lower() == "powershell":
        command = f"chcp 65001 > nul && {command}"
    else:
        command = f"chcp 65001 > nul & {command}"
    timeout = int(args.get("timeout", 15))
    return _make_request(
        "POST", "/exec",
        json_data={"command": command, "shell": shell, "timeout": timeout},
        agent=args.get("agent"),
    )


def _file_read_handler(args: dict[str, Any], **kwargs: Any) -> str:
    path = args.get("path", "")
    if isinstance(path, dict):
        path = path.get("path", "")
    return _make_request("GET", "/file", params={"path": str(path)}, agent=args.get("agent"))


def _file_write_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request(
        "PUT", "/file",
        json_data={"path": args["path"], "content": args["content"]},
        agent=args.get("agent"),
    )


def _file_delete_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request("POST", "/file/delete", json_data={"path": args["path"]}, agent=args.get("agent"))


def _mouse_move_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request(
        "POST", "/mouse/move",
        json_data={"x": int(args["x"]), "y": int(args["y"])},
        agent=args.get("agent"),
    )


def _mouse_click_handler(args: dict[str, Any], **kwargs: Any) -> str:
    body: dict[str, Any] = {"button": args.get("button", "left")}
    if args.get("x") is not None:
        body["x"] = int(args["x"])
    if args.get("y") is not None:
        body["y"] = int(args["y"])
    return _make_request("POST", "/mouse/click", json_data=body, agent=args.get("agent"))


def _mouse_doubleclick_handler(args: dict[str, Any], **kwargs: Any) -> str:
    body: dict[str, Any] = {}
    if args.get("x") is not None:
        body["x"] = int(args["x"])
    if args.get("y") is not None:
        body["y"] = int(args["y"])
    return _make_request("POST", "/mouse/doubleclick", json_data=body, agent=args.get("agent"))


def _mouse_scroll_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request(
        "POST", "/mouse/scroll",
        json_data={"direction": str(args.get("direction", "up")), "clicks": int(args.get("clicks", 3))},
        agent=args.get("agent"),
    )


def _mouse_position_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request("GET", "/mouse/position", agent=args.get("agent"))


def _keyboard_type_handler(args: dict[str, Any], **kwargs: Any) -> str:
    text = args.get("text", "")
    if isinstance(text, dict):
        text = text.get("text", "")
    return _make_request("POST", "/keyboard/type", json_data={"text": str(text)}, agent=args.get("agent"))


def _keyboard_press_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request(
        "POST", "/keyboard/press", json_data={"key": str(args["key"])}, agent=args.get("agent")
    )


def _keyboard_hotkey_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request(
        "POST", "/keyboard/hotkey", json_data={"keys": list(args["keys"])}, agent=args.get("agent")
    )


def _window_focus_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request(
        "POST", "/window/focus",
        json_data={"title_substring": str(args["title_substring"])},
        agent=args.get("agent"),
    )


def _window_active_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request("GET", "/window/active", agent=args.get("agent"))


def _window_list_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request("GET", "/window/list", agent=args.get("agent"))


def _screenshot_handler(args: dict[str, Any], **kwargs: Any) -> str:
    params: dict[str, Any] = {}
    region = args.get("region")
    if region:
        if isinstance(region, dict):
            region = region.get("region", "")
        params["region"] = str(region)
    return _make_request("GET", "/screenshot", params=params, timeout=10, agent=args.get("agent"))


def _processes_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request("GET", "/processes", agent=args.get("agent"))


def _process_kill_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request(
        "POST", "/process/kill", json_data={"pid": int(args["pid"])}, agent=args.get("agent")
    )


def _system_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request("GET", "/system", agent=args.get("agent"))


def _open_app_handler(args: dict[str, Any], **kwargs: Any) -> str:
    executable = str(args.get("executable", ""))
    arguments = str(args.get("arguments", ""))
    wait_focus = bool(args.get("wait_focus", True))
    agent = args.get("agent")

    if not executable:
        return json.dumps({"error": "missing executable"})

    cmd = f"start '' '{executable}'"
    if arguments:
        cmd += f" {arguments}"

    exec_result = json.loads(_make_request(
        "POST", "/exec",
        json_data={"command": cmd, "shell": "cmd", "timeout": 10},
        agent=agent,
    ))

    if wait_focus:
        time.sleep(1.5)
        focus_result = json.loads(_make_request(
            "POST", "/window/focus",
            json_data={"title_substring": executable.rsplit(".", 1)[0]},
            timeout=5,
            agent=agent,
        ))
        return json.dumps({"exec": exec_result, "focus": focus_result})

    return json.dumps({"exec": exec_result})


# ---------------------------------------------------------------------------
# Hook: on_session_start
# ---------------------------------------------------------------------------

def on_session_start(ctx: Any = None, **kwargs: Any) -> None:
    """Ping all configured agents on session start."""
    if ctx:
        set_plugin_context(ctx)

    config, source = _load_config()
    agents = config.get("agents", {})
    agent_names = ", ".join(agents.keys()) if agents else "(none)"
    print(f"[windows_control] Loaded {len(agents)} agent(s) from {source}: {agent_names}")

    for name, cfg in agents.items():
        try:
            url = f"{cfg['url'].rstrip('/')}/health"
            headers = {"X-Agent-Token": cfg["token"]}
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                status_msg = f"healthy (status: {data.get('status', 'ok')})"
            else:
                status_msg = f"status {r.status_code}"
        except requests.exceptions.ConnectionError:
            status_msg = "unreachable (connection refused)"
        except requests.exceptions.Timeout:
            status_msg = "unreachable (timeout)"
        except Exception as exc:
            status_msg = f"error: {exc}"
        print(f"[windows_control] Agent '{name}' ({cfg['url']}) — {status_msg}")
