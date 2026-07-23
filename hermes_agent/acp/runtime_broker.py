"""Runtime broker — acquire, spawn, health-check OpenCode instances."""

import logging
import os
import signal
import socket
import threading

from hermes_agent.acp.adapter_opencode import OpenCodeAdapter
from hermes_agent.acp.models import AcpRuntime

_log = logging.getLogger("hermes-agent")

DEFAULT_PORT = 4444
MAX_MANAGED = 5
HEALTH_TIMEOUT = 15


def _is_port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _find_port(start, max_attempts=5):
    for offset in range(max_attempts):
        port = start + offset
        if _is_port_available(port):
            return port
    return None


class RuntimeBroker:
    def __init__(self):
        self._lock = threading.Lock()
        self._adapter = OpenCodeAdapter()

    def acquire(self, conversation_id=None) -> dict:
        with self._lock:
            existing = AcpRuntime.get_ready_managed()
            for r in existing:
                endpoint = r["endpoint"]
                if self._adapter.health_check(endpoint):
                    return r

            if AcpRuntime.count_managed_ready() >= MAX_MANAGED:
                raise RuntimeError(f"Maximum managed runtimes ({MAX_MANAGED}) reached")

            port = _find_port(DEFAULT_PORT)
            if port is None:
                raise RuntimeError(f"No available port in range {DEFAULT_PORT}-{DEFAULT_PORT + 4}")

            pid = self._adapter.spawn(port)
            endpoint = f"http://127.0.0.1:{port}"

            import secrets

            runtime_id = "r_" + secrets.token_hex(6)
            AcpRuntime.create_runtime(runtime_id, "opencode", endpoint, pid=pid, managed=True)

            if not self._adapter.wait_ready(endpoint, HEALTH_TIMEOUT):
                AcpRuntime.mark_stale(runtime_id)
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
                raise RuntimeError(f"OpenCode failed health check on port {port}")

            version = self._adapter.get_version(endpoint)
            AcpRuntime.mark_ready(runtime_id, version)

            runtime = AcpRuntime.get_by_endpoint(endpoint)
            return {
                "runtime_id": runtime.runtime_id,
                "endpoint": runtime.endpoint,
                "adapter": runtime.adapter,
                "managed": runtime.managed,
            }

    def stop_runtime(self, runtime_id):
        runtime = AcpRuntime.get_or_none(AcpRuntime.runtime_id == runtime_id)
        if not runtime:
            return
        if runtime.pid:
            try:
                os.kill(runtime.pid, signal.SIGTERM)
            except OSError:
                pass
        AcpRuntime.mark_stopped(runtime_id)

    def get_adapter(self):
        return self._adapter

    def cleanup_zombies(self):
        runtimes = AcpRuntime.get_ready_managed()
        for r in runtimes:
            endpoint = r["endpoint"]
            if not self._adapter.health_check(endpoint):
                _log.warning("Runtime %s is stale (health check failed)", r["runtime_id"])
                AcpRuntime.mark_stale(r["runtime_id"])


_runtime_broker = None


def get_runtime_broker():
    global _runtime_broker
    if _runtime_broker is None:
        _runtime_broker = RuntimeBroker()
    return _runtime_broker
