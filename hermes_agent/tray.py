"""System tray icon for the Hermes Windows Agent using pystray and Pillow."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Optional

try:
    import pystray
except (ImportError, Exception):
    pystray = None  # type: ignore[assignment]

try:
    from PIL import Image as PILImage
    from PIL import ImageDraw, ImageFont
except ImportError:
    PILImage = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from PIL.Image import Image

from hermes_agent.config import PORT, log


class TrayState:
    """Simple state machine for the tray icon color and tooltip."""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"

    def __init__(self):
        self.status = self.GREEN
        self.request_count = 0
        self.error_count = 0
        self.uptime_start: Optional[float] = None

    @property
    def tooltip(self) -> str:
        return f"Hermes Agent \u2014 {self.request_count} req, {self.error_count} errors"


_tray_state = TrayState()


def _get_icon_path() -> Optional[Path]:
    candidates = [Path("icon.ico"), Path("hermes_agent/icon.ico"), Path("icon.png")]
    root = Path(__file__).resolve().parent.parent
    candidates.append(root / "icon.ico")
    candidates.append(root / "icon.png")
    for p in candidates:
        if p.exists():
            return p
    return None


def _generate_icon(color: str = "green"):
    """Generate a stylised 'H' on a round coloured background."""
    colors = {
        "green": (46, 160, 67),
        "yellow": (210, 153, 34),
        "red": (248, 81, 73),
    }
    fill = colors.get(color, colors["green"])
    size = 64
    image = PILImage.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse([2, 2, size - 2, size - 2], fill=fill)
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except Exception:
        font = ImageFont.load_default()
    draw.text((size // 2, size // 2), "H", fill="white", anchor="mm", font=font)
    return image


def _build_image(color: str = "green"):
    icon_path = _get_icon_path()
    if icon_path:
        img = PILImage.open(icon_path)
        return img.resize((64, 64))
    return _generate_icon(color)


def _open_dashboard(icon, item) -> None:
    webbrowser.open(f"http://localhost:{PORT}/dashboard")


def _show_status(icon, item) -> None:
    state = _tray_state
    duration = ""
    if state.uptime_start:
        secs = int(time.time() - state.uptime_start)
        h, m = divmod(secs, 3600)
        mi, s = divmod(m, 60)
        duration = f"{h}h {mi}m {s}s"
    line = f"Uptime: {duration}\nRequests: {state.request_count}\nErrors: {state.error_count}"
    icon.notify(line, title="Hermes Agent Status")


def _open_logs(icon, item) -> None:
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    resolved = str(log_dir.resolve())
    if sys.platform == "win32":
        os.startfile(resolved)
    else:
        subprocess.Popen(["xdg-open", resolved] if sys.platform != "darwin" else ["open", resolved])


def _quit_agent(icon, item) -> None:
    icon.stop()
    log.info("Tray quit requested \u2014 sending stop signal")
    os.kill(os.getpid(), signal.SIGINT)


def _create_menu() -> "pystray.Menu":  # noqa: F821
    return pystray.Menu(
        pystray.MenuItem("Dashboard", _open_dashboard, default=True),
        pystray.MenuItem("Status", _show_status),
        pystray.MenuItem("Logs", _open_logs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit_agent),
    )


def _get_image() -> "Image":  # noqa: F821
    color = _tray_state.status
    return _build_image(color)


_is_tray_running = False
_tray_thread: Optional[threading.Thread] = None
_icon = None


def start_tray() -> threading.Thread:
    """Start the system tray icon in a daemon thread.

    Returns the thread so callers can optionally join it.
    Does nothing if already running.
    """
    global _is_tray_running, _tray_thread, _icon

    if _is_tray_running:
        return _tray_thread

    if pystray is None:
        log.warning("pystray not installed – tray icon disabled")
        return None

    if _tray_state.uptime_start is None:
        _tray_state.uptime_start = time.time()

    _icon = pystray.Icon(
        "HermesAgent",
        _get_image(),
        "Hermes Agent",
        menu=_create_menu(),
    )

    def _run():
        global _is_tray_running
        _is_tray_running = True
        _icon.run()

    _tray_thread = threading.Thread(target=_run, daemon=True, name="hermes-tray")
    _tray_thread.start()

    try:
        _icon.notify(f"Hermes Agent started on port {PORT}", title="Hermes Agent")
    except Exception:
        pass

    return _tray_thread


def update_tray_status(status: str, request_count: int = 0, error_count: int = 0) -> None:
    """Update the tray icon colour and tooltip text."""
    global _icon
    _tray_state.status = status
    _tray_state.request_count = request_count
    _tray_state.error_count = error_count
    if _icon:
        _icon.icon = _build_image(status)
        _icon.title = _tray_state.tooltip


def stop_tray() -> None:
    """Stop the tray icon (call during shutdown)."""
    global _is_tray_running, _icon, _tray_thread
    if _icon:
        _icon.stop()
        _icon = None
    _is_tray_running = False
    _tray_thread = None
