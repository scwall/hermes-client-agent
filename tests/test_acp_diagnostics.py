"""Tests for ACP diagnostics endpoint and dashboard."""
import json
import os
import tempfile
from unittest import mock

from fastapi.testclient import TestClient

from hermes_agent.acp.diagnostics import (
    find_config_file,
    functional_test,
    inspect_binary,
    inspect_config,
    parse_jsonc,
    run_diagnostics,
)
from hermes_agent.app import app
from hermes_agent.config import TOKEN

client = TestClient(app)
AUTH = {"X-Agent-Token": TOKEN}


class TestParseJsonc:
    def test_parse_simple_json(self):
        assert parse_jsonc('{"a": 1}') == {"a": 1}

    def test_parse_line_comments(self):
        data = """{
            // this is a comment
            "key": "value" // trailing comment
        }"""
        assert parse_jsonc(data) == {"key": "value"}

    def test_parse_block_comments(self):
        data = """{
            /* block comment */
            "key": "value" /* inline */,
        }"""
        assert parse_jsonc(data) == {"key": "value"}

    def test_parse_trailing_comma(self):
        data = '{"items": [1, 2, 3,]}'
        assert parse_jsonc(data) == {"items": [1, 2, 3]}

    def test_parse_trailing_comma_in_object(self):
        data = '{"a": 1, "b": 2,}'
        assert parse_jsonc(data) == {"a": 1, "b": 2}

    def test_parse_invalid_json_raises(self):
        import pytest
        with pytest.raises(json.JSONDecodeError):
            parse_jsonc("{invalid}")

    def test_parse_double_slash_in_string(self):
        data = '{"url": "https://api.example.com/v1//path"}'
        assert parse_jsonc(data) == {"url": "https://api.example.com/v1//path"}

    def test_parse_block_comment_open_in_string(self):
        data = '{"code": "/* this is not a comment */ in a string"}'
        assert parse_jsonc(data) == {"code": "/* this is not a comment */ in a string"}

    def test_parse_escaped_quote_in_string(self):
        data = '{"msg": "he said \\"hello\\" // not a comment"}'
        assert parse_jsonc(data) == {"msg": 'he said "hello" // not a comment'}

    def test_parse_empty_returns_empty_dict(self):
        assert parse_jsonc("") == {}
        assert parse_jsonc("   ") == {}
        assert parse_jsonc("// only comments\n/* and blocks */") == {}


class TestFindConfigFile:
    def test_missing_config_returns_none(self):
        assert find_config_file("opencode_missing_xyz") is None


class TestInspectBinary:
    def test_opencode_installed(self):
        result = inspect_binary("opencode")
        assert result["installed"] is True
        assert result["path"] is not None

    def test_unknown_binary_not_installed(self):
        result = inspect_binary("no_such_agent_xyz")
        assert result["installed"] is False
        assert result["path"] is None


class TestInspectConfig:
    def test_config_not_found(self):
        result = inspect_config("opencode_missing_xyz")
        assert result["config_file"] is None

    def test_valid_config_parsed(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonc", delete=False) as f:
            f.write("""{
                "model": {"gpt-5": {"provider": "openai"}},
                "default_model": "gpt-5"
            }""")
            f.flush()
            from pathlib import Path
            with mock.patch("hermes_agent.acp.diagnostics.find_config_file", return_value=Path(f.name)):
                result = inspect_config("opencode")
            os.unlink(f.name)
        assert result["config_file"] == f.name
        assert result["default_model"] == "gpt-5"

    def test_invalid_config_returns_error(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonc", delete=False) as f:
            f.write("{invalid json content!!!")
            f.flush()
            from pathlib import Path
            with mock.patch("hermes_agent.acp.diagnostics.find_config_file", return_value=Path(f.name)):
                result = inspect_config("opencode")
            os.unlink(f.name)
        assert result.get("error") is not None
        assert "not valid JSON" in result.get("error", "")


class TestFunctionalTest:
    def test_ok_response(self):
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": "OK"}
        with mock.patch("hermes_agent.acp.diagnostics.httpx.post", return_value=mock_resp):
            result = functional_test("http://localhost:4096")
        assert result["status"] == "ok"

    def test_connect_error(self):
        with mock.patch("hermes_agent.acp.diagnostics.httpx.post", side_effect=__import__("httpx").ConnectError("refused")):
            result = functional_test("http://localhost:4096")
        assert result["status"] == "failed"
        assert "connect" in result["detail"].lower()

    def test_timeout(self):
        with mock.patch("hermes_agent.acp.diagnostics.httpx.post", side_effect=__import__("httpx").TimeoutException("timeout")):
            result = functional_test("http://localhost:4096")
        assert result["status"] == "failed"
        assert "timed out" in result["detail"].lower()

    def test_no_ok_in_response(self):
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "something else entirely"}
        with mock.patch("hermes_agent.acp.diagnostics.httpx.post", return_value=mock_resp):
            result = functional_test("http://localhost:4096")
        assert result["status"] == "failed"


class TestRunDiagnostics:
    def test_returns_structure(self):
        result = run_diagnostics("opencode")
        assert "agent_type" in result
        assert "binary" in result
        assert "config" in result
        assert "functional_test" in result
        assert "sessions" in result
        assert "issues" in result
        assert "healthy" in result
        assert "checked_at" in result

    def test_unknown_agent_type(self):
        result = run_diagnostics("unknown_agent")
        assert result["binary"]["installed"] is False
        assert result["config"]["config_file"] is None


class TestAcpDiagnosticsEndpoint:
    def test_requires_auth(self):
        resp = client.get("/acp/diagnostics")
        assert resp.status_code in (401, 422)

    def test_returns_json_with_auth(self):
        resp = client.get("/acp/diagnostics", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "agent_type" in data
        assert "binary" in data
        assert "functional_test" in data
        assert "issues" in data

    def test_agent_type_param(self):
        resp = client.get("/acp/diagnostics?agent_type=opencode", headers=AUTH)
        assert resp.status_code == 200


class TestDashboardAcpPage:
    def test_acp_page_returns_html(self):
        resp = client.get("/dashboard/acp")
        assert resp.status_code == 200
        html = resp.text
        assert "ACP" in html
        assert "Agent Binary" in html or "Version" in html

    def test_acp_page_no_crash_no_sessions(self):
        resp = client.get("/dashboard/acp")
        assert resp.status_code == 200
        assert "No active sessions" in resp.text or "Active Sessions" in resp.text
