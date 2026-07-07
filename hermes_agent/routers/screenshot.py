"""Screenshot capture endpoint — full screen or region as base64 with optional compression."""
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


def _rgba_to_image(rgba_data: bytes, width: int, height: int) -> "Image.Image":
    """Convert raw RGBA bytes to a PIL Image."""
    if Image is None:
        raise RuntimeError("Pillow (PIL) is not installed")
    return Image.frombuffer("RGBA", (width, height), rgba_data, "raw", "RGBA", 0, 1)


def _encode_image(img: "Image.Image", output_format: str, quality: int) -> bytes:
    """Encode a PIL Image to PNG or JPEG bytes."""
    buf = BytesIO()
    if output_format == "jpeg":
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=quality, optimize=True)
    else:
        img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


@router.get("/screenshot", summary="Capture the screen as base64 with optional compression")
async def screenshot(
    region: Optional[str] = Query(None, description="Optional region as x,y,w,h"),
    scale: float = Query(1.0, ge=0.1, le=1.0, description="Resize factor (0.1 to 1.0)"),
    quality: int = Query(70, ge=1, le=100, description="JPEG compression quality (1-100, ignored for PNG)"),
    fmt: str = Query("png", alias="format", description="Output format: 'jpeg' or 'png'"),
):
    """Take a screenshot of the full primary monitor, or a specific region.

    Supports optional compression via scale, quality, and format parameters.
    Returns a JSON object with the base64-encoded image and its dimensions.

    - ``scale`` : resize factor (0.1 to 1.0). Default 1.0 = full resolution.
    - ``quality`` : JPEG quality (1-100). Default 70. Ignored for PNG.
    - ``format`` : output format, ``jpeg`` or ``png``. Default ``png``.
    """
    if fmt not in ("jpeg", "png"):
        raise HTTPException(status_code=422, detail="format must be 'jpeg' or 'png'")

    try:
        if region:
            parts = [int(p.strip()) for p in region.split(",")]
            if len(parts) != 4:
                raise HTTPException(status_code=400, detail="Region must be x,y,w,h")
            rgba_data, sw, sh = _capture_screen_rgba()
            img = _rgba_to_image(rgba_data, sw, sh)
            img = img.crop((parts[0], parts[1], parts[0] + parts[2], parts[1] + parts[3]))
        else:
            rgba_data, sw, sh = _capture_screen_rgba()
            img = _rgba_to_image(rgba_data, sw, sh)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if scale < 1.0:
        new_w = max(1, int(img.width * scale))
        new_h = max(1, int(img.height * scale))
        img = img.resize((new_w, new_h), Image.LANCZOS)

    img_bytes = _encode_image(img, fmt, quality)

    b64 = base64.b64encode(img_bytes).decode("ascii")
    return {
        "image_base64": b64,
        "format": fmt,
        "width": img.width,
        "height": img.height,
        "original_size": len(img_bytes),
    }
