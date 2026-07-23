"""Task service — lifecycle management for ACP tasks."""

import asyncio
import json
import logging
import secrets

from hermes_agent.acp.conversation_store import get_conversation_store
from hermes_agent.acp.models import AcpTask
from hermes_agent.acp.runtime_broker import get_runtime_broker

_log = logging.getLogger("hermes-agent")

POLL_INTERNAL_S = 1
POLL_MAX_ITERATIONS = 10
MAX_CONCURRENT_ASYNC = 10
_async_semaphore = asyncio.Semaphore(MAX_CONCURRENT_ASYNC)


class TaskService:
    def submit_and_poll(self, conversation_id, prompt, model, timeout, workspace=""):
        task_id = "t_" + secrets.token_hex(6)
        AcpTask.create_task(task_id, conversation_id, prompt, model, timeout)

        try:
            return self._execute_and_poll(task_id, conversation_id, prompt, model, timeout, workspace)
        except Exception as exc:
            AcpTask.mark_failed(task_id, str(exc)[:1024])
            raise

    def _execute_and_poll(self, task_id, conversation_id, prompt, model, timeout, workspace):
        broker = get_runtime_broker()
        store = get_conversation_store()
        adapter = broker.get_adapter()

        runtime = broker.acquire(conversation_id)
        runtime_id = runtime["runtime_id"]
        endpoint = runtime["endpoint"]

        store.resolve(conversation_id, runtime_id, workspace, model)

        upstream_sid = store.get_upstream_session(conversation_id)
        if not upstream_sid:
            session_data = adapter.create_session(endpoint)
            upstream_sid = session_data["id"]
            store.set_upstream_session(conversation_id, upstream_sid)

        result = adapter.send_message(endpoint, upstream_sid, prompt, model, timeout)
        result_json = json.dumps(result, default=str)
        AcpTask.mark_completed(task_id, result_json)

        return {"task_id": task_id, "status": "completed", "mode": "sync", "result": result}

    def submit_async(self, conversation_id, prompt, model, timeout, workspace=""):
        task_id = "t_" + secrets.token_hex(6)
        AcpTask.create_task(task_id, conversation_id, prompt, model, timeout)

        asyncio.create_task(self._run_async(task_id, conversation_id, prompt, model, timeout, workspace))

        return {"task_id": task_id, "status": "running"}

    async def _run_async(self, task_id, conversation_id, prompt, model, timeout, workspace):
        async with _async_semaphore:
            try:
                result = self._execute_and_poll(task_id, conversation_id, prompt, model, timeout, workspace)
            except Exception as exc:
                AcpTask.mark_failed(task_id, str(exc)[:1024], "task_error")

    def poll(self, task_id):
        task = AcpTask.get_by_task_id(task_id)
        if not task:
            return None
        resp = {"task_id": task.task_id, "status": task.status, "created_at": task.created_at}
        if task.status == "completed":
            try:
                resp["result"] = json.loads(task.result) if task.result else {}
            except (json.JSONDecodeError, TypeError):
                resp["result"] = {"raw": (task.result or "")[:10000]}
        elif task.status == "failed":
            resp["error"] = task.error
            resp["error_code"] = task.error_code
        elif task.status == "cancelled":
            resp["error"] = "Task was cancelled"
        return resp

    def cancel(self, task_id):
        task = AcpTask.get_by_task_id(task_id)
        if not task:
            return None
        AcpTask.mark_cancelled(task_id)
        return {"task_id": task_id, "status": "cancelled"}


_task_service = None


def get_task_service():
    global _task_service
    if _task_service is None:
        _task_service = TaskService()
    return _task_service
