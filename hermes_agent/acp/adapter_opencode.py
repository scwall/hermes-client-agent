"""OpenCode adapter implementation."""

import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

_log = logging.getLogger("hermes-agent")


class OpenCodeAdapter:
    name = "opencode"

    def detect_binary(self) -> Optional[str]:
        path = shutil.which("opencode")
        if path:
            return path
        home = os.path.expanduser("~")
        for c in [
            os.path.join(home, ".npm-global", "bin", "opencode"),
            os.path.join(home, ".local", "bin", "opencode"),
            "/usr/local/bin/opencode",
            "/usr/bin/opencode",
        ]:
            if os.path.isfile(c):
                return c
        return None

    def spawn(self, port: int) -> int:
        binary = self.detect_binary()
        if not binary:
            raise RuntimeError("OpenCode binary not found")
        proc = subprocess.Popen(
            [binary, "serve", "--port", str(port), "--hostname", "127.0.0.1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return proc.pid

    def health_check(self, endpoint: str) -> bool:
        try:
            resp = httpx.get(f"{endpoint.rstrip('/')}/global/health", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def get_version(self, endpoint: str) -> Optional[str]:
        try:
            resp = httpx.get(f"{endpoint.rstrip('/')}/global/health", timeout=3)
            if resp.status_code == 200:
                return resp.json().get("version")
        except Exception:
            pass
        return None

    def create_session(self, endpoint: str) -> dict:
        base = endpoint.rstrip("/")
        resp = httpx.post(f"{base}/session", json={}, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _get_cached_providers(self, endpoint: str) -> dict[str, str]:
        from hermes_agent.acp.models import AcpRuntime

        runtime = AcpRuntime.get_by_endpoint(endpoint)
        if runtime and runtime.capabilities:
            try:
                data = json.loads(runtime.capabilities)
                providers = data.get("providers", {})
                if providers:
                    return providers
            except (json.JSONDecodeError, TypeError):
                pass

        providers = self.get_providers(endpoint)
        if providers and runtime:
            cache_data = json.dumps({"providers": providers, "fetched_at": datetime.now(timezone.utc).isoformat()})
            AcpRuntime.update(capabilities=cache_data).where(AcpRuntime.runtime_id == runtime.runtime_id).execute()
        return providers

    def get_providers(self, endpoint: str) -> dict[str, str]:
        base = endpoint.rstrip("/")
        providers: dict[str, str] = {}

        try:
            resp = httpx.get(f"{base}/config/providers", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                raw_providers = data.get("providers", []) if isinstance(data, dict) else []
                for p in raw_providers:
                    pid = p.get("id", "")
                    provider_models = p.get("models", {}) if isinstance(p, dict) else {}
                    if isinstance(provider_models, dict):
                        for mid in provider_models:
                            providers[mid] = pid
                if providers:
                    _log.info("Discovered %d provider mappings from /config/providers on %s", len(providers), base)
                    return providers
        except Exception:
            pass

        try:
            resp = httpx.get(f"{base}/config", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                default_model = data.get("model", "")
                if default_model and "/" in default_model:
                    provider, model_id = default_model.split("/", 1)
                    providers[model_id] = provider
                    _log.info("Fallback: inferred %s -> %s from /config", model_id, provider)
        except Exception:
            pass

        return providers

    def send_message(self, endpoint: str, session_id: str, prompt: str, model: str, timeout: int) -> dict:
        base = endpoint.rstrip("/")
        body: dict = {"parts": [{"type": "text", "text": prompt}]}
        if model:
            if "/" in model:
                provider, actual_model = model.split("/", 1)
            else:
                providers = self._get_cached_providers(endpoint)
                provider = providers.get(model, "")
                actual_model = model
            body["model"] = {"providerID": provider, "modelID": actual_model}
        resp = httpx.post(
            f"{base}/session/{session_id}/message",
            json=body,
            timeout=httpx.Timeout(timeout),
        )
        resp.raise_for_status()
        return resp.json()

    def cancel(self, endpoint: str, session_id: str) -> None:
        base = endpoint.rstrip("/")
        try:
            httpx.post(f"{base}/session/{session_id}/abort", json={}, timeout=10)
        except Exception:
            _log.warning("Failed to abort session %s on %s", session_id, endpoint)

    def get_default_port(self) -> int:
        return 4444

    def wait_ready(self, endpoint: str, timeout: int = 15) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.health_check(endpoint):
                return True
            time.sleep(1)
        return False
