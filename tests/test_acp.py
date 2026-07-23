"""Tests for the /acp ACP bridge endpoint."""

from unittest import mock

from fastapi.testclient import TestClient

from hermes_agent.app import app
from hermes_agent.config import TOKEN

client = TestClient(app)
AUTH = {"X-Agent-Token": TOKEN}


class TestAcpEndpoint:
    """Tests for POST /acp."""

    def test_acp_requires_token(self):
        resp = client.post("/acp", json={"agent_url": "http://localhost:4096", "prompt": "hello"})
        assert resp.status_code == 401 if resp.status_code != 422 else True

    def test_acp_requires_agent_url(self):
        resp = client.post("/acp", json={"prompt": "hello"}, headers=AUTH)
        assert resp.status_code == 422

    def test_acp_requires_prompt(self):
        resp = client.post("/acp", json={"agent_url": "http://localhost:4096"}, headers=AUTH)
        assert resp.status_code == 422

    def test_acp_missing_both(self):
        resp = client.post("/acp", json={}, headers=AUTH)
        assert resp.status_code == 422

    def test_acp_unreachable_agent_returns_503(self):
        with mock.patch("hermes_agent.routers.acp.httpx.AsyncClient") as mock_client:
            instance = mock_client.return_value.__aenter__.return_value
            instance.post.side_effect = __import__("httpx").ConnectError("connection refused")
            resp = client.post(
                "/acp",
                json={"agent_url": "http://localhost:19999", "prompt": "test", "timeout": 3},
                headers=AUTH,
            )
        assert resp.status_code == 503

    def test_acp_timeout_returns_504(self):
        with mock.patch("hermes_agent.routers.acp.httpx.AsyncClient") as mock_client:
            instance = mock_client.return_value.__aenter__.return_value
            instance.post.side_effect = __import__("httpx").TimeoutException("timeout")
            resp = client.post(
                "/acp",
                json={"agent_url": "http://localhost:19999", "prompt": "test", "timeout": 3},
                headers=AUTH,
            )
        assert resp.status_code == 504

    def test_acp_success_response(self):
        session_resp = mock.MagicMock()
        session_resp.status_code = 200
        session_resp.json.return_value = {"id": "ses_test", "directory": "/home/test"}

        message_resp = mock.MagicMock()
        message_resp.status_code = 200
        message_resp.json.return_value = {"result": "bonjour"}

        with mock.patch("hermes_agent.routers.acp.httpx.AsyncClient") as mock_client:
            instance = mock_client.return_value.__aenter__.return_value
            instance.post.side_effect = [session_resp, message_resp]
            resp = client.post(
                "/acp",
                json={"agent_url": "http://localhost:4096", "prompt": "hello"},
                headers=AUTH,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["response"] == {"result": "bonjour"}
        assert data["agent_url"] == "http://localhost:4096"

    def test_acp_with_context_and_model(self):
        session_resp = mock.MagicMock()
        session_resp.status_code = 200
        session_resp.json.return_value = {"id": "ses_ctx", "directory": "/home/test"}

        message_resp = mock.MagicMock()
        message_resp.status_code = 200
        message_resp.json.return_value = {"text": "done"}

        with mock.patch("hermes_agent.routers.acp.httpx.AsyncClient") as mock_client:
            instance = mock_client.return_value.__aenter__.return_value
            instance.post.side_effect = [session_resp, message_resp]
            resp = client.post(
                "/acp",
                json={
                    "agent_url": "http://localhost:4096",
                    "prompt": "explain",
                    "context": "python project",
                    "model": "gpt-5",
                    "timeout": 60,
                },
                headers=AUTH,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        call_bodies = [c[1]["json"] for c in instance.post.call_args_list]
        assert call_bodies[-1]["model"] == {"providerID": "", "modelID": "gpt-5"}
        assert "Context: python project" in call_bodies[-1]["parts"][0]["text"]

    def test_acp_agent_error_status_returns_502(self):
        session_resp = mock.MagicMock()
        session_resp.status_code = 200
        session_resp.json.return_value = {"id": "ses_err", "directory": "/home/test"}

        message_resp = mock.MagicMock()
        message_resp.status_code = 500
        message_resp.text = "Internal Server Error"

        with mock.patch("hermes_agent.routers.acp.httpx.AsyncClient") as mock_client:
            instance = mock_client.return_value.__aenter__.return_value
            instance.post.side_effect = [session_resp, message_resp]
            resp = client.post(
                "/acp",
                json={"agent_url": "http://localhost:4096", "prompt": "hello"},
                headers=AUTH,
            )
        assert resp.status_code == 502

    def test_acp_non_json_response(self):
        session_resp = mock.MagicMock()
        session_resp.status_code = 200
        session_resp.json.return_value = {"id": "ses_raw", "directory": "/home/test"}

        message_resp = mock.MagicMock()
        message_resp.status_code = 200
        message_resp.json.side_effect = ValueError("not json")
        message_resp.text = "plain text response"

        with mock.patch("hermes_agent.routers.acp.httpx.AsyncClient") as mock_client:
            instance = mock_client.return_value.__aenter__.return_value
            instance.post.side_effect = [session_resp, message_resp]
            resp = client.post(
                "/acp",
                json={"agent_url": "http://localhost:4096", "prompt": "hello"},
                headers=AUTH,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["response"] == {"raw": "plain text response"}
