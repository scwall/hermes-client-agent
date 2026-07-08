"""Unit tests for the audit package — AuditLog model class methods and AuditLogger."""
import json
import tempfile
from pathlib import Path

import pytest

from hermes_agent.audit.logger import AuditLogger
from hermes_agent.audit.models import AuditLog


class TestAuditLogModel:
    """Tests for AuditLog class methods (fetch_logs, fetch_stats, etc.)."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = str(Path(self.tmpdir) / "test_audit.db")
        AuditLog.init_db(self.db_path)

    def teardown_method(self):
        AuditLog.close_db()
        try:
            Path(self.db_path).unlink(missing_ok=True)
        except PermissionError:
            pass
        try:
            Path(self.tmpdir).rmdir()
        except OSError:
            pass

    def _log(self, endpoint="/x", method="GET", source_ip="1", status_code=200, duration_ms=10, **kw):
        return AuditLog.create_entry(endpoint=endpoint, method=method, source_ip=source_ip,
                                     response_status=status_code, duration_ms=duration_ms, **kw)

    def test_create_entry(self):
        eid = self._log()
        assert eid is not None

    def test_fetch_logs_empty(self):
        assert AuditLog.fetch_logs()["total"] == 0

    def test_fetch_logs_pagination(self):
        for i in range(5):
            self._log()
        r = AuditLog.fetch_logs(limit=3)
        assert r["total"] == 5
        assert len(r["entries"]) == 3

    def test_fetch_logs_endpoint_filter(self):
        self._log(endpoint="/exec")
        self._log(endpoint="/file")
        self._log(endpoint="/exec")
        assert AuditLog.fetch_logs(endpoint_filter="/exec")["total"] == 2

    def test_fetch_logs_status_success(self):
        self._log(status_code=200)
        self._log(status_code=401)
        assert AuditLog.fetch_logs(status_filter="success")["total"] == 1

    def test_fetch_logs_status_error(self):
        self._log(status_code=200)
        self._log(status_code=401)
        self._log(status_code=500)
        assert AuditLog.fetch_logs(status_filter="error")["total"] == 2

    def test_fetch_logs_search(self):
        self._log(command_executed="hostname")
        self._log(command_executed="dir")
        assert AuditLog.fetch_logs(search="hostname")["total"] == 1

    def test_fetch_logs_ip_filter(self):
        self._log(source_ip="192.168.1.10")
        self._log(source_ip="192.168.1.20")
        self._log(source_ip="10.0.0.1")
        assert AuditLog.fetch_logs(ip_filter="192.168")["total"] == 2
        assert AuditLog.fetch_logs(ip_filter="99.99.99.99")["total"] == 0

    def test_fetch_stats(self):
        for i in range(5):
            self._log(status_code=200)
        for i in range(2):
            self._log(status_code=500)
        stats = AuditLog.fetch_stats()
        assert stats["total"] == 7
        assert stats["success"] == 5

    def test_fetch_stats_empty(self):
        stats = AuditLog.fetch_stats()
        assert stats["total"] == 0

    def test_fetch_recent_errors(self):
        self._log(status_code=200)
        self._log(status_code=401)
        self._log(status_code=500)
        assert len(AuditLog.fetch_recent_errors()) == 2

    def test_truncate(self):
        for i in range(5):
            self._log()
        assert AuditLog.truncate() == 5
        assert AuditLog.fetch_stats()["total"] == 0

    def test_purge_older_than(self):
        self._log()
        r = AuditLog.purge_older_than(max_age_hours=0)
        assert r["action"] == "rotated"

    def test_export_csv(self):
        self._log(command_executed="hostname")
        out = AuditLog.export(fmt="csv")
        assert "timestamp" in out
        assert "hostname" in out

    def test_export_json(self):
        self._log()
        data = json.loads(AuditLog.export(fmt="json"))
        assert isinstance(data, list)
        assert len(data) == 1


class TestAuditLoggerOrchestrator:
    """Tests for the AuditLogger orchestrator (init, log_request, cleanup)."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self.tmpdir) / "test_audit.db"
        self.logger = AuditLogger(db_path=str(self.db_path), auto_cleanup=False)

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

    def test_log_request_returns_id(self):
        eid = self.logger.log_request(endpoint="/t", method="GET", source_ip="1", response_status=200, duration_ms=10)
        assert eid is not None

    def test_log_request_stores_body(self):
        self.logger.log_request(endpoint="/exec", method="POST", source_ip="1",
                                response_status=200, duration_ms=10,
                                request_body={"command": "hostname"}, command_executed="hostname")
        r = AuditLog.fetch_logs(limit=1)
        assert r["entries"][0]["command_executed"] == "hostname"

    def test_cleanup_triggered(self):
        logger = AuditLogger(db_path=str(self.db_path), auto_cleanup=True, max_rows=5, max_age_days=90)
        for i in range(10):
            logger.log_request(endpoint="/t", method="GET", source_ip="1", response_status=200, duration_ms=10)
        total = AuditLog.fetch_logs()["total"]
        assert total <= 10  # cleanup should have reduced count
        logger.close()
