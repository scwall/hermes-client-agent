"""FastAPI application factory with middleware, routers, and lifespan."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from hermes_agent.audit_logger import AuditMiddleware
from hermes_agent.config import PORT, TOKEN, log
from hermes_agent.log_manager import RequestLoggingMiddleware, log_router, setup_log_capture
from hermes_agent.modules import detect_modules
from hermes_agent.rate_limiter import RateLimitMiddleware
from hermes_agent.routers.capabilities import router as capabilities_router
from hermes_agent.routers.dashboard import init_templates
from hermes_agent.routers.dashboard import router as dashboard_router
from hermes_agent.routers.exec import router as exec_router
from hermes_agent.routers.file import router as file_router
from hermes_agent.routers.keyboard_ import router as keyboard_router
from hermes_agent.routers.mouse import router as mouse_router
from hermes_agent.routers.processes import router as processes_router
from hermes_agent.routers.screenshot import router as screenshot_router
from hermes_agent.routers.system import router as system_router
from hermes_agent.routers.windows import router as windows_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: detect modules, set up log capture. Shutdown: log stop message."""
    detect_modules()
    setup_log_capture(logging.getLogger())
    log.info("Hermes Agent starting on port %s", PORT)
    log.info("Token: %s...%s", TOKEN[:6], TOKEN[-4:] if len(TOKEN) > 10 else "****")
    yield
    from hermes_agent.audit_logger import get_audit_logger
    get_audit_logger().close()
    log.info("Hermes Agent shutting down")


app = FastAPI(
    title="Hermes Windows Agent",
    description=(
        "HTTP REST API for remote Windows machine control — "
        "shell, files, screenshot, mouse, keyboard, windows, system."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(capabilities_router)
app.include_router(exec_router)
app.include_router(file_router)
app.include_router(mouse_router)
app.include_router(keyboard_router)
app.include_router(windows_router)
app.include_router(processes_router)
app.include_router(system_router)
app.include_router(screenshot_router)
app.include_router(dashboard_router)
app.include_router(log_router)

_templates_dir = Path(__file__).parent / "templates"
_templates = Jinja2Templates(directory=str(_templates_dir))
init_templates(_templates)


@app.get("/health", tags=["health"], summary="Agent health check")
async def health():
    """Return a simple status response with the current server timestamp."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/logs", include_in_schema=False)
async def logs_redirect():
    """Redirect /logs to the new /dashboard page."""
    return RedirectResponse(url="/dashboard", status_code=302)
