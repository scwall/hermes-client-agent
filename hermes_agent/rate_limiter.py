"""Per-IP rate limiting as Starlette middleware."""
import time
import threading
import collections

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from hermes_agent.config import RATE_LIMIT, RATE_WINDOW


class RateLimiter:
    """Thread-safe sliding-window rate limiter keyed by client IP."""

    def __init__(self, max_requests: int = RATE_LIMIT, window: int = RATE_WINDOW):
        self.max_requests = max_requests
        self.window = window
        self._clients: dict[str, collections.deque] = {}
        self._lock = threading.Lock()

    def is_allowed(self, client_ip: str) -> bool:
        """Return True if the client has not exceeded the rate limit."""
        now = time.time()
        with self._lock:
            if client_ip not in self._clients:
                self._clients[client_ip] = collections.deque()
            timestamps = self._clients[client_ip]
            while timestamps and timestamps[0] < now - self.window:
                timestamps.popleft()
            if len(timestamps) >= self.max_requests:
                return False
            timestamps.append(now)
            return True


_rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that rejects requests exceeding the rate limit."""

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "127.0.0.1"
        if not _rate_limiter.is_allowed(client_ip):
            return JSONResponse(status_code=429, content={"error": "Too many requests"})
        return await call_next(request)
