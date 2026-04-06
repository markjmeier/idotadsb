import pytest

from app.text_grid import (
    BLE_TEXT_GLYPH_H,
    BLE_TEXT_GLYPH_W,
    ble_static_character_capacity,
    ble_static_first_screen,
    ble_text_grid_cells,
    wrap_words_into_pages,
)


def test_ble_grid_64_panel() -> None:
    assert ble_text_grid_cells(64) == (64 // BLE_TEXT_GLYPH_W, 64 // BLE_TEXT_GLYPH_H)
    assert ble_static_character_capacity(64) == (64 // BLE_TEXT_GLYPH_W) * (
        64 // BLE_TEXT_GLYPH_H
    )


def test_ble_static_first_screen_fits_capacity() -> None:
    # 64×64 → 8 cells; first words that fit
    s = ble_static_first_screen("HELLO WORLD FROM ADSB", panel_edge_px=64)
    assert len(s) <= 8
    assert s == "HELLO"


def test_ble_static_first_screen_short_string_unchanged() -> None:
    assert ble_static_first_screen("ABC 12k", panel_edge_px=64) == "ABC 12k"


def test_ble_static_first_screen_truncates_long_idle() -> None:
    # 9 chars → first word-fitting page only on 64×64 (capacity 8)
    assert ble_static_first_screen("NO PLANES", panel_edge_px=64) == "NO"


def test_ble_grid_32_panel() -> None:
    c, r = ble_text_grid_cells(32)
    assert c * BLE_TEXT_GLYPH_W <= 32
    assert r * BLE_TEXT_GLYPH_H <= 32
    assert ble_static_character_capacity(32) == c * r


@pytest.mark.parametrize(
    ("text", "cap", "expected"),
    [
        ("", 8, [""]),
        ("a", 8, ["a"]),
        ("one two three", 8, ["one two", "three"]),
        ("abcdefghijklmnop", 8, ["abcdefgh", "ijklmnop"]),
        ("supercalifragilistic", 8, ["supercal", "ifragili", "stic"]),
    ],
)
def test_wrap_words_into_pages(text: str, cap: int, expected: list[str]) -> None:
    assert wrap_words_into_pages(text, max_chars=cap) == expected
