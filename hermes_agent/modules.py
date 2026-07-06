"""Optional dependency detection and capability tracking."""
import json

from hermes_agent.config import log

_MODULES: dict[str, bool] = {}
_AVAILABLE_ENDPOINTS: set[str] = set()


def get_modules() -> dict[str, bool]:
    """Return a copy of the detected modules dictionary."""
    return dict(_MODULES)


def get_endpoints() -> set[str]:
    """Return a copy of the available endpoints set."""
    return set(_AVAILABLE_ENDPOINTS)


def is_module_available(name: str) -> bool:
    """Check whether an optional module was detected at startup."""
    return _MODULES.get(name, False)


def detect_module(name: str) -> bool:
    """Attempt to import a module and return True if successful."""
    try:
        __import__(name)
        return True
    except Exception:
        return False


def detect_modules() -> None:
    """Scan for optional dependencies and build the endpoint availability set.

    Called once at server startup. Logs detected modules and available endpoints.
    Must be called before the first request is handled.
    """
    global _MODULES, _AVAILABLE_ENDPOINTS

    _MODULES["pyautogui"] = detect_module("pyautogui")
    _MODULES["pygetwindow"] = detect_module("pygetwindow")
    _MODULES["psutil"] = detect_module("psutil")
    _MODULES["pillow"] = detect_module("PIL")

    _AVAILABLE_ENDPOINTS = {"exec", "file", "screenshot", "system", "processes", "health", "capabilities"}
    if _MODULES["pyautogui"]:
        _AVAILABLE_ENDPOINTS.update({"mouse", "keyboard"})
    if _MODULES["pygetwindow"]:
        _AVAILABLE_ENDPOINTS.add("window")

    log.info("Modules detected: %s", json.dumps(_MODULES))
    log.info("Available endpoints: %s", sorted(_AVAILABLE_ENDPOINTS))


def build_module_error(module_name: str) -> dict:
    """Build the standard error response body for a missing optional module."""
    return {
        "error": "module_not_installed",
        "module": module_name,
        "hint": f"pip install {module_name}",
    }
