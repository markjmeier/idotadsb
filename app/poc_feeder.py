"""
One-shot check: can we reach the local aircraft.json and parse rows?

Run from repo root:
  python -m app.poc_feeder

Uses DATA_SOURCE_URL and HTTP_TIMEOUT_SECONDS from the environment / .env.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, List

import requests

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

from app.aircraft_filter import rank_aircraft
from app.config import Settings
from app.formatter import callsign_or_hex, format_altitude_k
from app.models import Aircraft


def _normalize_rows(payload: Any) -> List[Aircraft]:
    rows: Any
    if isinstance(payload, dict):
        rows = payload.get("aircraft", [])
    elif isinstance(payload, list):
        rows = payload
    else:
        return []
    if not isinstance(rows, list):
        return []
    out: List[Aircraft] = []
    for item in rows:
        if isinstance(item, dict):
            ac = Aircraft.from_dump1090_row(item)
            if ac is not None:
                out.append(ac)
    return out


def main() -> int:
    if load_dotenv is not None:
        load_dotenv()
    logging.basicConfig(level=logging.WARNING)

    s = Settings.from_env()
    url = s.data_source_url
    timeout = s.http_timeout_seconds

    print(f"GET {url!r} (timeout={timeout}s)", flush=True)

    try:
        r = requests.get(url, timeout=timeout)
        print(f"HTTP {r.status_code}")
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"FAIL: {e}", file=sys.stderr)
        print(
            "Check: Pi/feeder IP, firewall, and that skyaware serves aircraft.json.",
            file=sys.stderr,
        )
        return 1

    try:
        payload: Any = r.json()
    except json.JSONDecodeError as e:
        print(f"FAIL: invalid JSON: {e}", file=sys.stderr)
        return 1

    aircraft = _normalize_rows(payload)
    print(f"OK: {len(aircraft)} aircraft after normalization")

    if not aircraft:
        print("(Empty list is valid if no traffic — endpoint still works.)")
        return 0

    ranked = rank_aircraft(aircraft, s)[:8]
    print("Top by score (hex / label / alt / rssi / seen):")
    for ac, sc in ranked:
        label = callsign_or_hex(ac)
        alt = format_altitude_k(ac.altitude_ft)
        rssi = ac.rssi if ac.rssi is not None else "—"
        seen = ac.seen_s if ac.seen_s is not None else "—"
        print(f"  {ac.hex}  {label:8}  {alt:>6}  rssi={rssi}  seen={seen}s  score={sc:.1f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
