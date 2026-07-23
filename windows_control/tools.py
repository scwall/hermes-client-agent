"""Tool handlers, HTTP helper, and state management for the windows-control plugin."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

import requests

_log = logging.getLogger("windows_control")
_plugin_debug = os.environ.get("HERMES_PLUGIN_DEBUG", "false").lower() in ("true", "1", "yes")
if _plugin_debug:
    _log.setLevel(logging.DEBUG)

_ctx = None
_agent_status: dict[str, bool] = {}


def set_plugin_context(ctx: Any) -> None:
    """Store the Hermes plugin context for config resolution."""
    global _ctx
    _ctx = ctx


def _load_config_from_ctx() -> dict[str, Any] | None:
    """Load windows_control section from Hermes config.yaml via hermes_cli.config."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        if isinstance(cfg, dict) and "windows_control" in cfg:
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
    """Load configuration from ctx.config (config.yaml)."""
    cfg = _load_config_from_ctx()
    if cfg:
        return cfg, "config.yaml"
    msg = "No agents configured. Add a windows_control section to config.yaml. Format: https://github.com/scwall/hermes-client-agent#hermes-plugin"
    raise RuntimeError(msg)


def _get_agent_config(config: dict[str, Any], agent: str | None = None) -> dict[str, Any]:
    """Resolve agent config by name, falling back to default_agent."""
    agents = config.get("agents", {})
    if not agents:
        raise RuntimeError("No agents configured. Add a windows_control section to config.yaml or check state.json.")
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


def _check_agent(agent_name: str, cfg: dict[str, Any]) -> bool:
    """Silently check if an agent is reachable. Warns only once per failure."""
    if agent_name in _agent_status:
        return _agent_status[agent_name]
    ok = False
    try:
        health_url = f"{cfg['url'].rstrip('/')}/health"
        r = requests.get(health_url, headers={"X-Agent-Token": cfg["token"]}, timeout=5)
        ok = r.status_code == 200
    except Exception:
        pass
    _agent_status[agent_name] = ok
    if not ok:
        _log.warning("Agent '%s' unreachable at %s", agent_name, cfg["url"])
    return ok


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
    agent_name = agent or config.get("default_agent") or next(iter(config.get("agents", {})), "default")
    url = f"{cfg['url'].rstrip('/')}{path}"
    headers = {"X-Agent-Token": cfg["token"]}
    _check_agent(agent_name, cfg)
    if _plugin_debug:
        _log.debug("-> %s %s %s json=%s url=%s timeout=%ss", agent or "default", method, path, json.dumps(json_data, default=str)[:200] if json_data else "-", url, timeout or cfg.get("timeout", 15))
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
    if sys.platform == "win32":
        if shell.lower() in ("powershell", "ps"):
            command = f"[Console]::OutputEncoding = [Text.Encoding]::UTF8; {command}"
        else:
            command = f"chcp 65001 > nul & {command}"
    timeout = int(args.get("timeout", 15))
    return _make_request(
        "POST",
        "/exec",
        json_data={"command": command, "shell": shell, "timeout": timeout},
        agent=args.get("agent"),
    )


def _exec_batch_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """POST /exec/batch — multiple commands sequentially."""
    return _make_request(
        "POST",
        "/exec/batch",
        json_data={
            "commands": args["commands"],
            "stop_on_error": bool(args.get("stop_on_error", False)),
        },
        agent=args.get("agent"),
    )


def _file_read_handler(args: dict[str, Any], **kwargs: Any) -> str:
    path = args.get("path", "")
    if isinstance(path, dict):
        path = path.get("path", "")
    return _make_request("GET", "/file", params={"path": str(path)}, agent=args.get("agent"))


def _file_write_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request(
        "PUT",
        "/file",
        json_data={"path": args["path"], "content": args["content"]},
        agent=args.get("agent"),
    )


def _file_delete_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request("POST", "/file/delete", json_data={"path": args["path"]}, agent=args.get("agent"))


def _mouse_move_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request(
        "POST",
        "/mouse/move",
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
        "POST",
        "/mouse/scroll",
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
    return _make_request("POST", "/keyboard/press", json_data={"key": str(args["key"])}, agent=args.get("agent"))


def _keyboard_hotkey_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request("POST", "/keyboard/hotkey", json_data={"keys": list(args["keys"])}, agent=args.get("agent"))


def _window_focus_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request(
        "POST",
        "/window/focus",
        json_data={"title_substring": str(args["title_substring"])},
        agent=args.get("agent"),
    )


def _window_active_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request("GET", "/window/active", agent=args.get("agent"))


def _window_list_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request("GET", "/window/list", agent=args.get("agent"))


def _screenshot_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """GET /screenshot — supports scale/quality/format compression."""
    params: dict[str, Any] = {}
    for key in ("region", "scale", "quality", "format"):
        val = args.get(key)
        if val is not None:
            params[key] = str(val) if isinstance(val, str) else val
    return _make_request("GET", "/screenshot", params=params, timeout=10, agent=args.get("agent"))


def _processes_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request("GET", "/processes", agent=args.get("agent"))


def _process_kill_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request("POST", "/process/kill", json_data={"pid": int(args["pid"])}, agent=args.get("agent"))


def _system_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request("GET", "/system", agent=args.get("agent"))


def _acp_handler(args: dict[str, Any], **kwargs: Any) -> str:
    return _make_request(
        "POST",
        "/acp",
        json_data={
            "agent_url": str(args["agent_url"]),
            "prompt": str(args["prompt"]),
            "context": str(args.get("context", "")) if args.get("context") else "",
            "model": str(args.get("model", "")) if args.get("model") else "",
            "timeout": int(args.get("timeout", 300)),
        },
        timeout=int(args.get("timeout", 300)) + 10,
        agent=args.get("agent"),
    )


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

    exec_result = json.loads(
        _make_request(
            "POST",
            "/exec",
            json_data={"command": cmd, "shell": "cmd", "timeout": 10},
            agent=agent,
        )
    )

    if wait_focus:
        time.sleep(1.5)
        focus_result = json.loads(
            _make_request(
                "POST",
                "/window/focus",
                json_data={"title_substring": executable.rsplit(".", 1)[0]},
                timeout=5,
                agent=agent,
            )
        )
        return json.dumps({"exec": exec_result, "focus": focus_result})

    return json.dumps({"exec": exec_result})
