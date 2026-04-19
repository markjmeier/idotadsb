from __future__ import annotations

import logging
import signal
import sys
import time

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

from app.aircraft_source import fetch_aircraft_json
from app.config import Settings
from app.display import create_display
from app.enrichment import AdsbdbEnricher
from app.quiet_hours import current_local_hour, in_quiet_hours_hour
from app.run_cycle import (
    SquawkLatchState,
    UiState,
    V3DisplayState,
    resolve_panel_view,
    should_refresh_display,
)

logger = logging.getLogger(__name__)


def _quiet_hours_now(settings: Settings) -> bool:
    if not settings.quiet_hours_enabled:
        return False
    tz = settings.quiet_hours_timezone.strip()
    h = current_local_hour(tz or None)
    return in_quiet_hours_hour(h, settings.quiet_hours_start_hour, settings.quiet_hours_end_hour)


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
                view, is_alert = resolve_panel_view(
                    all_ac,
                    settings,
                    now,
                    ui=state,
                    v3=v3_state,
                    squawk=squawk_state,
                    enricher=enricher,
                )

                now_mono = time.monotonic()
                if should_refresh_display(view, state, settings, now_mono):
                    display.show_panel(view, alert=is_alert)
                    state.last_pushed_critical = view.critical_fingerprint()
                    state.last_pushed_visual = view.visual_fingerprint()
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
