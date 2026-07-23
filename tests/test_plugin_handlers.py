"""Unit tests for the windows_control plugin config and all tool handlers."""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

import windows_control.tools as tools

# ── Config tests ─────────────────────────────────────────────────


class TestLoadConfig:
    """Tests for _load_config_from_ctx() and _load_config()."""

    def test_loads_from_hermes_config(self):
        with patch.object(tools, "_load_config_from_ctx", return_value={"agents": {"a": {"url": "http://x", "token": "t"}}}):
            cfg, src = tools._load_config()
            assert src == "config.yaml"
            assert "a" in cfg["agents"]

    def test_no_config_raises(self):
        with patch.object(tools, "_load_config_from_ctx", return_value=None):
            with pytest.raises(RuntimeError, match="No agents configured"):
                tools._load_config()


class TestGetAgentConfig:
    """Tests for _get_agent_config()."""

    def test_specific_agent(self):
        config = {"agents": {"a": {"url": "http://a"}, "b": {"url": "http://b"}}, "default_agent": "a"}
        assert tools._get_agent_config(config, "b")["url"] == "http://b"

    def test_default_fallback(self):
        config = {"agents": {"a": {"url": "http://a"}, "b": {"url": "http://b"}}, "default_agent": "b"}
        assert tools._get_agent_config(config)["url"] == "http://b"

    def test_first_fallback_no_default(self):
        config = {"agents": {"x": {"url": "http://x"}}}
        assert tools._get_agent_config(config)["url"] == "http://x"

    def test_empty_raises(self):
        with pytest.raises(RuntimeError, match="No agents configured"):
            tools._get_agent_config({"agents": {}})


class TestMaskToken:
    """Tests for _mask_token()."""

    def test_normal(self):
        masked = tools._mask_token("hermes-windows-agent-secret-change-me")
        assert "***" in masked
        assert masked.startswith("hermes")
        assert masked.endswith("e-me")

    def test_env_var(self):
        assert tools._mask_token("${LAPTOP_TOKEN}") == "${LAPTOP_TOKEN}"

    def test_short(self):
        assert tools._mask_token("abcd") == "abc***"

    def test_empty(self):
        assert tools._mask_token("") == ""


# ── Handler tests ─────────────────────────────────────────────────


def _mock_request(return_value=None, side_effect=None):
    return patch.object(tools, "_make_request", return_value=return_value, side_effect=side_effect)


