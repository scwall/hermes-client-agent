"""Peewee models for ACP runtimes, conversations, and tasks."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from peewee import BooleanField, CharField, IntegerField, Model, SqliteDatabase

DB_DIR = Path("acp_data")
_db = SqliteDatabase(None)


def _now():
    return datetime.now(timezone.utc).isoformat()


class _BaseModel(Model):
    @classmethod
    def _ensure_db(cls):
        if cls._meta.database is None or cls._meta.database.is_closed():
            AcpRuntime.init_db()

    @classmethod
    def init_db(cls, db_path=None):
        path = Path(db_path if db_path else (DB_DIR / "acp_data.db")).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        database = SqliteDatabase(str(path), pragmas={"journal_mode": "wal", "foreign_keys": "on"})
        database.connect()
        for model in [AcpRuntime, AcpConversation, AcpTask]:
            model._meta.database = database
        database.create_tables([AcpRuntime, AcpConversation, AcpTask], safe=True)

    @classmethod
    def close_db(cls):
        if not cls._meta.database.is_closed():
            cls._meta.database.close()


class AcpRuntime(_BaseModel):
    runtime_id = CharField(primary_key=True, max_length=16)
    adapter = CharField(max_length=32, default="opencode")
    endpoint = CharField(max_length=128)
    pid = IntegerField(null=True)
    managed = BooleanField(default=True)
    status = CharField(max_length=16, default="starting")
    version = CharField(max_length=32, null=True)
    capabilities = CharField(max_length=4096, null=True)
    created_at = CharField(max_length=30)
    last_health_check = CharField(max_length=30, null=True)

    class Meta:
        table_name = "acp_runtimes"

    @classmethod
    def get_ready_managed(cls):
        cls._ensure_db()
        return list(cls.select().where((cls.status == "ready") & cls.managed).dicts())

    @classmethod
    def get_by_endpoint(cls, endpoint):
        cls._ensure_db()
        return cls.get_or_none((cls.endpoint == endpoint) & (cls.status != "stopped"))

    @classmethod
    def create_runtime(cls, runtime_id, adapter, endpoint, pid=None, managed=True, version=None):
        cls._ensure_db()
        cls.create(
            runtime_id=runtime_id,
            adapter=adapter,
            endpoint=endpoint,
            pid=pid,
            managed=managed,
            status="starting",
            version=version,
            created_at=_now(),
            last_health_check=_now(),
        )

    @classmethod
    def mark_ready(cls, runtime_id, version=None):
        cls._ensure_db()
        updates = {"status": "ready", "last_health_check": _now()}
        if version:
            updates["version"] = version
        cls.update(**updates).where(cls.runtime_id == runtime_id).execute()

    @classmethod
    def mark_stale(cls, runtime_id):
        cls._ensure_db()
        cls.update(status="stale").where(cls.runtime_id == runtime_id).execute()

    @classmethod
    def mark_stopped(cls, runtime_id):
        cls._ensure_db()
        cls.update(status="stopped", pid=None).where(cls.runtime_id == runtime_id).execute()

    @classmethod
    def count_managed_ready(cls):
        cls._ensure_db()
        return cls.select().where((cls.status == "ready") & cls.managed).count()


class AcpConversation(_BaseModel):
    conversation_id = CharField(primary_key=True, max_length=64)
    runtime_id = CharField(max_length=16, null=True)
    upstream_session_id = CharField(max_length=64, null=True)
    workspace = CharField(max_length=512, null=True)
    model = CharField(max_length=128, null=True)
    created_at = CharField(max_length=30)
    last_used_at = CharField(max_length=30)

    class Meta:
        table_name = "acp_conversations"

    @classmethod
    def get_or_create_for_runtime(cls, conversation_id, runtime_id, workspace, model):
        cls._ensure_db()
        row = cls.get_or_none(cls.conversation_id == conversation_id)
        now = _now()
        if row:
            cls.update(runtime_id=runtime_id, last_used_at=now, model=model or row.model).where(cls.conversation_id == conversation_id).execute()
            return row
        cls.create(
            conversation_id=conversation_id,
            runtime_id=runtime_id,
            workspace=workspace or "",
            model=model or "",
            created_at=now,
            last_used_at=now,
        )
        return cls.get_or_none(cls.conversation_id == conversation_id)

    @classmethod
    def get_by_conversation_id(cls, conversation_id):
        cls._ensure_db()
        return cls.get_or_none(cls.conversation_id == conversation_id)

    @classmethod
    def update_upstream_session(cls, conversation_id, upstream_session_id):
        cls._ensure_db()
        cls.update(upstream_session_id=upstream_session_id, last_used_at=_now()).where(cls.conversation_id == conversation_id).execute()


class AcpTask(_BaseModel):
    task_id = CharField(primary_key=True, max_length=16)
    conversation_id = CharField(max_length=64, null=True, index=True)
    prompt = CharField(max_length=4096)
    model = CharField(max_length=128, null=True)
    timeout = IntegerField(default=300)
    status = CharField(max_length=16, default="queued")
    result = CharField(max_length=1048576, null=True)
    error = CharField(max_length=1024, null=True)
    error_code = CharField(max_length=64, null=True)
    created_at = CharField(max_length=30)
    completed_at = CharField(max_length=30, null=True)
    deadline = CharField(max_length=30, null=True)
    lease_until = CharField(max_length=30, null=True)

    class Meta:
        table_name = "acp_tasks"

    @classmethod
    def create_task(cls, task_id, conversation_id, prompt, model, timeout):
        now = _now()
        deadline = (datetime.now(timezone.utc) + timedelta(seconds=timeout)).isoformat()
        cls._ensure_db()
        cls.create(
            task_id=task_id,
            conversation_id=conversation_id,
            prompt=prompt,
            model=model or "",
            timeout=timeout,
            status="running",
            created_at=now,
            deadline=deadline,
        )

    @classmethod
    def mark_completed(cls, task_id, result_json):
        cls._ensure_db()
        if len(result_json) > 1048576:
            result_json = result_json[:1048576]
        cls.update(status="completed", result=result_json, completed_at=_now()).where(cls.task_id == task_id).execute()

    @classmethod
    def mark_failed(cls, task_id, error_msg, error_code=None):
        cls._ensure_db()
        cls.update(
            status="failed",
            error=error_msg[:1024],
            error_code=error_code,
            completed_at=_now(),
        ).where(cls.task_id == task_id).execute()

    @classmethod
    def mark_cancelled(cls, task_id):
        cls._ensure_db()
        cls.update(status="cancelled", completed_at=_now()).where(cls.task_id == task_id).execute()

    @classmethod
    def get_by_task_id(cls, task_id):
        cls._ensure_db()
        return cls.get_or_none(cls.task_id == task_id)

    @classmethod
    def count_running(cls):
        cls._ensure_db()
        return cls.select().where(cls.status == "running").count()

    @classmethod
    def get_running_tasks(cls):
        cls._ensure_db()
        return list(cls.select().where(cls.status == "running").dicts())

    @classmethod
    def fail_tasks_for_runtime(cls, runtime_id):
        cls._ensure_db()
        tasks = list(cls.select(cls.task_id).join(AcpConversation, on=(cls.conversation_id == AcpConversation.conversation_id)).where((AcpConversation.runtime_id == runtime_id) & (cls.status == "running")))
        for t in tasks:
            cls.mark_failed(t.task_id, "Runtime lost", "runtime_lost")

    @classmethod
    def cleanup_old(cls, max_age_hours=24):
        cls._ensure_db()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        cls.delete().where((cls.status != "running") & (cls.completed_at.is_null(False)) & (cls.completed_at < cutoff)).execute()

    @classmethod
    def reconcile_on_startup(cls):
        cls._ensure_db()
        now = datetime.now(timezone.utc)
        for t in cls.get_running_tasks():
            deadline = t.get("deadline")
            if deadline and datetime.fromisoformat(deadline) < now:
                cls.mark_failed(t["task_id"], "Task timed out", "task_timeout")
