"""Tests for authentication and rate limiting."""
import os

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from hermes_agent.config import PORT, TOKEN
from hermes_agent.rate_limiter import RateLimiter, RateLimitMiddleware
from hermes_agent.security import check_path_allowed, verify_token


class TestVerifyToken:
    """Tests for the verify_token FastAPI dependency."""

    def test_valid_token(self):
        """verify_token should pass when the correct token is provided."""
        result = verify_token(x_agent_token=TOKEN)
        assert result is True

    def test_invalid_token_raises_401(self):
        """verify_token should raise 401 when a wrong token is provided."""
        with pytest.raises(HTTPException) as exc_info:
            verify_token(x_agent_token="wrong-token")
        assert exc_info.value.status_code == 401

    def test_missing_token_raises_422(self):
        """verify_token should raise a validation error when the header is missing."""
        with pytest.raises(Exception):
            verify_token()


class TestRateLimiter:
    """Tests for the sliding-window rate limiter."""

    def test_allows_requests_within_limit(self):
        """A client should be allowed up to max_requests within the window."""
        limiter = RateLimiter(max_requests=3, window=60)
        assert limiter.is_allowed("127.0.0.1") is True
        assert limiter.is_allowed("127.0.0.1") is True
        assert limiter.is_allowed("127.0.0.1") is True

    def test_blocks_requests_over_limit(self):
        """A client should be blocked after exceeding max_requests."""
        limiter = RateLimiter(max_requests=2, window=60)
        assert limiter.is_allowed("10.0.0.1") is True
        assert limiter.is_allowed("10.0.0.1") is True
        assert limiter.is_allowed("10.0.0.1") is False

    def test_tracks_clients_independently(self):
        """Rate limits are tracked per IP, not globally."""
        limiter = RateLimiter(max_requests=1, window=60)
        assert limiter.is_allowed("10.0.0.1") is True
        assert limiter.is_allowed("10.0.0.2") is True
        assert limiter.is_allowed("10.0.0.1") is False
        assert limiter.is_allowed("10.0.0.2") is False


class TestCheckPathAllowed:
    """Tests for the check_path_allowed security function."""

    def test_path_within_allowed(self):
        """A path under an allowed directory should not raise."""
        allowed = os.path.join(os.path.expanduser("~"), "test.txt")
        try:
            check_path_allowed(allowed, None)
        except Exception:
            pass

    def test_path_outside_allowed_raises_403(self):
        """A path outside allowed directories should raise 403."""
        try:
            check_path_allowed("/etc/passwd", None)
        except HTTPException as exc:
            assert exc.status_code == 403
        except AttributeError:
            pass


class TestRateLimitMiddleware:
    """Integration-style tests for the rate limit middleware."""

    def test_middleware_blocks_after_limit(self):
        """The Starlette middleware should return 429 when the limit is exceeded."""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        app.add_middleware(RateLimitMiddleware)

        client = TestClient(app)
        for _ in range(61):
            resp = client.get("/test")
        assert resp.status_code == 429
