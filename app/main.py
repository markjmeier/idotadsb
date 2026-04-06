from __future__ import annotations

import logging
import signal
import sys
import time
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

from app.aircraft_filter import (
    filter_aircraft,
    filter_degraded,
    pick_best,
    pick_panel_alert,
    rank_aircraft,
    top_n,
    top_n_v3_carousel,
)
from app.aircraft_source import fetch_aircraft_json
from app.config import Settings
from app.display import create_display
from app.enrichment import AdsbdbEnricher
from app.models import Aircraft
from app.panel_view import PanelView, panel_view_from_alert
from app.v3_logic import v3_active_card

logger = logging.getLogger(__name__)


@dataclass
class UiState:
    last_pushed_critical: str | None = None
    last_pushed_visual: str | None = None
    last_push_mono: float = 0.0
    pinned_hex: str | None = None
    last_pin_change_mono: float = 0.0
    rotate_index: int = 0
    last_top_signature: tuple[str, ...] = field(default_factory=tuple)
    last_rotate_tick_mono: float = 0.0


@dataclass
class V3DisplayState:
    """Live/Identity card alternation epoch for the aircraft currently on screen."""
    card_epoch_mono: float = 0.0


def _configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def _choose_closest_with_debounce(
    candidates: list[Aircraft],
    settings: Settings,
    state: UiState,
    now: float,
) -> Aircraft | None:
    best = pick_best(candidates, settings)
    if best is None:
        return None
    if (
        state.pinned_hex
        and (now - state.last_pin_change_mono) < settings.debounce_seconds
    ):
        pinned = [c for c in candidates if c.hex == state.pinned_hex]
        if pinned:
            return rank_aircraft(pinned, settings)[0][0]
    return best


def run_loop(settings: Settings, stop_flag: dict[str, bool]) -> None:
    display = create_display(settings)
    display.connect()
    state = UiState()
    state.last_rotate_tick_mono = time.monotonic()
    v3_state = V3DisplayState()
    enricher = AdsbdbEnricher(settings) if settings.display_mode == "v3" else None

    try:
        while not stop_flag.get("stop"):
            now = time.monotonic()
            try:
                raw = fetch_aircraft_json(settings.data_source_url, settings.http_timeout_seconds)
                candidates = filter_aircraft(raw, settings, require_position=False)
                if not candidates:
                    candidates = filter_degraded(raw, settings.degraded_stale_seconds)

                # v3: no full-screen alert takeovers (emergency-any-distance can be added later).
                panel_alert = (
                    None
                    if settings.display_mode == "v3"
                    else pick_panel_alert(candidates, settings)
                )

                if panel_alert is not None:
                    view = panel_view_from_alert(panel_alert)
                    is_alert = True
                    state.pinned_hex = panel_alert.aircraft.hex
                    state.last_pin_change_mono = now
                elif not candidates:
                    view = PanelView("idle", None, settings.idle_message)
                    is_alert = False
                    state.pinned_hex = None
                    v3_state.card_epoch_mono = 0.0
                elif settings.display_mode == "v3":
                    is_alert = False
                    ranked_top = top_n_v3_carousel(
                        candidates, settings, settings.v3_rotate_top_n
                    )
                    sig = tuple(a.hex for a in ranked_top)
                    if sig != state.last_top_signature:
                        state.last_top_signature = sig
                        state.rotate_index = 0
                        state.last_rotate_tick_mono = now
                        v3_state.card_epoch_mono = now
                    if not ranked_top:
                        view = PanelView("idle", None, settings.idle_message)
                        state.pinned_hex = None
                        state.last_top_signature = ()
                    else:
                        if now - state.last_rotate_tick_mono >= settings.rotate_interval_seconds:
                            state.rotate_index = (state.rotate_index + 1) % len(ranked_top)
                            state.last_rotate_tick_mono = now
                            v3_state.card_epoch_mono = now
                        ac = ranked_top[state.rotate_index]
                        state.pinned_hex = ac.hex
                        state.last_pin_change_mono = now
                        if enricher is not None:
                            for plane in ranked_top:
                                enricher.schedule_fetch(plane.hex, plane.flight)
                        en = enricher.get_cached(ac.hex) if enricher is not None else None
                        card = v3_active_card(
                            now,
                            v3_state.card_epoch_mono,
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
                elif settings.display_mode == "rotate":
                    is_alert = False
                    ranked_top = top_n(candidates, settings, settings.rotate_top_n)
                    sig = tuple(a.hex for a in ranked_top)
                    if sig != state.last_top_signature:
                        state.last_top_signature = sig
                        state.rotate_index = 0
                        state.last_rotate_tick_mono = now
                    if not ranked_top:
                        view = PanelView("idle", None, settings.idle_message)
                    else:
                        if now - state.last_rotate_tick_mono >= settings.rotate_interval_seconds:
                            state.rotate_index = (state.rotate_index + 1) % len(ranked_top)
                            state.last_rotate_tick_mono = now
                        ac = ranked_top[state.rotate_index]
                        view = PanelView("flight", ac, None)
                        state.pinned_hex = ac.hex
                        state.last_pin_change_mono = now
                else:
                    is_alert = False
                    chosen = _choose_closest_with_debounce(candidates, settings, state, now)
                    if chosen is None:
                        view = PanelView("idle", None, settings.idle_message)
                        state.pinned_hex = None
                    else:
                        view = PanelView("flight", chosen, None)
                        if state.pinned_hex != chosen.hex:
                            state.pinned_hex = chosen.hex
                            state.last_pin_change_mono = now

                crit = view.critical_fingerprint()
                vis = view.visual_fingerprint()
                min_s = settings.display_min_refresh_seconds
                now_mono = time.monotonic()

                if crit != state.last_pushed_critical:
                    should_push = True
                elif vis != state.last_pushed_visual and (
                    min_s <= 0.0 or (now_mono - state.last_push_mono) >= min_s
                ):
                    should_push = True
                else:
                    should_push = False

                if should_push:
                    display.show_panel(view, alert=is_alert)
                    state.last_pushed_critical = crit
                    state.last_pushed_visual = vis
                    state.last_push_mono = now_mono
            except Exception:
                logger.exception("cycle error; continuing next poll")

            time.sleep(max(0.05, settings.poll_interval_seconds))
    finally:
        display.close()


def main() -> None:
    if load_dotenv is not None:
        load_dotenv()
    settings = Settings.from_env()
    _configure_logging(settings.log_level)

    stop_flag: dict[str, bool] = {"stop": False}

    def _handle_stop(*_args: object) -> None:
        stop_flag["stop"] = True

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    logger.info("starting flight display (backend=%s)", settings.display_backend)
    run_loop(settings, stop_flag)
    logger.info("shutdown complete")


if __name__ == "__main__":
    main()
