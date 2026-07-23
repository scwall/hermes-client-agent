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

    class Meta:
        table_name = "acp_sessions"

    @classmethod
    def init_db(cls, db_path=None):
        path = Path(db_path if db_path else (DB_DIR / "acp_sessions.db")).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        cls._meta.database = SqliteDatabase(str(path), pragmas={"journal_mode": "wal", "foreign_keys": "on"})
        cls._meta.database.connect()
        cls._meta.database.create_tables([cls], safe=True)

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
        return (
            cls.update(status="stopped", stopped_at=datetime.now(timezone.utc).isoformat(), pid=None)
            .where(cls.pid.in_(zombie_pids))
            .execute()
        )

    @classmethod
    def count_active(cls):
        cls._ensure_db()
        return cls.select().where(cls.status == "active").count()
