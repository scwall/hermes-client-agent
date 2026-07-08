"""Peewee ORM audit logger and ASGI middleware for all HTTP requests."""
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from peewee import CharField, IntegerField, Model, SqliteDatabase, TextField, fn

LOG_DIR = Path("logs")
_db = SqliteDatabase(None)


class AuditLog(Model):
    """Peewee model for the audit_logs table — database set at init time."""
    id = CharField(primary_key=True, max_length=36)
    timestamp = CharField(max_length=30)
    method = CharField(max_length=10)
    endpoint = CharField(max_length=100)
    source_ip = CharField(max_length=45)
    status_code = IntegerField()
    duration_ms = IntegerField()
    request_body = TextField(null=True)
    response_summary = TextField(null=True)
    error = TextField(null=True)
    command_executed = TextField(null=True)

    class Meta:
        table_name = "audit_logs"


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    return os.environ.get(key, str(default).lower()).lower() in ("true", "1", "yes")


class AuditLogger:
    """Thread-safe audit log writer/reader backed by SQLite via Peewee ORM.
    Stores structured request logs with automatic retention cleanup.
    """

    def __init__(self, db_path=None, max_rows=None, max_age_days=None, auto_cleanup=None):
        self._db_path = (db_path if db_path else (LOG_DIR / "audit.db")).resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_rows = max_rows if max_rows is not None else _env_int("HERMES_AUDIT_MAX_ROWS", 100000)
        self.max_age_days = max_age_days if max_age_days is not None else _env_int("HERMES_AUDIT_MAX_AGE_DAYS", 90)
        self.auto_cleanup = auto_cleanup if auto_cleanup is not None else _env_bool("HERMES_AUDIT_AUTO_CLEANUP", True)
        self._db = SqliteDatabase(str(self._db_path), pragmas={"journal_mode": "wal", "foreign_keys": "on"})
        self._db.connect()
        AuditLog._meta.database = self._db
        self._db.create_tables([AuditLog], safe=True)

    def close(self):
        if not self._db.is_closed():
            self._db.close()

    def log_request(self, endpoint, method, source_ip, response_status, duration_ms,
                    request_body=None, response_summary="", error=None, command_executed=None):
        """Write a single audit entry."""
        AuditLog._meta.database = self._db
        entry_id = str(uuid4())
        body_json = json.dumps(request_body, default=str) if request_body else None
        AuditLog.create(
            id=entry_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            method=method,
            endpoint=endpoint,
            source_ip=source_ip,
            status_code=response_status,
            duration_ms=int(round(duration_ms)),
            request_body=body_json,
            response_summary=response_summary or None,
            error=error or None,
            command_executed=command_executed or None,
        )
        if self.auto_cleanup:
            self._cleanup()
        return entry_id

    def _cleanup(self):
        AuditLog._meta.database = self._db
        deleted = 0
        total = AuditLog.select().count()
        if total > self.max_rows:
            excess = total - self.max_rows + int(self.max_rows * 0.1)
            for log in AuditLog.select().order_by(AuditLog.timestamp.asc()).limit(excess):
                log.delete_instance()
                deleted += 1
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.max_age_days)).isoformat()
        for log in AuditLog.select().where(AuditLog.timestamp < cutoff):
            log.delete_instance()
            deleted += 1
        if deleted:
            logging.getLogger("hermes-agent").info("Audit cleanup: deleted %s rows", deleted)

    def get_logs(self, limit=100, offset=0, endpoint_filter=None, status_filter=None,
                 ip_filter=None, search=None):
        """Return paginated, filtered log entries."""
        AuditLog._meta.database = self._db
        query = AuditLog.select()
        if endpoint_filter:
            query = query.where(AuditLog.endpoint == endpoint_filter)
        if status_filter:
            if status_filter == "success":
                query = query.where(AuditLog.status_code.between(200, 399))
            elif status_filter == "error":
                query = query.where(AuditLog.status_code >= 400)
            else:
                try:
                    query = query.where(AuditLog.status_code == int(status_filter))
                except ValueError:
                    pass
        if ip_filter:
            query = query.where(AuditLog.source_ip.contains(ip_filter))
        if search:
            query = query.where(
                AuditLog.command_executed.contains(search)
                | AuditLog.request_body.contains(search)
                | AuditLog.error.contains(search)
            )
        total = query.count()
        rows = list(query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).dicts())
        entries = []
        for r in rows:
            r["response_status"] = r.pop("status_code", 0)
            if r.get("request_body"):
                try:
                    r["request_body"] = json.loads(r["request_body"])
                except (json.JSONDecodeError, TypeError):
                    pass
            entries.append(r)
        return {"total": total, "limit": limit, "offset": offset, "entries": entries}

    def get_stats(self):
        """Compute aggregate statistics."""
        AuditLog._meta.database = self._db
        total = AuditLog.select().count()
        if total == 0:
            return dict(total=0, success=0, errors=0, avg_duration_ms=0, top_endpoints=[], top_ips=[],
                        slowest_commands=[], retention=dict(max_rows=self.max_rows, max_age_days=self.max_age_days, current_rows=0))
        success = AuditLog.select().where(AuditLog.status_code.between(200, 399)).count()
        avg = AuditLog.select(fn.AVG(AuditLog.duration_ms)).scalar() or 0
        top_eps = list(AuditLog.select(AuditLog.endpoint, fn.COUNT(AuditLog.id).alias("count"))
                       .group_by(AuditLog.endpoint).order_by(fn.COUNT(AuditLog.id).desc()).limit(10).dicts())
        top_ips = list(AuditLog.select(AuditLog.source_ip, fn.COUNT(AuditLog.id).alias("count"))
                       .where(AuditLog.source_ip != "?").group_by(AuditLog.source_ip)
                       .order_by(fn.COUNT(AuditLog.id).desc()).limit(5).dicts())
        slowest = list(AuditLog.select().order_by(AuditLog.duration_ms.desc()).limit(5).dicts())
        return dict(total=total, success=success, errors=total - success, avg_duration_ms=round(avg, 2),
                    top_endpoints=[{"endpoint": e["endpoint"], "count": e["count"]} for e in top_eps],
                    top_ips=[{"ip": e["source_ip"], "count": e["count"]} for e in top_ips],
                    slowest_commands=[
                        {"endpoint": s["endpoint"], "command": s["command_executed"],
                         "duration_ms": s["duration_ms"], "timestamp": s["timestamp"]} for s in slowest
                    ],
                    retention=dict(max_rows=self.max_rows, max_age_days=self.max_age_days, current_rows=total))

    def get_recent_errors(self, limit=20):
        AuditLog._meta.database = self._db
        rows = list(AuditLog.select().where(AuditLog.status_code >= 400)
                    .order_by(AuditLog.timestamp.desc()).limit(limit).dicts())
        return rows

    def clear_all(self):
        AuditLog._meta.database = self._db
        count = AuditLog.select().count()
        AuditLog.delete().execute()
        return count

    def clear_old_logs(self, max_age_hours=168):
        AuditLog._meta.database = self._db
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        before = AuditLog.select().count()
        AuditLog.delete().where(AuditLog.timestamp < cutoff).execute()
        after = AuditLog.select().count()
        return {"action": "rotated", "removed": before - after, "kept": after}

    def export_logs(self, fmt="json", **filters):
        if "limit" not in filters:
            filters["limit"] = 100000
        result = self.get_logs(**filters)
        entries = result["entries"]
        if fmt == "csv":
            import csv
            import io
            buf = io.StringIO()
            if entries:
                fields = ["timestamp", "method", "endpoint", "source_ip", "response_status", "duration_ms", "command_executed"]
                writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(entries)
            return buf.getvalue()
        return json.dumps(entries, indent=2, default=str)


_audit_logger = None


def get_audit_logger():
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    AuditLog._meta.database = _audit_logger._db
    return _audit_logger


def _sanitize_body(body):
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
        get_audit_logger().log_request(
            endpoint=path, method=method, source_ip=source_ip, response_status=status_code,
            duration_ms=duration_ms, request_body=request_body, response_summary=response_summary,
            error=error, command_executed=command_executed,
        )


def _parse_body(body_text):
    if not body_text:
        return None
    try:
        data = json.loads(body_text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _log_audit_console(method, endpoint, source_ip, status, duration_ms, body):
    logger = logging.getLogger("hermes-agent")
    body_str = json.dumps(_sanitize_body(body), default=str) if body else "-"
    level = logging.WARNING if status >= 400 else logging.INFO
    logger.log(level, "[AUDIT] %s %s | ip=%s | status=%s | duration=%.0fms | body=%s",
               method, endpoint, source_ip, status, duration_ms, body_str)
