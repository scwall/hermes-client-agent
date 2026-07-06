"""In-memory log capture, request middleware, and a real-time HTML dashboard."""
import logging
import collections
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

MAX_LOG_ENTRIES = 500
_log_entries: collections.deque = collections.deque(maxlen=MAX_LOG_ENTRIES)


class LogCaptureHandler(logging.Handler):
    """Python logging handler that stores formatted entries in an in-memory deque."""

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": self.format(record),
            "client": getattr(record, "client", "-"),
            "method": getattr(record, "method", ""),
            "path": getattr(record, "path", ""),
        }
        _log_entries.append(entry)


_log_handler = LogCaptureHandler()
_log_handler.setLevel(logging.INFO)
_log_handler.setFormatter(logging.Formatter("%(message)s"))
_log_handler.addFilter(lambda r: not r.name.startswith("uvicorn"))


def setup_log_capture(root_logger: logging.Logger) -> None:
    """Attach the in-memory log handler to the root logger at startup."""
    root_logger.addHandler(_log_handler)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that logs every HTTP request with timing."""

    async def dispatch(self, request: Request, call_next):
        start = datetime.now(timezone.utc)
        response = await call_next(request)
        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        client_ip = request.client.host if request.client else "?"
        logger = logging.getLogger("hermes-agent")
        logger.info(
            "%s %s %s %s %.0fms",
            client_ip,
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
            extra={
                "client": client_ip,
                "method": request.method,
                "path": request.url.path,
            },
        )
        return response


log_router = APIRouter(tags=["logs"])
