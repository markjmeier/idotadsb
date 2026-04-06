from __future__ import annotations

from typing import Literal

from app.enrichment import EnrichmentData


def v3_active_card(
    now_mono: float,
    selected_at_mono: float,
    rotation_seconds: float,
    enrichment: EnrichmentData | None,
) -> Literal["live", "identity"]:
    """Alternate Live / Identity when any enrichment fields exist."""
    if enrichment is None or not enrichment.has_identity_card():
        return "live"
    rot = max(0.5, float(rotation_seconds))
    slot = int((now_mono - selected_at_mono) // rot) % 2
    return "live" if slot == 0 else "identity"
