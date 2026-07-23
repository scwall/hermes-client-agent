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
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "bonjour"}

        with mock.patch("hermes_agent.routers.acp.httpx.AsyncClient") as mock_client:
            instance = mock_client.return_value.__aenter__.return_value
            instance.post.return_value = mock_response
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
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "done"}

        with mock.patch("hermes_agent.routers.acp.httpx.AsyncClient") as mock_client:
            instance = mock_client.return_value.__aenter__.return_value
            instance.post.return_value = mock_response
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

    def test_acp_agent_error_status_returns_502(self):
        mock_response = mock.MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with mock.patch("hermes_agent.routers.acp.httpx.AsyncClient") as mock_client:
            instance = mock_client.return_value.__aenter__.return_value
            instance.post.return_value = mock_response
            resp = client.post(
                "/acp",
                json={"agent_url": "http://localhost:4096", "prompt": "hello"},
                headers=AUTH,
            )
        assert resp.status_code == 502

    def test_acp_non_json_response(self):
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("not json")
        mock_response.text = "plain text response"

        with mock.patch("hermes_agent.routers.acp.httpx.AsyncClient") as mock_client:
            instance = mock_client.return_value.__aenter__.return_value
            instance.post.return_value = mock_response
            resp = client.post(
                "/acp",
                json={"agent_url": "http://localhost:4096", "prompt": "hello"},
                headers=AUTH,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["response"] == {"raw": "plain text response"}
