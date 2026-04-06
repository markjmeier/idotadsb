"""
Geometry of the PyPI ``idotmatrix`` Text module: each character is rasterized into a
fixed cell (see ``idotmatrix.modules.text.Text.image_width`` / ``image_height``).
On a square panel, static text is laid out in a row-major grid of those cells, then
the firmware paginates anything beyond one screen.

For **pixel-accurate** typography and multi-line flight cards, use
``IDOTMATRIX_RENDER=canvas`` (or ``raster``) — we draw with Pillow at full panel
resolution and upload via DIY mode instead of this cell grid.
"""

from __future__ import annotations

# idotmatrix Text._StringToBitmaps uses these bitmap dimensions per glyph.
BLE_TEXT_GLYPH_W = 16
BLE_TEXT_GLYPH_H = 32


def ble_text_grid_cells(panel_edge_px: int) -> tuple[int, int]:
    """How many 16×32 character cells fit on one edge of a square panel."""
    px = max(int(panel_edge_px), BLE_TEXT_GLYPH_W)
    cols = max(1, px // BLE_TEXT_GLYPH_W)
    rows = max(1, px // BLE_TEXT_GLYPH_H)
    return cols, rows


def ble_static_character_capacity(panel_edge_px: int) -> int:
    """Max characters visible on one static Text “page” (before firmware paginates)."""
    c, r = ble_text_grid_cells(panel_edge_px)
    return c * r


def ble_static_first_screen(text: str, *, panel_edge_px: int) -> str:
    """
    One screen of BLE static text: at most ``ble_static_character_capacity`` characters,
    word-aware (no mid-word cut when possible). Remaining text is dropped unless you use
    marquee mode or canvas render.
    """
    cap = ble_static_character_capacity(panel_edge_px)
    pages = wrap_words_into_pages(text, max_chars=cap)
    return pages[0] if pages else ""


def wrap_words_into_pages(text: str, *, max_chars: int) -> list[str]:
    """
    Split ``text`` into pages so each page is at most ``max_chars`` characters,
    preferring breaks between words. Long words are hard-split.

    Use with BLE static Text if you rotate pages in software; otherwise prefer
    marquee mode or the PIL/ DIY ``canvas`` renderer.
    """
    if max_chars < 1:
        return [text.strip() or ""]
    t = " ".join(text.split())
    if not t:
        return [""]
    if len(t) <= max_chars:
        return [t]

    words = t.split()
    pages: list[str] = []
    current: list[str] = []
    cur_len = 0

    def flush() -> None:
        nonlocal current, cur_len
        if current:
            pages.append(" ".join(current))
            current = []
            cur_len = 0

    for w in words:
        if len(w) > max_chars:
            flush()
            pages.extend(_hard_chunk(w, max_chars))
            continue
        add = len(w) + (1 if current else 0)
        if cur_len + add <= max_chars:
            current.append(w)
            cur_len += add
        else:
            flush()
            current = [w]
            cur_len = len(w)
    flush()
    return pages


def _hard_chunk(word: str, max_chars: int) -> list[str]:
    return [word[i : i + max_chars] for i in range(0, len(word), max_chars)]
