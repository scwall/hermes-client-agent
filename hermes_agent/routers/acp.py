"""ACP bridge — relay tasks to coding agents with runtime management."""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from hermes_agent.acp.diagnostics import run_diagnostics
from hermes_agent.acp.models import AcpRuntime, AcpTask
from hermes_agent.acp.runtime_broker import get_runtime_broker
from hermes_agent.acp.task_service import get_task_service
from hermes_agent.security import verify_token

router = APIRouter(tags=["acp"], dependencies=[Depends(verify_token)])
_log = logging.getLogger("hermes-agent")

DEFAULT_TIMEOUT = 300
POLL_CUTOFF_S = 10


class AcpTaskRequest(BaseModel):
    prompt: str = Field(..., description="The task to delegate")
    model: Optional[str] = Field(None, description="Model ID (e.g. deepseek-chat)")
    timeout: int = Field(DEFAULT_TIMEOUT, ge=1, le=3600, description="Max wait in seconds")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for session reuse")


class AcpTaskItem(BaseModel):
    task_id: str
    status: str
    model: Optional[str]
    agent_url: str


@router.post("/acp/tasks", summary="Submit a task to the ACP coding agent")
async def acp_submit_task(body: AcpTaskRequest):
    svc = get_task_service()
    conversation_id = body.conversation_id or "default"

    try:
        result = svc.submit_and_poll(
            conversation_id=conversation_id,
            prompt=body.prompt,
            model=body.model or "",
            timeout=body.timeout,
        )
        _log.info("ACP task %s completed in sync mode", result["task_id"])
        return result
    except Exception as exc:
        detail = str(exc)
        error_code = "task_error"
        if "binary not found" in detail.lower():
            error_code = "runtime_not_installed"
        elif "health check" in detail.lower():
            error_code = "runtime_start_failed"
        elif "maximum" in detail.lower():
            error_code = "too_many_runtimes"
        _log.error("ACP task failed: %s", detail)
        raise HTTPException(status_code=503, detail=detail)


@router.get("/acp/tasks/{task_id}", summary="Get task status and result")
async def acp_task_status(task_id: str):
    svc = get_task_service()
    result = svc.poll(task_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return result


@router.delete("/acp/tasks/{task_id}", summary="Cancel a running task")
async def acp_task_cancel(task_id: str):
    svc = get_task_service()
    result = svc.cancel(task_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return result


@router.get("/acp/status", summary="ACP system status and diagnostics")
async def acp_status():
    runtimes = AcpRuntime.get_ready_managed()
    tasks_running = AcpTask.count_running()
    return {
        "runtimes": [{"runtime_id": r["runtime_id"], "endpoint": r["endpoint"], "status": r["status"]} for r in runtimes],
        "runtimes_count": len(runtimes),
        "tasks_running": tasks_running,
    }


@router.get("/acp/sessions", summary="List active ACP sessions")
async def acp_list_sessions():
    runtimes = AcpRuntime.get_ready_managed()
    return {"sessions": runtimes, "count": len(runtimes)}


@router.get("/acp/diagnostics", summary="Run ACP diagnostics")
async def acp_diagnostics(agent_type: str = Query("opencode")):
    return run_diagnostics(agent_type)
