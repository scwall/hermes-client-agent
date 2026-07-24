"""OpenCode adapter implementation."""

import logging
import os
import shutil
import subprocess
import time
from typing import Optional

import httpx

_log = logging.getLogger("hermes-agent")

PROVIDER_MAP = {
    "deepseek": "deepseek",
    "deepseek-chat": "deepseek",
    "deepseek-coder": "deepseek",
    "deepseek-reasoner": "deepseek",
    "deepseek-v4": "deepseek",
    "claude": "anthropic",
    "claude-sonnet": "anthropic",
    "claude-opus": "anthropic",
    "claude-sonnet-4": "anthropic",
    "claude-opus-4": "anthropic",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "gpt-5": "openai",
    "gemini": "google",
}


def _infer_provider(model_id: str) -> str:
    if not model_id:
        return ""
    for key, provider in PROVIDER_MAP.items():
        if key in model_id.lower():
            return provider
    return ""


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

    def send_message(self, endpoint: str, session_id: str, prompt: str, model: str, timeout: int) -> dict:
        base = endpoint.rstrip("/")
        body: dict = {"parts": [{"type": "text", "text": prompt}]}
        if model:
            provider = _infer_provider(model)
            body["model"] = {"providerID": provider, "modelID": model}
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
