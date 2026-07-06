"""Authentication and path-security dependencies for FastAPI."""
import os

from fastapi import Header, HTTPException, Request

from hermes_agent.config import TOKEN, ALLOWED_PATHS, log


def verify_token(x_agent_token: str = Header(...)):
    """FastAPI dependency: validate the X-Agent-Token header.

    Raises 401 if the token does not match HERMES_AGENT_TOKEN.
    """
    if x_agent_token != TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing token")
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
