from __future__ import annotations

import io
import logging
from typing import Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from app.panel_view import PanelView

logger = logging.getLogger(__name__)

# Pillow: anchor="lt" so textbbox height matches draw placement (see layoutcontract.md).
_TEXT_ANCHOR = "lt"

# 64×64: callsign-only top, altitude+FT, full-width motion state, then speed|dir (shared font).
# 18 + 14 + 12 + 20 = 64.
FLIGHT_BOXES_64: dict[str, tuple[int, int, int, int]] = {
    "callsign": (0, 0, 64, 18),
    "altitude": (0, 18, 64, 14),
    "state": (0, 32, 64, 12),
    "speed": (0, 44, 32, 20),
    "direction": (32, 44, 32, 20),
}

# Alerts: callsign top, altitude+FT, single alert label (no duplicate with title+state), speed|dir.
# 14 + 12 + 10 + 28 = 64.
ALERT_BOXES_64: dict[str, tuple[int, int, int, int]] = {
    "callsign": (0, 0, 64, 14),
    "altitude": (0, 14, 64, 12),
    "alert_label": (0, 26, 64, 10),
    "speed": (0, 36, 32, 28),
    "direction": (32, 36, 32, 28),
}


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        logger.warning("truetype size %s failed for %s; using default bitmap font", size, path)
        return ImageFont.load_default()


