from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.panel_view import PanelView


@dataclass(frozen=True)
class MatrixColorProfile:
    """Per-frame colors for matrix canvas (version3spec + alerts)."""

    default_fg: tuple[int, int, int]
    default_accent_rgb: tuple[int, int, int]
    bg: tuple[int, int, int]
    enable_airline_colors: bool
    unknown_airline_rgb: tuple[int, int, int]
    alert_fg: tuple[int, int, int]
    climb_rgb: tuple[int, int, int]
    descent_rgb: tuple[int, int, int]
    level_rgb: tuple[int, int, int]

    @staticmethod
    def neutral(settings: Settings) -> MatrixColorProfile:
        return MatrixColorProfile(
            default_fg=settings.idotmatrix_fg_rgb,
            default_accent_rgb=settings.idotmatrix_fg_rgb,
            bg=settings.idotmatrix_bg_rgb,
            enable_airline_colors=False,
            unknown_airline_rgb=settings.idotmatrix_fg_rgb,
            alert_fg=settings.idotmatrix_fg_rgb,
            climb_rgb=settings.idotmatrix_fg_rgb,
            descent_rgb=settings.idotmatrix_fg_rgb,
            level_rgb=settings.idotmatrix_fg_rgb,
        )

    @staticmethod
    def from_settings(settings: Settings) -> MatrixColorProfile:
        if not settings.v3_enable_airline_colors:
            return MatrixColorProfile.neutral(settings)
        return MatrixColorProfile(
            default_fg=settings.v3_default_text_rgb,
            default_accent_rgb=settings.v3_default_accent_rgb,
            bg=settings.idotmatrix_bg_rgb,
            enable_airline_colors=True,
            unknown_airline_rgb=settings.v3_unknown_airline_rgb,
            alert_fg=settings.v3_alert_rgb,
            climb_rgb=settings.v3_climb_rgb,
            descent_rgb=settings.v3_descent_rgb,
            level_rgb=settings.v3_level_rgb,
        )


def snap_chrome_rgb_for_panel(
    settings: Settings, view: PanelView, *, alert_panel: bool
) -> tuple[int, int, int] | None:
    """
    DIY snap palette: exact RGB used for the callsign (or alert text) on this frame.
    Per-airline accents must be listed here only — not every entry in AIRLINE_COLORS —
    or similar blues snap to the wrong airline after quantization.
    """
    if not settings.v3_enable_airline_colors:
        return None
    if view.aircraft is None:
        return None
    prof = MatrixColorProfile.from_settings(settings)
    if alert_panel:
        return prof.alert_fg
    from app.airline_colors import resolve_airline_accent_rgb
    from app.formatter import callsign_for_matrix

    ac = view.aircraft
    raw = (ac.flight or "").strip() or callsign_for_matrix(ac)
    return resolve_airline_accent_rgb(
        raw,
        unknown_rgb=prof.unknown_airline_rgb,
        enable=True,
    )
