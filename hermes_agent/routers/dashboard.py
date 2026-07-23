"""Dashboard API endpoints, HTML pages via Jinja2 templates, and log export."""
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from hermes_agent.acp.diagnostics import run_diagnostics
from hermes_agent.audit.models import AuditLog
from hermes_agent.security import verify_local_or_token

router = APIRouter(tags=["dashboard"], dependencies=[Depends(verify_local_or_token)])

_templates = None

DEFAULT_ENDPOINTS = [
    "/exec", "/file", "/file/delete", "/mouse/move", "/mouse/click",
    "/mouse/doubleclick", "/mouse/scroll", "/mouse/position",
    "/keyboard/type", "/keyboard/press", "/keyboard/hotkey",
    "/window/active", "/window/list", "/window/focus", "/window/resize",
    "/screenshot", "/processes", "/process/kill", "/system",
    "/health", "/capabilities", "/dashboard", "/dashboard/logs",
    "/dashboard/errors", "/dashboard/exec", "/api/logs", "/api/stats",
]


def init_templates(templates) -> None:
    """Inject the Jinja2Templates instance from app.py."""
    global _templates
    _templates = templates


def _render(page: str, request: Request, extra: Optional[dict] = None, data: Optional[dict] = None) -> HTMLResponse:
    stats = AuditLog.fetch_stats()
    if data is None:
        data = AuditLog.fetch_logs(limit=50)
    ctx = {
        "request": request,
        "stats": stats,
        "endpoints": DEFAULT_ENDPOINTS,
        "entries": data.get("entries", []),
        "total": data.get("total", 0),
        "offset": data.get("offset", 0),
        "limit": data.get("limit", 50),
    }
    if extra:
        ctx.update(extra)
    return _templates.TemplateResponse(request, page, ctx)


@router.get("/api/logs", summary="Get filtered audit log entries as JSON")
async def api_logs(
    count: int = Query(100, description="Number of entries to return"),
    offset: int = Query(0, description="Pagination offset"),
    status: Optional[str] = Query(None, description="Filter by status code or 'success'/'error'"),
    endpoint: Optional[str] = Query(None, description="Filter by endpoint path"),
    ip: Optional[str] = Query(None, description="Filter by source IP"),
    search: Optional[str] = Query(None, description="Full-text search across all fields"),
):
    """Return paginated and filtered audit log entries."""
    return AuditLog.fetch_logs(
        limit=count,
        offset=offset,
        endpoint_filter=endpoint,
        status_filter=status,
        ip_filter=ip,
        search=search,
    )


@router.get("/api/stats", summary="Get aggregate audit statistics")
async def api_stats():
    """Return summary statistics from the audit log."""
    return AuditLog.fetch_stats()


@router.get("/api/logs/export", summary="Export audit logs as CSV or JSON")
async def api_logs_export(
    format: str = Query("csv", description="Export format: csv or json"),
    count: int = Query(10000, description="Max entries to export"),
    endpoint: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    """Download filtered audit logs as a CSV or JSON file."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    content = AuditLog.export(
        fmt=format, limit=count, endpoint_filter=endpoint, status_filter=status, search=search,
    )
    mime = "application/json" if format == "json" else "text/csv"
    encoding = "utf-8" if format == "json" else "utf-8-sig"
    return StreamingResponse(
        io.BytesIO(content.encode(encoding)),
        media_type=mime,
        headers={"Content-Disposition": f"attachment; filename=hermes-logs-{ts}.{format}"},
    )


@router.post("/api/clear-logs", summary="Manually trigger log rotation")
async def api_clear_logs():
    """Remove old log entries (older than 7 days) if the log file exceeds 10 MiB."""
    return AuditLog.purge_older_than()


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False, summary="Main dashboard page")
async def dashboard_page(request: Request):
    """Serve the main dashboard overview page."""
    data = AuditLog.fetch_logs(limit=50)
    return _render("pages/dashboard.html", request, {"active_page": "dashboard"}, data)


@router.get("/dashboard/logs", response_class=HTMLResponse, include_in_schema=False, summary="Filtered logs page")
async def dashboard_logs_page(
    request: Request,
    count: int = Query(50),
    offset: int = Query(0),
    status: Optional[str] = Query(None),
    endpoint: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    """Serve the filtered logs dashboard page."""
    data = AuditLog.fetch_logs(limit=count, offset=offset, endpoint_filter=endpoint, status_filter=status, search=search)
    return _render("pages/dashboard.html", request, {
        "active_page": "dashboard",
        "endpoint_filter": endpoint or "",
        "status_filter": status or "",
        "search_query": search or "",
    }, data)


@router.get("/dashboard/errors", response_class=HTMLResponse, include_in_schema=False, summary="Errors only page")
async def dashboard_errors_page(
    request: Request,
    count: int = Query(50),
    offset: int = Query(0),
    search: Optional[str] = Query(None),
):
    """Serve the errors-only dashboard page."""
    data = AuditLog.fetch_logs(limit=count, offset=offset, status_filter="error", search=search)
    return _render("pages/errors.html", request, {
        "active_page": "errors",
        "status_filter": "error",
        "search_query": search or "",
    }, data)


@router.get("/dashboard/exec", response_class=HTMLResponse, include_in_schema=False, summary="Executed commands page")
async def dashboard_exec_page(
    request: Request,
    count: int = Query(50),
    offset: int = Query(0),
    search: Optional[str] = Query(None),
):
    """Serve the executed-commands dashboard page."""
    data = AuditLog.fetch_logs(limit=count, offset=offset, endpoint_filter="/exec", search=search)
    return _render("pages/exec.html", request, {
        "active_page": "exec",
        "endpoint_filter": "/exec",
        "search_query": search or "",
    }, data)


@router.get("/dashboard/acp", response_class=HTMLResponse, include_in_schema=False, summary="ACP agent diagnostics page")
async def dashboard_acp_page(request: Request):
    """Serve the ACP diagnostics dashboard page."""
    extra = {
        "active_page": "acp",
        "acp": run_diagnostics(),
    }
    stats = AuditLog.fetch_stats()
    ctx = {
        "request": request,
        "stats": stats,
        "endpoints": DEFAULT_ENDPOINTS,
        "entries": [],
        "total": 0,
        "offset": 0,
        "limit": 50,
    }
    ctx.update(extra)
    return _templates.TemplateResponse(request, "pages/acp.html", ctx)
