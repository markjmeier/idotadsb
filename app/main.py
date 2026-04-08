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
    find_aircraft_by_hex,
    is_emergency_squawk,
    pick_emergency_squawk_aircraft,
    top_n_v3_carousel,
)
from app.aircraft_source import fetch_aircraft_json
from app.config import Settings
from app.display import create_display
from app.enrichment import AdsbdbEnricher
from app.panel_view import PanelView
from app.quiet_hours import current_local_hour, in_quiet_hours_hour
from app.v3_logic import v3_active_card

logger = logging.getLogger(__name__)


def _quiet_hours_now(settings: Settings) -> bool:
    if not settings.quiet_hours_enabled:
        return False
    tz = settings.quiet_hours_timezone.strip()
    h = current_local_hour(tz or None)
    return in_quiet_hours_hour(h, settings.quiet_hours_start_hour, settings.quiet_hours_end_hour)


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


def _configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def run_loop(settings: Settings, stop_flag: dict[str, bool]) -> None:
    display = create_display(settings)
    display.connect()
    state = UiState()
    state.last_rotate_tick_mono = time.monotonic()
    v3_state = V3DisplayState()
    squawk_state = SquawkLatchState()
    enricher = AdsbdbEnricher(settings) if settings.enable_adsbdb_enrichment else None
    was_quiet = False

    try:
        while not stop_flag.get("stop"):
            quiet = _quiet_hours_now(settings)
            if quiet != was_quiet:
                if quiet:
                    logger.info("quiet hours: pausing feeder and enrichment; dimming display")
                else:
                    logger.info("quiet hours ended: resuming normal operation")
                display.set_quiet_hours_active(quiet)
                was_quiet = quiet
                state.last_pushed_critical = None
                state.last_pushed_visual = None
            if quiet:
                time.sleep(max(0.05, settings.quiet_hours_poll_interval_seconds))
                continue

            now = time.monotonic()
            try:
                all_ac = fetch_aircraft_json(settings.data_source_url, settings.http_timeout_seconds)
                candidates = filter_aircraft(all_ac, settings, require_position=False)
                if not candidates:
                    candidates = filter_degraded(all_ac, settings.degraded_stale_seconds)

                squawk_active = False
                view: PanelView
                is_alert = False

                if settings.squawk_alerting_enabled:
                    lh = squawk_state.latched_hex
                    if lh:
                        ac_l = find_aircraft_by_hex(all_ac, lh)
                        if ac_l is None or not is_emergency_squawk(ac_l):
                            squawk_state.latched_hex = None
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
                            squawk_state.latched_hex = new_hit.hex
                            view = PanelView("alert_squawk", new_hit, None)
                            is_alert = True
                            squawk_active = True

                if not squawk_active:
                    if not candidates:
                        view = PanelView("idle", None, settings.idle_message)
                        is_alert = False
                        state.pinned_hex = None
                        state.last_top_signature = ()
                        v3_state.card_epoch_mono = 0.0
                    else:
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
                            is_alert = False

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
