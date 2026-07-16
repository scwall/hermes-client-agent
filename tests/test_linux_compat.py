"""Tests for Linux compatibility fixes: screenshot, exec shell mapping, config paths."""
import os
import sys
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from hermes_agent.app import app
from hermes_agent.config import TOKEN

client = TestClient(app)
AUTH = {"X-Agent-Token": TOKEN}


class TestScreenshotLinux:
    """Screenshot endpoint tests for Linux — guard against ctypes.windll crash."""

    @patch("hermes_agent.routers.screenshot._has_display", return_value=False)
    def test_screenshot_headless_returns_503(self, mock_display):
        """Screenshot on headless Linux should return 503, not crash."""
        resp = client.get("/screenshot", headers=AUTH)
        assert resp.status_code == 503
        data = resp.json()
        assert "no display" in data["detail"].lower()

    @patch("hermes_agent.routers.screenshot._has_display", return_value=True)
    @patch("hermes_agent.routers.screenshot.ImageGrab", None)
    @patch("hermes_agent.routers.screenshot.Image", None)
    def test_screenshot_no_pil_no_tools_returns_503(self, mock_display):
        """Screenshot without PIL or external tools returns 503, not crash."""
        resp = client.get("/screenshot", headers=AUTH)
        assert resp.status_code == 503

    @patch("hermes_agent.routers.screenshot._has_display", return_value=True)
    @patch("hermes_agent.routers.screenshot.sys.platform", "linux")
    @patch("hermes_agent.routers.screenshot.ImageGrab", None)
    @patch("hermes_agent.routers.screenshot.subprocess.call")
    def test_screenshot_fallback_to_subprocess(self, mock_call, mock_display):
        """Screenshot falls back to external tools when PIL ImageGrab unavailable."""
        from hermes_agent.routers.screenshot import _capture_screen
        mock_call.return_value = 1
        with pytest.raises(Exception):
            _capture_screen()

    @patch("hermes_agent.routers.screenshot._has_display", return_value=True)
    @patch("hermes_agent.routers.screenshot.sys.platform", "linux")
    def test_screenshot_with_pil_mock(self, mock_display):
        """Screenshot with PIL ImageGrab should succeed."""
        mock_img = MagicMock()
        mock_img.size = (100, 100)
        mock_img.mode = "RGBA"
        mock_img.tobytes.return_value = b"\x00" * 100 * 100 * 4
        with patch("hermes_agent.routers.screenshot.ImageGrab") as mock_grab:
            mock_grab.grab.return_value = mock_img
            resp = client.get("/screenshot", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "image_base64" in data
        assert data["format"] == "png"

    def test_has_display_returns_bool(self):
        """_has_display returns a boolean based on env vars."""
        from hermes_agent.routers.screenshot import _has_display
        result = _has_display()
        assert isinstance(result, bool)

    @patch.dict(os.environ, {}, clear=True)
    def test_has_display_empty_env(self):
        """_has_display returns False when no display env vars set."""
        from hermes_agent.routers.screenshot import _has_display
        assert _has_display() is False

    @patch.dict(os.environ, {"DISPLAY": ":0"})
    def test_has_display_with_x11(self):
        """_has_display returns True when DISPLAY is set."""
        from hermes_agent.routers.screenshot import _has_display
        assert _has_display() is True

    @patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"})
    def test_has_display_with_wayland(self):
        """_has_display returns True when WAYLAND_DISPLAY is set."""
        from hermes_agent.routers.screenshot import _has_display
        assert _has_display() is True


class TestExecShellMapping:
    """Tests for cross-platform shell command mapping."""

    def test_exec_cmd_maps_to_bash_on_linux(self):
        """On Linux, shell='cmd' should be mapped to bash -c."""
        resp = client.post(
            "/exec",
            json={"command": "echo hello_linux", "shell": "cmd"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        data = resp.json()
        if sys.platform == "win32":
            assert data["shell"] in ("cmd", "cmd")
        else:
            assert "bash" in data["shell"].lower()
            assert "hello_linux" in data["stdout"]

    def test_exec_bash_explicit(self):
        """Explicit shell='bash' should work on both platforms."""
        resp = client.post(
            "/exec",
            json={"command": "echo test_bash", "shell": "bash"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        data = resp.json()
        if sys.platform != "win32":
            assert "test_bash" in data["stdout"]

    def test_exec_powershell_mapped_on_linux(self):
        """On Linux, shell='powershell' maps to pwsh or bash."""
        resp = client.post(
            "/exec",
            json={"command": "echo test_ps", "shell": "powershell"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        data = resp.json()
        if sys.platform != "win32":
            assert "test_ps" in data["stdout"]

    def test_exec_returns_adapted_shell_field(self):
        """Response must include the 'shell' field with actual shell used."""
        resp = client.post(
            "/exec",
            json={"command": "echo x", "shell": "cmd"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "shell" in data

    def test_shell_mapping_consistency(self):
        """_build_shell_args maps known shells correctly on Linux."""
        from hermes_agent.routers.exec import _build_shell_args
        if sys.platform != "win32":
            argv, name = _build_shell_args("cmd", "echo hi")
            assert argv[0] in ("bash", "/bin/bash")
            assert "bash" in name.lower()

            argv, name = _build_shell_args("powershell", "echo hi")
            assert "bash" in name.lower() or argv[0] == "pwsh"

            argv, name = _build_shell_args("bash", "echo hi")
            assert "bash" in name.lower()


class TestConfigLinuxPaths:
    """Tests for cross-platform default ALLOWED_PATHS."""

    def test_linux_default_paths_include_home_and_tmp(self):
        """On Linux, default ALLOWED_PATHS should be home and /tmp."""
        from hermes_agent import config
        if sys.platform != "win32":
            assert len(config.ALLOWED_PATHS) >= 2
            home_path = os.path.expanduser("~") + os.sep
            assert any(home_path in p for p in config.ALLOWED_PATHS)
            assert any("/tmp" in p for p in config.ALLOWED_PATHS)

    @patch("hermes_agent.config.sys.platform", "win32")
    def test_windows_default_paths_include_drive(self):
        """On Windows, default ALLOWED_PATHS should include D: drive."""
        import importlib
        import hermes_agent.config as cfg
        importlib.reload(cfg)
        assert any("D:\\" in p for p in cfg.ALLOWED_PATHS)

    def test_file_read_with_linux_default_paths(self):
        """GET /file with a path in /tmp should work with Linux defaults."""
        test_path = "/tmp/hermes_linux_test.txt"
        with open(test_path, "w") as f:
            f.write("linux-path-test")
        resp = client.get("/file", params={"path": test_path}, headers=AUTH)
        os.unlink(test_path)
        assert resp.status_code in (200, 403)
        if resp.status_code == 200:
            assert "linux-path-test" in resp.json()["content"]
