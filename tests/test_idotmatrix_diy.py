from app.idotmatrix_diy import (
    diy_upload_pixel_size,
    resize_png_to_square,
    snap_png_for_upload,
    snap_png_to_fg_bg,
    snap_png_to_nearest_palette,
)


def test_diy_upload_pixel_size() -> None:
    assert diy_upload_pixel_size(16) == 16
    assert diy_upload_pixel_size(32) == 32
    assert diy_upload_pixel_size(64) == 32
    assert diy_upload_pixel_size(64, ble_cap=64) == 64
    assert diy_upload_pixel_size(128, ble_cap=32) == 32


def test_resize_png_to_square() -> None:
    from app.matrix_canvas import render_lines_png
    from app.matrix_font import resolve_matrix_font_path

    font = resolve_matrix_font_path(None)
    if font is None:
        import pytest

        pytest.skip("no font")
    png64 = render_lines_png(["A", "B", "C", "D"], 64, font)
    png32 = resize_png_to_square(png64, 32)
    assert len(png32) > 100
    assert png32[:8] == b"\x89PNG\r\n\x1a\n"


def test_snap_png_to_fg_bg() -> None:
    from PIL import Image as PilImage
    import io

    im = PilImage.new("RGB", (4, 4), (0, 0, 0))
    im.putpixel((1, 1), (200, 200, 200))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    out = snap_png_to_fg_bg(buf.getvalue(), (255, 255, 255), (0, 0, 0))
    with PilImage.open(io.BytesIO(out)) as o:
        # Mid-gray is closer to white than to black in RGB distance.
        assert o.getpixel((1, 1)) == (255, 255, 255)
        assert o.getpixel((0, 0)) == (0, 0, 0)


def test_snap_png_to_nearest_palette_keeps_descent_blue() -> None:
    """Colored glyphs must not snap to black when only fg/bg were used before."""
    from PIL import Image as PilImage
    import io

    descent = (80, 200, 255)
    im = PilImage.new("RGB", (3, 1), (0, 0, 0))
    im.putpixel((0, 0), descent)
    im.putpixel((1, 0), (85, 198, 252))  # antialias edge near descent
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    palette = [(0, 0, 0), (255, 255, 255), descent]
    out = snap_png_to_nearest_palette(buf.getvalue(), palette)
    with PilImage.open(io.BytesIO(out)) as o:
        assert o.getpixel((0, 0)) == descent
        assert o.getpixel((1, 0)) == descent
        assert o.getpixel((2, 0)) == (0, 0, 0)


def test_snap_png_for_upload_palette_when_airline_colors_enabled() -> None:
    from tests.test_filter import _settings

    s = _settings(v3_enable_airline_colors=True)
    from PIL import Image as PilImage
    import io

    descent = s.v3_descent_rgb
    im = PilImage.new("RGB", (2, 1), (0, 0, 0))
    im.putpixel((0, 0), descent)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    out = snap_png_for_upload(buf.getvalue(), s, chrome_rgb=descent)
    with PilImage.open(io.BytesIO(out)) as o:
        assert o.getpixel((0, 0)) == descent


def test_snap_png_for_upload_chrome_snaps_airline_ink() -> None:
    """Per-frame chrome RGB must be in the snap palette so carrier ink is stable."""
    from tests.test_filter import _settings

    s = _settings(v3_enable_airline_colors=True)
    from PIL import Image as PilImage
    import io

    united = (0, 70, 160)
    im = PilImage.new("RGB", (2, 1), (0, 0, 0))
    im.putpixel((0, 0), (5, 68, 158))  # antialias-ish near United blue
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    out = snap_png_for_upload(buf.getvalue(), s, chrome_rgb=united)
    with PilImage.open(io.BytesIO(out)) as o:
        assert o.getpixel((0, 0)) == united
