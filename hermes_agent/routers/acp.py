"""ACP bridge — relay tasks to any ACP-compatible agent via HTTP, with session management."""

import logging
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from hermes_agent.acp import get_session_manager
from hermes_agent.acp.diagnostics import run_diagnostics
from hermes_agent.acp.models import AcpSession
from hermes_agent.security import verify_token

router = APIRouter(tags=["acp"], dependencies=[Depends(verify_token)])
_log = logging.getLogger("hermes-agent")

DEFAULT_TIMEOUT = 300

PROVIDER_MAP = {
    "deepseek": "deepseek",
    "deepseek-chat": "deepseek",
    "deepseek-coder": "deepseek",
    "deepseek-reasoner": "deepseek",
    "deepseek-v4": "deepseek",
    "claude": "anthropic",
    "claude-sonnet": "anthropic",
    "claude-opus": "anthropic",
    "claude-sonnet-4": "anthropic",
    "claude-opus-4": "anthropic",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "gpt-5": "openai",
    "gpt-5.1": "openai",
    "gpt-5.2": "openai",
    "gpt-5.5": "openai",
    "gpt-5.6": "openai",
    "gemini": "google",
    "gemini-pro": "google",
    "gemini-flash": "google",
}


def _infer_provider(model_id: str) -> str:
    if not model_id:
        return ""
    model_lower = model_id.lower()
    for key, provider in PROVIDER_MAP.items():
        if key in model_lower:
            return provider
    return ""


class AcpRequest(BaseModel):
    agent_url: str = Field(..., description="Base URL of the ACP agent (e.g. http://localhost:4096)")
    prompt: str = Field(..., description="The task prompt to send")
    context: Optional[str] = Field(None, description="Additional context for the task")
    model: Optional[str] = Field(None, description="Model ID to use (agent-specific)")
    timeout: int = Field(DEFAULT_TIMEOUT, ge=1, le=3600, description="Max wait time in seconds")


class AcpSpawnResponse(BaseModel):
    session_id: str
    port: int
    pid: Optional[int]
    status: str
    created_at: Optional[str]


class AcpSessionItem(BaseModel):
    session_id: str
    agent_type: str
    pid: Optional[int]
    port: int
    status: str
    created_at: str
    last_heartbeat: Optional[str]
    exchange_count: int


async def _relay_to_opencode(agent_url: str, payload: dict, timeout: int, acp_session=None):
    base = agent_url.rstrip("/")
    opencode_sid = acp_session.opencode_session_id if acp_session else None
    opencode_dir = acp_session.opencode_directory if acp_session else None
    hermes_session_id = acp_session.session_id if acp_session else None

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        if not opencode_sid:
            try:
                r = await client.post(f"{base}/session", json={})
                r.raise_for_status()
            except httpx.ConnectError:
                raise HTTPException(status_code=503, detail=f"Cannot connect to ACP agent at {agent_url}")
            except httpx.TimeoutException:
                raise HTTPException(status_code=504, detail=f"ACP agent at {agent_url} timed out after {timeout}s")
            except httpx.HTTPStatusError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"ACP agent returned HTTP {exc.response.status_code} on session creation: {exc.response.text[:500]}",
                )
            try:
                data = r.json()
                opencode_sid = data["id"]
                opencode_dir = data.get("directory", "/")
            except (KeyError, ValueError):
                raise HTTPException(status_code=502, detail="Invalid response from ACP agent on session creation")

            if hermes_session_id:
                AcpSession.update_opencode_session(hermes_session_id, opencode_sid, opencode_dir)

        model_id = payload.get("model", "")
        text = payload["prompt"]
        if payload.get("context"):
            text = f"Context: {payload['context']}\n\n{text}"

        message_body: dict = {"parts": [{"type": "text", "text": text}]}
        if model_id:
            message_body["model"] = {"providerID": _infer_provider(model_id), "modelID": model_id}
        headers = {"x-opencode-directory": opencode_dir}

        try:
            r = await client.post(
                f"{base}/session/{opencode_sid}/message",
                json=message_body,
                headers=headers,
            )
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail=f"Cannot connect to ACP agent at {agent_url}")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail=f"ACP agent at {agent_url} timed out after {timeout}s")

        if r.status_code == 404:
            if hermes_session_id:
                AcpSession.update_opencode_session(hermes_session_id, None, None)
            return await _relay_to_opencode(agent_url, payload, timeout, acp_session)

        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"ACP agent returned HTTP {r.status_code}: {r.text[:500]}")

        try:
            data = r.json()
        except ValueError:
            data = {"raw": r.text[:10000]}

        return {"success": True, "agent_url": agent_url, "response": data}


@router.post("/acp", summary="Relay a task to an ACP-compatible agent")
async def acp_relay(body: AcpRequest):
    agent_url = body.agent_url.rstrip("/")
    payload: dict = {"prompt": body.prompt}
    if body.context:
        payload["context"] = body.context
    if body.model:
        payload["model"] = body.model

    _log.info("ACP relay to %s: prompt=%r timeout=%s", agent_url, body.prompt[:120], body.timeout)

    acp_session = None
    if "127.0.0.1" in agent_url or "localhost" in agent_url:
        parsed = urlparse(agent_url)
        port = parsed.port or 4444
        acp_session = AcpSession.get_active_on_port(port)
        if acp_session:
            _log.info("Using ACP session %s for %s", acp_session.session_id, agent_url)

    try:
        result = await _relay_to_opencode(agent_url, payload, body.timeout, acp_session)
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("ACP relay failed")
        raise HTTPException(status_code=502, detail=f"ACP relay error: {exc}")

    if acp_session:
        result["session_id"] = acp_session.session_id
        AcpSession.increment_exchange(acp_session.session_id)

    return result


@router.post("/acp/spawn", summary="Launch an ACP agent on a fixed port")
async def acp_spawn():
    mgr = get_session_manager()
    try:
        info = mgr.spawn()
        return info
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        _log.exception("Failed to spawn ACP agent")
        raise HTTPException(status_code=500, detail=f"Spawn failed: {exc}")


@router.get("/acp/sessions", summary="List active ACP sessions")
async def acp_list_sessions():
    mgr = get_session_manager()
    sessions = mgr.list_sessions()
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/acp/sessions/{session_id}", summary="Get a specific ACP session")
async def acp_get_session(session_id: str):
    mgr = get_session_manager()
    session = mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {
        "session_id": session.session_id,
        "agent_type": session.agent_type,
        "pid": session.pid,
        "port": session.port,
        "status": session.status,
        "created_at": session.created_at,
        "last_heartbeat": session.last_heartbeat,
        "exchange_count": session.exchange_count,
    }


@router.delete("/acp/sessions/{session_id}", summary="Stop an ACP session")
async def acp_stop_session(session_id: str):
    mgr = get_session_manager()
    try:
        result = mgr.stop(session_id)
        return result
    except LookupError:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    except Exception as exc:
        _log.exception("Failed to stop session %s", session_id)
        raise HTTPException(status_code=500, detail=f"Failed to stop session: {exc}")


@router.get("/acp/diagnostics", summary="Run ACP diagnostics to inspect agent config and health")
async def acp_diagnostics(agent_type: str = Query("opencode", description="ACP agent type to diagnose")):
    return run_diagnostics(agent_type)
