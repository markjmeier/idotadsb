from app.aircraft_filter import (
    effective_distance_nm,
    filter_aircraft,
    filter_degraded,
    is_low_aircraft,
    pick_best,
    pick_best_v3,
    pick_low_aircraft_alert,
    pick_panel_alert,
    score_aircraft,
    top_n,
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
        debounce_seconds=2.0,
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


def test_scoring_prefers_stronger_rssi() -> None:
    s = _settings()
    a = Aircraft(hex="a", seen_s=1.0, rssi=-30.0, flight="X")
    b = Aircraft(hex="b", seen_s=1.0, rssi=-10.0, flight="Y")
    assert score_aircraft(b, s) > score_aircraft(a, s)


def test_pick_best() -> None:
    s = _settings()
    rows = [
        Aircraft(hex="a", seen_s=1.0, rssi=-40.0, flight="A"),
        Aircraft(hex="b", seen_s=1.0, rssi=-15.0, flight="B"),
    ]
    best = pick_best(rows, s)
    assert best is not None and best.hex == "b"


def test_top_n_order() -> None:
    s = _settings()
    rows = [
        Aircraft(hex="a", seen_s=1.0, rssi=-40.0),
        Aircraft(hex="b", seen_s=1.0, rssi=-20.0),
        Aircraft(hex="c", seen_s=1.0, rssi=-10.0),
    ]
    t = top_n(rows, s, 2)
    assert [x.hex for x in t] == ["c", "b"]


def test_low_altitude_alert() -> None:
    s = _settings(low_altitude_feet=5000)
    ac = Aircraft(hex="x", seen_s=1.0, altitude_ft=4000)
    hit = is_low_aircraft(ac, s)
    assert hit is not None and hit.reason == "altitude"


def test_high_rssi_alert() -> None:
    s = _settings(high_rssi_threshold=-10.0)
    ac = Aircraft(hex="x", seen_s=1.0, rssi=-5.0)
    hit = is_low_aircraft(ac, s)
    assert hit is not None and hit.reason == "rssi"


def test_pick_panel_alert_emergency_over_low() -> None:
    s = _settings()
    rows = [
        Aircraft(hex="em", squawk="7700", altitude_ft=3000, seen_s=1.0),
        Aircraft(hex="lo", altitude_ft=2000, seen_s=1.0),
    ]
    pa = pick_panel_alert(rows, s)
    assert pa is not None
    assert pa.kind == "emergency"
    assert pa.aircraft.hex == "em"


def test_pick_panel_rapid_descent() -> None:
    s = _settings(rapid_rate_fpm=2000)
    rows = [Aircraft(hex="x", baro_rate_fpm=-2500, seen_s=1.0)]
    pa = pick_panel_alert(rows, s)
    assert pa is not None and pa.kind == "descent"


def test_pick_low_aircraft_prefers_lower_altitude() -> None:
    s = _settings(low_altitude_feet=8000)
    rows = [
        Aircraft(hex="a", seen_s=1.0, altitude_ft=7000),
        Aircraft(hex="b", seen_s=1.0, altitude_ft=2000),
    ]
    alert = pick_low_aircraft_alert(rows, s)
    assert alert is not None and alert.aircraft.hex == "b"


def test_pick_best_v3_prefers_smaller_nm_over_rssi() -> None:
    s = _settings()
    rows = [
        Aircraft(hex="far", seen_s=1.0, rssi=-5.0, flight="A", distance_nm=50.0),
        Aircraft(hex="near", seen_s=1.0, rssi=-50.0, flight="B", distance_nm=2.0),
    ]
    assert pick_best_v3(rows, s) is not None
    assert pick_best_v3(rows, s).hex == "near"


def test_pick_best_v3_falls_back_without_distance() -> None:
    s = _settings()
    rows = [
        Aircraft(hex="a", seen_s=1.0, rssi=-40.0, flight="A"),
        Aircraft(hex="b", seen_s=1.0, rssi=-10.0, flight="B"),
    ]
    assert pick_best_v3(rows, s) is not None
    assert pick_best_v3(rows, s).hex == "b"


def test_top_n_v3_carousel_requires_callsign() -> None:
    s = _settings()
    rows = [
        Aircraft(hex="a", seen_s=1.0, rssi=-10.0, flight="", distance_nm=1.0),
        Aircraft(hex="b", seen_s=1.0, rssi=-40.0, flight="B", distance_nm=99.0),
    ]
    out = top_n_v3_carousel(rows, s, 5)
    assert [x.hex for x in out] == ["b"]


def test_top_n_v3_carousel_closest_by_distance() -> None:
    s = _settings()
    rows = [
        Aircraft(hex="far", seen_s=1.0, flight="F", distance_nm=50.0),
        Aircraft(hex="near", seen_s=1.0, flight="N", distance_nm=2.0),
        Aircraft(hex="mid", seen_s=1.0, flight="M", distance_nm=10.0),
    ]
    out = top_n_v3_carousel(rows, s, 2)
    assert [x.hex for x in out] == ["near", "mid"]


def test_top_n_v3_carousel_falls_back_to_score_without_distance() -> None:
    s = _settings()
    rows = [
        Aircraft(hex="a", seen_s=1.0, rssi=-40.0, flight="A"),
        Aircraft(hex="b", seen_s=1.0, rssi=-10.0, flight="B"),
    ]
    out = top_n_v3_carousel(rows, s, 5)
    assert [x.hex for x in out] == ["b", "a"]


def test_effective_distance_nm_haversine_when_home_set() -> None:
    s = _settings(home_lat=40.0, home_lon=-88.0)
    ac = Aircraft(hex="x", lat=40.1, lon=-88.0, seen_s=1.0)
    d = effective_distance_nm(ac, s)
    assert d is not None and d < 20.0