class TestHandlers:
    """Tests for all 22 tool handlers."""

    def test_health(self):
        with _mock_request('{"status":"ok"}'):
            r = json.loads(tools._health_handler({}))
            assert r["status"] == "ok"

    def test_capabilities(self):
        with _mock_request('{"modules":{"pyautogui":true}}'):
            r = json.loads(tools._capabilities_handler({}))
            assert r["modules"]["pyautogui"] is True

    def test_exec_cmd(self):
        with _mock_request('{"stdout":"hello","exit_code":0}') as mock:
            tools._exec_handler({"command": "echo hello", "shell": "cmd"})
            cmd = mock.call_args[1]["json_data"]["command"]
            if sys.platform == "win32":
                assert "chcp 65001" in cmd
            else:
                assert cmd == "echo hello"

    def test_exec_powershell(self):
        with _mock_request('{"stdout":"hello","exit_code":0}') as mock:
            tools._exec_handler({"command": "Write-Output hello", "shell": "powershell"})
            cmd = mock.call_args[1]["json_data"]["command"]
            if sys.platform == "win32":
                assert "OutputEncoding" in cmd
            else:
                assert cmd == "Write-Output hello"

    def test_file_read(self):
        with _mock_request('{"path":"/f","content":"data"}'):
            r = json.loads(tools._file_read_handler({"path": "/f"}))
            assert r["path"] == "/f"

    def test_file_read_double_wrap(self):
        with _mock_request('{"path":"/f","content":"data"}'):
            r = json.loads(tools._file_read_handler({"path": {"path": "/f"}}))
            assert r["path"] == "/f"

    def test_file_write(self):
        with _mock_request('{"written":true}'):
            r = json.loads(tools._file_write_handler({"path": "/f", "content": "c"}))
            assert r["written"] is True

    def test_file_delete(self):
        with _mock_request('{"deleted":true}'):
            r = json.loads(tools._file_delete_handler({"path": "/f"}))
            assert r["deleted"] is True

    def test_mouse_move(self):
        with _mock_request('{"x":100,"y":200}'):
            r = json.loads(tools._mouse_move_handler({"x": 100, "y": 200}))
            assert r == {"x": 100, "y": 200}

    def test_mouse_click(self):
        with _mock_request("{}") as mock:
            tools._mouse_click_handler({"button": "right", "x": 42, "y": 99})
            data = mock.call_args[1]["json_data"]
            assert data["button"] == "right"
            assert data["x"] == 42

    def test_mouse_click_no_coords(self):
        with _mock_request("{}") as mock:
            tools._mouse_click_handler({"button": "left"})
            data = mock.call_args[1]["json_data"]
            assert "x" not in data

    def test_mouse_doubleclick(self):
        with _mock_request("{}") as mock:
            tools._mouse_doubleclick_handler({"x": 10, "y": 20})
            data = mock.call_args[1]["json_data"]
            assert data["x"] == 10

    def test_mouse_scroll(self):
        with _mock_request("{}") as mock:
            tools._mouse_scroll_handler({"direction": "up", "clicks": 5})
            data = mock.call_args[1]["json_data"]
            assert data["clicks"] == 5

    def test_mouse_position(self):
        with _mock_request('{"x":0,"y":0}'):
            r = json.loads(tools._mouse_position_handler({}))
            assert "x" in r

    def test_keyboard_type(self):
        with _mock_request("{}") as mock:
            tools._keyboard_type_handler({"text": "hello"})
            assert mock.call_args[1]["json_data"]["text"] == "hello"

    def test_keyboard_type_double_wrap(self):
        with _mock_request("{}") as mock:
            tools._keyboard_type_handler({"text": {"text": "world"}})
            assert mock.call_args[1]["json_data"]["text"] == "world"

    def test_keyboard_press(self):
        with _mock_request("{}") as mock:
            tools._keyboard_press_handler({"key": "enter"})
            assert mock.call_args[1]["json_data"]["key"] == "enter"

    def test_keyboard_hotkey(self):
        with _mock_request("{}") as mock:
            tools._keyboard_hotkey_handler({"keys": ["ctrl", "c"]})
            assert mock.call_args[1]["json_data"]["keys"] == ["ctrl", "c"]

    def test_window_focus(self):
        with _mock_request('{"focused":"Notepad"}'):
            r = json.loads(tools._window_focus_handler({"title_substring": "Notepad"}))
            assert r["focused"] == "Notepad"

    def test_window_active(self):
        with _mock_request('{"title":"Terminal"}'):
            r = json.loads(tools._window_active_handler({}))
            assert r["title"] == "Terminal"

    def test_window_list(self):
        with _mock_request('[{"title":"a"},{"title":"b"}]'):
            r = json.loads(tools._window_list_handler({}))
            assert len(r) == 2

    def test_screenshot(self):
        with _mock_request('{"format":"jpeg","width":800}'):
            r = json.loads(tools._screenshot_handler({}))
            assert r["format"] == "jpeg"

    def test_screenshot_with_params(self):
        with _mock_request("{}") as mock:
            tools._screenshot_handler({"scale": 0.5, "quality": 60, "format": "jpeg"})
            params = mock.call_args[1]["params"]
            assert params["scale"] == 0.5
            assert params["quality"] == 60

    def test_processes(self):
        with _mock_request('[{"name":"python","pid":123}]'):
            r = json.loads(tools._processes_handler({}))
            assert r[0]["name"] == "python"

    def test_process_kill(self):
        with _mock_request("{}") as mock:
            tools._process_kill_handler({"pid": 9999})
            assert mock.call_args[1]["json_data"]["pid"] == 9999

    def test_system(self):
        with _mock_request('{"hostname":"PC","os":"Windows"}'):
            r = json.loads(tools._system_handler({}))
            assert r["hostname"] == "PC"

    def test_open_app(self):
        with patch.object(tools, "_make_request") as mock:
            mock.side_effect = [
                json.dumps({"stdout": "started", "exit_code": 0}),
                json.dumps({"focused": "notepad"}),
            ]
            r = json.loads(tools._open_app_handler({"executable": "notepad.exe", "wait_focus": True}))
            assert r["exec"]["stdout"] == "started"
            assert r["focus"]["focused"] == "notepad"

    def test_open_app_missing_exe(self):
        r = json.loads(tools._open_app_handler({"executable": ""}))
        assert r["error"] == "missing executable"

    def test_acp_direct_success(self):
        with _mock_request('{"task_id":"t_ok123","status":"completed","mode":"sync","result":{"text":"OK"}}') as mock:
            result = json.loads(tools._acp_handler({"prompt": "test"}))
            assert result["task_id"] == "t_ok123"
            assert result["status"] == "completed"
            assert mock.call_args[0][1] == "/acp/tasks"

    def test_acp_async_timeout_returns_task_id(self):
        with _mock_request('{"task_id":"t_slow123","status":"running","mode":"async"}') as mock:
            result = json.loads(tools._acp_handler({"prompt": "heavy task", "timeout": 300}))
            assert result["task_id"] == "t_slow123"
            assert result["status"] == "running"

    def test_acp_poll(self):
        with _mock_request('{"task_id":"t_abc123","status":"completed","result":"OK"}') as mock:
            result = json.loads(tools._acp_poll_handler({"task_id": "t_abc123"}))
            assert result["status"] == "completed"
            assert mock.call_args[0][1] == "/acp/tasks/t_abc123"

    def test_agent_passed_to_make_request(self):
        with _mock_request('{"status":"ok"}') as mock:
            tools._health_handler({"agent": "laptop"})
            assert mock.call_args[1]["agent"] == "laptop"

    def test_no_agent_defaults_to_none(self):
        with _mock_request('{"status":"ok"}') as mock:
            tools._health_handler({})
            assert mock.call_args[1]["agent"] is None


