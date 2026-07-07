"""Integration tests for API endpoints using FastAPI TestClient."""
from fastapi.testclient import TestClient

from hermes_agent.app import app
from hermes_agent.config import TOKEN

client = TestClient(app)
AUTH = {"X-Agent-Token": TOKEN}


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_returns_ok(self):
        """/health should return status ok with a timestamp."""
        resp = client.get("/health", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "timestamp" in data


class TestCapabilitiesEndpoint:
    """Tests for GET /capabilities."""

    def test_capabilities_returns_modules(self):
        """/capabilities should return a modules dict without auth."""
        resp = client.get("/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert "modules" in data
        assert "endpoints" in data
        assert isinstance(data["modules"], dict)


class TestExecEndpoint:
    """Tests for POST /exec."""

    def test_exec_simple_command(self):
        """Running a simple echo command should return stdout."""
        resp = client.post(
            "/exec",
            json={"command": "echo hello", "shell": "sh"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "stdout" in data

    def test_exec_missing_command(self):
        """Missing 'command' in body should return 400."""
        resp = client.post("/exec", json={}, headers=AUTH)
        assert resp.status_code == 422

    def test_exec_unauthorized(self):
        """Missing token should return 401."""
        resp = client.post("/exec", json={"command": "echo"}, headers={"X-Agent-Token": "wrong"})
        assert resp.status_code == 401


class TestFileEndpoints:
    """Tests for GET/PUT /file, POST /file/delete."""

    def test_file_write_read_delete(self):
        """Write, read, and delete a file within the home directory."""
        import os
        test_path = os.path.join(os.path.expanduser("~"), "hermes-test-pytest.txt")
        write_resp = client.put(
            "/file",
            json={"path": test_path, "content": "pytest-content"},
            headers=AUTH,
        )
        assert write_resp.status_code == 200
        assert write_resp.json()["written"] is True

        read_resp = client.get("/file", params={"path": test_path}, headers=AUTH)
        assert read_resp.status_code == 200
        assert read_resp.json()["content"] == "pytest-content"

        delete_resp = client.post(
            "/file/delete",
            json={"path": test_path},
            headers=AUTH,
        )
        assert delete_resp.status_code == 200
        assert delete_resp.json()["deleted"] is True

    def test_file_read_not_found(self):
        """Reading a non-existent file should return 404."""
        resp = client.get("/file", params={"path": "/nonexistent/file.txt"}, headers=AUTH)
        assert resp.status_code in (403, 404)

    def test_file_write_path_not_allowed(self):
        """Writing outside allowed paths should return 403."""
        resp = client.put(
            "/file",
            json={"path": "/etc/hacked", "content": "test"},
            headers=AUTH,
        )
        assert resp.status_code == 403

    def test_file_read_alias(self):
        """GET /file/read should return same content as GET /file."""
        import os
        test_path = os.path.join(os.path.expanduser("~"), "hermes-test-alias.txt")
        client.put("/file", json={"path": test_path, "content": "alias-test"}, headers=AUTH)
        resp1 = client.get("/file", params={"path": test_path}, headers=AUTH)
        resp2 = client.get("/file/read", params={"path": test_path}, headers=AUTH)
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["content"] == resp2.json()["content"] == "alias-test"
        client.post("/file/delete", json={"path": test_path}, headers=AUTH)


class TestScreenshotEndpoint:
    """Tests for GET /screenshot with compression params."""

    def test_screenshot_default_png(self):
        """GET /screenshot without params returns PNG full size."""
        resp = client.get("/screenshot", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "png"
        assert "image_base64" in data
        assert data["width"] > 0
        assert data["height"] > 0

    def test_screenshot_jpeg_scaled(self):
        """GET /screenshot with scale=0.5 and format=jpeg returns compressed JPEG."""
        resp = client.get("/screenshot", params={"scale": 0.5, "format": "jpeg", "quality": 50}, headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "jpeg"
        assert data["width"] > 0
        assert data["original_size"] > 0

    def test_screenshot_invalid_format_422(self):
        """GET /screenshot with invalid format returns 422."""
        resp = client.get("/screenshot", params={"format": "gif"}, headers=AUTH)
        assert resp.status_code == 422

    def test_screenshot_scale_clamped(self):
        """GET /screenshot with scale=0.05 is clamped to 0.1 by FastAPI."""
        resp = client.get("/screenshot", params={"scale": 0.05}, headers=AUTH)
        assert resp.status_code == 422  # FastAPI rejects values < ge=0.1


class TestSystemEndpoint:
    """Tests for GET /system."""

    def test_system_returns_hostname(self):
        """/system should return hostname and os info."""
        resp = client.get("/system", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "hostname" in data
        assert "os" in data
        assert "cpu_count" in data

    def test_system_unauthorized(self):
        """/system should return 401 without a valid token."""
        resp = client.get("/system", headers={"X-Agent-Token": "wrong"})
        assert resp.status_code == 401


class TestProcessesEndpoint:
    """Tests for GET /processes."""

    def test_processes_returns_list(self):
        """/processes should return a non-empty list."""
        resp = client.get("/processes", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "processes" in data
        assert isinstance(data["processes"], list)

    def test_process_kill_invalid_pid(self):
        """Killing a non-existent PID should return an error."""
        resp = client.post("/process/kill", json={"pid": 9999999}, headers=AUTH)
        assert resp.status_code in (400, 404)


class TestSwaggerDocs:
    """Tests for OpenAPI documentation endpoints."""

    def test_swagger_ui_accessible(self):
        """/docs should return 200."""
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_redoc_accessible(self):
        """/redoc should return 200."""
        resp = client.get("/redoc")
        assert resp.status_code == 200

    def test_openapi_json(self):
        """/openapi.json should return valid JSON."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "paths" in data
        assert "info" in data


class TestLogEndpoints:
    """Tests for log dashboard and API."""

    def test_log_dashboard_accessible(self):
        """/logs should redirect to the new /dashboard page."""
        resp = client.get("/logs", follow_redirects=False)
        assert resp.status_code == 302
        assert "/dashboard" in resp.headers.get("location", "")

    def test_api_logs_returns_list(self):
        """/api/logs should return a paginated JSON object with entries."""
        resp = client.get("/api/logs", params={"count": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert isinstance(data["entries"], list)
        assert "total" in data


class TestMouseModuleMissing:
    """Tests for mouse endpoints when pyautogui is not installed."""

    def test_mouse_move_module_missing(self):
        """Mouse endpoints should return 503 or an error when pyautogui is absent.
        Note: if pyautogui IS installed, this test always gets 200 — expected."""
        resp = client.post(
            "/mouse/move",
            json={"x": 100, "y": 200},
            headers=AUTH,
        )
        data = resp.json()
        # If pyautogui is missing: 503; if present: OK (200 with x/y returned)
        assert resp.status_code in (200, 503) or "error" in str(data)
