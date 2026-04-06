from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _strip_str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    return str(v).strip() or None


def _opt_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _opt_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Aircraft:
    """Normalized aircraft record; only `hex` is required."""

    hex: str
    flight: str | None = None
    lat: float | None = None
    lon: float | None = None
    altitude_ft: int | None = None
    speed_kt: float | None = None
    track_deg: float | None = None
    rssi: float | None = None
    seen_s: float | None = None
    seen_pos_s: float | None = None
    baro_rate_fpm: int | None = None
    geom_rate_fpm: int | None = None
    squawk: str | None = None
    # Some feeders / SkyAware forks add great-circle distance from the receiver (nautical miles).
    distance_nm: float | None = None

    @property
    def vertical_rate_fpm(self) -> int | None:
        """Prefer baro_rate; fall back to geom_rate (readsb / dump1090)."""
        if self.baro_rate_fpm is not None:
            return self.baro_rate_fpm
        return self.geom_rate_fpm

    @staticmethod
    def from_dump1090_row(row: Mapping[str, Any]) -> Aircraft | None:
        """Parse a single object from readsb/dump1090 `aircraft.json` aircraft array."""
        hex_raw = row.get("hex")
        if hex_raw is None:
            return None
        hex_s = str(hex_raw).strip().lower()
        if not hex_s:
            return None

        flight = _strip_str(row.get("flight"))

        lat = _opt_float(row.get("lat"))
        lon = _opt_float(row.get("lon"))

        alt: int | None = None
        for key in ("alt_baro", "alt_geom", "altitude"):
            if key in row and row[key] not in (None, "ground"):
                alt = _opt_int(row.get(key))
                if alt is not None:
                    break

        gs = _opt_float(row.get("gs"))
        track = _opt_float(row.get("track"))
        rssi = _opt_float(row.get("rssi"))
        seen = _opt_float(row.get("seen"))
        seen_pos = _opt_float(row.get("seen_pos"))
        baro_rate = _opt_int(row.get("baro_rate"))
        geom_rate = _opt_int(row.get("geom_rate"))
        squawk_raw = row.get("squawk")
        squawk: str | None = None
        if squawk_raw is not None and squawk_raw != "":
            squawk = str(squawk_raw).strip().replace(" ", "") or None

        distance_nm: float | None = None
        for dkey in ("nm", "dist_nm", "distance_nm", "dst_nm"):
            if dkey in row:
                dv = _opt_float(row.get(dkey))
                if dv is not None and dv >= 0.0:
                    distance_nm = dv
                    break

        return Aircraft(
            hex=hex_s,
            flight=flight,
            lat=lat,
            lon=lon,
            altitude_ft=alt,
            speed_kt=gs,
            track_deg=track,
            rssi=rssi,
            seen_s=seen,
            seen_pos_s=seen_pos,
            baro_rate_fpm=baro_rate,
            geom_rate_fpm=geom_rate,
            squawk=squawk,
            distance_nm=distance_nm,
        )
