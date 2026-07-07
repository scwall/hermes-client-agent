"""Keyboard input endpoints — requires pyautogui."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hermes_agent.modules import build_module_error
from hermes_agent.security import verify_token

try:
    import pyautogui
except Exception:
    pyautogui = None

router = APIRouter(tags=["keyboard"], dependencies=[Depends(verify_token)])


class KeyboardTypeRequest(BaseModel):
    """Payload for simulating typed text."""

    text: str
    interval: float = 0.0


class KeyboardPressRequest(BaseModel):
    """Payload for pressing a single keyboard key."""

    key: str


class KeyboardHotkeyRequest(BaseModel):
    """Payload for pressing a key combination (e.g. Ctrl+C)."""

    keys: List[str]


def _require_pyautogui():
    """Raise 503 if pyautogui is not installed."""
    if pyautogui is None:
        raise HTTPException(status_code=503, detail=build_module_error("pyautogui"))


@router.post("/keyboard/type", summary="Type a text string")
async def keyboard_type(body: KeyboardTypeRequest):
    """Simulate typing the given text with an optional delay between keystrokes."""
    _require_pyautogui()
    pyautogui.typewrite(body.text, interval=body.interval)
    return {"typed": True, "length": len(body.text)}


@router.post("/keyboard/press", summary="Press a single key")
async def keyboard_press(body: KeyboardPressRequest):
    """Press and release a single key (enter, tab, escape, f1-f12, etc.)."""
    _require_pyautogui()
    if not body.key:
        raise HTTPException(status_code=400, detail="Missing 'key'")
    pyautogui.press(body.key.lower())
    return {"pressed": body.key.lower()}


@router.post("/keyboard/hotkey", summary="Press a key combination")
async def keyboard_hotkey(body: KeyboardHotkeyRequest):
    """Press a combination of keys simultaneously (e.g. ["ctrl", "c"])."""
    _require_pyautogui()
    if not body.keys:
        raise HTTPException(status_code=400, detail="Missing 'keys'")
    pyautogui.hotkey(*body.keys)
    return {"hotkey": "+".join(body.keys)}
