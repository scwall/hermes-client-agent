"""Unit tests for the system tray module."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hermes_agent.tray import TrayState, _build_image, _generate_icon, _get_icon_path


class TestTrayState:
    """Tests for the TrayState class."""

    def test_initial_state_is_green(self):
        state = TrayState()
        assert state.status == TrayState.GREEN

    def test_status_change(self):
        state = TrayState()
        state.status = TrayState.RED
        assert state.status == TrayState.RED

    def test_tooltip_contains_counts(self):
        state = TrayState()
        state.request_count = 45
        state.error_count = 0
        tooltip = state.tooltip
        assert "45" in tooltip
        assert "0 errors" in tooltip

    def test_uptime_start_none_by_default(self):
        state = TrayState()
        assert state.uptime_start is None


class TestIconGeneration:
    """Tests for the icon generation function."""

    def test_generate_icon_returns_image(self):
        try:
            from PIL import Image as _Image  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")
        img = _generate_icon("green")
        assert img is not None
        assert img.size == (64, 64)

    def test_generate_icon_colors(self):
        try:
            from PIL import Image as _Image  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")
        green_img = _generate_icon("green")
        yellow_img = _generate_icon("yellow")
        red_img = _generate_icon("red")
        assert green_img is not None
        assert yellow_img is not None
        assert red_img is not None

    def test_get_icon_path_returns_none_when_no_icon(self):
        with patch.object(Path, "exists", return_value=False):
            result = _get_icon_path()
            assert result is None

    def test_build_image_falls_back_to_generated(self):
        with patch("hermes_agent.tray._get_icon_path", return_value=None):
            try:
                img = _build_image("green")
                assert img is not None
                assert img.size == (64, 64)
            except ImportError:
                pytest.skip("Pillow not installed")


class TestTrayStartup:
    """Tests for tray startup/shutdown behavior."""

    def test_start_tray_without_pystray(self):
        with patch("hermes_agent.tray.pystray", None):
            from hermes_agent.tray import start_tray
            result = start_tray()
            assert result is None

    def test_start_tray_already_running(self):
        if "pystray" not in sys.modules:
            pytest.skip("pystray not installed")
        with patch("hermes_agent.tray._is_tray_running", True):
            with patch("hermes_agent.tray._tray_thread", MagicMock()):
                from hermes_agent.tray import start_tray
                result = start_tray()
                assert result is not None
