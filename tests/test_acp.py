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

    def test_submit_with_model(self):
        from hermes_agent.acp.runtime_broker import get_runtime_broker
        from hermes_agent.acp.task_service import get_task_service

        broker = get_runtime_broker()
        adapter = broker.get_adapter()

        with mock.patch.object(adapter, "detect_binary", return_value="/fake/opencode"):
            with mock.patch.object(adapter, "spawn", return_value=99999):
                with mock.patch.object(adapter, "health_check", return_value=True):
                    with mock.patch.object(adapter, "wait_ready", return_value=True):
                        with mock.patch.object(adapter, "get_version", return_value="1.0.0"):
                            with mock.patch.object(adapter, "create_session", return_value={"id": "ses_test", "directory": "/"}):
                                with mock.patch.object(adapter, "send_message", return_value={"result": "hello"}):
                                    resp = client.post(
                                        "/acp/tasks",
                                        json={"prompt": "hello", "model": "deepseek-chat", "timeout": 30},
                                        headers=AUTH,
                                    )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert "task_id" in data

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
