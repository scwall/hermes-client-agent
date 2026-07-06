"""Unit tests for the dashboard router and pages."""
import csv
import io
import json

from fastapi.testclient import TestClient

from hermes_agent.app import app

client = TestClient(app)


class TestDashboardAPI:
    """Tests for dashboard API endpoints."""

    def test_api_stats_returns_dict(self):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "success" in data
        assert "errors" in data
        assert "avg_duration_ms" in data

    def test_api_logs_pagination(self):
        resp = client.get("/api/logs", params={"count": 5, "offset": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "total" in data
        assert isinstance(data["entries"], list)

    def test_api_logs_filter_by_status(self):
        resp = client.get("/api/logs", params={"status": "error"})
        assert resp.status_code == 200
        data = resp.json()
        for e in data["entries"]:
            assert e["response_status"] >= 400

    def test_api_logs_filter_by_endpoint(self):
        resp = client.get("/api/logs", params={"endpoint": "/exec"})
        assert resp.status_code == 200
        data = resp.json()
        for e in data["entries"]:
            assert e["endpoint"] == "/exec"

    def test_api_logs_search(self):
        resp = client.get("/api/logs", params={"search": "zzzzz_nonexistent_zzzzz"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_api_clear_logs(self):
        resp = client.post("/api/clear-logs")
        assert resp.status_code == 200
        data = resp.json()
        assert "action" in data

    def test_api_logs_export_csv(self):
        resp = client.get("/api/logs/export", params={"format": "csv", "count": 10})
        assert resp.status_code == 200
        content = resp.content.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(content))
        header = next(reader)
        assert "timestamp" in header
        assert "method" in header
        assert "endpoint" in header
        rows = list(reader)
        assert len(rows) <= 10

    def test_api_logs_export_json(self):
        resp = client.get("/api/logs/export", params={"format": "json", "count": 5})
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        data = json.loads(content)
        assert isinstance(data, list)
        assert len(data) <= 5


class TestDashboardPages:
    """Tests for dashboard HTML pages."""

    def test_dashboard_page_returns_html(self):
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Dashboard" in resp.text

    def test_dashboard_logs_page(self):
        resp = client.get("/dashboard/logs")
        assert resp.status_code == 200
        assert "Dashboard" in resp.text

    def test_dashboard_errors_page(self):
        resp = client.get("/dashboard/errors")
        assert resp.status_code == 200
        assert "Errors" in resp.text

    def test_dashboard_exec_page(self):
        resp = client.get("/dashboard/exec")
        assert resp.status_code == 200
        assert "Commands" in resp.text

    def test_dashboard_pages_render_without_js_error_markers(self):
        for path in ["/dashboard", "/dashboard/logs", "/dashboard/errors", "/dashboard/exec"]:
            resp = client.get(path)
            assert resp.status_code == 200
            assert "Jinja2" not in resp.text
            assert "Traceback" not in resp.text
            assert "SyntaxError" not in resp.text

    def test_logs_redirect(self):
        resp = client.get("/logs", follow_redirects=False)
        assert resp.status_code == 302
        assert "/dashboard" in resp.headers.get("location", "")

    def test_base_template_includes_css(self):
        resp = client.get("/dashboard")
        assert "status-ok" in resp.text
        assert "status-err" in resp.text
        assert "stat-card" in resp.text

    def test_base_template_includes_js(self):
        resp = client.get("/dashboard")
        assert "Dashboard.init" in resp.text
        assert "function fetchStats" in resp.text or "fetchStats" in resp.text
