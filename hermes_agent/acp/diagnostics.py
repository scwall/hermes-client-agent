"""ACP diagnostics — inspect agent config, binary, and run functional test."""

import json
import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx

from hermes_agent.acp.models import AcpTask

_log = logging.getLogger("hermes-agent")

AGENT_CONFIG_PATHS = {
    "opencode": [
        "~/.config/opencode/opencode.jsonc",
        "~/.config/opencode/opencode.json",
        "~/.config/opencode/config.json",
    ],
    "claude": [
        "~/.claude/config.json",
        "~/.config/claude/config.json",
    ],
    "junie": [],
}

FUNCTIONAL_TEST_TIMEOUT = 10


def _strip_jsonc_comments(text):
    result = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                result.append(ch)
                i += 1
                result.append(text[i])
            elif ch == '"':
                in_string = False
                result.append(ch)
            else:
                result.append(ch)
            i += 1
            continue
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                while i < n and text[i] != "\n":
                    i += 1
                continue
            if nxt == "*":
                i += 2
                while i < n - 1 and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i += 2
                continue
        result.append(ch)
        i += 1
    return "".join(result)


def _strip_trailing_commas(text):
    return re.sub(r",(\s*[}\]])", r"\1", text)


def parse_jsonc(text):
    cleaned = _strip_jsonc_comments(text)
    cleaned = _strip_trailing_commas(cleaned)
    if not cleaned.strip():
        cleaned = "{}"
    return json.loads(cleaned)


def find_config_file(agent_type):
    paths = AGENT_CONFIG_PATHS.get(agent_type, [])
    for raw_path in paths:
        expanded = Path(raw_path).expanduser()
        if expanded.is_file():
            return expanded
    return None


def inspect_binary(agent_type):
    bin_name = agent_type if agent_type != "junie" else "opencode"
    path = shutil.which(bin_name)
    if not path:
        home_candidates = [
            Path.home() / ".npm-global" / "bin" / bin_name,
            Path.home() / ".local" / "bin" / bin_name,
            f"/usr/local/bin/{bin_name}",
            f"/usr/bin/{bin_name}",
        ]
        for c in home_candidates:
            if Path(c).is_file():
                path = str(c)
                break
    if not path:
        return {"installed": False, "path": None, "version": None}

    version = None
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version = result.stdout.strip()
    except Exception:
        pass
    return {"installed": True, "path": path, "version": version}


def inspect_config(agent_type):
    config_path = find_config_file(agent_type)
    if not config_path:
        return {"config_file": None, "default_model": None}

    try:
        raw = Path(config_path).read_text()
        data = parse_jsonc(raw)
    except json.JSONDecodeError as e:
        return {"config_file": str(config_path), "error": f"Config file is not valid JSON: {e}", "default_model": None}
    except Exception as e:
        return {"config_file": str(config_path), "error": f"Failed to read config: {e}", "default_model": None}

    default_model = None
    if isinstance(data, dict):
        default_model = data.get("default_model", data.get("defaultModel", None))

    return {
        "config_file": str(config_path),
        "default_model": default_model,
    }


def inspect_models(agent_url):
    result = {"models": [], "providers": [], "default": {}, "error": None}

    try:
        resp = httpx.get(f"{agent_url.rstrip('/')}/config", timeout=5)
        resp.raise_for_status()
        config_data = resp.json()
    except Exception as exc:
        result["error"] = f"Cannot fetch config from agent: {exc}"
        return result

    enabled = config_data.get("enabled_providers", [])
    if isinstance(enabled, list):
        for p in enabled:
            result["providers"].append({"id": p, "name": p})

    model_config = config_data.get("model", "")
    if model_config:
        result["default"] = {"model": model_config}

    try:
        proc = subprocess.run(
            ["opencode", "models", "--verbose"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            lines = proc.stdout.strip().split("\n")
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if line and line != "{" and not line.startswith("{") and not line.startswith("}"):
                    parts = line.split("/")
                    provider_candidate = parts[0] if len(parts) > 0 else ""
                    i += 1
                    json_lines = []
                    brace_count = 0
                    while i < len(lines):
                        current = lines[i].rstrip()
                        json_lines.append(current)
                        brace_count += current.count("{") - current.count("}")
                        if current.strip() == "}" and brace_count == 0:
                            i += 1
                            break
                        i += 1
                    try:
                        model_data = json.loads("\n".join(json_lines))
                        result["models"].append(
                            {
                                "id": model_data.get("id", ""),
                                "name": model_data.get("name", ""),
                                "providerID": model_data.get("providerID", provider_candidate),
                                "family": model_data.get("family", ""),
                                "status": model_data.get("status", ""),
                                "limit_context": (model_data.get("limit") or {}).get("context"),
                            }
                        )
                    except json.JSONDecodeError:
                        pass
                else:
                    i += 1
    except Exception:
        pass

    return result


def functional_test(agent_url):
    try:
        resp = httpx.post(
            agent_url.rstrip("/"),
            json={"prompt": "respond with exactly the word OK and nothing else"},
            timeout=FUNCTIONAL_TEST_TIMEOUT,
        )
        if resp.status_code >= 400:
            return {"status": "failed", "detail": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text[:500]}
        has_ok = False
        if isinstance(data, dict):
            flat = json.dumps(data).lower()
            has_ok = "ok" in flat
        return {"status": "ok" if has_ok else "failed", "detail": "Response received" if has_ok else "Response did not contain OK"}
    except httpx.ConnectError:
        return {"status": "failed", "detail": "Cannot connect to agent"}
    except httpx.TimeoutException:
        return {"status": "failed", "detail": f"Timed out after {FUNCTIONAL_TEST_TIMEOUT}s"}
    except Exception as e:
        return {"status": "failed", "detail": str(e)[:200]}


def run_diagnostics(agent_type="opencode"):
    binary = inspect_binary(agent_type)
    config = inspect_config(agent_type)
    issues = []

    if not binary["installed"]:
        issues.append("OpenCode binary not found on this system")

    if config.get("config_file") is None:
        issues.append(f"No config file found for {agent_type}")

    if config.get("error"):
        issues.append(config["error"])

    models_info = {"models": [], "providers": [], "default": None, "error": "No agent URL available"}
    ft = {"status": "skipped", "detail": "No agent URL available"}
    from hermes_agent.acp import get_session_manager

    mgr = get_session_manager()
    sessions = mgr.list_sessions()
    if sessions:
        s = sessions[0]
        port = s["port"]
        agent_url = f"http://127.0.0.1:{port}"
        models_info = inspect_models(agent_url)
        ft = functional_test(agent_url)
        if ft["status"] == "failed":
            issues.append(f"Functional test failed: {ft['detail']}")

    return {
        "agent_type": agent_type,
        "binary": binary,
        "config": config,
        "models": models_info,
        "functional_test": ft,
        "sessions": sessions,
        "sessions_active": len(sessions),
        "async_tasks_running": AcpTask.count_running(),
        "issues": issues,
        "healthy": len(issues) == 0,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
