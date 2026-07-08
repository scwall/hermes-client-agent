"""Lightweight AuditLogger orchestrator — delegates to AuditLog model."""
import logging
import os
from pathlib import Path

from hermes_agent.audit.models import AuditLog

LOG_DIR = Path("logs")


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    return os.environ.get(key, str(default).lower()).lower() in ("true", "1", "yes")


class AuditLogger:
    """Orchestrates audit logging: DB init, entry creation with cleanup, console output."""

    def __init__(self, db_path=None, max_rows=None, max_age_days=None, auto_cleanup=None):
        self._db_path = Path(db_path if db_path else (LOG_DIR / "audit.db")).resolve()
        self.max_rows = max_rows if max_rows is not None else _env_int("HERMES_AUDIT_MAX_ROWS", 100000)
        self.max_age_days = max_age_days if max_age_days is not None else _env_int("HERMES_AUDIT_MAX_AGE_DAYS", 90)
        self.auto_cleanup = auto_cleanup if auto_cleanup is not None else _env_bool("HERMES_AUDIT_AUTO_CLEANUP", True)
        AuditLog.init_db(str(self._db_path))

    def close(self):
        AuditLog.close_db()

    def log_request(self, endpoint, method, source_ip, response_status, duration_ms,
                    request_body=None, response_summary="", error=None, command_executed=None):
        """Create an audit entry, optionally cleanup, and log to console."""
        entry_id = AuditLog.create_entry(
            endpoint=endpoint, method=method, source_ip=source_ip,
            response_status=response_status, duration_ms=duration_ms,
            request_body=request_body, response_summary=response_summary,
            error=error, command_executed=command_executed,
        )
        if self.auto_cleanup:
            deleted = AuditLog.clear_old_entries(max_rows=self.max_rows, max_age_days=self.max_age_days)
            if deleted:
                logging.getLogger("hermes-agent").info("Audit cleanup: deleted %s rows", deleted)
        return entry_id


_audit_logger = None


def get_audit_logger():
    """Return the singleton AuditLogger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
