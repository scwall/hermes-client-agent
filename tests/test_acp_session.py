"""Tests for ACP session manager: model, manager, and endpoints."""
import os
import tempfile
from unittest import mock

from fastapi.testclient import TestClient

from hermes_agent.acp.models import AcpSession
from hermes_agent.acp.session_manager import SessionManager
from hermes_agent.app import app
from hermes_agent.config import TOKEN

client = TestClient(app)
AUTH = {"X-Agent-Token": TOKEN}


class TestAcpSessionModel:
    """Tests for the AcpSession Peewee model."""

    @classmethod
    def setup_class(cls):
        cls._tmpdir = tempfile.mkdtemp()
        cls._db_path = os.path.join(cls._tmpdir, "test_acp.db")
        AcpSession.init_db(cls._db_path)

    @classmethod
    def teardown_class(cls):
        AcpSession.close_db()
        for f in os.listdir(cls._tmpdir):
            os.unlink(os.path.join(cls._tmpdir, f))
        os.rmdir(cls._tmpdir)

    def setup_method(self):
        AcpSession.delete().execute()

    def test_create_session(self):
        AcpSession.create_session("test-s1", pid=12345, port=4444)
        sessions = AcpSession.get_active_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "test-s1"
        assert sessions[0]["port"] == 4444
        assert sessions[0]["pid"] == 12345
        assert sessions[0]["status"] == "active"

    def test_update_heartbeat(self):
        AcpSession.create_session("test-hb", pid=100, port=5555)
        AcpSession.update_heartbeat("test-hb")
        s = AcpSession.get_by_session_id("test-hb")
        assert s.last_heartbeat is not None

    def test_increment_exchange(self):
        AcpSession.create_session("test-ex", pid=200, port=6666)
        AcpSession.increment_exchange("test-ex")
        s = AcpSession.get_by_session_id("test-ex")
        assert s.exchange_count == 1
        AcpSession.increment_exchange("test-ex")
        s = AcpSession.get_by_session_id("test-ex")
        assert s.exchange_count == 2

    def test_mark_stopped(self):
        AcpSession.create_session("test-stop", pid=300, port=7777)
        AcpSession.mark_stopped("test-stop")
        sessions = AcpSession.get_active_sessions()
        assert len(sessions) == 0
        s = AcpSession.get_by_session_id("test-stop")
        assert s.status == "stopped"
        assert s.pid is None

    def test_get_active_on_port(self):
        AcpSession.create_session("test-port", pid=400, port=8888)
        s = AcpSession.get_active_on_port(8888)
        assert s is not None
        assert s.session_id == "test-port"
        s2 = AcpSession.get_active_on_port(9999)
        assert s2 is None

    def test_mark_zombies_stopped(self):
        AcpSession.create_session("z1", pid=10, port=4001)
        AcpSession.create_session("z2", pid=20, port=4002)
        AcpSession.mark_zombies_stopped([10, 20])
        assert AcpSession.count_active() == 0

    def test_count_active(self):
        assert AcpSession.count_active() == 0
        AcpSession.create_session("a1", pid=1, port=4101)
        AcpSession.create_session("a2", pid=2, port=4102)
        assert AcpSession.count_active() == 2
        AcpSession.mark_stopped("a1")
        assert AcpSession.count_active() == 1


class TestSessionManagerUnit:
    """Unit tests for SessionManager logic (no real subprocess)."""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "test_mgr.db")
        AcpSession.init_db(self._db_path)
        AcpSession.delete().execute()

    def teardown_method(self):
        AcpSession.close_db()
        for f in os.listdir(self._tmpdir):
            os.unlink(os.path.join(self._tmpdir, f))
        os.rmdir(self._tmpdir)

    def test_is_pid_alive_dead_pid(self):
        mgr = SessionManager.__new__(SessionManager)
        mgr._opencode_binary = "/usr/bin/opencode"
        assert mgr._is_pid_alive(99999999) is False

    def test_cleanup_zombies(self):
        AcpSession.create_session("z", pid=99999999, port=4999)
        mgr = SessionManager.__new__(SessionManager)
        mgr._opencode_binary = "/usr/bin/opencode"
        mgr._lock = mock.MagicMock()
        mgr._cleanup_zombies()
        assert AcpSession.count_active() == 0

    def test_get_or_create_for_localhost_no_session(self):
        mgr = SessionManager.__new__(SessionManager)
        mgr._lock = mock.MagicMock()
        sid = mgr.get_or_create_for_localhost("http://localhost:4096")
        assert sid is None

    def test_get_or_create_for_localhost_existing(self):
        AcpSession.create_session("existing", pid=100, port=4096)
        mgr = SessionManager.__new__(SessionManager)
        mgr._lock = mock.MagicMock()
        sid = mgr.get_or_create_for_localhost("http://localhost:4096")
        assert sid == "existing"

    def test_stop_session(self):
        AcpSession.create_session("s-stop", pid=99999999, port=5001)
        mgr = SessionManager.__new__(SessionManager)
        mgr._lock = mock.MagicMock()
        result = mgr.stop("s-stop")
        assert result["status"] == "stopped"
        assert AcpSession.count_active() == 0

    def test_stop_missing_session(self):
        mgr = SessionManager.__new__(SessionManager)
        mgr._lock = mock.MagicMock()
        import pytest
        with pytest.raises(LookupError):
            mgr.stop("nonexistent")

    def test_list_sessions(self):
        AcpSession.create_session("s1", pid=1, port=4001)
        AcpSession.create_session("s2", pid=2, port=4002)
        mgr = SessionManager.__new__(SessionManager)
        mgr._lock = mock.MagicMock()
        sessions = mgr.list_sessions()
        assert len(sessions) == 2

    def test_spawn_no_binary(self):
        mgr = SessionManager.__new__(SessionManager)
        mgr._lock = mock.MagicMock()
        mgr._opencode_binary = None
        import pytest
        with pytest.raises(RuntimeError, match="not found"):
            mgr.spawn()

    def test_spawn_existing_session(self):
        AcpSession.create_session("existing", pid=123, port=4444)
        mgr = SessionManager.__new__(SessionManager)
        mgr._lock = mock.MagicMock()
        mgr._opencode_binary = "/usr/bin/opencode"
        result = mgr.spawn()
        assert result["status"] == "reused"
        assert result["session_id"] == "existing"


class TestAcpSessionEndpoints:
    """Integration tests for ACP session REST endpoints."""

    def test_spawn_returns_503_when_no_binary(self):
        with mock.patch("hermes_agent.routers.acp.get_session_manager") as mock_mgr:
            mgr_instance = mock.MagicMock()
            mgr_instance.spawn.side_effect = RuntimeError("not found")
            mock_mgr.return_value = mgr_instance
            resp = client.post("/acp/spawn", headers=AUTH)
        assert resp.status_code == 503

    def test_list_sessions_empty(self):
        resp = client.get("/acp/sessions", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert "count" in data

    def test_list_sessions_requires_auth(self):
        resp = client.get("/acp/sessions")
        assert resp.status_code in (401, 422)

    def test_get_session_not_found(self):
        resp = client.get("/acp/sessions/nonexistent", headers=AUTH)
        assert resp.status_code == 404

    def test_delete_session_not_found(self):
        resp = client.delete("/acp/sessions/nonexistent", headers=AUTH)
        assert resp.status_code == 404

    def test_spawn_requires_auth(self):
        resp = client.post("/acp/spawn")
        assert resp.status_code in (401, 422)
