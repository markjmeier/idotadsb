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
from app.models import Aircraft

from tests.helpers import make_test_settings as _settings


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
