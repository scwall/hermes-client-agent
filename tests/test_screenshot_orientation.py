"""Windows GDI screenshot orientation regression tests.

`_capture_screen_rgba` calls GetDIBits with a BITMAPINFOHEADER and then
reorders the raw scanlines into top->bottom order. The sign of `biHeight`
in that header selects the DIB orientation GetDIBits returns:

  * biHeight < 0  -> top-down DIB  -> buffer[0] = top scanline
  * biHeight > 0  -> bottom-up DIB -> buffer[0] = bottom scanline  (GDI default)

The trailing row loop does `rows[y] = buf[(h-1-y)]`, i.e. it REVERSES the
buffer. So an upright image only results when the header orientation and the
reversal agree:

  * bottom-up buffer (bih>0) + reversal  -> upright   (correct)
  * top-down buffer  (bih<0) + reversal  -> mirrored  (the original bug)

The original code packed `biHeight = -height` (top-down) AND kept the reversal
loop, which cancelled into a vertically flipped image (taskbar at the top,
text upside-down). The fix packs `biHeight = +height` so the reversal loop
produces an upright image.

These tests mock ctypes.windll so they run cross-platform and fail if the
orientation logic regresses.
"""
import ctypes as _ctypes
import struct
from unittest.mock import MagicMock, patch

import hermes_agent.routers.screenshot as shot

W, H = 4, 5


def _screen_rows(w, h):
    """Physical screen: row 0 (top) red, last row (bottom) blue, rest ramped."""
    rows = []
    for y in range(h):
        r = 255 if y == 0 else (0 if y == h - 1 else y)
        b = 255 if y == h - 1 else (0 if y == 0 else y)
        row = bytes([r, 0, b, 255]) * w
        rows.append(row)
    return rows


def _buffer_from_rows(rows):
    return b"".join(rows)


def _mock_windll(w, h):
    """Mock ctypes.windll. GetDIBits returns a buffer whose orientation depends
    on the biHeight the code packed (faithful to the Win32 sign convention).
    Returns (windll, captured) where captured['bih'] is the packed biHeight."""
    rows = _screen_rows(w, h)
    top_down = _buffer_from_rows(rows)               # buf[0] = top
    bottom_up = _buffer_from_rows(list(reversed(rows)))  # buf[0] = bottom
    captured = {}

    def _getdibits(hdc, bmp, start, count, data, info, usage):
        header = _ctypes.string_at(info, 52)
        bih = struct.unpack_from("<i", header, 8)[0]
        captured["bih"] = bih
        data[:] = (top_down if bih < 0 else bottom_up)
        return h

    user32 = MagicMock()
    user32.GetSystemMetrics.side_effect = [w, h]
    user32.GetDC.return_value = 0xBEEF
    gdi32 = MagicMock()
    gdi32.CreateCompatibleDC.return_value = 0xCAFE
    gdi32.CreateCompatibleBitmap.return_value = 0xF00D
    gdi32.GetDIBits.side_effect = _getdibits
    windll = MagicMock()
    windll.user32 = user32
    windll.gdi32 = gdi32
    return windll, captured


class TestWindowsOrientation:
    def _capture(self):
        windll, captured = _mock_windll(W, H)
        with patch.object(shot.ctypes, "windll", windll, create=True), \
             patch.object(shot.sys, "platform", "win32"):
            rgba, rw, rh = shot._capture_screen_rgba()
        return rgba, (rw, rh), captured

    def test_biheight_positive_bottom_up(self):
        """The code must pack a POSITIVE biHeight (bottom-up DIB) so the
        existing reversal loop yields an upright image."""
        _, _, captured = self._capture()
        assert captured["bih"] > 0, (
            "biHeight must be positive (bottom-up DIB); got %d" % captured["bih"]
        )

    def test_row_order_top_to_bottom(self):
        """Row 0 must be the physical top (red) and the last row the physical
        bottom (blue) — i.e. not vertically flipped."""
        rgba, size, _ = self._capture()
        assert size == (W, H)
        row0 = rgba[0:4]
        lastrow = rgba[(H - 1) * W * 4:(H - 1) * W * 4 + 4]
        assert row0 == bytes([255, 0, 0, 255]), "top row should be red, got %r" % (row0,)
        assert lastrow == bytes([0, 0, 255, 255]), "bottom row should be blue, got %r" % (lastrow,)

    def test_no_double_flip(self):
        """Guard against the original bug: top-down DIB + reversal loop mirrors
        the image (the red top row would end up at the bottom)."""
        rgba, _, _ = self._capture()
        lastrow = rgba[(H - 1) * W * 4:(H - 1) * W * 4 + 4]
        assert lastrow[0] != 255, "bottom row is red => image is vertically flipped"
