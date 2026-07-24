"""Tests for POST /acp/tasks, GET /acp/tasks/{id}, DELETE /acp/tasks/{id}."""
from unittest import mock

from fastapi.testclient import TestClient

from hermes_agent.app import app
from hermes_agent.config import TOKEN

client = TestClient(app)
AUTH = {"X-Agent-Token": TOKEN}


class TestAcpTasksEndpoint:
    def test_submit_requires_token(self):
        resp = client.post("/acp/tasks", json={"prompt": "hello"})
        assert resp.status_code in (401, 422)

    def test_submit_requires_prompt(self):
        resp = client.post("/acp/tasks", json={}, headers=AUTH)
        assert resp.status_code == 422

    def test_submit_returns_immediately(self):
        with mock.patch("hermes_agent.routers.acp.get_task_service") as mock_svc:
            instance = mock_svc.return_value
            instance.submit_and_return_task_id.return_value = "t_abc123def456"
            resp = client.post(
                "/acp/tasks",
                json={"prompt": "hello", "timeout": 60},
                headers=AUTH,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "t_abc123def456"
        assert data["status"] == "running"

    def test_submit_with_model(self):
        with mock.patch("hermes_agent.routers.acp.get_task_service") as mock_svc:
            instance = mock_svc.return_value
            instance.submit_and_return_task_id.return_value = "t_model12345678"
            resp = client.post(
                "/acp/tasks",
                json={"prompt": "hello", "model": "deepseek-chat", "timeout": 30},
                headers=AUTH,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "t_model12345678"
        assert data["status"] == "running"

    def test_task_not_found(self):
        resp = client.get("/acp/tasks/t_nonexistent", headers=AUTH)
        assert resp.status_code == 404

    def test_task_cancel_not_found(self):
        resp = client.delete("/acp/tasks/t_nonexistent", headers=AUTH)
        assert resp.status_code == 404

    def test_acp_status(self):
        resp = client.get("/acp/status", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "runtimes_count" in data
        assert "tasks_running" in data
