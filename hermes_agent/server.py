"""Uvicorn server launcher with graceful shutdown via SIGINT/SIGTERM and system tray."""
import signal

import uvicorn

from hermes_agent.app import app as fastapi_app
from hermes_agent.config import HOST, PORT, log
from hermes_agent.tray import start_tray, stop_tray


def run_server() -> None:
    """Start the uvicorn ASGI server on the configured port.

    Handles SIGINT (Ctrl+C) and SIGTERM for clean shutdown.
    Starts the system tray icon in a background daemon thread.
    """
    config = uvicorn.Config(
        app=fastapi_app,
        host=HOST,
        port=PORT,
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)

    def shutdown_handler(signum, frame):
        log.info("Shutting down gracefully...")
        server.should_exit = True

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    tray_thread = start_tray()

    try:
        server.run()
    finally:
        stop_tray()
