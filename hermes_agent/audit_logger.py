"""Structured JSON Lines audit logger and FastAPI middleware for all HTTP requests."""
import json
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

LOG_DIR = Path("logs")
MAX_LOG_SIZE_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_AGE_HOURS = 168

_lock = threading.Lock()


class AuditLogger:
    """Thread-safe JSON Lines audit log writer and reader.

    Writes one JSON object per line to `./logs/audit.jsonl`.
    Provides helpers to read, filter, aggregate, and clean up log entries.
    """

    def __init__(self, log_path: Optional[Path] = None):
        self._log_path = log_path or (LOG_DIR / "audit.jsonl")
        self._ensure_log_dir()

    def _ensure_log_dir(self) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

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
        """Write a single audit entry to the JSON Lines log file."""
        entry = {
            "id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "method": method,
            "source_ip": source_ip,
            "request_body": request_body,
            "response_status": response_status,
            "response_summary": response_summary,
            "duration_ms": round(duration_ms, 2),
            "error": error,
            "command_executed": command_executed,
        }
        line = json.dumps(entry, default=str)
        with _lock:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return entry["id"]

    def _read_all(self) -> list[dict[str, Any]]:
        """Read all entries from the log file (most recent first)."""
        if not self._log_path.exists():
            return []
        with _lock:
            with open(self._log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        entries: list[dict[str, Any]] = []
        for line in reversed(lines):
            stripped = line.strip()
            if stripped:
                try:
                    entries.append(json.loads(stripped))
                except json.JSONDecodeError:
                    continue
        return entries

    def get_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        endpoint_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> dict[str, Any]:
        """Return paginated, filtered log entries."""
        all_entries = self._read_all()
        filtered: list[dict[str, Any]] = []

        for e in all_entries:
            if endpoint_filter and e.get("endpoint", "") != endpoint_filter:
                continue
            if status_filter:
                try:
                    code = int(status_filter)
                    if e.get("response_status") != code:
                        continue
                except ValueError:
                    if status_filter.lower() == "success" and (e.get("response_status") or 0) >= 400:
                        continue
                    if status_filter.lower() == "error" and (e.get("response_status") or 0) < 400:
                        continue
            if search:
                haystack = json.dumps(e, default=str).lower()
                if search.lower() not in haystack:
                    continue
            filtered.append(e)

        total = len(filtered)
        page = filtered[offset : offset + limit]
        return {"total": total, "limit": limit, "offset": offset, "entries": page}

    def get_stats(self) -> dict[str, Any]:
        """Compute aggregate statistics from the log file."""
        entries = self._read_all()
        if not entries:
            return {
                "total": 0,
                "success": 0,
                "errors": 0,
                "avg_duration_ms": 0,
                "top_endpoints": [],
                "slowest_commands": [],
            }

        success = sum(1 for e in entries if (e.get("response_status") or 0) < 400)
        errors = len(entries) - success
        durations = [e.get("duration_ms", 0) for e in entries if e.get("duration_ms")]
        avg = round(sum(durations) / len(durations), 2) if durations else 0

        endpoint_counts: dict[str, int] = defaultdict(int)
        for e in entries:
            ep = e.get("endpoint", "?")
            endpoint_counts[ep] += 1
        top_endpoints = sorted(endpoint_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        slowest = sorted(entries, key=lambda e: e.get("duration_ms", 0), reverse=True)[:5]
        slowest_commands = [
            {
                "endpoint": s.get("endpoint"),
                "command": s.get("command_executed"),
                "duration_ms": s.get("duration_ms"),
                "timestamp": s.get("timestamp"),
            }
            for s in slowest
        ]

        return {
            "total": len(entries),
            "success": success,
            "errors": errors,
            "avg_duration_ms": avg,
            "top_endpoints": [{"endpoint": ep, "count": c} for ep, c in top_endpoints],
            "slowest_commands": slowest_commands,
        }

    def get_recent_errors(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent errors (status >= 400)."""
        entries = self._read_all()
        errors = [e for e in entries if (e.get("response_status") or 0) >= 400]
        return errors[:limit]

    def clear_old_logs(self, max_age_hours: int = DEFAULT_MAX_AGE_HOURS) -> dict[str, Any]:
        """Remove entries older than *max_age_hours* if the file exceeds 10 MiB."""
        if not self._log_path.exists():
            return {"action": "nothing", "reason": "no log file"}

        file_size = self._log_path.stat().st_size
        if file_size < MAX_LOG_SIZE_BYTES:
            return {"action": "nothing", "reason": f"file is {file_size} bytes, below {MAX_LOG_SIZE_BYTES} threshold"}

        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
        entries = self._read_all()
        kept: list[dict[str, Any]] = []

        for e in entries:
            try:
                ts = datetime.fromisoformat(e["timestamp"]).timestamp()
                if ts >= cutoff:
                    kept.append(e)
            except (KeyError, ValueError):
                kept.append(e)

        kept.reverse()
        removed = len(entries) - len(kept)

        with _lock:
            with open(self._log_path, "w", encoding="utf-8") as f:
                for e in kept:
                    f.write(json.dumps(e, default=str) + "\n")

        return {"action": "rotated", "removed": removed, "kept": len(kept)}


_audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    """Return the singleton AuditLogger instance."""
    return _audit_logger


class AuditMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that logs every HTTP request via AuditLogger.

    Placed after the rate-limiter and auth middleware so that even 401/403
    responses are captured.
    """

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        source_ip = request.client.host if request.client else "?"
        endpoint = request.url.path
        method = request.method
        status = response.status_code

        request_body: Optional[dict[str, Any]] = None
        if method in ("POST", "PUT") and request.url.path.startswith("/exec"):
            try:
                body_bytes = await request.body()
                body_text = body_bytes.decode("utf-8", errors="replace")
                if body_text:
                    body_data = json.loads(body_text)
                    if isinstance(body_data, dict):
                        request_body = body_data
                        if body_data.get("command"):
                            _ = body_data.get("command")
            except Exception:
                pass

        error = None
        response_summary = str(status)
        if status == 401:
            error = "unauthorized"
            response_summary = "Unauthorized"
        elif status == 403:
            error = "forbidden"
            response_summary = "Forbidden"
        elif status == 429:
            error = "rate_limited"
            response_summary = "Too Many Requests"
        elif status >= 500:
            error = "server_error"
            response_summary = "Internal Server Error"

        command_executed = None
        if request_body and isinstance(request_body, dict):
            command_executed = request_body.get("command")

        _audit_logger.log_request(
            endpoint=endpoint,
            method=method,
            source_ip=source_ip,
            response_status=status,
            duration_ms=duration_ms,
            request_body=request_body,
            response_summary=response_summary,
            error=error,
            command_executed=command_executed,
        )
        return response
