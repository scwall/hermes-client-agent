"""Task service — lifecycle management for ACP tasks."""

import asyncio
import json
import logging
import secrets
from datetime import datetime, timezone

import httpx

from hermes_agent.acp.conversation_store import get_conversation_store
from hermes_agent.acp.models import AcpTask
from hermes_agent.acp.runtime_broker import get_runtime_broker

_log = logging.getLogger("hermes-agent")

POLL_INTERVAL_S = 2
MAX_CONCURRENT_ASYNC = 10
_async_semaphore = asyncio.Semaphore(MAX_CONCURRENT_ASYNC)
_active_tasks: dict[str, asyncio.Task] = {}


class TaskService:
    def submit_and_return_task_id(self, conversation_id, prompt, model, timeout, workspace=""):
        task_id = "t_" + secrets.token_hex(6)
        AcpTask.create_task(task_id, conversation_id, prompt, model, timeout)
        task = asyncio.create_task(self._run_async(task_id, conversation_id, prompt, model, timeout, workspace))
        _active_tasks[task_id] = task
        return task_id

    async def submit_and_poll(self, conversation_id, prompt, model, timeout, workspace=""):
        task_id = self.submit_and_return_task_id(conversation_id, prompt, model, timeout, workspace)
        try:
            deadline = asyncio.get_event_loop().time() + 2
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(0.3)
                poll_data = self.poll(task_id)
                if poll_data and poll_data["status"] in ("completed", "failed", "cancelled"):
                    return {"task_id": task_id, "status": poll_data["status"], "mode": "sync", "result": poll_data.get("result", {}), "error": poll_data.get("error")}
            return {"task_id": task_id, "status": "running", "mode": "async"}
        except Exception:
            return {"task_id": task_id, "status": "running", "mode": "async"}

    async def _run_async(self, task_id, conversation_id, prompt, model, timeout, workspace):
        async with _async_semaphore:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(self._execute_and_poll, task_id, conversation_id, prompt, model, timeout, workspace),
                    timeout=timeout + 10,
                )
            except asyncio.TimeoutError:
                self._abort_running_session(conversation_id)
                AcpTask.mark_failed(task_id, f"Task timed out after {timeout}s", "task_timeout")
            except Exception as exc:
                AcpTask.mark_failed(task_id, str(exc)[:1024], "task_error")
            finally:
                _active_tasks.pop(task_id, None)

    def _abort_running_session(self, conversation_id):
        try:
            store = get_conversation_store()
            broker = get_runtime_broker()
            adapter = broker.get_adapter()
            upstream_sid = store.get_upstream_session(conversation_id)
            runtime_id = store.get_runtime_id(conversation_id)
            if upstream_sid and runtime_id:
                runtimes = broker._adapter  # we have adapter directly
                # find endpoint from runtime_id
                from hermes_agent.acp.models import AcpRuntime

                runtime = AcpRuntime.get_or_none(AcpRuntime.runtime_id == runtime_id)
                if runtime:
                    adapter.cancel(runtime.endpoint, upstream_sid)
        except Exception:
            _log.warning("Failed to abort session for conversation %s", conversation_id)

    def _execute_and_poll(self, task_id, conversation_id, prompt, model, timeout, workspace):
        broker = get_runtime_broker()
        store = get_conversation_store()
        adapter = broker.get_adapter()

        runtime = broker.acquire(conversation_id)
        endpoint = runtime["endpoint"]

        store.resolve(conversation_id, runtime["runtime_id"], workspace, model)

        upstream_sid = store.get_upstream_session(conversation_id)
        if not upstream_sid:
            session_data = adapter.create_session(endpoint)
            upstream_sid = session_data["id"]
            store.set_upstream_session(conversation_id, upstream_sid)

        result = self._send_message_with_session_recovery(
            adapter,
            store,
            broker,
            endpoint,
            conversation_id,
            upstream_sid,
            prompt,
            model,
            timeout,
            workspace,
        )
        result_json = json.dumps(result, default=str)
        AcpTask.mark_completed(task_id, result_json)

        return {"task_id": task_id, "status": "completed", "mode": "sync", "result": result}

    def _send_message_with_session_recovery(self, adapter, store, broker, endpoint, conversation_id, upstream_sid, prompt, model, timeout, workspace):
        try:
            return adapter.send_message(endpoint, upstream_sid, prompt, model, timeout)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (404, 500):
                raise
            _log.info("OpenCode session %s invalid (HTTP %d) — recreating session", upstream_sid, exc.response.status_code)
            try:
                session_data = adapter.create_session(endpoint)
                upstream_sid = session_data["id"]
                store.set_upstream_session(conversation_id, upstream_sid)
                _log.info("Session recreated: %s", upstream_sid)
            except Exception:
                _log.warning("Session creation failed on %s — acquiring new runtime", endpoint)
                runtime = broker.acquire(conversation_id)
                endpoint = runtime["endpoint"]
                store.resolve(conversation_id, runtime["runtime_id"], workspace, model)
                session_data = adapter.create_session(endpoint)
                upstream_sid = session_data["id"]
                store.set_upstream_session(conversation_id, upstream_sid)
                _log.info("New runtime %s, session %s", endpoint, upstream_sid)
            return adapter.send_message(endpoint, upstream_sid, prompt, model, timeout)

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
        if task.status == "running":
            conv_id = task.conversation_id
            if conv_id:
                self._abort_running_session(conv_id)
            handle = _active_tasks.pop(task_id, None)
            if handle and not handle.done():
                handle.cancel()
        AcpTask.mark_cancelled(task_id)
        return {"task_id": task_id, "status": "cancelled"}

    def cancel_handle(self, task_id):
        handle = _active_tasks.pop(task_id, None)
        if handle and not handle.done():
            handle.cancel()

    def reconcile_stale_tasks(self):
        now = datetime.now(timezone.utc)
        for t in AcpTask.get_running_tasks():
            deadline_str = t.get("deadline")
            if deadline_str:
                try:
                    deadline = datetime.fromisoformat(deadline_str)
                    if deadline < now:
                        AcpTask.mark_failed(t["task_id"], "Task timed out during restart", "task_timeout")
                        continue
                except (ValueError, TypeError):
                    pass
        AcpTask.cleanup_old(max_age_hours=24)


_task_service = None


def get_task_service():
    global _task_service
    if _task_service is None:
        _task_service = TaskService()
    return _task_service
