"""Screenshot capture endpoint — full screen or region as PNG base64."""
import base64
import ctypes
import struct
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from hermes_agent.security import verify_token

try:
    from PIL import Image
except Exception:
    Image = None

router = APIRouter(tags=["screenshot"], dependencies=[Depends(verify_token)])


def _get_screen_width() -> int:
    """Get the primary monitor width in pixels (Windows only)."""
    return ctypes.windll.user32.GetSystemMetrics(0)


def _get_screen_height() -> int:
    """Get the primary monitor height in pixels (Windows only)."""
    return ctypes.windll.user32.GetSystemMetrics(1)


def _capture_screen_rgba() -> tuple:
    """Capture the full primary screen as raw RGBA bytes using Win32 GDI.

    Returns (rgba_bytes, width, height).
    """
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
    gdi32.SelectObject(hdc_mem, hbmp)
    gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, 0, 0, 0x00CC0020)

    bmp_size = width * height * 4
    bmp_data = (ctypes.c_ubyte * bmp_size)()
    bmp_info = (ctypes.c_ubyte * 52)()
    struct.pack_into("<I", bmp_info, 0, 52)
    struct.pack_into("<i", bmp_info, 4, width)
    struct.pack_into("<i", bmp_info, 8, -height)
    struct.pack_into("<H", bmp_info, 12, 1)
    struct.pack_into("<H", bmp_info, 14, 32)
    gdi32.GetDIBits(hdc_mem, hbmp, 0, height, bmp_data, ctypes.cast(bmp_info, ctypes.POINTER(ctypes.c_ubyte)), 0)

    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)

    bmp_row_size = width * 4
    rows = []
    for y in range(height):
        src_start = (height - 1 - y) * bmp_row_size
        rows.append(bytes(bmp_data)[src_start:src_start + bmp_row_size])
    return b"".join(rows), width, height


def _rgba_to_png(rgba_data: bytes, width: int, height: int) -> bytes:
    """Convert raw RGBA bytes to PNG using PIL, or fall back to BMP header."""
    if Image is not None:
        img = Image.frombuffer("RGBA", (width, height), rgba_data, "raw", "RGBA", 0, 1)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    header = struct.pack("<2sIHHI", b"BM", 54 + len(rgba_data), 0, 0, 54)
    return header + rgba_data


def _take_full_screenshot() -> tuple[bytes, int, int]:
    """Capture the full screen and return (png_bytes, width, height)."""
    rgba_data, width, height = _capture_screen_rgba()
    png_data = _rgba_to_png(rgba_data, width, height)
    return png_data, width, height


def _take_region_screenshot(x: int, y: int, w: int, h: int) -> tuple[bytes, int, int]:
    """Capture a screen region and return (png_bytes, width, height)."""
    rgba_data, sw, sh = _capture_screen_rgba()
    if Image is not None:
        img = Image.frombuffer("RGBA", (sw, sh), rgba_data, "raw", "RGBA", 0, 1)
        cropped = img.crop((x, y, x + w, y + h))
        buf = BytesIO()
        cropped.save(buf, format="PNG")
        return buf.getvalue(), w, h
    return _take_full_screenshot()


@router.get("/screenshot", summary="Capture the screen as PNG base64")
async def screenshot(region: Optional[str] = Query(None, description="Optional region as x,y,w,h")):
    """Take a screenshot of the full primary monitor, or a specific region.

    Returns a JSON object with the base64-encoded PNG image and its dimensions.
    """
    try:
        if region:
            parts = [int(p.strip()) for p in region.split(",")]
            if len(parts) != 4:
                raise HTTPException(status_code=400, detail="Region must be x,y,w,h")
            img_bytes, scr_w, scr_h = _take_region_screenshot(*parts)
        else:
            img_bytes, scr_w, scr_h = _take_full_screenshot()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    b64 = base64.b64encode(img_bytes).decode("ascii")
    return {"image_base64": b64, "format": "png", "width": scr_w, "height": scr_h}
