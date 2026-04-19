"""Tests for ``app.run_cycle`` panel resolution and display refresh gating."""

from __future__ import annotations

from app.models import Aircraft
from app.panel_view import PanelView
from app.run_cycle import (
    SquawkLatchState,
    UiState,
    V3DisplayState,
    resolve_panel_view,
    should_refresh_display,
)

from tests.helpers import make_test_settings


def test_resolve_idle_when_empty_feed() -> None:
    s = make_test_settings(squawk_alerting_enabled=False)
    ui = UiState()
    ui.last_rotate_tick_mono = 100.0
    v3 = V3DisplayState()
    sq = SquawkLatchState()
    view, is_alert = resolve_panel_view([], s, 200.0, ui=ui, v3=v3, squawk=sq, enricher=None)
    assert view.kind == "idle"
    assert is_alert is False


def test_resolve_flight_when_one_eligible_aircraft() -> None:
    s = make_test_settings(squawk_alerting_enabled=False, stale_seconds=60.0)
    rows = [
        Aircraft(hex="abc123", flight="UAL123", seen_s=1.0, altitude_ft=10000, speed_kt=300.0, track_deg=90.0),
    ]
    ui = UiState()
    ui.last_rotate_tick_mono = 0.0
    v3 = V3DisplayState()
    sq = SquawkLatchState()
    view, is_alert = resolve_panel_view(rows, s, 10.0, ui=ui, v3=v3, squawk=sq, enricher=None)
    assert view.kind == "flight"
    assert view.aircraft is not None
    assert view.aircraft.hex == "abc123"
    assert is_alert is False


def test_resolve_squawk_alert_takes_priority() -> None:
    s = make_test_settings(squawk_alerting_enabled=True, stale_seconds=60.0)
    rows = [
        Aircraft(
            hex="abc123",
            flight="UAL123",
            seen_s=1.0,
            squawk="7700",
            altitude_ft=10000,
        ),
    ]
    ui = UiState()
    ui.last_rotate_tick_mono = 0.0
    v3 = V3DisplayState()
    sq = SquawkLatchState()
    view, is_alert = resolve_panel_view(rows, s, 10.0, ui=ui, v3=v3, squawk=sq, enricher=None)
    assert view.kind == "alert_squawk"
    assert is_alert is True
    assert sq.latched_hex == "abc123"


def test_should_refresh_on_critical_change() -> None:
    s = make_test_settings(display_min_refresh_seconds=60.0)
    ui = UiState(last_pushed_critical="flight:aaa", last_pushed_visual="x", last_push_mono=0.0)
    v = PanelView("flight", Aircraft(hex="bbb", seen_s=1.0), None)
    assert should_refresh_display(v, ui, s, now_mono=1.0) is True


def test_should_refresh_visual_after_min_interval() -> None:
    s = make_test_settings(display_min_refresh_seconds=4.0)
    ui = UiState(
        last_pushed_critical="flight:aaa",
        last_pushed_visual="old_vis",
        last_push_mono=0.0,
    )
    v = PanelView("flight", Aircraft(hex="aaa", altitude_ft=20000, seen_s=1.0), None)
    assert should_refresh_display(v, ui, s, now_mono=3.0) is False
    assert should_refresh_display(v, ui, s, now_mono=5.0) is True


def test_should_refresh_always_when_min_refresh_zero() -> None:
    s = make_test_settings(display_min_refresh_seconds=0.0)
    ui = UiState(
        last_pushed_critical="flight:aaa",
        last_pushed_visual="old_vis",
        last_push_mono=0.0,
    )
    v = PanelView("flight", Aircraft(hex="aaa", altitude_ft=50000, seen_s=1.0), None)
    assert should_refresh_display(v, ui, s, now_mono=0.1) is True
