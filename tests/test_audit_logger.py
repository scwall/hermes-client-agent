"""Unit tests for the Peewee ORM AuditLogger and AuditMiddleware."""
import json
import tempfile
from pathlib import Path

import pytest

from hermes_agent.audit_logger import AuditLogger, AuditLog


class TestAuditLogger:
    """Tests for the Peewee AuditLogger class."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self.tmpdir) / "test_audit.db"
        self.logger = AuditLogger(db_path=self.db_path, auto_cleanup=False)

    def teardown_method(self):
        self.logger.close()
        try:
            self.db_path.unlink(missing_ok=True)
        except PermissionError:
            pass
        try:
            Path(self.tmpdir).rmdir()
        except OSError:
            pass

    def test_log_request_inserts_row(self):
        eid = self.logger.log_request(
            endpoint="/exec", method="POST", source_ip="192.168.1.2",
            response_status=200, duration_ms=145.0,
            request_body={"command": "hostname"}, command_executed="hostname",
        )
        assert eid is not None
        log = AuditLog.get_by_id(eid)
        assert log is not None
        assert log.endpoint == "/exec"
        assert log.status_code == 200

    def test_log_request_error_status(self):
        eid = self.logger.log_request(
            endpoint="/exec", method="POST", source_ip="1",
            response_status=401, duration_ms=5.0, error="unauthorized",
        )
        log = AuditLog.get_by_id(eid)
        assert log.status_code == 401
        assert log.error == "unauthorized"

    def test_get_logs_empty(self):
        result = self.logger.get_logs()
        assert result["total"] == 0
        assert result["entries"] == []

    def test_get_logs_returns_entries(self):
        for i in range(5):
            self.logger.log_request(endpoint="/test", method="GET", source_ip="127.0.0.1",
                                    response_status=200, duration_ms=10.0)
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
        self.logger.log_request(endpoint="/exec", method="POST", source_ip="1", response_status=200,
                                duration_ms=10, command_executed="hostname")
        self.logger.log_request(endpoint="/exec", method="POST", source_ip="1", response_status=200,
                                duration_ms=10, command_executed="dir")
        result = self.logger.get_logs(search="hostname")
        assert result["total"] == 1

    def test_get_logs_ip_filter(self):
        self.logger.log_request(endpoint="/a", method="GET", source_ip="192.168.1.10", response_status=200, duration_ms=10)
        self.logger.log_request(endpoint="/b", method="GET", source_ip="192.168.1.20", response_status=200, duration_ms=10)
        self.logger.log_request(endpoint="/c", method="GET", source_ip="10.0.0.1", response_status=200, duration_ms=10)
        assert self.logger.get_logs(ip_filter="192.168")["total"] == 2
        assert self.logger.get_logs(ip_filter="99.99.99.99")["total"] == 0

    def test_get_logs_pagination(self):
        for i in range(10):
            self.logger.log_request(endpoint="/test", method="GET", source_ip="1", response_status=200, duration_ms=10)
        result = self.logger.get_logs(limit=3, offset=3)
        assert result["total"] == 10
        assert len(result["entries"]) == 3

    def test_get_stats_aggregates_correctly(self):
        for i in range(5):
            self.logger.log_request(endpoint="/test", method="GET", source_ip="1", response_status=200, duration_ms=100)
        for i in range(2):
            self.logger.log_request(endpoint="/test", method="GET", source_ip="1", response_status=500, duration_ms=200)
        stats = self.logger.get_stats()
        assert stats["total"] == 7
        assert stats["success"] == 5
        assert stats["errors"] == 2

    def test_get_stats_empty(self):
        stats = self.logger.get_stats()
        assert stats["total"] == 0
        assert stats["retention"]["current_rows"] == 0

    def test_get_recent_errors(self):
        self.logger.log_request(endpoint="/a", method="GET", source_ip="1", response_status=200, duration_ms=10)
        self.logger.log_request(endpoint="/b", method="GET", source_ip="1", response_status=401, duration_ms=10)
        self.logger.log_request(endpoint="/c", method="GET", source_ip="1", response_status=500, duration_ms=10)
        errors = self.logger.get_recent_errors(limit=10)
        assert len(errors) == 2

    def test_clear_all(self):
        for i in range(5):
            self.logger.log_request(endpoint="/t", method="GET", source_ip="1", response_status=200, duration_ms=10)
        assert self.logger.clear_all() == 5
        assert self.logger.get_stats()["total"] == 0

    def test_clear_old_logs(self):
        self.logger.log_request(endpoint="/t", method="GET", source_ip="1", response_status=200, duration_ms=10)
        result = self.logger.clear_old_logs(max_age_hours=0)
        assert result["action"] == "rotated"
        assert result["removed"] > 0

    def test_export_csv(self):
        self.logger.log_request(endpoint="/a", method="GET", source_ip="1", response_status=200, duration_ms=10,
                                command_executed="hostname")
        csv_out = self.logger.export_logs(fmt="csv", limit=10)
        assert "timestamp" in csv_out
        assert "hostname" in csv_out

    def test_export_json(self):
        self.logger.log_request(endpoint="/a", method="GET", source_ip="1", response_status=200, duration_ms=10)
        json_out = self.logger.export_logs(fmt="json", limit=10)
        data = json.loads(json_out)
        assert isinstance(data, list)
        assert len(data) == 1
