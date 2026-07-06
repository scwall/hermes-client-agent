"""Unit tests for the AuditLogger and AuditMiddleware."""
import json
import os
import tempfile
from pathlib import Path

import pytest

from hermes_agent.audit_logger import AuditLogger


class TestAuditLogger:
    """Tests for the AuditLogger class."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = Path(self.tmpdir) / "test_audit.jsonl"
        self.logger = AuditLogger(log_path=self.log_path)

    def teardown_method(self):
        if self.log_path.exists():
            self.log_path.unlink(missing_ok=True)
        Path(self.tmpdir).rmdir()

    def test_log_request_writes_json_line(self):
        entry_id = self.logger.log_request(
            endpoint="/exec",
            method="POST",
            source_ip="192.168.1.2",
            response_status=200,
            duration_ms=145.0,
            request_body={"command": "hostname"},
            command_executed="hostname",
        )
        assert entry_id is not None
        assert self.log_path.exists()
        lines = self.log_path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["endpoint"] == "/exec"
        assert data["method"] == "POST"
        assert data["source_ip"] == "192.168.1.2"
        assert data["response_status"] == 200
        assert data["duration_ms"] == 145.0
        assert data["command_executed"] == "hostname"

    def test_log_request_error_status(self):
        self.logger.log_request(
            endpoint="/exec",
            method="POST",
            source_ip="192.168.1.2",
            response_status=401,
            duration_ms=5.0,
            error="unauthorized",
        )
        lines = self.log_path.read_text().strip().split("\n")
        data = json.loads(lines[0])
        assert data["response_status"] == 401
        assert data["error"] == "unauthorized"

    def test_get_logs_empty(self):
        result = self.logger.get_logs()
        assert result["total"] == 0
        assert result["entries"] == []

    def test_get_logs_returns_entries(self):
        for i in range(5):
            self.logger.log_request(
                endpoint="/test",
                method="GET",
                source_ip="127.0.0.1",
                response_status=200,
                duration_ms=10.0,
            )
        result = self.logger.get_logs(limit=3)
        assert result["total"] == 5
        assert len(result["entries"]) == 3

    def test_get_logs_endpoint_filter(self):
        self.logger.log_request(endpoint="/exec", method="POST", source_ip="1", response_status=200, duration_ms=10)
        self.logger.log_request(endpoint="/file", method="GET", source_ip="1", response_status=200, duration_ms=10)
        self.logger.log_request(endpoint="/exec", method="POST", source_ip="1", response_status=401, duration_ms=10)
        result = self.logger.get_logs(endpoint_filter="/exec")
        assert result["total"] == 2

    def test_get_logs_status_filter_success(self):
        self.logger.log_request(endpoint="/a", method="GET", source_ip="1", response_status=200, duration_ms=10)
        self.logger.log_request(endpoint="/b", method="GET", source_ip="1", response_status=401, duration_ms=10)
        result = self.logger.get_logs(status_filter="success")
        assert result["total"] == 1

    def test_get_logs_status_filter_error(self):
        self.logger.log_request(endpoint="/a", method="GET", source_ip="1", response_status=200, duration_ms=10)
        self.logger.log_request(endpoint="/b", method="GET", source_ip="1", response_status=401, duration_ms=10)
        self.logger.log_request(endpoint="/c", method="GET", source_ip="1", response_status=500, duration_ms=10)
        result = self.logger.get_logs(status_filter="error")
        assert result["total"] == 2

    def test_get_logs_text_search(self):
        self.logger.log_request(endpoint="/exec", method="POST", source_ip="1", response_status=200, duration_ms=10, command_executed="hostname")
        self.logger.log_request(endpoint="/exec", method="POST", source_ip="1", response_status=200, duration_ms=10, command_executed="dir")
        result = self.logger.get_logs(search="hostname")
        assert result["total"] == 1

    def test_get_logs_pagination(self):
        for i in range(10):
            self.logger.log_request(endpoint="/test", method="GET", source_ip="1", response_status=200, duration_ms=10)
        result = self.logger.get_logs(limit=3, offset=3)
        assert result["total"] == 10
        assert len(result["entries"]) == 3
        assert result["offset"] == 3

    def test_get_stats_aggregates_correctly(self):
        for i in range(5):
            self.logger.log_request(endpoint="/test", method="GET", source_ip="1", response_status=200, duration_ms=100)
        for i in range(2):
            self.logger.log_request(endpoint="/test", method="GET", source_ip="1", response_status=500, duration_ms=200)
        stats = self.logger.get_stats()
        assert stats["total"] == 7
        assert stats["success"] == 5
        assert stats["errors"] == 2
        assert stats["avg_duration_ms"] == pytest.approx((5 * 100 + 2 * 200) / 7, rel=0.1)

    def test_get_stats_empty(self):
        stats = self.logger.get_stats()
        assert stats["total"] == 0
        assert stats["success"] == 0
        assert stats["errors"] == 0

    def test_get_recent_errors(self):
        self.logger.log_request(endpoint="/a", method="GET", source_ip="1", response_status=200, duration_ms=10)
        self.logger.log_request(endpoint="/b", method="GET", source_ip="1", response_status=401, duration_ms=10)
        self.logger.log_request(endpoint="/c", method="GET", source_ip="1", response_status=500, duration_ms=10)
        errors = self.logger.get_recent_errors(limit=10)
        assert len(errors) == 2

    def test_clear_old_logs_does_nothing_when_small(self):
        self.logger.log_request(endpoint="/test", method="GET", source_ip="1", response_status=200, duration_ms=10)
        result = self.logger.clear_old_logs(max_age_hours=168)
        assert result["action"] == "nothing"

    def test_log_concurrent_writes(self):
        import threading

        def write_logs(start_idx, count):
            for i in range(start_idx, start_idx + count):
                self.logger.log_request(
                    endpoint="/test",
                    method="GET",
                    source_ip=f"192.168.1.{i % 255}",
                    response_status=200,
                    duration_ms=float(i),
                )

        threads = []
        for t in range(4):
            th = threading.Thread(target=write_logs, args=(t * 25, 25))
            threads.append(th)
            th.start()
        for th in threads:
            th.join()

        result = self.logger.get_logs(limit=200)
        assert result["total"] == 100


class TestAuditMiddleware:
    """Integration tests for AuditMiddleware via FastAPI TestClient."""

    def test_middleware_logs_requests(self):
        from hermes_agent.app import app
        from fastapi.testclient import TestClient

        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200

        auditor = __import__("hermes_agent.audit_logger", fromlist=["get_audit_logger"]).get_audit_logger()
        result = auditor.get_logs(limit=10)
        assert result["total"] > 0

    def test_middleware_logs_401(self):
        from hermes_agent.app import app
        from fastapi.testclient import TestClient

        with TestClient(app) as client:
            resp = client.post("/exec", headers={"X-Agent-Token": "wrong"}, json={"command": "hostname"})
            assert resp.status_code == 401

        auditor = __import__("hermes_agent.audit_logger", fromlist=["get_audit_logger"]).get_audit_logger()
        result = auditor.get_logs(status_filter="error", limit=50)
        assert result["total"] > 0
