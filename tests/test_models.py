from app.models import Aircraft


def test_from_dump1090_minimal() -> None:
    row = {"hex": "A1B2C3"}
    ac = Aircraft.from_dump1090_row(row)
    assert ac is not None
    assert ac.hex == "a1b2c3"
    assert ac.flight is None


def test_from_dump1090_full() -> None:
    row = {
        "hex": "abc",
        "flight": "UAL123  ",
        "lat": 40.0,
        "lon": -88.0,
        "alt_baro": 18825,
        "gs": 420.5,
        "track": 90.0,
        "rssi": -15.2,
        "seen": 0.4,
        "seen_pos": 0.8,
    }
    ac = Aircraft.from_dump1090_row(row)
    assert ac is not None
    assert ac.flight == "UAL123"
    assert ac.altitude_ft == 18825
    assert ac.speed_kt == 420.5
    assert ac.track_deg == 90.0


def test_from_dump1090_invalid() -> None:
    assert Aircraft.from_dump1090_row({}) is None


def test_vertical_rate_prefers_baro() -> None:
    a = Aircraft(hex="a", baro_rate_fpm=100, geom_rate_fpm=999)
    assert a.vertical_rate_fpm == 100


def test_from_dump1090_rates_squawk() -> None:
    row = {"hex": "aa", "baro_rate": -1500, "squawk": "7700"}
    ac = Aircraft.from_dump1090_row(row)
    assert ac is not None
    assert ac.baro_rate_fpm == -1500
    assert ac.squawk == "7700"


def test_from_dump1090_distance_nm() -> None:
    row = {"hex": "ab", "nm": 12.5}
    ac = Aircraft.from_dump1090_row(row)
    assert ac is not None
    assert ac.distance_nm == 12.5
