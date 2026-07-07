"""Mouse control endpoints — requires pyautogui."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hermes_agent.modules import build_module_error
from hermes_agent.security import verify_token

try:
    import pyautogui
except Exception:
    pyautogui = None

router = APIRouter(tags=["mouse"], dependencies=[Depends(verify_token)])


class MouseMoveRequest(BaseModel):
    """Payload for moving the mouse cursor to absolute coordinates."""

    x: int
    y: int


class MouseClickRequest(BaseModel):
    """Payload for a mouse click, optionally at a target position."""

    button: str = "left"
    x: Optional[int] = None
    y: Optional[int] = None


class MouseScrollRequest(BaseModel):
    """Payload for scrolling the mouse wheel."""

    direction: str = "up"
    clicks: int = 1


def _require_pyautogui():
    """Raise 503 if pyautogui is not installed on the system."""
    if pyautogui is None:
        raise HTTPException(status_code=503, detail=build_module_error("pyautogui"))


@router.post("/mouse/move", summary="Move the mouse cursor")
async def mouse_move(body: MouseMoveRequest):
    """Move the cursor to absolute screen coordinates (x, y)."""
    _require_pyautogui()
    pyautogui.moveTo(body.x, body.y)
    return {"x": body.x, "y": body.y}


@router.post("/mouse/click", summary="Perform a mouse click")
async def mouse_click(body: MouseClickRequest):
    """Left, right, or middle click at the current or target position."""
    _require_pyautogui()
    if body.x is not None and body.y is not None:
        pyautogui.click(body.x, body.y, button=body.button)
    else:
        pyautogui.click(button=body.button)
    return {"clicked": True, "button": body.button}


@router.post("/mouse/doubleclick", summary="Perform a double-click")
async def mouse_doubleclick(body: MouseClickRequest):
    """Double-click at the current position, or move-then-double-click."""
    _require_pyautogui()
    if body.x is not None and body.y is not None:
        pyautogui.doubleClick(body.x, body.y)
    else:
        pyautogui.doubleClick()
    return {"double_clicked": True}


@router.post("/mouse/scroll", summary="Scroll the mouse wheel")
async def mouse_scroll(body: MouseScrollRequest):
    """Scroll up or down by a number of clicks."""
    _require_pyautogui()
    amount = body.clicks if body.direction == "up" else -body.clicks
    pyautogui.scroll(amount)
    return {"scrolled": True, "direction": body.direction, "clicks": body.clicks}


@router.get("/mouse/position", summary="Get current cursor position")
async def mouse_position():
    """Return the current (x, y) screen position of the mouse."""
    _require_pyautogui()
    pos = pyautogui.position()
    return {"x": pos.x, "y": pos.y}
