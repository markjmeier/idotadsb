"""
DIY image prep before BLE upload (resize, optional palette snap).

Many 64×64 panels need a 64×64 payload. Use ``diy_upload_pixel_size(..., ble_cap=...)``
(from ``IDOTMATRIX_BLE_UPLOAD_CAP``, defaulting to 64 when pixel size ≥ 48) so the
BLE edge size matches the hardware.
"""

from __future__ import annotations

import io
import logging
from typing import Callable, Iterable

from PIL import Image as PilImage

from app.config import Settings

logger = logging.getLogger(__name__)


def _dist_sq(p: tuple[int, ...], q: tuple[int, int, int]) -> int:
    return sum((int(p[i]) - q[i]) ** 2 for i in range(3))


def diy_upload_pixel_size(requested: int, *, ble_cap: int = 32) -> int:
    """
    Target edge size for DIY image upload over BLE.

    Library docs mention 16/32; some 64×64 panels accept 64. Use env
    IDOTMATRIX_BLE_UPLOAD_CAP (e.g. 64) if 32×32 shows a blank panel.
    """
    cap = max(16, min(128, ble_cap))
    if requested <= 16:
        return 16
    return min(requested, cap)


def resize_png_to_square(png_bytes: bytes, edge_px: int) -> bytes:
    """Ensure RGB PNG is exactly edge_px×edge_px for uploadProcessed."""
    with PilImage.open(io.BytesIO(png_bytes)) as im:
        im = im.convert("RGB")
        if im.size != (edge_px, edge_px):
            im = im.resize((edge_px, edge_px), PilImage.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()


def snap_png_to_fg_bg(
    png_bytes: bytes,
    fg: tuple[int, int, int],
    bg: tuple[int, int, int],
) -> bytes:
    """
    Map every pixel to exactly ``fg`` or ``bg`` (whichever is closer in RGB).
    Some DIY firmware thresholds badly on antialiased grays from TrueType; this
    keeps the PNG strictly two-color before BLE upload.
    """
    fg_t = (int(fg[0]), int(fg[1]), int(fg[2]))
    bg_t = (int(bg[0]), int(bg[1]), int(bg[2]))

    with PilImage.open(io.BytesIO(png_bytes)) as im:
        im = im.convert("RGB")
        pix = im.load()
        w, h = im.size
        for y in range(h):
            for x in range(w):
                p = pix[x, y]
                # Prefer fg on tie so antialiased grays become ink, not holes.
                pix[x, y] = fg_t if _dist_sq(p, fg_t) <= _dist_sq(p, bg_t) else bg_t
        buf = io.BytesIO()
        im.save(buf, format="PNG", compress_level=6)
        return buf.getvalue()


def snap_png_to_nearest_palette(
    png_bytes: bytes,
    palette: Iterable[tuple[int, int, int]],
) -> bytes:
    """
    Map each pixel to the closest RGB in ``palette`` (for DIY upload after multi-color canvas).
    Tie-break: prefer higher channel sum so antialiased grays lean toward ink, not background.
    """
    colors: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int, int]] = set()
    for raw in palette:
        c = (int(raw[0]), int(raw[1]), int(raw[2]))
        if c not in seen:
            seen.add(c)
            colors.append(c)
    if len(colors) < 2:
        raise ValueError("palette needs at least background + one foreground")

    def nearest(p: tuple[int, ...]) -> tuple[int, int, int]:
        best = colors[0]
        best_d = _dist_sq(p, best)
        for cand in colors[1:]:
            d = _dist_sq(p, cand)
            if d < best_d or (d == best_d and sum(cand) > sum(best)):
                best, best_d = cand, d
        return best

    with PilImage.open(io.BytesIO(png_bytes)) as im:
        im = im.convert("RGB")
        pix = im.load()
        w, h = im.size
        for y in range(h):
            for x in range(w):
                pix[x, y] = nearest(pix[x, y])
        buf = io.BytesIO()
        im.save(buf, format="PNG", compress_level=6)
        return buf.getvalue()


def _lerp_rgb(
    a: tuple[int, int, int], b: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(round(a[i] * (1.0 - t) + b[i] * t)))) for i in range(3))


def _add_antialias_ramps(
    add: Callable[[tuple[int, int, int]], None],
    bg: tuple[int, int, int],
    foregrounds: list[tuple[int, int, int]],
) -> None:
    """
    TrueType edges are RGB blends; nearest-palette snap otherwise maps grays to the wrong hue
    (e.g. white body text picking climb green). Add a few fg↔bg blends per ink color.
    """
    seen_fg = {bg}
    for fg in foregrounds:
        t = (max(0, min(255, int(fg[0]))), max(0, min(255, int(fg[1]))), max(0, min(255, int(fg[2]))))
        if t in seen_fg:
            continue
        seen_fg.add(t)
        for u in (0.25, 0.45, 0.65, 0.82):
            add(_lerp_rgb(t, bg, u))


def _diy_snap_palette_for_frame(
    settings: Settings,
    fg: tuple[int, int, int],
    bg: tuple[int, int, int],
    chrome_rgb: tuple[int, int, int] | None,
) -> list[tuple[int, int, int]]:
    """
    Theme colors + this frame's callsign/alert ink only.
    Listing every airline blue causes antialiased glyphs to snap to the wrong carrier.
    """
    seen: set[tuple[int, int, int]] = set()
    out: list[tuple[int, int, int]] = []

    def add(c: tuple[int, int, int]) -> None:
        t = (max(0, min(255, int(c[0]))), max(0, min(255, int(c[1]))), max(0, min(255, int(c[2]))))
        if t not in seen:
            seen.add(t)
            out.append(t)

    add(bg)
    add(fg)
    add(settings.v3_default_text_rgb)
    add(settings.v3_alert_rgb)
    add(settings.v3_climb_rgb)
    add(settings.v3_descent_rgb)
    add(settings.v3_level_rgb)
    add(settings.v3_unknown_airline_rgb)
    add(settings.v3_default_accent_rgb)
    if chrome_rgb is not None:
        add(chrome_rgb)

    ramp_sources = [
        settings.v3_default_text_rgb,
        settings.v3_default_accent_rgb,
        settings.v3_climb_rgb,
        settings.v3_descent_rgb,
        settings.v3_level_rgb,
        settings.v3_unknown_airline_rgb,
        settings.v3_alert_rgb,
        fg,
    ]
    if chrome_rgb is not None:
        ramp_sources.append(chrome_rgb)
    _add_antialias_ramps(add, bg, ramp_sources)
    return out


def snap_png_for_upload(
    png_bytes: bytes,
    settings: Settings,
    chrome_rgb: tuple[int, int, int] | None = None,
) -> bytes:
    """
    Quantize rendered PNG for DIY BLE: two-color when monochrome; with airline colors,
    snap to theme + optional ``chrome_rgb`` (this frame's callsign / alert ink).
    """
    fg, bg = settings.idotmatrix_fg_rgb, settings.idotmatrix_bg_rgb
    if settings.idotmatrix_swap_fg_bg:
        fg, bg = bg, fg
    if not settings.v3_enable_airline_colors:
        return snap_png_to_fg_bg(png_bytes, fg, bg)
    palette = _diy_snap_palette_for_frame(settings, fg, bg, chrome_rgb)
    return snap_png_to_nearest_palette(png_bytes, palette)
