"""Authentication and path-security dependencies for FastAPI."""
import os
from typing import Optional

from fastapi import Header, HTTPException, Request

from hermes_agent.config import ALLOWED_PATHS, DASHBOARD_TOKEN, TOKEN, log


def verify_token(x_agent_token: str = Header(...)):
    """FastAPI dependency: validate the X-Agent-Token header.

    Raises 401 if the token does not match HERMES_AGENT_TOKEN.
    """
    if x_agent_token != TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing token")
    return True


def _is_local(client_ip: str) -> bool:
    """Return True if the IP is a loopback or test address."""
    if not client_ip:
        return True
    return client_ip in ("127.0.0.1", "::1", "testclient") or client_ip.startswith("127.")


def verify_local_or_token(request: Request, x_agent_token: Optional[str] = Header(None)):
    """FastAPI dependency: allow localhost without token, require token otherwise.

    Requests from loopback addresses (127.x.x.x, ::1) bypass authentication.
    All other IPs must provide a valid X-Agent-Token matching HERMES_DASHBOARD_TOKEN
    (or HERMES_AGENT_TOKEN if no dashboard token is set).
    """
    client_ip = request.client.host if request.client else ""
    if _is_local(client_ip):
        return True
    if not x_agent_token or x_agent_token != DASHBOARD_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized: token required for remote access")
    return True


def check_path_allowed(target_path: str, request: Request) -> None:
    """Validate that a file path is within the allowed directories.

    Raises 403 if the resolved absolute path is not under any of the
    directories listed in HERMES_ALLOWED_PATHS.
    """
    resolved = os.path.realpath(os.path.abspath(target_path))
    for allowed in ALLOWED_PATHS:
        allowed_resolved = os.path.realpath(os.path.abspath(allowed))
        if resolved.startswith(allowed_resolved + os.sep) or resolved == allowed_resolved.rstrip(os.sep):
            return
    log.warning("Path access denied: %s from %s", target_path, request.client.host if request.client else "?")
    raise HTTPException(status_code=403, detail="Access denied: path not allowed")
