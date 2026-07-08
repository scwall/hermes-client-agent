"""Utility functions: sanitize, parse, console audit logging."""
import json
import logging
from typing import Any, Optional


def sanitize_body(body: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Return a copy of the body with sensitive fields masked."""
    if not body:
        return body
    sanitized = dict(body)
    for key in ("password", "token", "secret", "api_key", "apikey"):
        if key in sanitized:
            sanitized[key] = "***"
    return sanitized


def parse_body(body_text: str) -> Optional[dict[str, Any]]:
    """Parse a JSON body string, returning a dict or None."""
    if not body_text:
        return None
    try:
        data = json.loads(body_text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def log_audit_console(method: str, endpoint: str, source_ip: str, status: int,
                      duration_ms: float, body: Optional[dict[str, Any]]) -> None:
    """Log a structured audit line to the console."""
    logger = logging.getLogger("hermes-agent")
    body_str = json.dumps(sanitize_body(body), default=str) if body else "-"
    level = logging.WARNING if status >= 400 else logging.INFO
    logger.log(level, "[AUDIT] %s %s | ip=%s | status=%s | duration=%.0fms | body=%s",
               method, endpoint, source_ip, status, duration_ms, body_str)
