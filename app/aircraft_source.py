from __future__ import annotations

import json
import logging
from typing import Any, List

import requests

from app.models import Aircraft

logger = logging.getLogger(__name__)


def fetch_aircraft_json(url: str, timeout_seconds: float) -> List[Aircraft]:
    """
    GET aircraft.json and return normalized aircraft rows.
    On any failure returns an empty list and logs the error.
    """
    try:
        r = requests.get(url, timeout=timeout_seconds)
        r.raise_for_status()
    except requests.RequestException as e:
        logger.warning("aircraft fetch failed: %s", e)
        return []

    try:
        payload: Any = r.json()
    except json.JSONDecodeError as e:
        logger.warning("aircraft JSON decode failed: %s", e)
        return []

    rows: Any
    if isinstance(payload, dict):
        rows = payload.get("aircraft", [])
    elif isinstance(payload, list):
        rows = payload
    else:
        logger.warning("unexpected aircraft JSON shape")
        return []

    if not isinstance(rows, list):
        return []

    out: List[Aircraft] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        ac = Aircraft.from_dump1090_row(item)
        if ac is not None:
            out.append(ac)
    return out
