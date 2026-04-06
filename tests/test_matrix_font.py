import os

from app.matrix_font import resolve_matrix_font_path


def test_explicit_path_when_file_exists(tmp_path) -> None:
    p = tmp_path / "x.ttf"
    p.write_bytes(b"dummy")
    assert resolve_matrix_font_path(str(p)) == str(p.resolve())


def test_none_resolves_to_existing_file_or_none() -> None:
    """On dev machines with system fonts, expect a path; in minimal CI, None is ok."""
    r = resolve_matrix_font_path(None)
    assert r is None or os.path.isfile(r)