class TestMakeRequest:
    """Tests for _make_request HTTP behavior."""

    def test_connection_error(self):
        with patch.object(tools, "_load_config", return_value=({"agents": {"a": {"url": "http://x", "token": "t", "timeout": 10}}}, "config.yaml")):
            with patch("requests.request", side_effect=__import__("requests").exceptions.ConnectionError):
                r = json.loads(tools._make_request("GET", "/health"))
                assert r["error"] == "agent_unreachable"

    def test_timeout(self):
        with patch.object(tools, "_load_config", return_value=({"agents": {"a": {"url": "http://x", "token": "t", "timeout": 10}}}, "config.yaml")):
            with patch("requests.request", side_effect=__import__("requests").exceptions.Timeout):
                r = json.loads(tools._make_request("GET", "/health", timeout=5))
                assert r["error"] == "agent_timeout"

    def test_http_error_includes_body(self):
        resp = MagicMock()
        resp.status_code = 422
        resp.text = '{"detail":"bad request"}'
        resp.raise_for_status.side_effect = __import__("requests").exceptions.HTTPError(response=resp)
        with patch.object(tools, "_load_config", return_value=({"agents": {"a": {"url": "http://x", "token": "t", "timeout": 10}}}, "config.yaml")):
            with patch("requests.request", return_value=resp):
                r = json.loads(tools._make_request("POST", "/keyboard/type", json_data={"text": "x"}))
                assert r["error"] == "http_422"
                assert "body" in r
