from __future__ import annotations

import io
import logging
from typing import Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from app.matrix_theme import MatrixColorProfile
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

# Emergency squawk 7500/7600/7700: four equal bands (ALERT / SQUAWK / code / flight id).
SQUAWK_ALERT_BOXES_64: dict[str, tuple[int, int, int, int]] = {
    "l1": (0, 0, 64, 16),
    "l2": (0, 16, 64, 16),
    "l3": (0, 32, 64, 16),
    "l4": (0, 48, 64, 16),
}

# version3spec Card A: 3 lines (no route), 64px tall.
FLIGHT_CARD_LIVE_64: dict[str, tuple[int, int, int, int]] = {
    "callsign": (0, 0, 64, 22),
    "altitude": (0, 22, 64, 20),
    "motion": (0, 42, 64, 22),
}
# Card A with ADSBDB route between altitude and motion row (taller route band for → + larger type).
FLIGHT_CARD_LIVE_ROUTE_64: dict[str, tuple[int, int, int, int]] = {
    "callsign": (0, 0, 64, 14),
    "altitude": (0, 14, 64, 12),
    "route": (0, 26, 64, 18),
    "motion": (0, 44, 64, 20),
}
FLIGHT_CARD_IDENTITY_64: dict[str, tuple[int, int, int, int]] = {
    "callsign": (0, 0, 64, 22),
    "line2": (0, 22, 64, 21),
    "line3": (0, 43, 64, 21),
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


def _matrix_profile(
    fg: Tuple[int, int, int],
    bg: Tuple[int, int, int],
    color_profile: MatrixColorProfile | None,
) -> MatrixColorProfile:
    if color_profile is not None:
        return color_profile
    return MatrixColorProfile(
        default_fg=fg,
        default_accent_rgb=fg,
        bg=bg,
        enable_airline_colors=False,
        unknown_airline_rgb=fg,
        alert_fg=fg,
        climb_rgb=fg,
        descent_rgb=fg,
        level_rgb=fg,
    )


def _callsign_accent_rgb(ac, profile: MatrixColorProfile) -> Tuple[int, int, int]:
    from app.airline_colors import resolve_airline_accent_rgb
    from app.formatter import callsign_for_matrix

    raw = (ac.flight or "").strip() or callsign_for_matrix(ac)
    return resolve_airline_accent_rgb(
        raw,
        unknown_rgb=profile.unknown_airline_rgb,
        enable=profile.enable_airline_colors,
    )


def _motion_state_fg(ac, profile: MatrixColorProfile) -> Tuple[int, int, int]:
    from app.formatter import vertical_motion_state

    st = vertical_motion_state(ac)
    if st == "CLIMB":
        return profile.climb_rgb
    if st == "DESC":
        return profile.descent_rgb
    return profile.level_rgb


def draw_text_in_box(
    img: Image.Image,
    text: str,
    box: tuple[int, int, int, int],
    font_path: str,
    font_priority: tuple[int, int, int],
    fg: Tuple[int, int, int],
    bg: Tuple[int, int, int],
    *,
    h_align: str = "center",
    pad_left: int = 0,
    fixed_font_px: int | None = None,
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

    chosen: ImageFont.FreeTypeFont | ImageFont.ImageFont
    display = t
    if fixed_font_px is not None:
        font = _load_font(font_path, fixed_font_px)
        while len(display) > 0:
            tw, th = _measure_text(display, font)
            if tw <= bw and th <= bh:
                break
            display = display[:-1]
        chosen = font
    else:
        chosen_loop: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
        for sz in sizes:
            font = _load_font(font_path, sz)
            tw, th = _measure_text(display, font)
            if tw <= bw and th <= bh:
                chosen_loop = font
                break

        if chosen_loop is None:
            font = _load_font(font_path, sizes[2])
            display = t
            while len(display) > 0:
                tw, th = _measure_text(display, font)
                if tw <= bw and th <= bh:
                    break
                display = display[:-1]
            chosen_loop = font
        chosen = chosen_loop

    tw, th = _measure_text(display, chosen)
    if h_align == "left":
        px = min(max(0, pad_left), max(0, bw - tw))
    else:
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
    alert_panel: bool = False,
    color_profile: MatrixColorProfile | None = None,
) -> bytes:
    """
    Flight / alert layouts: 64×64 contract zones (scaled for other sizes).
    """
    profile = _matrix_profile(fg, bg, color_profile)
    w = h = pixel_size
    img = Image.new("RGB", (w, h), profile.bg)

    lg = max(11, min(22, int(pixel_size * 0.30)))
    md = max(9, min(16, int(pixel_size * 0.21)))
    sm = max(7, min(12, int(pixel_size * 0.15)))
    font_triple = (lg, md, sm)
    default_fg = profile.default_fg

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
        draw.text(((w - tw) // 2, (h - th) // 2), msg, font=f, fill=default_fg, anchor=_TEXT_ANCHOR)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    ac = view.aircraft
    if ac is None:
        return render_lines_png(["—"], pixel_size, font_path, fg=default_fg, bg=profile.bg)

    if view.kind == "flight":
        if view.flight_card == "live":
            _draw_flight_card_live(
                img, ac, view.enrichment, font_path, font_triple, profile, pixel_size
            )
        elif view.flight_card == "identity":
            _draw_flight_card_identity(img, ac, view, font_path, font_triple, profile, pixel_size)
        else:
            _draw_flight_contract(img, ac, font_path, font_triple, profile, pixel_size)
    elif view.kind == "alert_squawk":
        _draw_squawk_alert(img, ac, font_path, font_triple, profile, pixel_size, alert_panel=alert_panel)
    else:
        _draw_flight_contract(img, ac, font_path, font_triple, profile, pixel_size)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _draw_route_band(
    img: Image.Image,
    route_text: str,
    box: tuple[int, int, int, int],
    font_path: str,
    font_triple: tuple[int, int, int],
    fg: Tuple[int, int, int],
    bg: Tuple[int, int, int],
) -> None:
    """Largest font (lg→md→sm) that fits full route string; centered. Keeps Unicode → from ADSBDB."""
    bx, by, bw, bh = box
    if bw <= 0 or bh <= 0 or not route_text:
        return
    lg, md, sm = font_triple
    chosen_font = None
    display = route_text
    for fs in (lg, md, sm):
        font = _load_font(font_path, fs)
        tw, th = _measure_text(display, font)
        if tw <= bw and th <= bh:
            chosen_font = font
            break
    if chosen_font is None:
        font = _load_font(font_path, sm)
        display = route_text
        while len(display) > 0:
            tw, th = _measure_text(display, font)
            if tw <= bw and th <= bh:
                break
            display = display[:-1]
        chosen_font = font
    tw, th = _measure_text(display, chosen_font)
    cell = Image.new("RGB", (bw, bh), bg)
    draw = ImageDraw.Draw(cell)
    px = max(0, (bw - tw) // 2)
    py = max(0, (bh - th) // 2)
    draw.text((px, py), display, font=chosen_font, fill=fg, anchor=_TEXT_ANCHOR)
    img.paste(cell, (bx, by))


def _motion_row_pad_left(pixel_size: int) -> int:
    """A few pixels inset so CLB/DSC/LVL sit left; frees perceived space for speed + cardinal."""
    return max(1, int(round(3 * pixel_size / 64.0)))


def _draw_flight_card_live(
    img: Image.Image,
    ac,
    enrichment,
    font_path: str,
    font_triple: tuple[int, int, int],
    profile: MatrixColorProfile,
    pixel_size: int,
) -> None:
    from app.formatter import callsign_for_matrix, format_altitude_k_ft, format_live_card_motion_line

    route = (
        (enrichment.route or "").strip()
        if enrichment is not None and getattr(enrichment, "route", None)
        else ""
    )
    template = FLIGHT_CARD_LIVE_ROUTE_64 if route else FLIGHT_CARD_LIVE_64
    boxes = _boxes_for_panel(template, pixel_size)
    bg = profile.bg
    cs = callsign_for_matrix(ac)
    accent = _callsign_accent_rgb(ac, profile)
    draw_text_in_box(img, cs, boxes["callsign"], font_path, font_triple, accent, bg)
    draw_text_in_box(
        img, format_altitude_k_ft(ac.altitude_ft), boxes["altitude"], font_path, font_triple, profile.default_fg, bg
    )
    if route:
        _draw_route_band(
            img,
            route,
            boxes["route"],
            font_path,
            font_triple,
            profile.default_accent_rgb,
            bg,
        )
    draw_text_in_box(
        img,
        format_live_card_motion_line(ac, compact=True),
        boxes["motion"],
        font_path,
        font_triple,
        _motion_state_fg(ac, profile),
        bg,
        h_align="left",
        pad_left=_motion_row_pad_left(pixel_size),
    )


def _draw_flight_card_identity(
    img: Image.Image,
    ac,
    view: PanelView,
    font_path: str,
    font_triple: tuple[int, int, int],
    profile: MatrixColorProfile,
    pixel_size: int,
) -> None:
    from app.formatter import callsign_for_matrix, matrix_route_display

    en = view.enrichment
    pair = en.identity_two_lines() if en is not None else None
    if pair is None:
        _draw_flight_card_live(img, ac, en, font_path, font_triple, profile, pixel_size)
        return
    boxes = _boxes_for_panel(FLIGHT_CARD_IDENTITY_64, pixel_size)
    bg = profile.bg
    cs = callsign_for_matrix(ac)
    accent = _callsign_accent_rgb(ac, profile)
    draw_text_in_box(img, cs, boxes["callsign"], font_path, font_triple, accent, bg)
    draw_text_in_box(
        img, matrix_route_display(pair[0]), boxes["line2"], font_path, font_triple, profile.default_fg, bg
    )
    draw_text_in_box(
        img, matrix_route_display(pair[1]), boxes["line3"], font_path, font_triple, profile.default_fg, bg
    )


def _draw_flight_contract(
    img: Image.Image,
    ac,
    font_path: str,
    font_triple: tuple[int, int, int],
    profile: MatrixColorProfile,
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
    bg = profile.bg
    fg = profile.default_fg
    callsign = callsign_for_matrix(ac)
    alt_t = format_altitude_k_ft(ac.altitude_ft)
    state_t = vertical_motion_state(ac)
    spd_t = _format_speed_kt(ac.speed_kt)
    dir_t = track_to_cardinal(ac.track_deg)

    accent = _callsign_accent_rgb(ac, profile)
    draw_text_in_box(img, callsign, boxes["callsign"], font_path, font_triple, accent, bg)
    draw_text_in_box(img, alt_t, boxes["altitude"], font_path, font_triple, fg, bg)
    draw_text_in_box(img, state_t, boxes["state"], font_path, font_triple, fg, bg)
    draw_speed_direction_same_font(img, spd_t, dir_t, boxes["speed"], boxes["direction"], font_path, font_triple, fg, bg)


def _draw_squawk_alert(
    img: Image.Image,
    ac,
    font_path: str,
    font_triple: tuple[int, int, int],
    profile: MatrixColorProfile,
    pixel_size: int,
    *,
    alert_panel: bool,
) -> None:
    from app.formatter import callsign_for_matrix

    fg = profile.alert_fg if alert_panel else profile.default_fg
    bg = profile.bg
    sq = (ac.squawk or "").strip() or "---"
    lines = ["ALERT", "SQUAWK", sq, callsign_for_matrix(ac)]
    boxes = _boxes_for_panel(SQUAWK_ALERT_BOXES_64, pixel_size)
    for key, text in zip(("l1", "l2", "l3", "l4"), lines, strict=True):
        draw_text_in_box(img, text, boxes[key], font_path, font_triple, fg, bg)
