from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _candidates_for_platform() -> list[str]:
    if sys.platform == "darwin":
        return [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
            "/System/Library/Fonts/Supplemental/Courier New.ttf",
        ]
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        return [
            os.path.join(windir, "Fonts", "arial.ttf"),
            os.path.join(windir, "Fonts", "segoeui.ttf"),
        ]
    # Linux / Raspberry Pi OS
    return [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    ]


def resolve_matrix_font_path(explicit: str | None) -> str | None:
    """
    Pillow needs a real font file. idotmatrix defaults to ./fonts/Rain-DRM3.otf,
    which is usually missing — use env IDOTMATRIX_FONT_PATH or common OS paths.
    """
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return str(p.resolve())
        logger.warning("IDOTMATRIX_FONT_PATH is not a file: %s", explicit)

    repo_font = Path(__file__).resolve().parent.parent / "fonts" / "DejaVuSans.ttf"
    if repo_font.is_file():
        return str(repo_font)

    for path in _candidates_for_platform():
        if os.path.isfile(path):
            logger.debug("Using matrix font fallback: %s", path)
            return path

    return None
