from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from app.config import Settings
from app.models import Aircraft
from app.utils import clamp_seen, distance_score_nm, haversine_nm


def is_fresh(ac: Aircraft, stale_seconds: float) -> bool:
    return clamp_seen(ac.seen_s) <= stale_seconds


def has_fresh_position(ac: Aircraft, stale_position_seconds: float) -> bool:
    if ac.lat is None or ac.lon is None:
        return False
    sp = ac.seen_pos_s
    if sp is None:
        return False
    return clamp_seen(sp, default=999.0) <= stale_position_seconds


def filter_aircraft(
    aircraft: Iterable[Aircraft],
    settings: Settings,
    *,
    require_position: bool = False,
) -> List[Aircraft]:
    """Primary filter: fresh `seen` and optional fresh position."""
    stale = settings.stale_seconds
    stale_pos = settings.stale_position_seconds
    out: List[Aircraft] = []
    for ac in aircraft:
        if not is_fresh(ac, stale):
            continue
        if require_position and not has_fresh_position(ac, stale_pos):
            continue
        out.append(ac)
    return out


def filter_degraded(aircraft: Iterable[Aircraft], degraded_stale_seconds: float) -> List[Aircraft]:
    """Fallback when strict filter yields nothing."""
    return [ac for ac in aircraft if is_fresh(ac, degraded_stale_seconds)]


def score_aircraft(ac: Aircraft, settings: Settings) -> float:
    """
    Higher is better. RSSI is negative dBm; closer to 0 is stronger.
    """
    rssi = ac.rssi if ac.rssi is not None else -100.0
    seen = clamp_seen(ac.seen_s)
    freshness = max(0.0, settings.stale_seconds - min(seen, settings.stale_seconds))
    callsign = settings.callsign_bonus if ac.flight else 0.0
    position = settings.position_bonus if (ac.lat is not None and ac.lon is not None) else 0.0
    dist_part = 0.0
    if settings.enable_distance and settings.home_lat is not None and settings.home_lon is not None:
        if ac.lat is not None and ac.lon is not None:
            d = haversine_nm(settings.home_lat, settings.home_lon, ac.lat, ac.lon)
            dist_part = distance_score_nm(d, settings.distance_bonus_max)
    return (
        settings.rssi_weight * rssi
        + settings.freshness_weight * freshness
        + callsign
        + position
        + dist_part
    )


def rank_aircraft(aircraft: Sequence[Aircraft], settings: Settings) -> List[Tuple[Aircraft, float]]:
    scored = [(ac, score_aircraft(ac, settings)) for ac in aircraft]
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored


def pick_best(aircraft: Sequence[Aircraft], settings: Settings) -> Aircraft | None:
    ranked = rank_aircraft(aircraft, settings)
    if not ranked:
        return None
    return ranked[0][0]


def effective_distance_nm(ac: Aircraft, settings: Settings) -> float | None:
    """Distance from receiver: JSON `nm` (or similar) if present, else haversine from HOME_*."""
    if ac.distance_nm is not None and ac.distance_nm >= 0.0:
        return float(ac.distance_nm)
    if (
        settings.home_lat is not None
        and settings.home_lon is not None
        and ac.lat is not None
        and ac.lon is not None
    ):
        return haversine_nm(settings.home_lat, settings.home_lon, ac.lat, ac.lon)
    return None


def pick_best_v3(aircraft: Sequence[Aircraft], settings: Settings) -> Aircraft | None:
    """
    v3 “closest” target: prefer smallest distance_nm (from feed or HOME_* + position).
    Falls back to RSSI-weighted pick_best when no candidate has distance.
    """
    seq = list(aircraft)
    if not seq:
        return None
    with_dist: list[tuple[Aircraft, float]] = []
    for ac in seq:
        d = effective_distance_nm(ac, settings)
        if d is not None:
            with_dist.append((ac, d))
    if not with_dist:
        return pick_best(seq, settings)
    with_dist.sort(key=lambda t: (t[1], -score_aircraft(t[0], settings)))
    return with_dist[0][0]


def _v3_carousel_eligible(ac: Aircraft) -> bool:
    """v3 rotate + ADSBDB: need ICAO hex and a callsign from the feed."""
    h = (ac.hex or "").strip()
    f = (ac.flight or "").strip()
    return bool(h and f)


def top_n_v3_carousel(aircraft: Sequence[Aircraft], settings: Settings, n: int) -> List[Aircraft]:
    """
    Up to n closest identified aircraft (hex + callsign) for v3 carousel.
    Uses distance_nm or HOME_* haversine; if no distance is known, falls back to score ranking.
    """
    if n <= 0:
        return []
    eligible = [ac for ac in aircraft if _v3_carousel_eligible(ac)]
    if not eligible:
        return []
    with_dist: list[tuple[Aircraft, float]] = []
    for ac in eligible:
        d = effective_distance_nm(ac, settings)
        if d is not None:
            with_dist.append((ac, d))
    if with_dist:
        with_dist.sort(key=lambda t: (t[1], -score_aircraft(t[0], settings)))
        return [ac for ac, _ in with_dist[:n]]
    ranked = rank_aircraft(eligible, settings)
    return [ac for ac, _ in ranked[:n]]


_EMERGENCY_SQUAWKS = frozenset({"7500", "7600", "7700"})


def is_emergency_squawk(ac: Aircraft) -> bool:
    if not ac.squawk:
        return False
    return ac.squawk in _EMERGENCY_SQUAWKS


def find_aircraft_by_hex(rows: Sequence[Aircraft], hex_lower: str) -> Aircraft | None:
    key = hex_lower.strip().lower()
    for ac in rows:
        if ac.hex == key:
            return ac
    return None


def pick_emergency_squawk_aircraft(all_rows: Sequence[Aircraft], settings: Settings) -> Aircraft | None:
    """
    Best-scoring aircraft in ``all_rows`` with squawk 7500/7600/7700, or None.
    Respects ``settings.squawk_alerting_enabled``.
    """
    if not settings.squawk_alerting_enabled:
        return None
    best: Aircraft | None = None
    best_score = -1e9
    for ac in all_rows:
        if is_emergency_squawk(ac):
            sc = score_aircraft(ac, settings)
            if best is None or sc > best_score:
                best = ac
                best_score = sc
    return best
