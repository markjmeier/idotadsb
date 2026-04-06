from __future__ import annotations

import math
def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles."""
    r_earth_nm = 3440.065  # nautical miles (mean Earth radius)
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return r_earth_nm * c


def distance_score_nm(distance_nm: float, max_bonus: float, cap_nm: float = 50.0) -> float:
    """Higher score when closer; zero beyond cap_nm."""
    if distance_nm < 0 or cap_nm <= 0:
        return 0.0
    if distance_nm >= cap_nm:
        return 0.0
    closeness = 1.0 - (distance_nm / cap_nm)
    return max_bonus * closeness


def clamp_seen(seen: float | None, default: float = 999.0) -> float:
    if seen is None:
        return default
    return float(seen)
