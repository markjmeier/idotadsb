from __future__ import annotations

from app.models import Aircraft


def callsign_or_hex(ac: Aircraft) -> str:
    if ac.flight:
        return ac.flight
    return ac.hex.upper()


# Feeders sometimes put vertical-state text in `flight`; matrix top row should stay a real id.
_MATRIX_BOGUS_FLIGHT = frozenset(
    {
        "CLIMB",
        "DESC",
        "DESCENT",
        "LEVEL",
        "GND",
        "GROUND",
        "UP",
        "DOWN",
    }
)


def callsign_for_matrix(ac: Aircraft) -> str:
    """Callsign for panel top band; hex if `flight` is an obvious non-callsign token."""
    f = ac.flight
    if f and f.strip().upper() in _MATRIX_BOGUS_FLIGHT:
        return ac.hex.upper()
    return callsign_or_hex(ac)


def format_altitude_k(altitude_ft: int | None) -> str:
    if altitude_ft is None:
        return "---"
    a = abs(int(altitude_ft))
    thousands = a / 1000.0
    if a % 1000 == 0:
        return f"{a // 1000}k"
    s = f"{thousands:.1f}".rstrip("0").rstrip(".")
    return f"{s}k"


def format_altitude_k_ft(altitude_ft: int | None) -> str:
    """Panel / matrix: thousands-style altitude plus FT suffix."""
    if altitude_ft is None:
        return "---"
    return f"{format_altitude_k(altitude_ft)} FT"


def track_to_arrow(track_deg: float | None) -> str | None:
    if track_deg is None:
        return None
    t = float(track_deg) % 360.0
    if t < 45 or t >= 315:
        return "↑"
    if 45 <= t < 135:
        return "→"
    if 135 <= t < 225:
        return "↓"
    return "←"


def track_to_cardinal(track_deg: float | None) -> str:
    """layoutcontract.md v2: N, NE, E, SE, S, SW, W, NW from track (45° sectors)."""
    if track_deg is None:
        return "---"
    t = float(track_deg) % 360.0
    dirs = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    idx = int((t + 22.5) // 45) % 8
    return dirs[idx]


def vertical_motion_state(ac: Aircraft) -> str:
    """layoutcontract.md v2: CLIMB / DESC / LEVEL from vertical rate (±200 fpm)."""
    v = ac.vertical_rate_fpm
    if v is None:
        return "LEVEL"
    if v > 200:
        return "CLIMB"
    if v < -200:
        return "DESC"
    return "LEVEL"


def _format_speed_kt(speed_kt: float | None) -> str:
    if speed_kt is None:
        return "---"
    return f"{int(round(float(speed_kt)))}kt"


def _format_speed_k(speed_kt: float | None) -> str:
    """Compact speed for tight matrix rows (saves one glyph vs `kt`)."""
    if speed_kt is None:
        return "---"
    return f"{int(round(float(speed_kt)))}k"


_MOTION_COMPACT = {"CLIMB": "CLB", "DESC": "DSC", "LEVEL": "LVL"}


def format_live_card_motion_line(ac: Aircraft, *, compact: bool = False) -> str:
    """Card A bottom row: CLIMB 299kt NE — or compact CLB 299k NE for narrow bands."""
    st = vertical_motion_state(ac)
    if compact:
        st = _MOTION_COMPACT.get(st, st)
        spd = _format_speed_k(ac.speed_kt)
    else:
        spd = _format_speed_kt(ac.speed_kt)
    card = track_to_cardinal(ac.track_deg)
    return f"{st} {spd} {card}"


def matrix_route_display(text: str) -> str:
    """Trim padding for matrix cells; keep API arrow (→) for route readability."""
    if not text:
        return text
    return text.strip()


def _format_track_line(ac: Aircraft) -> str:
    if ac.track_deg is not None:
        return track_to_cardinal(ac.track_deg)
    return "HDG ---"


def _format_rssi_seen_line(ac: Aircraft) -> str:
    parts: list[str] = []
    if ac.rssi is not None:
        parts.append(f"RSSI {ac.rssi:.0f}")
    else:
        parts.append("RSSI ---")
    if ac.seen_s is not None:
        parts.append(f"{float(ac.seen_s):.0f}s")
    return "  ".join(parts)


def format_closest_lines(ac: Aircraft) -> str:
    """Four-line dashboard for 64×64 (or mock logs); still readable when flattened for text mode."""
    line1 = callsign_or_hex(ac)
    alt = format_altitude_k(ac.altitude_ft)
    spd = _format_speed_kt(ac.speed_kt)
    line2 = f"{alt}  {spd}"
    line3 = _format_track_line(ac)
    line4 = _format_rssi_seen_line(ac)
    return "\n".join([line1, line2, line3, line4])


def format_low_alert_lines(ac: Aircraft) -> str:
    line1 = "LOW ✈"
    line2 = "ALERT"
    line3 = callsign_or_hex(ac)
    line4 = format_altitude_k(ac.altitude_ft)
    return "\n".join([line1, line2, line3, line4])


def format_idle(idle_message: str) -> str:
    m = idle_message.strip() or "NO PLANES"
    return "\n".join([m, "", "listening", "ADS-B"])


def format_closest_marquee(ac: Aircraft) -> str:
    """Single line for idotmatrix Text; use marquee mode on 64×64 — static mode paginates ~8 glyphs wide."""
    cs = callsign_or_hex(ac)
    alt = format_altitude_k(ac.altitude_ft)
    spd = _format_speed_kt(ac.speed_kt)
    parts = [cs, alt, spd]
    if ac.track_deg is not None:
        parts.append(track_to_cardinal(ac.track_deg))
    return " ".join(parts)


def format_low_alert_marquee(ac: Aircraft) -> str:
    """One line; short tokens for small static grids / marquee."""
    return f"LOW {callsign_or_hex(ac)} {format_altitude_k(ac.altitude_ft)}"


def format_idle_marquee(idle_message: str) -> str:
    return idle_message.strip() or "NO PLANES"


def vertical_rate_display(ac: Aircraft) -> str:
    """displayspec.md: >+200 → ↑####, <-200 → ↓####, else —."""
    v = ac.vertical_rate_fpm
    if v is None:
        return "—"
    if v > 200:
        return f"↑{abs(int(v))}"
    if v < -200:
        return f"↓{abs(int(v))}"
    return "—"


def flight_status_suffix(ac: Aircraft) -> str:
    """Tiny proximity hint (optional); keep empty if not notable."""
    if ac.rssi is not None and ac.rssi > -5.0:
        return " ●"
    return ""
