from app.aircraft_filter import (
    effective_distance_nm,
    filter_aircraft,
    filter_degraded,
    find_aircraft_by_hex,
    is_emergency_squawk,
    pick_best,
    pick_best_v3,
    pick_emergency_squawk_aircraft,
    rank_aircraft,
    score_aircraft,
    top_n_v3_carousel,
)
from app.config import Settings
from app.models import Aircraft


def _settings(**kwargs: object) -> Settings:
    base = dict(
        data_source_url="http://x",
        poll_interval_seconds=1.0,
        http_timeout_seconds=3.0,
        stale_seconds=10.0,
        stale_position_seconds=10.0,
        v3_rotate_top_n=5,
        rotate_interval_seconds=3.0,
        enable_distance=False,
        home_lat=None,
        home_lon=None,
        log_level="INFO",
        display_backend="mock",
        idle_message="NO PLANES",
        rssi_weight=1.0,
        freshness_weight=2.0,
        callsign_bonus=5.0,
        position_bonus=3.0,
        distance_bonus_max=15.0,
        degraded_stale_seconds=60.0,
        squawk_alerting_enabled=True,
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
        quiet_hours_enabled=False,
        quiet_hours_start_hour=23,
        quiet_hours_end_hour=7,
        quiet_hours_timezone="",
        quiet_hours_poll_interval_seconds=60.0,
        quiet_hours_brightness_pct=0,
    )
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def test_filter_fresh_seen() -> None:
    s = _settings(stale_seconds=10.0)
    rows = [
        Aircraft(hex="a", seen_s=2.0),
        Aircraft(hex="b", seen_s=20.0),
    ]
    out = filter_aircraft(rows, s)
    assert [x.hex for x in out] == ["a"]


def test_filter_degraded() -> None:
    rows = [Aircraft(hex="a", seen_s=30.0)]
    out = filter_degraded(rows, 60.0)
    assert len(out) == 1


def test_pick_best() -> None:
    s = _settings()
    rows = [
        Aircraft(hex="a", rssi=-30.0, seen_s=1.0),
        Aircraft(hex="b", rssi=-10.0, seen_s=1.0),
    ]
    best = pick_best(rows, s)
    assert best is not None and best.hex == "b"


def test_rank_orders_by_score() -> None:
    s = _settings()
    rows = [
        Aircraft(hex="w", rssi=-40.0, seen_s=1.0),
        Aircraft(hex="z", rssi=-10.0, seen_s=1.0),
    ]
    r = rank_aircraft(rows, s)
    assert [x[0].hex for x in r] == ["z", "w"]


def test_pick_best_v3_prefers_smaller_nm_over_rssi() -> None:
    rows = [
        Aircraft(hex="far", flight="FAR1", rssi=-5.0, seen_s=1.0, distance_nm=50.0),
        Aircraft(hex="near", flight="NR1", rssi=-30.0, seen_s=1.0, distance_nm=5.0),
    ]
    s = _settings()
    assert pick_best_v3(rows, s) is not None
    assert pick_best_v3(rows, s).hex == "near"


def test_pick_best_v3_falls_back_without_distance() -> None:
    rows = [
        Aircraft(hex="a", flight="A1", rssi=-30.0, seen_s=1.0),
        Aircraft(hex="b", flight="B1", rssi=-10.0, seen_s=1.0),
    ]
    s = _settings()
    assert pick_best_v3(rows, s) is not None
    assert pick_best_v3(rows, s).hex == "b"


def test_top_n_v3_carousel_requires_callsign() -> None:
    s = _settings(v3_rotate_top_n=3)
    rows = [
        Aircraft(hex="a", flight="A1", seen_s=1.0, distance_nm=10.0),
        Aircraft(hex="b", seen_s=1.0, distance_nm=5.0),
    ]
    top = top_n_v3_carousel(rows, s, 3)
    assert len(top) == 1 and top[0].hex == "a"


def test_is_emergency_squawk() -> None:
    assert is_emergency_squawk(Aircraft(hex="a", squawk="7700"))
    assert is_emergency_squawk(Aircraft(hex="a", squawk="7500"))
    assert not is_emergency_squawk(Aircraft(hex="a", squawk="1200"))
    assert not is_emergency_squawk(Aircraft(hex="a"))


def test_find_aircraft_by_hex() -> None:
    rows = [Aircraft(hex="abc123", seen_s=1.0)]
    assert find_aircraft_by_hex(rows, "ABC123") is not None
    assert find_aircraft_by_hex(rows, "abc123") is not None
    assert find_aircraft_by_hex(rows, "none") is None


def test_pick_emergency_squawk_respects_enabled() -> None:
    rows = [Aircraft(hex="e", flight="E1", squawk="7700", seen_s=1.0, rssi=-20.0)]
    assert pick_emergency_squawk_aircraft(rows, _settings(squawk_alerting_enabled=True)) is not None
    assert pick_emergency_squawk_aircraft(rows, _settings(squawk_alerting_enabled=False)) is None


def test_pick_emergency_squawk_prefers_score() -> None:
    rows = [
        Aircraft(hex="a", flight="A1", squawk="7700", seen_s=1.0, rssi=-30.0),
        Aircraft(hex="b", flight="B1", squawk="7700", seen_s=1.0, rssi=-5.0),
    ]
    s = _settings()
    hit = pick_emergency_squawk_aircraft(rows, s)
    assert hit is not None and hit.hex == "b"


def test_effective_distance_nm_from_json() -> None:
    s = _settings(home_lat=40.0, home_lon=-88.0)
    ac = Aircraft(hex="x", lat=41.0, lon=-88.0, seen_s=1.0)
    d = effective_distance_nm(ac, s)
    assert d is not None and d > 0