def _measure_text(text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bbox = d.textbbox((0, 0), text, font=font, anchor=_TEXT_ANCHOR)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _scale_box_64(box: tuple[int, int, int, int], pixel_size: int) -> tuple[int, int, int, int]:
    """Scale a 64×64 contract box to another square panel (nearest int, min width/height 1)."""
    if pixel_size == 64:
        return box
    x, y, w, h = box
    s = pixel_size / 64.0
    return (
        int(round(x * s)),
        int(round(y * s)),
        max(1, int(round(w * s))),
        max(1, int(round(h * s))),
    )


def _boxes_for_panel(template: dict[str, tuple[int, int, int, int]], pixel_size: int) -> dict[str, tuple[int, int, int, int]]:
    return {k: _scale_box_64(v, pixel_size) for k, v in template.items()}


def draw_text_in_box(
    img: Image.Image,
    text: str,
    box: tuple[int, int, int, int],
    font_path: str,
    font_priority: tuple[int, int, int],
    fg: Tuple[int, int, int],
    bg: Tuple[int, int, int],
) -> None:
    """
    layoutcontract.md: try large → medium → small; center in box; truncate with no suffix if needed.
    Renders into a cell-sized buffer and pastes back so ink cannot spill into neighboring zones.
    """
    bx, by, bw, bh = box
    if bw <= 0 or bh <= 0:
        return

    # Contract order: large → medium → small (caller passes lg, md, sm from render_panel_view).
    sizes = (font_priority[0], font_priority[1], font_priority[2])
    t = text if text else "—"

    cell = Image.new("RGB", (bw, bh), bg)
    draw = ImageDraw.Draw(cell)

    chosen: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
    display = t
    for sz in sizes:
        font = _load_font(font_path, sz)
        tw, th = _measure_text(display, font)
        if tw <= bw and th <= bh:
            chosen = font
            break

    if chosen is None:
        font = _load_font(font_path, sizes[2])
        display = t
        while len(display) > 0:
            tw, th = _measure_text(display, font)
            if tw <= bw and th <= bh:
                break
            display = display[:-1]
        chosen = font

    tw, th = _measure_text(display, chosen)
    px = max(0, (bw - tw) // 2)
    py = max(0, (bh - th) // 2)
    draw.text((px, py), display, font=chosen, fill=fg, anchor=_TEXT_ANCHOR)
    img.paste(cell, (bx, by))


def _draw_text_in_cell_at_font(
    img: Image.Image,
    text: str,
    box: tuple[int, int, int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fg: Tuple[int, int, int],
    bg: Tuple[int, int, int],
) -> None:
    """Center text in box at a fixed font size; truncate if needed (same font for every string)."""
    bx, by, bw, bh = box
    if bw <= 0 or bh <= 0:
        return
    cell = Image.new("RGB", (bw, bh), bg)
    draw = ImageDraw.Draw(cell)
    display = text if text else "—"
    while len(display) > 0:
        tw, th = _measure_text(display, font)
        if tw <= bw and th <= bh:
            break
        display = display[:-1]
    tw, th = _measure_text(display, font)
    px = max(0, (bw - tw) // 2)
    py = max(0, (bh - th) // 2)
    draw.text((px, py), display, font=font, fill=fg, anchor=_TEXT_ANCHOR)
    img.paste(cell, (bx, by))


def draw_speed_direction_same_font(
    img: Image.Image,
    speed_text: str,
    direction_text: str,
    speed_box: tuple[int, int, int, int],
    direction_box: tuple[int, int, int, int],
    font_path: str,
    font_priority: tuple[int, int, int],
    fg: Tuple[int, int, int],
    bg: Tuple[int, int, int],
) -> None:
    """
    Pick one font size that fits both strings in their boxes (largest that works).
    Avoids W at 12px next to SW at 9px when each cell would otherwise shrink independently.
    """
    sizes = font_priority
    lw, lh = speed_box[2], speed_box[3]
    rw, rh = direction_box[2], direction_box[3]
    left = speed_text if speed_text else "—"
    right = direction_text if direction_text else "—"
    chosen: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
    for sz in sizes:
        font = _load_font(font_path, sz)
        w1, h1 = _measure_text(left, font)
        w2, h2 = _measure_text(right, font)
        if w1 <= lw and h1 <= lh and w2 <= rw and h2 <= rh:
            chosen = font
            break
    if chosen is None:
        chosen = _load_font(font_path, sizes[2])
    _draw_text_in_cell_at_font(img, left, speed_box, chosen, fg, bg)
    _draw_text_in_cell_at_font(img, right, direction_box, chosen, fg, bg)


def render_lines_png(
    lines: Sequence[str],
    pixel_size: int,
    font_path: str,
    *,
    fg: Tuple[int, int, int] = (255, 255, 255),
    bg: Tuple[int, int, int] = (0, 0, 0),
) -> bytes:
    """
    Draw up to four lines centered on a square RGB image and return PNG bytes.
    Scales font sizes down if the title overflows width.
    """
    raw = [ln.strip() for ln in lines[:4]]
    while len(raw) < 4:
        raw.append("")

    img = Image.new("RGB", (pixel_size, pixel_size), bg)
    draw = ImageDraw.Draw(img)

    title_size = max(10, min(26, pixel_size // 3))
    body_size = max(8, min(14, pixel_size // 5))

    title_font = _load_font(font_path, title_size)
    body_font = _load_font(font_path, body_size)

    title_text = raw[0] or "—"
    for _ in range(8):
        tw, th = _measure_text(title_text, title_font)
        if tw <= pixel_size - 6:
            break
        title_size = max(8, title_size - 2)
        title_font = _load_font(font_path, title_size)

    line_fonts = [title_font, body_font, body_font, body_font]
    heights: list[int] = []
    widths: list[int] = []
    for i, line in enumerate(raw):
        if not line:
            heights.append(0)
            widths.append(0)
            continue
        font = line_fonts[i]
        w_m, h_m = _measure_text(line, font)
        widths.append(w_m)
        heights.append(h_m)

    used_h = sum(h for h in heights if h > 0) + 2 * max(0, sum(1 for h in heights if h > 0) - 1)
    y = max(2, (pixel_size - used_h) // 2)

    for i, line in enumerate(raw):
        if not line:
            continue
        font = line_fonts[i]
        w_m, h_m = widths[i], heights[i]
        x = max(2, (pixel_size - w_m) // 2)
        draw.text((x, y), line, font=font, fill=fg, anchor=_TEXT_ANCHOR)
        y += h_m + 2

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_panel_view(
    view: PanelView,
    pixel_size: int,
    font_path: str,
    *,
    fg: Tuple[int, int, int] = (255, 255, 255),
    bg: Tuple[int, int, int] = (0, 0, 0),
) -> bytes:
    """
    Flight / alert layouts: 64×64 contract zones (scaled for other sizes).
    """
    w = h = pixel_size
    img = Image.new("RGB", (w, h), bg)

    lg = max(11, min(22, int(pixel_size * 0.30)))
    md = max(9, min(16, int(pixel_size * 0.21)))
    sm = max(7, min(12, int(pixel_size * 0.15)))
    font_triple = (lg, md, sm)

    if view.kind == "idle":
        msg = (view.idle_message or "NO PLANES").strip() or "NO PLANES"
        if "SCAN" in msg.upper() or "SCANNING" in msg.upper():
            msg = "SCANNING ✈"
        draw = ImageDraw.Draw(img)
        f = _load_font(font_path, md)
        tw, th = _measure_text(msg, f)
        for _ in range(6):
            if tw <= w - 4:
                break
            md = max(8, md - 1)
            f = _load_font(font_path, md)
            tw, th = _measure_text(msg, f)
        draw.text(((w - tw) // 2, (h - th) // 2), msg, font=f, fill=fg, anchor=_TEXT_ANCHOR)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    ac = view.aircraft
    if ac is None:
        return render_lines_png(["—"], pixel_size, font_path, fg=fg, bg=bg)

    if view.kind == "flight":
        _draw_flight_contract(img, ac, font_path, font_triple, fg, bg, pixel_size)
    else:
        _draw_alert_contract(img, view.kind, ac, font_path, font_triple, fg, bg, pixel_size)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _draw_flight_contract(
    img: Image.Image,
    ac,
    font_path: str,
    font_triple: tuple[int, int, int],
    fg: Tuple[int, int, int],
    bg: Tuple[int, int, int],
    pixel_size: int,
) -> None:
    from app.formatter import (
        _format_speed_kt,
        callsign_for_matrix,
        format_altitude_k_ft,
        track_to_cardinal,
        vertical_motion_state,
    )

    boxes = _boxes_for_panel(FLIGHT_BOXES_64, pixel_size)
    callsign = callsign_for_matrix(ac)
    alt_t = format_altitude_k_ft(ac.altitude_ft)
    state_t = vertical_motion_state(ac)
    spd_t = _format_speed_kt(ac.speed_kt)
    dir_t = track_to_cardinal(ac.track_deg)

    draw_text_in_box(img, callsign, boxes["callsign"], font_path, font_triple, fg, bg)
    draw_text_in_box(img, alt_t, boxes["altitude"], font_path, font_triple, fg, bg)
    draw_text_in_box(img, state_t, boxes["state"], font_path, font_triple, fg, bg)
    draw_speed_direction_same_font(
        img, spd_t, dir_t, boxes["speed"], boxes["direction"], font_path, font_triple, fg, bg
    )


def _draw_alert_contract(
    img: Image.Image,
    kind: str,
    ac,
    font_path: str,
    font_triple: tuple[int, int, int],
    fg: Tuple[int, int, int],
    bg: Tuple[int, int, int],
    pixel_size: int,
) -> None:
    from app.formatter import (
        _format_speed_kt,
        callsign_for_matrix,
        format_altitude_k_ft,
        track_to_cardinal,
    )

    alert_labels = {
        "alert_low": "LOW ✈",
        "alert_overhead": "OVERHEAD ✈",
        "alert_emergency": "EMERGENCY",
        "alert_descent": "DESCENT",
        "alert_climb": "CLIMB",
    }
    label = alert_labels.get(kind, "ALERT")
    cs = callsign_for_matrix(ac)
    alt_t = format_altitude_k_ft(ac.altitude_ft)
    spd_t = _format_speed_kt(ac.speed_kt)
    dir_t = track_to_cardinal(ac.track_deg)

    boxes = _boxes_for_panel(ALERT_BOXES_64, pixel_size)
    draw_text_in_box(img, cs, boxes["callsign"], font_path, font_triple, fg, bg)
    draw_text_in_box(img, alt_t, boxes["altitude"], font_path, font_triple, fg, bg)
    draw_text_in_box(img, label, boxes["alert_label"], font_path, font_triple, fg, bg)
    draw_speed_direction_same_font(
        img, spd_t, dir_t, boxes["speed"], boxes["direction"], font_path, font_triple, fg, bg
    )
