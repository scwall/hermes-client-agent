"""Structured SQLite audit logger and ASGI middleware for all HTTP requests."""
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

LOG_DIR = Path("logs")
DEFAULT_DB = LOG_DIR / "audit.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    method TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    source_ip TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    duration_ms REAL NOT NULL,
    request_body TEXT,
    response_summary TEXT,
    error TEXT,
    command_executed TEXT,
    state TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_endpoint ON audit_logs(endpoint);
CREATE INDEX IF NOT EXISTS idx_status_code ON audit_logs(status_code);
CREATE INDEX IF NOT EXISTS idx_source_ip ON audit_logs(source_ip);
"""


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    return os.environ.get(key, str(default).lower()).lower() in ("true", "1", "yes")


class AuditLogger:
    """Thread-safe SQLite audit log writer and reader.

    Stores structured request logs in ``./logs/audit.db`` with automatic
    retention cleanup based on max rows and max age.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        max_rows: Optional[int] = None,
        max_age_days: Optional[int] = None,
        auto_cleanup: Optional[bool] = None,
    ):
        self._db_path = db_path or DEFAULT_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_rows = max_rows if max_rows is not None else _env_int("HERMES_AUDIT_MAX_ROWS", 100000)
        self.max_age_days = max_age_days if max_age_days is not None else _env_int("HERMES_AUDIT_MAX_AGE_DAYS", 90)
        self.auto_cleanup = auto_cleanup if auto_cleanup is not None else _env_bool("HERMES_AUDIT_AUTO_CLEANUP", True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript(SCHEMA_SQL)

    def log_request(
        self,
        endpoint: str,
        method: str,
        source_ip: str,
        response_status: int,
        duration_ms: float,
        request_body: Optional[dict[str, Any]] = None,
        response_summary: str = "",
        error: Optional[str] = None,
        command_executed: Optional[str] = None,
    ) -> str:
        """Write a single audit entry to the SQLite database."""
        entry_id = str(uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        body_str = json.dumps(request_body, default=str) if request_body else None
        state = json.dumps({})

        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO audit_logs
                   (id, timestamp, method, endpoint, source_ip, status_code,
                    duration_ms, request_body, response_summary, error, command_executed, state)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry_id, ts, method, endpoint, source_ip, response_status,
                 round(duration_ms, 2), body_str, response_summary, error, command_executed, state),
            )

        if self.auto_cleanup:
            self._cleanup_old_logs()

        return entry_id

    def _cleanup_old_logs(self) -> int:
        """Remove logs exceeding retention limits. Returns count deleted."""
        deleted = 0
        with self._get_conn() as conn:
            row_count = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
            if row_count > self.max_rows:
                excess = row_count - self.max_rows + int(self.max_rows * 0.1)
                conn.execute(
                    "DELETE FROM audit_logs WHERE id IN ("
                    "SELECT id FROM audit_logs ORDER BY timestamp ASC LIMIT ?)",
                    (excess,),
                )
                deleted += conn.execute("SELECT CHANGES()").fetchone()[0]

            cutoff = (datetime.now(timezone.utc) - timedelta(days=self.max_age_days)).isoformat()
            conn.execute("DELETE FROM audit_logs WHERE timestamp < ?", (cutoff,))
            deleted += conn.execute("SELECT CHANGES()").fetchone()[0]

        if deleted:
            logging.getLogger("hermes-agent").info("Audit cleanup: deleted %s rows", deleted)
        return deleted

    def get_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        endpoint_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        ip_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> dict[str, Any]:
        """Return paginated, filtered log entries."""
        where = []
        params: list[Any] = []

        if endpoint_filter:
            where.append("endpoint = ?")
            params.append(endpoint_filter)
        if status_filter:
            if status_filter == "success":
                where.append("status_code >= 200 AND status_code < 400")
            elif status_filter == "error":
                where.append("(status_code >= 400 OR error IS NOT NULL)")
            else:
                try:
                    where.append("status_code = ?")
                    params.append(int(status_filter))
                except ValueError:
                    pass
        if ip_filter:
            where.append("source_ip LIKE ?")
            params.append(f"%{ip_filter}%")
        if search:
            where.append("(command_executed LIKE ? OR request_body LIKE ? OR error LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

        where_clause = ("WHERE " + " AND ".join(where)) if where else ""

        with self._get_conn() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM audit_logs {where_clause}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM audit_logs {where_clause} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()

        entries = []
        for row in rows:
            entry = dict(row)
            if entry.get("request_body"):
                try:
                    entry["request_body"] = json.loads(entry["request_body"])
                except (json.JSONDecodeError, TypeError):
                    pass
            entry["response_status"] = entry.pop("status_code", 0)
            entries.append(entry)

        return {"total": total, "limit": limit, "offset": offset, "entries": entries}

    def get_stats(self) -> dict[str, Any]:
        """Compute aggregate statistics from the audit database."""
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
            if total == 0:
                return {
                    "total": 0, "success": 0, "errors": 0, "avg_duration_ms": 0,
                    "top_endpoints": [], "top_ips": [], "slowest_commands": [],
                    "retention": {"max_rows": self.max_rows, "max_age_days": self.max_age_days, "current_rows": 0},
                }

            success = conn.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE status_code >= 200 AND status_code < 400"
            ).fetchone()[0]
            errors = total - success
            avg = conn.execute("SELECT AVG(duration_ms) FROM audit_logs").fetchone()[0] or 0
            top_eps = [dict(r) for r in conn.execute(
                "SELECT endpoint, COUNT(*) as count FROM audit_logs GROUP BY endpoint ORDER BY count DESC LIMIT 10"
            ).fetchall()]
            top_ips = [dict(r) for r in conn.execute(
                "SELECT source_ip, COUNT(*) as count FROM audit_logs WHERE source_ip != '?' GROUP BY source_ip ORDER BY count DESC LIMIT 5"
            ).fetchall()]
            slowest = [dict(r) for r in conn.execute(
                "SELECT endpoint, command_executed, duration_ms, timestamp FROM audit_logs ORDER BY duration_ms DESC LIMIT 5"
            ).fetchall()]
            slowest_cmds = [
                {"endpoint": s["endpoint"], "command": s["command_executed"],
                 "duration_ms": s["duration_ms"], "timestamp": s["timestamp"]}
                for s in slowest
            ]

        return {
            "total": total, "success": success, "errors": errors,
            "avg_duration_ms": round(avg, 2),
            "top_endpoints": [{"endpoint": e["endpoint"], "count": e["count"]} for e in top_eps],
            "top_ips": [{"ip": e["source_ip"], "count": e["count"]} for e in top_ips],
            "slowest_commands": slowest_cmds,
            "retention": {"max_rows": self.max_rows, "max_age_days": self.max_age_days, "current_rows": total},
        }

    def get_recent_errors(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent errors (status >= 400)."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_logs WHERE status_code >= 400 OR error IS NOT NULL "
                "ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def clear_all(self) -> int:
        """Delete all log entries. Returns count deleted."""
        with self._get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
            conn.execute("DELETE FROM audit_logs")
            return count

    def clear_old_logs(self, max_age_hours: int = 168) -> dict[str, Any]:
        """Remove entries older than *max_age_hours*. Returns action summary."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        with self._get_conn() as conn:
            before = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
            conn.execute("DELETE FROM audit_logs WHERE timestamp < ?", (cutoff,))
            after = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
            removed = before - after
        return {"action": "rotated", "removed": removed, "kept": after}

    def export_logs(self, fmt: str = "json", **filters: Any) -> str:
        """Export filtered logs as CSV or JSON string."""
        if "limit" not in filters:
            filters["limit"] = 100000
        result = self.get_logs(**filters)
        entries = result["entries"]

        if fmt == "csv":
            import csv
            import io
            buf = io.StringIO()
            if entries:
                writer = csv.DictWriter(buf, fieldnames=["timestamp", "method", "endpoint", "source_ip", "status_code", "duration_ms", "command_executed"])
                writer.writeheader()
                for e in entries:
                    writer.writerow({k: e.get(k, "") for k in writer.fieldnames})
            return buf.getvalue()
        return json.dumps(entries, indent=2, default=str)


_audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    """Return the singleton AuditLogger instance."""
    return _audit_logger


def _sanitize_body(body: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Return a copy of the body with sensitive fields masked."""
    if not body:
        return body
    sanitized = dict(body)
    for key in ("password", "token", "secret", "api_key", "apikey"):
        if key in sanitized:
            sanitized[key] = "***"
    return sanitized


class AuditMiddleware:
    """ASGI middleware that captures the request body before FastAPI consumes it."""

    _SKIP_ENDPOINTS = {"/api/stats", "/api/logs", "/api/logs/export", "/api/clear-logs"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")
        source_ip = scope.get("client", ("?", 0))[0]

        if path in self._SKIP_ENDPOINTS:
            await self.app(scope, receive, send)
            return

        start_ts = time.perf_counter()
        body_bytes = b""
        more_body = True
        while more_body:
            message = await receive()
            body_bytes += message.get("body", b"")
            more_body = message.get("more_body", False)

        body_sent = False

        async def _receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return await receive()

        status_code = 200

        async def _send(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        await self.app(scope, _receive, _send)
        duration_ms = (time.perf_counter() - start_ts) * 1000

        body_text = body_bytes.decode("utf-8", errors="replace") if body_bytes else ""
        request_body = _parse_body(body_text)

        _log_audit_console(method, path, source_ip, status_code, duration_ms, request_body)

        error = None
        response_summary = str(status_code)
        if status_code == 401:
            error = "unauthorized"; response_summary = "Unauthorized"
        elif status_code == 403:
            error = "forbidden"; response_summary = "Forbidden"
        elif status_code == 429:
            error = "rate_limited"; response_summary = "Too Many Requests"
        elif status_code >= 500:
            error = "server_error"; response_summary = "Internal Server Error"

        command_executed = None
        if request_body and isinstance(request_body, dict):
            command_executed = request_body.get("command")

        _audit_logger.log_request(
            endpoint=path, method=method, source_ip=source_ip, response_status=status_code,
            duration_ms=duration_ms, request_body=request_body, response_summary=response_summary,
            error=error, command_executed=command_executed,
        )


def _parse_body(body_text: str) -> Optional[dict[str, Any]]:
    if not body_text:
        return None
    try:
        data = json.loads(body_text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _log_audit_console(method: str, endpoint: str, source_ip: str, status: int,
                       duration_ms: float, body: Optional[dict[str, Any]]) -> None:
    logger = logging.getLogger("hermes-agent")
    body_str = json.dumps(_sanitize_body(body), default=str) if body else "-"
    level = logging.WARNING if status >= 400 else logging.INFO
    logger.log(level, "[AUDIT] %s %s | ip=%s | status=%s | duration=%.0fms | body=%s",
               method, endpoint, source_ip, status, duration_ms, body_str)
