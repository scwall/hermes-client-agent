"""Window management endpoints — requires pygetwindow (Windows only)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hermes_agent.modules import is_module_available, build_module_error
from hermes_agent.security import verify_token

try:
    import pygetwindow as gw
except Exception:
    gw = None

router = APIRouter(tags=["window"], dependencies=[Depends(verify_token)])


class WindowFocusRequest(BaseModel):
    """Payload to focus a window by title substring."""

    title_substring: str


class WindowResizeRequest(BaseModel):
    """Payload to move and resize a window by title substring."""

    title_substring: str
    x: int
    y: int
    w: int
    h: int


def _require_pygetwindow():
    """Raise 503 if pygetwindow is not installed."""
    if gw is None:
        raise HTTPException(status_code=503, detail=build_module_error("pygetwindow"))


@router.get("/window/active", summary="Get the active window info")
async def window_active():
    """Return title and geometry of the currently focused window."""
    _require_pygetwindow()
    win = gw.getActiveWindow()
    if win:
        return {"title": win.title, "x": win.left, "y": win.top, "width": win.width, "height": win.height}
    return {"title": "", "x": 0, "y": 0, "width": 0, "height": 0}


@router.get("/window/list", summary="List all visible windows")
async def window_list():
    """Return a list of all windows that have a non-empty title."""
    _require_pygetwindow()
    windows = []
    for w in gw.getAllWindows():
        if w.title.strip():
            windows.append({
                "title": w.title, "x": w.left, "y": w.top,
                "width": w.width, "height": w.height,
            })
    return {"windows": windows}


@router.post("/window/focus", summary="Focus a window by title")
async def window_focus(body: WindowFocusRequest):
    """Bring a window to the foreground by matching its title substring."""
    _require_pygetwindow()
    if not body.title_substring:
        raise HTTPException(status_code=400, detail="Missing 'title_substring'")
    wins = gw.getWindowsWithTitle(body.title_substring)
    if wins:
        wins[0].activate()
        return {"focused": wins[0].title}
    raise HTTPException(status_code=404, detail=f"No window found matching '{body.title_substring}'")


@router.post("/window/resize", summary="Move and resize a window")
async def window_resize(body: WindowResizeRequest):
    """Change the position and dimensions of a window by title substring."""
    _require_pygetwindow()
    wins = gw.getWindowsWithTitle(body.title_substring)
    if wins:
        win = wins[0]
        win.moveTo(body.x, body.y)
        win.resizeTo(body.w, body.h)
        return {
            "resized": win.title,
            "x": win.left, "y": win.top,
            "width": win.width, "height": win.height,
        }
    raise HTTPException(status_code=404, detail=f"No window found matching '{body.title_substring}'")
