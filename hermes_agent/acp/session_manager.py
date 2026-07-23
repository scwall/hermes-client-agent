"""ACP session manager — launch, monitor, and cleanup ACP agent processes."""
import logging
import os
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from hermes_agent.acp.models import AcpSession

_log = logging.getLogger("hermes-agent")

DEFAULT_ACP_PORT = 4444
MAX_PORT_ATTEMPTS = 5
HEALTH_CHECK_TIMEOUT = 15
HEARTBEAT_INTERVAL = 30
SESSION_INACTIVE_TIMEOUT = 3600


def _find_opencode_binary():
    path = shutil.which("opencode")
    if path:
        return path
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".npm-global", "bin", "opencode"),
        os.path.join(home, ".local", "bin", "opencode"),
        "/usr/local/bin/opencode",
        "/usr/bin/opencode",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def _is_port_available(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _find_available_port(start, max_attempts):
    for offset in range(max_attempts):
        port = start + offset
        if _is_port_available(port):
            return port
    return None


class SessionManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._heartbeat_thread = None
        self._heartbeat_stop = threading.Event()
        self._opencode_binary = _find_opencode_binary()
        AcpSession.init_db()
        if self._opencode_binary:
            _log.info("ACP session manager: opencode binary found at %s", self._opencode_binary)
        else:
            _log.warning("ACP session manager: opencode binary NOT found — spawn disabled")

    def _cleanup_zombies(self):
        active = AcpSession.get_active_sessions()
        zombie_pids = []
        for s in active:
            pid = s.get("pid")
            if pid and not self._is_pid_alive(pid):
                _log.warning("ACP session %s (PID %s) is dead — marking as zombie", s["session_id"], pid)
                zombie_pids.append(pid)
        if zombie_pids:
            AcpSession.mark_zombies_stopped(zombie_pids)

    def _is_pid_alive(self, pid):
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def spawn(self, agent_url=None, agent_type="opencode"):
        with self._lock:
            if not self._opencode_binary:
                raise RuntimeError("OpenCode binary not found on this system")

            existing = AcpSession.get_active_sessions()
            if existing:
                s = existing[0]
                _log.info("Reusing existing ACP session %s on port %s", s["session_id"], s["port"])
                return {
                    "session_id": s["session_id"],
                    "port": s["port"],
                    "pid": s["pid"],
                    "status": "reused",
                    "created_at": s["created_at"],
                }

            self._cleanup_zombies()

            port = _find_available_port(DEFAULT_ACP_PORT, MAX_PORT_ATTEMPTS)
            if port is None:
                ports_range = f"{DEFAULT_ACP_PORT}-{DEFAULT_ACP_PORT + MAX_PORT_ATTEMPTS - 1}"
                raise RuntimeError(f"No available port in range {ports_range}")

            _log.info("Launching OpenCode on port %s", port)
            try:
                proc = subprocess.Popen(
                    [self._opencode_binary, "serve", "--port", str(port), "--hostname", "127.0.0.1"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except FileNotFoundError:
                raise RuntimeError(f"OpenCode binary not found at {self._opencode_binary}")
            except Exception as e:
                raise RuntimeError(f"Failed to launch OpenCode: {e}")

            health_ok = self._wait_for_health(port, HEALTH_CHECK_TIMEOUT)
            if not health_ok:
                try:
                    os.kill(proc.pid, signal.SIGTERM)
                except Exception:
                    pass
                raise RuntimeError(f"OpenCode failed health check on port {port} within {HEALTH_CHECK_TIMEOUT}s")

            session_id = f"acp-{uuid4().hex[:12]}"
            AcpSession.create_session(
                session_id=session_id,
                pid=proc.pid,
                port=port,
                agent_type=agent_type,
            )
            _log.info("ACP session %s started — PID %s, port %s", session_id, proc.pid, port)
            return {
                "session_id": session_id,
                "port": port,
                "pid": proc.pid,
                "status": "created",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

    def _wait_for_health(self, port, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                resp = httpx.get(f"http://127.0.0.1:{port}/global/health", timeout=2)
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def stop(self, session_id):
        with self._lock:
            session = AcpSession.get_by_session_id(session_id)
            if not session:
                raise LookupError(f"Session {session_id} not found")
            pid = session.pid
            if pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                    try:
                        os.waitpid(pid, os.WNOHANG)
                    except ChildProcessError:
                        pass
                except OSError:
                    pass
            AcpSession.mark_stopped(session_id)
            _log.info("ACP session %s stopped (PID %s)", session_id, pid)
            return {"session_id": session_id, "status": "stopped"}

    def get_or_create_for_localhost(self, agent_url):
        with self._lock:
            parsed = urlparse(agent_url.rstrip("/"))
            port = parsed.port or 4444

            existing = AcpSession.get_active_on_port(port)
            if existing:
                AcpSession.increment_exchange(existing.session_id)
                return existing.session_id

            return None

    def list_sessions(self):
        return AcpSession.get_active_sessions()

    def get_session(self, session_id):
        return AcpSession.get_by_session_id(session_id)

    def start_heartbeat(self):
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="acp-heartbeat")
        self._heartbeat_thread.start()
        _log.info("ACP heartbeat started (interval=%ss)", HEARTBEAT_INTERVAL)

    def stop_heartbeat(self):
        self._heartbeat_stop.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)
        _log.info("ACP heartbeat stopped")

    def _heartbeat_loop(self):
        while not self._heartbeat_stop.wait(HEARTBEAT_INTERVAL):
            try:
                self._run_heartbeat()
            except Exception:
                _log.exception("ACP heartbeat error")

    def _run_heartbeat(self):
        active = AcpSession.get_active_sessions()
        now = datetime.now(timezone.utc)
        zombie_pids = []
        inactive_sessions = []

        for s in active:
            pid = s.get("pid")
            if pid and not self._is_pid_alive(pid):
                zombie_pids.append(pid)
                continue
            last_hb = s.get("last_heartbeat")
            if last_hb:
                try:
                    age = (now - datetime.fromisoformat(last_hb)).total_seconds()
                    if age > SESSION_INACTIVE_TIMEOUT:
                        inactive_sessions.append(s["session_id"])
                except (ValueError, TypeError):
                    pass
            AcpSession.update_heartbeat(s["session_id"])

        if zombie_pids:
            AcpSession.mark_zombies_stopped(zombie_pids)
        for sid in inactive_sessions:
            _log.info("ACP session %s inactive for >%ss — cleaning up", sid, SESSION_INACTIVE_TIMEOUT)
            try:
                self.stop(sid)
            except Exception:
                pass

    def cleanup(self):
        active = AcpSession.get_active_sessions()
        for s in active:
            pid = s.get("pid")
            if pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
            AcpSession.mark_stopped(s["session_id"])
        _log.info("ACP cleanup complete — %s session(s) stopped", len(active))

    def shutdown(self):
        self.stop_heartbeat()
        self.cleanup()
        AcpSession.close_db()


_session_manager = None


def get_session_manager():
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
