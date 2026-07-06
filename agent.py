import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path


def _startup_log(msg: str) -> None:
    """Write a timestamped message to the startup log file."""
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "startup.log"
    ts = datetime.now(timezone.utc).isoformat()
    line = f"{ts} {msg}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)
    print(msg)


if __name__ == "__main__":
    _startup_log("=== Hermes Agent starting ===")
    _startup_log(f"Python: {sys.version}")
    _startup_log(f"Executable: {sys.executable}")
    _startup_log(f"Working dir: {Path.cwd()}")
    _startup_log(f"Args: {sys.argv}")

    if getattr(sys, "frozen", False):
        _startup_log(f"Bundle dir: {sys._MEIPASS}")
    else:
        _startup_log("Running from source (not frozen)")

    try:
        t0 = time.perf_counter()
        _startup_log("Importing hermes_agent...")
        from hermes_agent import run_server
        _startup_log(f"Imports OK ({time.perf_counter() - t0:.2f}s)")
        _startup_log("Starting server...")
        run_server()
    except SystemExit:
        _startup_log("Server exited cleanly")
        raise
    except Exception:
        err = traceback.format_exc()
        _startup_log(f"FATAL: {err}")
        print(err, file=sys.stderr)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, err[:1000], "Hermes Agent Startup Error", 0x10)
        except Exception:
            pass
        sys.exit(1)
    except KeyboardInterrupt:
        _startup_log("Keyboard interrupt")
        sys.exit(0)
