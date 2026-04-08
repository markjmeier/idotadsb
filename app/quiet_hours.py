from __future__ import annotations

import logging
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)


def current_local_hour(timezone_name: str | None) -> int:
    """
    Current hour 0–23 in the configured IANA zone, or the process/system local zone if unset/invalid.
    Set ``TZ`` on the Pi or use ``QUIET_HOURS_TIMEZONE`` for consistent wall time.
    """
    name = (timezone_name or "").strip()
    if name and ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(name)).hour
        except Exception as e:
            logger.warning("QUIET_HOURS_TIMEZONE=%r invalid (%s); using system local", name, e)
    return datetime.now().astimezone().hour


def in_quiet_hours_hour(hour: int, start: int, end: int) -> bool:
    """
    Whether ``hour`` falls in the quiet window.

    * If ``start > end`` (e.g. 23 and 7): overnight — quiet when hour >= start or hour < end.
    * If ``start < end``: same-day — quiet when start <= hour < end.
    * If ``start == end``: treated as no window (always active / never quiet).
    """
    start = max(0, min(23, start))
    end = max(0, min(23, end))
    hour = max(0, min(23, hour))
    if start == end:
        return False
    if start > end:
        return hour >= start or hour < end
    return start <= hour < end
