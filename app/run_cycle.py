"""
One poll-cycle panel resolution: squawk latch → v3 carousel → :class:`PanelView`.

Keeps ``run_loop`` in ``main`` focused on I/O (fetch, sleep, display). State objects
are mutated in place to match the previous single-function behavior.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.aircraft_filter import (
    filter_aircraft,
    filter_degraded,
    find_aircraft_by_hex,
    is_emergency_squawk,
    pick_emergency_squawk_aircraft,
    top_n_v3_carousel,
)
from app.config import Settings
from app.enrichment import AdsbdbEnricher
from app.models import Aircraft
from app.panel_view import PanelView
from app.v3_logic import v3_active_card


@dataclass
class UiState:
    last_pushed_critical: str | None = None
    last_pushed_visual: str | None = None
    last_push_mono: float = 0.0
    pinned_hex: str | None = None
    rotate_index: int = 0
    last_top_signature: tuple[str, ...] = field(default_factory=tuple)
    last_rotate_tick_mono: float = 0.0


@dataclass
class V3DisplayState:
    """Live/Identity card alternation epoch for the aircraft currently on screen."""

    card_epoch_mono: float = 0.0


@dataclass
class SquawkLatchState:
    """Hold emergency squawk display until that aircraft clears 75/76/77 or leaves the feed."""

    latched_hex: str | None = None


def resolve_panel_view(
    all_ac: Sequence[Aircraft],
    settings: Settings,
    now: float,
    *,
    ui: UiState,
    v3: V3DisplayState,
    squawk: SquawkLatchState,
    enricher: AdsbdbEnricher | None,
) -> tuple[PanelView, bool]:
    """
    Compute the next panel from the current feed snapshot.

    Mutates ``ui``, ``v3``, and ``squawk`` like the original inline ``run_loop`` body.
    Callers must still run ``filter_aircraft`` / ``filter_degraded`` on ``all_ac`` first.
    """
    candidates = filter_aircraft(all_ac, settings, require_position=False)
    if not candidates:
        candidates = filter_degraded(all_ac, settings.degraded_stale_seconds)

    squawk_active = False
    view: PanelView
    is_alert = False

    if settings.squawk_alerting_enabled:
        lh = squawk.latched_hex
        if lh:
            ac_l = find_aircraft_by_hex(all_ac, lh)
            if ac_l is None or not is_emergency_squawk(ac_l):
                squawk.latched_hex = None
                lh = None
        if lh:
            ac_hold = find_aircraft_by_hex(all_ac, lh)
            if ac_hold is not None and is_emergency_squawk(ac_hold):
                view = PanelView("alert_squawk", ac_hold, None)
                is_alert = True
                squawk_active = True
        if not squawk_active:
            new_hit = pick_emergency_squawk_aircraft(all_ac, settings)
            if new_hit is not None:
                squawk.latched_hex = new_hit.hex
                view = PanelView("alert_squawk", new_hit, None)
                is_alert = True
                squawk_active = True

    if not squawk_active:
        if not candidates:
            view = PanelView("idle", None, settings.idle_message)
            is_alert = False
            ui.pinned_hex = None
            ui.last_top_signature = ()
            v3.card_epoch_mono = 0.0
        else:
            ranked_top = top_n_v3_carousel(candidates, settings, settings.v3_rotate_top_n)
            sig = tuple(a.hex for a in ranked_top)
            if sig != ui.last_top_signature:
                ui.last_top_signature = sig
                ui.rotate_index = 0
                ui.last_rotate_tick_mono = now
                v3.card_epoch_mono = now
            if not ranked_top:
                view = PanelView("idle", None, settings.idle_message)
                ui.pinned_hex = None
                ui.last_top_signature = ()
            else:
                if now - ui.last_rotate_tick_mono >= settings.rotate_interval_seconds:
                    ui.rotate_index = (ui.rotate_index + 1) % len(ranked_top)
                    ui.last_rotate_tick_mono = now
                    v3.card_epoch_mono = now
                ac = ranked_top[ui.rotate_index]
                ui.pinned_hex = ac.hex
                if enricher is not None:
                    for plane in ranked_top:
                        enricher.schedule_fetch(plane.hex, plane.flight)
                en = enricher.get_cached(ac.hex) if enricher is not None else None
                card = v3_active_card(
                    now,
                    v3.card_epoch_mono,
                    settings.card_rotation_seconds,
                    en,
                )
                view = PanelView(
                    "flight",
                    ac,
                    None,
                    flight_card=card,
                    enrichment=en,
                )
                is_alert = False

    return view, is_alert


def should_refresh_display(
    view: PanelView,
    ui: UiState,
    settings: Settings,
    now_mono: float,
) -> bool:
    """
    Whether the display should accept a new frame (critical change or visual debounce).
    """
    crit = view.critical_fingerprint()
    vis = view.visual_fingerprint()
    min_s = settings.display_min_refresh_seconds
    if crit != ui.last_pushed_critical:
        return True
    if vis != ui.last_pushed_visual and (
        min_s <= 0.0 or (now_mono - ui.last_push_mono) >= min_s
    ):
        return True
    return False
