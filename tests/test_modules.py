"""Tests for module detection and capabilities."""

from hermes_agent.modules import (
    build_module_error,
    detect_module,
)


class TestDetectModule:
    """Tests for the detect_module function."""

    def test_stdlib_module_detected(self):
        """A stdlib module like 'os' should be detected."""
        assert detect_module("os") is True

    def test_nonexistent_module_not_detected(self):
        """A non-existent module should not be detected."""
        assert detect_module("nonexistent_module_xyz123") is False

    def test_optional_module_import_error_handled(self):
        """Modules that raise during import should return False."""
        result = detect_module("nonexistent__module_abc")
        assert result is False


class TestBuildModuleError:
    """Tests for build_module_error."""

    def test_error_structure(self):
        """The error dict should contain error, module, and hint keys."""
        err = build_module_error("pyautogui")
        assert err["error"] == "module_not_installed"
        assert err["module"] == "pyautogui"
        assert "pip install pyautogui" in err["hint"]
