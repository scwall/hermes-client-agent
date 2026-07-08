"""ASGI middleware that captures the request body before FastAPI consumes it."""
import logging
import time

from hermes_agent.audit.logger import get_audit_logger
from hermes_agent.audit.utils import log_audit_console, parse_body

_log = logging.getLogger("hermes-agent")


class AuditMiddleware:
    """ASGI middleware: logs every non-dashboard request to the audit DB."""

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
        _log.debug("-> REQUEST %s %s ip=%s body_bytes=%d", method, path, source_ip, len(body_bytes))
        request_body = parse_body(body_text)
        log_audit_console(method, path, source_ip, status_code, duration_ms, request_body)
        error = None
        response_summary = str(status_code)
        if status_code == 401:
            error = "unauthorized"
            response_summary = "Unauthorized"
        elif status_code == 403:
            error = "forbidden"
            response_summary = "Forbidden"
        elif status_code == 429:
            error = "rate_limited"
            response_summary = "Too Many Requests"
        elif status_code >= 500:
            error = "server_error"
            response_summary = "Internal Server Error"
        command_executed = None
        if request_body and isinstance(request_body, dict):
            command_executed = request_body.get("command")
        get_audit_logger().log_request(
            endpoint=path, method=method, source_ip=source_ip, response_status=status_code,
            duration_ms=duration_ms, request_body=request_body, response_summary=response_summary,
            error=error, command_executed=command_executed,
        )
        _log.debug("<- RESPONSE %s %s status=%s duration=%.0fms", method, path, status_code, duration_ms)
