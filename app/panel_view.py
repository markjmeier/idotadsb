from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.enrichment import EnrichmentData
from app.formatter import (
    callsign_or_hex,
    format_closest_marquee,
    format_idle_marquee,
    vertical_motion_state,
)
from app.models import Aircraft

PanelKind = Literal["flight", "idle", "alert_squawk"]


@dataclass(frozen=True)
class PanelView:
    """What to draw on the pixel panel (canvas) or compress for text marquee."""

    kind: PanelKind
    aircraft: Aircraft | None = None
    idle_message: str | None = None
    flight_card: Literal["live", "identity"] | None = None
    enrichment: EnrichmentData | None = None

    def critical_fingerprint(self) -> str:
        """Identity / mode change → push immediately (new aircraft, idle vs flight, alert type)."""
        if self.kind == "idle":
            return f"idle:{(self.idle_message or '').strip().lower()}"
        if self.aircraft is None:
            return self.kind
        if self.kind == "alert_squawk":
            sq = (self.aircraft.squawk or "").strip()
            return f"alert_squawk:{self.aircraft.hex}:{sq}"
        return f"{self.kind}:{self.aircraft.hex}"

    def visual_fingerprint(self) -> str:
        """
        Quantized fields that match what the user sees — excludes RSSI and raw floats
        so ADS-B jitter does not spam BLE on every 1s poll.
        """
        if self.kind == "idle":
            return (self.idle_message or "NO PLANES").strip().lower()
        ac = self.aircraft
        if ac is None:
            return self.kind

        def q_alt(ft: int | None) -> str:
            if ft is None:
                return "na"
            return str((int(ft) // 250) * 250)

        def q_spd(kt: float | None) -> str:
            if kt is None:
                return "na"
            return str(int(round(float(kt) / 15.0)) * 15)

        def q_cardinal_sector(d: float | None) -> str:
            """Match layout v2 direction cell (45° sectors)."""
            if d is None:
                return "na"
            t = float(d) % 360.0
            return str(int((t + 22.5) // 45) % 8)

        if self.kind == "alert_squawk":
            return f"sq|{ac.squawk or 'na'}|{callsign_or_hex(ac).strip().upper()}"

        if self.kind == "flight":
            parts: list[str] = []
            if self.flight_card:
                parts.append(self.flight_card)
            parts.extend(
                [
                    vertical_motion_state(ac),
                    q_alt(ac.altitude_ft),
                    q_spd(ac.speed_kt),
                    q_cardinal_sector(ac.track_deg),
                ]
            )
            if self.flight_card == "identity" and self.enrichment is not None:
                pair = self.enrichment.identity_two_lines()
                if pair:
                    parts.extend(pair)
            if self.flight_card == "live" and self.enrichment is not None:
                en = self.enrichment
                extra = (en.route or en.aircraft_type or en.airline or "").strip()
                if extra:
                    parts.append(extra)
            return "|".join(parts)

        return self.kind


def panel_view_to_marquee(view: PanelView) -> str:
    """Single-line BLE text fallback."""
    if view.kind == "idle":
        return format_idle_marquee(view.idle_message or "NO PLANES")
    if view.aircraft is None:
        return "—"
    ac = view.aircraft
    if view.kind == "flight":
        if view.flight_card == "identity" and view.enrichment is not None:
            pair = view.enrichment.identity_two_lines()
            if pair:
                return f"{callsign_or_hex(ac)} {pair[0]} {pair[1]}"
        return format_closest_marquee(ac)
    if view.kind == "alert_squawk":
        sq = (ac.squawk or "").strip()
        cs = callsign_or_hex(ac)
        return f"ALERT SQ{sq} {cs}".strip() if sq else f"ALERT {cs}"
    return callsign_or_hex(ac)


def panel_view_mock_text(view: PanelView) -> str:
    """Multi-line log for mock backend (matrix layout bands)."""
    from app.formatter import (
        _format_speed_kt,
        callsign_for_matrix,
        format_altitude_k_ft,
        format_live_card_motion_line,
        matrix_route_display,
        track_to_cardinal,
        vertical_motion_state,
    )

    if view.kind == "idle":
        return view.idle_message or "NO PLANES"
    if view.aircraft is None:
        return "—"
    ac = view.aircraft
    if view.kind == "alert_squawk":
        sq = (ac.squawk or "").strip() or "---"
        return f"ALERT\nSQUAWK\n{sq}\n{callsign_for_matrix(ac)}"
    if view.kind == "flight":
        cs = callsign_for_matrix(ac)
        if view.flight_card == "identity" and view.enrichment is not None:
            pair = view.enrichment.identity_two_lines()
            if pair:
                return f"{cs}\n{matrix_route_display(pair[0])}\n{matrix_route_display(pair[1])}"
        if view.flight_card == "live":
            alt = format_altitude_k_ft(ac.altitude_ft)
            motion = format_live_card_motion_line(ac, compact=True)
            en = view.enrichment
            if en is not None and (en.route or "").strip():
                return f"{cs}\n{alt}\n{matrix_route_display(en.route)}\n{motion}"
            return f"{cs}\n{alt}\n{motion}"
        alt = format_altitude_k_ft(ac.altitude_ft)
        st = vertical_motion_state(ac)
        spd = _format_speed_kt(ac.speed_kt)
        card = track_to_cardinal(ac.track_deg)
        return f"{cs}\n{alt}\n{st}\n{spd}  {card}"
    return f"ALERT\n{callsign_or_hex(ac)}"
