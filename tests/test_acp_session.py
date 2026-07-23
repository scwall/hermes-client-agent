"""Tests for ACP runtime broker and models."""
import os
import tempfile
from unittest import mock

from fastapi.testclient import TestClient

from hermes_agent.acp.models import AcpRuntime, AcpConversation, AcpTask
from hermes_agent.app import app
from hermes_agent.config import TOKEN

client = TestClient(app)
AUTH = {"X-Agent-Token": TOKEN}


class TestAcpModels:
    @classmethod
    def setup_class(cls):
        cls._tmpdir = tempfile.mkdtemp()
        cls._db_path = os.path.join(cls._tmpdir, "test.db")
        AcpRuntime.init_db(cls._db_path)

    @classmethod
    def teardown_class(cls):
        AcpRuntime.close_db()
        import shutil
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def test_create_runtime(self):
        AcpRuntime.create_runtime("tst", "opencode", "http://127.0.0.1:4444", pid=1234)
        r = AcpRuntime.get_or_none(AcpRuntime.runtime_id == "tst")
        assert r is not None
        assert r.status == "starting"

    def test_mark_ready(self):
        AcpRuntime.mark_ready("tst", "1.0")
        r = AcpRuntime.get_or_none(AcpRuntime.runtime_id == "tst")
        assert r.status == "ready"
        assert r.version == "1.0"

    def test_create_task(self):
        AcpTask.create_task("t_abc", None, "test", "", 300)
        t = AcpTask.get_by_task_id("t_abc")
        assert t is not None
        assert t.status == "running"

    def test_mark_completed(self):
        AcpTask.mark_completed("t_abc", '{"ok":true}')
        t = AcpTask.get_by_task_id("t_abc")
        assert t.status == "completed"

    def test_count_running(self):
        count = AcpTask.count_running()
        assert count == 0


class TestAcpEndpoints:
    def test_sessions_list(self):
        resp = client.get("/acp/sessions", headers=AUTH)
        assert resp.status_code == 200

    def test_diagnostics(self):
        resp = client.get("/acp/diagnostics", headers=AUTH)
        assert resp.status_code == 200

    def test_diagnostics_unauthorized(self):
        resp = client.get("/acp/diagnostics")
        assert resp.status_code in (401, 422)
