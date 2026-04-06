from pathlib import Path

import pytest

from app.matrix_canvas import (
    FLIGHT_BOXES_64,
    FLIGHT_CARD_LIVE_ROUTE_64,
    draw_text_in_box,
    render_lines_png,
    render_panel_view,
)
from app.panel_view import PanelView


@pytest.fixture
def font_path(tmp_path: Path) -> str:
    # Minimal valid font: DejaVu often on dev machines; skip if missing
    from app.matrix_font import resolve_matrix_font_path

    p = resolve_matrix_font_path(None)
    if p is None:
        pytest.skip("no system font for canvas test")
    return p


def test_render_panel_view_flight_is_png(font_path: str) -> None:
    from app.models import Aircraft

    ac = Aircraft(hex="ab", flight="ZZ123", altitude_ft=18000, speed_kt=450.0, track_deg=90.0, baro_rate_fpm=1200)
    view = PanelView("flight", ac, None)
    png = render_panel_view(view, 64, font_path)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_layout_contract_live_route_boxes_tile_64() -> None:
    """Route variant of Card A partitions 64×64."""
    y = 0
    for key in ("callsign", "altitude", "route", "motion"):
        b = FLIGHT_CARD_LIVE_ROUTE_64[key]
        assert b[0] == 0 and b[2] == 64
        assert b[1] == y
        y += b[3]
    assert y == 64


def test_layout_contract_flight_boxes_tile_64() -> None:
    """Flight zones partition 64×64 without overlap."""
    c = FLIGHT_BOXES_64["callsign"]
    a = FLIGHT_BOXES_64["altitude"]
    st = FLIGHT_BOXES_64["state"]
    s = FLIGHT_BOXES_64["speed"]
    d = FLIGHT_BOXES_64["direction"]
    assert c == (0, 0, 64, 18)
    assert c[1] + c[3] == 18
    assert a == (0, 18, 64, 14)
    assert a[1] + a[3] == 32
    assert st == (0, 32, 64, 12)
    assert st[1] + st[3] == 44
    assert s == (0, 44, 32, 20)
    assert d == (32, 44, 32, 20)
    assert s[1] == d[1] and s[1] + s[3] == 64
    assert s[0] + s[2] == d[0] and d[0] + d[2] == 64


def test_draw_text_in_box_truncation_fallback(font_path: str) -> None:
    """When no priority size fits, smallest font + character truncation must not raise."""
    from PIL import Image

    img = Image.new("RGB", (64, 64), (0, 0, 0))
    draw_text_in_box(
        img,
        "VERYLONGCALLSIGN",
        (0, 20, 8, 8),
        font_path,
        (18, 14, 10),
        (255, 255, 255),
        (0, 0, 0),
    )


def test_draw_text_in_box_runs(font_path: str) -> None:
    from PIL import Image

    img = Image.new("RGB", (64, 64), (0, 0, 0))
    before = img.tobytes()
    draw_text_in_box(
        img,
        "ABC",
        (0, 0, 64, 20),
        font_path,
        (14, 11, 8),
        (255, 255, 255),
        (0, 0, 0),
    )
    assert img.tobytes() != before


def test_render_panel_view_alert_climb_is_png(font_path: str) -> None:
    from app.models import Aircraft

    ac = Aircraft(
        hex="a1b2c3",
        flight="DAL2310",
        altitude_ft=12000,
        speed_kt=380.0,
        track_deg=45.0,
        baro_rate_fpm=3200,
    )
    view = PanelView("alert_climb", ac, None)
    png = render_panel_view(view, 64, font_path)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_lines_png_is_png(font_path: str) -> None:
    png = render_lines_png(
        ["ABCD", "line2", "line3", "line4"],
        64,
        font_path,
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
