from __future__ import annotations

import re

# version3spec.md — airline-inspired display colors (RGB).
AIRLINE_COLORS: dict[str, tuple[int, int, int]] = {
    "UAL": (0, 70, 160),
    "AAL": (0, 102, 180),
    "DAL": (200, 30, 60),
    "JBU": (0, 110, 220),
    "SWA": (255, 180, 0),
    "ASA": (0, 120, 90),
    "FFT": (0, 160, 60),
    "NKS": (255, 220, 0),
    "MXY": (255, 120, 0),
    "RPA": (110, 110, 160),
    "EDV": (120, 140, 180),
    "ASH": (150, 50, 160),
    "SKW": (100, 130, 180),
    "JIA": (70, 120, 200),
    "GJS": (120, 150, 210),
    "FDX": (120, 60, 180),
    "UPS": (110, 80, 40),
    "ABX": (200, 60, 60),
    "GTI": (210, 160, 0),
    "5X": (120, 60, 180),
    "EJA": (150, 150, 150),
    "LXJ": (180, 180, 180),
    "VJA": (200, 200, 200),
    "PJC": (170, 170, 170),
    "XFL": (140, 140, 180),
    "BAW": (30, 60, 130),
    "VIR": (220, 40, 80),
    "IBE": (210, 170, 0),
    "AUA": (220, 40, 40),
    "DLH": (20, 40, 120),
    "KLM": (0, 150, 255),
    "AFR": (0, 80, 160),
    "EIN": (0, 140, 110),
    "RYR": (0, 70, 190),
    "EZY": (255, 110, 0),
    "SAS": (0, 60, 140),
    "FIN": (0, 90, 170),
    "TAP": (0, 150, 90),
    "THY": (210, 40, 40),
    "ETD": (180, 140, 80),
    "UAE": (180, 20, 20),
    "ACA": (180, 20, 20),
    "WJA": (0, 140, 170),
}

# Feeder `flight` is often IATA (UA1234) while this table keys ICAO (UAL). Map 2-letter IATA → ICAO.
IATA_TO_ICAO_PREFIX: dict[str, str] = {
    "UA": "UAL",
    "AA": "AAL",
    "DL": "DAL",
    "WN": "SWA",
    "B6": "JBU",
    "AS": "ASA",
    "F9": "FFT",
    "NK": "NKS",
    "MX": "MXY",
    "VS": "VIR",
    "BA": "BAW",
    "LH": "DLH",
    "AF": "AFR",
    "KL": "KLM",
    "AC": "ACA",
}


def extract_airline_prefix(callsign: str) -> str | None:
    """Leading alphabetic airline prefix (e.g. UAL2215 → UAL)."""
    s = callsign.strip().upper()
    if not s:
        return None
    m = re.match(r"^([A-Z]+)", s)
    if not m:
        return None
    prefix = m.group(1)
    return prefix if len(prefix) >= 2 else None


def resolve_airline_accent_rgb(
    callsign: str,
    *,
    unknown_rgb: tuple[int, int, int],
    enable: bool,
) -> tuple[int, int, int]:
    if not enable:
        return unknown_rgb
    p = extract_airline_prefix(callsign)
    if not p:
        return unknown_rgb
    # Longest ICAO-style match (try 3 then 2 chars).
    for n in (3, 2):
        if len(p) >= n:
            key = p[:n]
            if key in AIRLINE_COLORS:
                return AIRLINE_COLORS[key]
    if len(p) >= 2:
        icao = IATA_TO_ICAO_PREFIX.get(p[:2])
        if icao and icao in AIRLINE_COLORS:
            return AIRLINE_COLORS[icao]
    return unknown_rgb
