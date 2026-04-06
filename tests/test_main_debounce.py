import time

from app.config import Settings
from app.main import UiState, _choose_closest_with_debounce
from app.models import Aircraft


def _s() -> Settings:
    return Settings(
        data_source_url="http://x",
        poll_interval_seconds=1.0,
        http_timeout_seconds=3.0,
        stale_seconds=10.0,
        stale_position_seconds=10.0,
        low_altitude_feet=5000,
        high_rssi_threshold=-10.0,
        rotate_top_n=3,
        v3_rotate_top_n=5,
        rotate_interval_seconds=3.0,
        display_mode="closest",
        enable_distance=False,
        home_lat=None,
        home_lon=None,
        log_level="INFO",
        display_backend="mock",
        idle_message="NO PLANES",
        debounce_seconds=5.0,
        rssi_weight=1.0,
        freshness_weight=2.0,
        callsign_bonus=5.0,
        position_bonus=3.0,
        distance_bonus_max=15.0,
        degraded_stale_seconds=60.0,
        rapid_rate_fpm=2000,
        idotmatrix_ble_address=None,
        idotmatrix_font_path=None,
        idotmatrix_render="canvas",
        idotmatrix_text_mode=1,
        idotmatrix_font_size=11,
        idotmatrix_pixel_size=64,
        idotmatrix_fg_rgb=(255, 255, 255),
        idotmatrix_bg_rgb=(0, 0, 0),
        display_min_refresh_seconds=4.0,
        idotmatrix_ble_upload_cap=32,
        idotmatrix_swap_fg_bg=False,
        idotmatrix_brightness_pct=None,
        idotmatrix_diy_reset=True,
        idotmatrix_diy_snap_colors=True,
        card_rotation_seconds=3.0,
        aircraft_hold_seconds=60.0,
        min_card_rotation_seconds=2.0,
        max_card_rotation_seconds=4.0,
        v3_enable_airline_colors=False,
        v3_default_text_rgb=(255, 255, 255),
        v3_default_accent_rgb=(180, 200, 255),
        v3_alert_rgb=(255, 80, 80),
        v3_climb_rgb=(255, 191, 0),
        v3_descent_rgb=(80, 200, 255),
        v3_level_rgb=(120, 255, 120),
        v3_unknown_airline_rgb=(200, 200, 200),
        enable_adsbdb_enrichment=False,
        adsbdb_api_base="https://api.adsbdb.com",
        enrichment_cache_ttl_seconds=1800.0,
        enrichment_refetch_interval_seconds=90.0,
        enrichment_min_lookup_interval_seconds=5.0,
        enrichment_http_timeout_seconds=3.0,
    )


def test_debounce_keeps_pinned_aircraft() -> None:
    settings = _s()
    state = UiState()
    now = time.monotonic()
    state.pinned_hex = "aaa111"
    state.last_pin_change_mono = now
    candidates = [
        Aircraft(hex="bbb222", seen_s=1.0, rssi=-10.0, flight="BEST"),
        Aircraft(hex="aaa111", seen_s=1.0, rssi=-50.0, flight="OLD"),
    ]
    chosen = _choose_closest_with_debounce(candidates, settings, state, now + 0.5)
    assert chosen is not None
    assert chosen.hex == "aaa111"


def test_debounce_expired_allows_new_best() -> None:
    settings = _s()
    state = UiState()
    t0 = time.monotonic()
    state.pinned_hex = "aaa111"
    state.last_pin_change_mono = t0
    candidates = [
        Aircraft(hex="bbb222", seen_s=1.0, rssi=-10.0, flight="BEST"),
        Aircraft(hex="aaa111", seen_s=1.0, rssi=-50.0, flight="OLD"),
    ]
    chosen = _choose_closest_with_debounce(candidates, settings, state, t0 + 10.0)
    assert chosen is not None
    assert chosen.hex == "bbb222"
