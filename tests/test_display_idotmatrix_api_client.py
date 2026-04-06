from app.display_idotmatrix_api_client import idotmatrix_panel_edge_pixels


def test_idotmatrix_panel_edge_pixels_buckets() -> None:
    assert idotmatrix_panel_edge_pixels(64) == 64
    assert idotmatrix_panel_edge_pixels(48) == 64
    assert idotmatrix_panel_edge_pixels(47) == 32
    assert idotmatrix_panel_edge_pixels(32) == 32
    assert idotmatrix_panel_edge_pixels(24) == 32
    assert idotmatrix_panel_edge_pixels(23) == 16
    assert idotmatrix_panel_edge_pixels(16) == 16
