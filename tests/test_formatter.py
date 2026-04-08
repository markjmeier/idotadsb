import pytest

from app.formatter import (
    callsign_for_matrix,
    callsign_or_hex,
    format_altitude_k,
    format_altitude_k_ft,
    format_closest_lines,
    format_closest_marquee,
    format_idle,
    format_idle_marquee,
    format_live_card_motion_line,
    matrix_route_display,
    track_to_arrow,
    track_to_cardinal,
    vertical_motion_state,
    vertical_rate_display,
)
from app.models import Aircraft


@pytest.mark.parametrize(
    ("ft", "expected"),
    [
        (4900, "4.9k"),
        (18825, "18.8k"),
        (32000, "32k"),
        (800, "0.8k"),
        (None, "---"),
    ],
)
def test_format_altitude_k(ft: int | None, expected: str) -> None:
    assert format_altitude_k(ft) == expected


def test_format_altitude_k_ft() -> None:
    assert format_altitude_k_ft(4900) == "4.9k FT"
    assert format_altitude_k_ft(18000) == "18k FT"
    assert format_altitude_k_ft(None) == "---"


def test_callsign_or_hex() -> None:
    ac = Aircraft(hex="a1b2c3", flight="UAL123")
    assert callsign_or_hex(ac) == "UAL123"
    ac2 = Aircraft(hex="abcdef")
    assert callsign_or_hex(ac2) == "ABCDEF"


def test_callsign_for_matrix_falls_back_when_flight_is_motion_token() -> None:
    ac = Aircraft(hex="a1b2c3", flight="CLIMB")
    assert callsign_for_matrix(ac) == "A1B2C3"
    ok = Aircraft(hex="a1b2c3", flight="DAL90")
    assert callsign_for_matrix(ok) == "DAL90"


def test_track_to_arrow() -> None:
    assert track_to_arrow(0) == "↑"
    assert track_to_arrow(90) == "→"
    assert track_to_arrow(180) == "↓"
    assert track_to_arrow(270) == "←"
    assert track_to_arrow(None) is None


@pytest.mark.parametrize(
    ("deg", "expected"),
    [
        (0, "N"),
        (22, "N"),
        (23, "NE"),
        (45, "NE"),
        (90, "E"),
        (180, "S"),
        (270, "W"),
        (337, "NW"),
        (360, "N"),
        (None, "---"),
    ],
)
def test_track_to_cardinal(deg: float | None, expected: str) -> None:
    assert track_to_cardinal(deg) == expected


def test_format_live_card_motion_line_compact() -> None:
    ac = Aircraft(hex="a", baro_rate_fpm=None, speed_kt=420.0, track_deg=90.0)
    assert format_live_card_motion_line(ac) == "LEVEL 420kt E"
    assert format_live_card_motion_line(ac, compact=True) == "LVL 420k E"


def test_matrix_route_display_strips() -> None:
    assert matrix_route_display("  EWR→ORD  ") == "EWR→ORD"
    assert matrix_route_display("LGA→CLT") == "LGA→CLT"


def test_vertical_motion_state() -> None:
    base = dict(hex="a")
    assert vertical_motion_state(Aircraft(**base, baro_rate_fpm=None)) == "LEVEL"
    assert vertical_motion_state(Aircraft(**base, baro_rate_fpm=0)) == "LEVEL"
    assert vertical_motion_state(Aircraft(**base, baro_rate_fpm=200)) == "LEVEL"
    assert vertical_motion_state(Aircraft(**base, baro_rate_fpm=201)) == "CLIMB"
    assert vertical_motion_state(Aircraft(**base, baro_rate_fpm=-200)) == "LEVEL"
    assert vertical_motion_state(Aircraft(**base, baro_rate_fpm=-201)) == "DESC"


def test_format_closest_lines() -> None:
    ac = Aircraft(
        hex="abc",
        flight="JBU816",
        altitude_ft=22000,
        track_deg=45.0,
        speed_kt=400.0,
        rssi=-10.0,
        seen_s=0.2,
    )
    assert format_closest_lines(ac) == (
        "JBU816\n"
        "22k  400kt\n"
        "NE\n"
        "RSSI -10  0s"
    )


def test_format_idle() -> None:
    assert format_idle("NO PLANES") == "NO PLANES\n\nlistening\nADS-B"
    assert format_idle("  SCANNING  ") == "SCANNING\n\nlistening\nADS-B"


def test_format_closest_marquee_single_line() -> None:
    ac = Aircraft(
        hex="abc",
        flight="JBU816",
        altitude_ft=22000,
        speed_kt=400.0,
        track_deg=45.0,
    )
    assert format_closest_marquee(ac) == "JBU816 22k 400kt NE"
    ac2 = Aircraft(hex="abc", flight="X", altitude_ft=1000, speed_kt=None, track_deg=None)
    assert format_closest_marquee(ac2) == "X 1k ---"


def test_format_idle_marquee() -> None:
    assert format_idle_marquee("NO PLANES") == "NO PLANES"


@pytest.mark.parametrize(
    ("baro", "geom", "expected"),
    [
        (1500, None, "↑1500"),
        (-2400, None, "↓2400"),
        (500, -5000, "↑500"),
        (None, -500, "↓500"),
        (50, None, "—"),
        (None, None, "—"),
    ],
)
def test_vertical_rate_display(baro: int | None, geom: int | None, expected: str) -> None:
    ac = Aircraft(hex="a", baro_rate_fpm=baro, geom_rate_fpm=geom)
    assert vertical_rate_display(ac) == expected
