"""AuditLog Peewee model with class methods for all DB operations."""
import csv
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from peewee import CharField, IntegerField, Model, SqliteDatabase, TextField, fn

LOG_DIR = Path("logs")

_db = SqliteDatabase(None)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    return os.environ.get(key, str(default).lower()).lower() in ("true", "1", "yes")


class AuditLog(Model):
    """Peewee model for the audit_logs table. All queries are class methods."""

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

    @classmethod
    def init_db(cls, db_path=None):
        """Initialize the database connection and create tables."""
        path = Path(db_path if db_path else (LOG_DIR / "audit.db")).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        cls._meta.database = SqliteDatabase(str(path), pragmas={"journal_mode": "wal", "foreign_keys": "on"})
        cls._meta.database.connect()
        cls._meta.database.create_tables([cls], safe=True)

    @classmethod
    def close_db(cls):
        """Close the database connection."""
        if not cls._meta.database.is_closed():
            cls._meta.database.close()

    @classmethod
    def _ensure_db(cls):
        """Initialize the default DB if not yet connected."""
        if cls._meta.database is None or cls._meta.database.is_closed():
            cls.init_db()

    @classmethod
    def create_entry(cls, endpoint, method, source_ip, response_status, duration_ms,
                     request_body=None, response_summary="", error=None, command_executed=None):
        """Insert a single audit entry. Returns the entry id."""
        cls._ensure_db()
        entry_id = str(uuid4())
        body_json = json.dumps(request_body, default=str) if request_body else None
        cls.create(
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
        return entry_id

    @classmethod
    def fetch_logs(cls, limit=100, offset=0, endpoint_filter=None, status_filter=None,
                   ip_filter=None, search=None):
        """Return paginated, filtered log entries as dicts."""
        cls._ensure_db()
        query = cls.select()
        if endpoint_filter:
            query = query.where(cls.endpoint == endpoint_filter)
        if status_filter:
            if status_filter == "success":
                query = query.where(cls.status_code.between(200, 399))
            elif status_filter == "error":
                query = query.where(cls.status_code >= 400)
            else:
                try:
                    query = query.where(cls.status_code == int(status_filter))
                except ValueError:
                    pass
        if ip_filter:
            query = query.where(cls.source_ip.contains(ip_filter))
        if search:
            query = query.where(
                cls.command_executed.contains(search)
                | cls.request_body.contains(search)
                | cls.error.contains(search)
            )
        total = query.count()
        rows = list(query.order_by(cls.timestamp.desc()).offset(offset).limit(limit).dicts())
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

    @classmethod
    def fetch_stats(cls, max_rows=100000, max_age_days=90):
        """Compute aggregate statistics."""
        cls._ensure_db()
        total = cls.select().count()
        if total == 0:
            return dict(total=0, success=0, errors=0, avg_duration_ms=0, top_endpoints=[], top_ips=[],
                        slowest_commands=[], retention=dict(max_rows=max_rows, max_age_days=max_age_days, current_rows=0))
        success = cls.select().where(cls.status_code.between(200, 399)).count()
        avg = cls.select(fn.AVG(cls.duration_ms)).scalar() or 0
        top_eps = list(cls.select(cls.endpoint, fn.COUNT(cls.id).alias("count"))
                       .group_by(cls.endpoint).order_by(fn.COUNT(cls.id).desc()).limit(10).dicts())
        top_ips = list(cls.select(cls.source_ip, fn.COUNT(cls.id).alias("count"))
                       .where(cls.source_ip != "?").group_by(cls.source_ip)
                       .order_by(fn.COUNT(cls.id).desc()).limit(5).dicts())
        slowest = list(cls.select().order_by(cls.duration_ms.desc()).limit(5).dicts())
        return dict(total=total, success=success, errors=total - success, avg_duration_ms=round(avg, 2),
                    top_endpoints=[{"endpoint": e["endpoint"], "count": e["count"]} for e in top_eps],
                    top_ips=[{"ip": e["source_ip"], "count": e["count"]} for e in top_ips],
                    slowest_commands=[
                        {"endpoint": s["endpoint"], "command": s["command_executed"],
                         "duration_ms": s["duration_ms"], "timestamp": s["timestamp"]} for s in slowest
                    ],
                    retention=dict(max_rows=max_rows, max_age_days=max_age_days, current_rows=total))

    @classmethod
    def fetch_recent_errors(cls, limit=20):
        """Return the most recent error entries."""
        cls._ensure_db()
        return list(cls.select().where(cls.status_code >= 400)
                    .order_by(cls.timestamp.desc()).limit(limit).dicts())

    @classmethod
    def clear_old_entries(cls, max_rows=100000, max_age_days=90):
        """Remove entries exceeding retention limits. Returns count deleted."""
        cls._ensure_db()
        deleted = 0
        total = cls.select().count()
        if total > max_rows:
            excess = total - max_rows + int(max_rows * 0.1)
            for entry in cls.select().order_by(cls.timestamp.asc()).limit(excess):
                entry.delete_instance()
                deleted += 1
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        for entry in cls.select().where(cls.timestamp < cutoff):
            entry.delete_instance()
            deleted += 1
        return deleted

    @classmethod
    def truncate(cls):
        """Delete all entries. Returns count deleted."""
        cls._ensure_db()
        count = cls.select().count()
        cls.delete().execute()
        return count

    @classmethod
    def purge_older_than(cls, max_age_hours=168):
        """Delete entries older than N hours. Returns action summary."""
        cls._ensure_db()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        before = cls.select().count()
        cls.delete().where(cls.timestamp < cutoff).execute()
        after = cls.select().count()
        return {"action": "rotated", "removed": before - after, "kept": after}

    @classmethod
    def export(cls, fmt="json", limit=100000, endpoint_filter=None, status_filter=None,
               ip_filter=None, search=None):
        """Export filtered logs as CSV or JSON string."""
        cls._ensure_db()
        result = cls.fetch_logs(limit=limit, endpoint_filter=endpoint_filter,
                                status_filter=status_filter, ip_filter=ip_filter, search=search)
        entries = result["entries"]
        if fmt == "csv":
            buf = io.StringIO()
            fields = ["timestamp", "method", "endpoint", "source_ip", "response_status", "duration_ms", "command_executed"]
            writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            if entries:
                writer.writerows(entries)
            return buf.getvalue()
        return json.dumps(entries, indent=2, default=str)
