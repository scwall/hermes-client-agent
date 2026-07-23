"""Peewee model for ACP agent sessions."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from peewee import CharField, IntegerField, Model, SqliteDatabase

DB_DIR = Path("acp_data")
_db = SqliteDatabase(None)


class AcpSession(Model):
    id = CharField(primary_key=True, max_length=36)
    session_id = CharField(max_length=64, unique=True, index=True)
    agent_type = CharField(max_length=32, default="opencode")
    pid = IntegerField(null=True)
    port = IntegerField()
    status = CharField(max_length=16, default="active")
    created_at = CharField(max_length=30)
    last_heartbeat = CharField(max_length=30, null=True)
    exchange_count = IntegerField(default=0)
    stopped_at = CharField(max_length=30, null=True)
    opencode_session_id = CharField(max_length=64, null=True)
    opencode_directory = CharField(max_length=512, null=True)

    class Meta:
        table_name = "acp_sessions"

    @classmethod
    def init_db(cls, db_path=None):
        path = Path(db_path if db_path else (DB_DIR / "acp_sessions.db")).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        database = SqliteDatabase(str(path), pragmas={"journal_mode": "wal", "foreign_keys": "on"})
        database.connect()
        cls._meta.database = database
        AcpTask._meta.database = database
        database.create_tables([cls, AcpTask], safe=True)
        cls._migrate_schema()

    @classmethod
    def close_db(cls):
        if not cls._meta.database.is_closed():
            cls._meta.database.close()

    @classmethod
    def _ensure_db(cls):
        if cls._meta.database is None or cls._meta.database.is_closed():
            cls.init_db()

    @classmethod
    def create_session(cls, session_id, pid, port, agent_type="opencode"):
        cls._ensure_db()
        entry_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        cls.create(
            id=entry_id,
            session_id=session_id,
            agent_type=agent_type,
            pid=pid,
            port=port,
            status="active",
            created_at=now,
            last_heartbeat=now,
            exchange_count=0,
        )
        return entry_id

    @classmethod
    def update_heartbeat(cls, session_id):
        cls._ensure_db()
        now = datetime.now(timezone.utc).isoformat()
        cls.update(last_heartbeat=now).where(cls.session_id == session_id).execute()

    @classmethod
    def increment_exchange(cls, session_id):
        cls._ensure_db()
        row = cls.get_or_none(cls.session_id == session_id)
        if row:
            row.exchange_count += 1
            row.last_heartbeat = datetime.now(timezone.utc).isoformat()
            row.save()

    @classmethod
    def mark_stopped(cls, session_id):
        cls._ensure_db()
        cls.update(
            status="stopped",
            stopped_at=datetime.now(timezone.utc).isoformat(),
            pid=None,
        ).where(cls.session_id == session_id).execute()

    @classmethod
    def get_active_sessions(cls):
        cls._ensure_db()
        return list(cls.select().where(cls.status == "active").dicts())

    @classmethod
    def get_by_session_id(cls, session_id):
        cls._ensure_db()
        return cls.get_or_none(cls.session_id == session_id)

    @classmethod
    def get_active_on_port(cls, port):
        cls._ensure_db()
        return cls.get_or_none((cls.port == port) & (cls.status == "active"))

    @classmethod
    def delete_stopped(cls):
        cls._ensure_db()
        count = cls.delete().where(cls.status == "stopped").execute()
        return count

    @classmethod
    def mark_zombies_stopped(cls, zombie_pids):
        cls._ensure_db()
        if not zombie_pids:
            return 0
        return cls.update(status="stopped", stopped_at=datetime.now(timezone.utc).isoformat(), pid=None).where(cls.pid.in_(zombie_pids)).execute()

    @classmethod
    def count_active(cls):
        cls._ensure_db()
        return cls.select().where(cls.status == "active").count()

    @classmethod
    def _migrate_schema(cls):
        try:
            cls._meta.database.execute_sql("ALTER TABLE acp_sessions ADD COLUMN opencode_session_id TEXT")
        except Exception:
            pass
        try:
            cls._meta.database.execute_sql("ALTER TABLE acp_sessions ADD COLUMN opencode_directory TEXT")
        except Exception:
            pass

    @classmethod
    def update_opencode_session(cls, hermes_session_id, opencode_session_id, opencode_directory):
        cls._ensure_db()
        row = cls.get_or_none(cls.session_id == hermes_session_id)
        if row:
            row.opencode_session_id = opencode_session_id
            row.opencode_directory = opencode_directory
            row.save()


class AcpTask(Model):
    task_id = CharField(primary_key=True, max_length=16)
    session_id = CharField(max_length=64, null=True, index=True)
    prompt = CharField(max_length=4096)
    agent_url = CharField(max_length=512)
    timeout = IntegerField(default=300)
    model = CharField(max_length=128, null=True)
    context = CharField(max_length=4096, null=True)
    status = CharField(max_length=16, default="running")
    result = CharField(max_length=1048576, null=True)
    error = CharField(max_length=1024, null=True)
    created_at = CharField(max_length=30)
    completed_at = CharField(max_length=30, null=True)

    class Meta:
        table_name = "acp_tasks"

    @classmethod
    def _ensure_db(cls):
        if cls._meta.database is None or cls._meta.database.is_closed():
            AcpSession.init_db()

    @classmethod
    def create_task(cls, task_id, session_id, prompt, agent_url, timeout, model, context):
        now = datetime.now(timezone.utc).isoformat()
        cls._ensure_db()
        cls.create(
            task_id=task_id,
            session_id=session_id,
            prompt=prompt,
            agent_url=agent_url,
            timeout=timeout,
            model=model or "",
            context=context or "",
            status="running",
            created_at=now,
        )

    @classmethod
    def mark_completed(cls, task_id, result_json):
        cls._ensure_db()
        if len(result_json) > 1048576:
            result_json = result_json[:1048576]
        cls.update(
            status="completed",
            result=result_json,
            completed_at=datetime.now(timezone.utc).isoformat(),
        ).where(cls.task_id == task_id).execute()

    @classmethod
    def mark_failed(cls, task_id, error_msg):
        cls._ensure_db()
        cls.update(
            status="failed",
            error=error_msg[:1024],
            completed_at=datetime.now(timezone.utc).isoformat(),
        ).where(cls.task_id == task_id).execute()

    @classmethod
    def get_by_task_id(cls, task_id):
        cls._ensure_db()
        return cls.get_or_none(cls.task_id == task_id)

    @classmethod
    def count_running(cls):
        cls._ensure_db()
        return cls.select().where(cls.status == "running").count()

    @classmethod
    def fail_tasks_for_session(cls, session_id):
        cls._ensure_db()
        cls.update(
            status="failed",
            error="ACP session stopped",
            completed_at=datetime.now(timezone.utc).isoformat(),
        ).where((cls.session_id == session_id) & (cls.status == "running")).execute()

    @classmethod
    def cleanup_old(cls, max_age_hours=24):
        cls._ensure_db()
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        cls.delete().where((cls.status != "running") & (cls.completed_at.is_null(False)) & (cls.completed_at < cutoff)).execute()
