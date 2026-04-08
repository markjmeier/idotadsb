from __future__ import annotations

import os
from dataclasses import dataclass


def _env_str(key: str, default: str) -> str:
    v = os.environ.get(key)
    return default if v is None or v == "" else v


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_rgb(key: str, default: tuple[int, int, int]) -> tuple[int, int, int]:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 3:
        return default
    try:
        return tuple(max(0, min(255, int(p))) for p in parts)  # type: ignore[return-value]
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    data_source_url: str
    poll_interval_seconds: float
    http_timeout_seconds: float
    stale_seconds: float
    stale_position_seconds: float
    v3_rotate_top_n: int
    rotate_interval_seconds: float
    enable_distance: bool
    home_lat: float | None
    home_lon: float | None
    log_level: str
    display_backend: str  # "mock" | "idotmatrix_api_client"
    idle_message: str
    rssi_weight: float
    freshness_weight: float
    callsign_bonus: float
    position_bonus: float
    distance_bonus_max: float
    degraded_stale_seconds: float
    squawk_alerting_enabled: bool
    idotmatrix_ble_address: str | None
    idotmatrix_font_path: str | None
    idotmatrix_render: str  # "canvas" | "text"
    idotmatrix_text_mode: int
    idotmatrix_font_size: int
    idotmatrix_pixel_size: int
    idotmatrix_fg_rgb: tuple[int, int, int]
    idotmatrix_bg_rgb: tuple[int, int, int]
    display_min_refresh_seconds: float
    idotmatrix_ble_upload_cap: int
    idotmatrix_swap_fg_bg: bool
    # 5–100 after BLE connect, or None to skip (library requires ≥5 when set).
    idotmatrix_brightness_pct: int | None
    # DIY: setMode(0) before setMode(1); disable if your panel goes blank after reset.
    idotmatrix_diy_reset: bool
    # DIY: quantize rendered PNG before BLE upload (helps flaky firmware).
    idotmatrix_diy_snap_colors: bool
    # version3spec.md
    card_rotation_seconds: float
    aircraft_hold_seconds: float
    min_card_rotation_seconds: float
    max_card_rotation_seconds: float
    v3_enable_airline_colors: bool
    v3_default_text_rgb: tuple[int, int, int]
    v3_default_accent_rgb: tuple[int, int, int]
    v3_alert_rgb: tuple[int, int, int]
    v3_climb_rgb: tuple[int, int, int]
    v3_descent_rgb: tuple[int, int, int]
    v3_level_rgb: tuple[int, int, int]
    v3_unknown_airline_rgb: tuple[int, int, int]
    enable_adsbdb_enrichment: bool
    adsbdb_api_base: str
    enrichment_cache_ttl_seconds: float
    enrichment_refetch_interval_seconds: float
    enrichment_min_lookup_interval_seconds: float
    enrichment_http_timeout_seconds: float
    # Local wall-clock quiet hours: skip feeder + enrichment HTTP; dim/blank panel (BLE).
    quiet_hours_enabled: bool
    quiet_hours_start_hour: int
    quiet_hours_end_hour: int
    quiet_hours_timezone: str
    quiet_hours_poll_interval_seconds: float
    quiet_hours_brightness_pct: int

    @staticmethod
    def from_env() -> Settings:
        home_lat_raw = os.environ.get("HOME_LAT", "").strip()
        home_lon_raw = os.environ.get("HOME_LON", "").strip()
        home_lat: float | None = None
        home_lon: float | None = None
        if home_lat_raw and home_lon_raw:
            try:
                home_lat = float(home_lat_raw)
                home_lon = float(home_lon_raw)
            except ValueError:
                home_lat = None
                home_lon = None

        addr = os.environ.get("IDOTMATRIX_BLE_ADDRESS", "").strip() or None
        font = os.environ.get("IDOTMATRIX_FONT_PATH", "").strip() or None

        render = _env_str("IDOTMATRIX_RENDER", "canvas").lower()
        # raster = our Pillow layout at full panel resolution + DIY upload (same as canvas).
        if render == "raster":
            render = "canvas"
        elif render not in ("canvas", "text"):
            render = "canvas"

        px = max(16, _env_int("IDOTMATRIX_PIXEL_SIZE", 64))
        cap_env = os.environ.get("IDOTMATRIX_BLE_UPLOAD_CAP", "").strip()
        ble_upload_cap: int
        if cap_env:
            try:
                ble_upload_cap = max(16, min(128, int(cap_env)))
            except ValueError:
                ble_upload_cap = 64 if px >= 48 else 32
        else:
            # 64×64 panels often need a 64-wide DIY payload; 32×32 upload can show blank.
            ble_upload_cap = 64 if px >= 48 else 32

        # After BLE connect (same idea as ariatron display_server setBrightness(100)).
        bright_raw = os.environ.get("IDOTMATRIX_BRIGHTNESS", "").strip()
        idotmatrix_brightness_pct: int | None
        if not bright_raw:
            idotmatrix_brightness_pct = 100
        elif bright_raw.lower() in ("0", "off", "skip"):
            idotmatrix_brightness_pct = None
        else:
            try:
                bv = int(bright_raw)
                idotmatrix_brightness_pct = None if bv <= 0 else max(5, min(100, bv))
            except ValueError:
                idotmatrix_brightness_pct = 100

        card_rot = _env_float("CARD_ROTATION_SECONDS", 3.0)
        card_rot = max(_env_float("MIN_CARD_ROTATION_SECONDS", 2.0), min(card_rot, _env_float("MAX_CARD_ROTATION_SECONDS", 4.0)))

        return Settings(
            data_source_url=_env_str(
                "DATA_SOURCE_URL",
                "http://192.168.4.36/skyaware/data/aircraft.json",
            ),
            poll_interval_seconds=_env_float("POLL_INTERVAL_SECONDS", 15.0),
            http_timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 3.0),
            stale_seconds=_env_float("STALE_SECONDS", 10.0),
            stale_position_seconds=_env_float("STALE_POSITION_SECONDS", 10.0),
            v3_rotate_top_n=max(1, _env_int("V3_ROTATE_TOP_N", 5)),
            rotate_interval_seconds=_env_float("ROTATE_INTERVAL_SECONDS", 3.0),
            enable_distance=_env_bool("ENABLE_DISTANCE", False),
            home_lat=home_lat,
            home_lon=home_lon,
            log_level=_env_str("LOG_LEVEL", "INFO").upper(),
            display_backend=_env_str("DISPLAY_BACKEND", "mock").lower(),
            idle_message=_env_str("IDLE_MESSAGE", "NO PLANES"),
            rssi_weight=_env_float("RSSI_WEIGHT", 1.0),
            freshness_weight=_env_float("FRESHNESS_WEIGHT", 2.0),
            callsign_bonus=_env_float("CALLSIGN_BONUS", 5.0),
            position_bonus=_env_float("POSITION_BONUS", 3.0),
            distance_bonus_max=_env_float("DISTANCE_BONUS_MAX", 15.0),
            degraded_stale_seconds=_env_float("DEGRADED_STALE_SECONDS", 60.0),
            squawk_alerting_enabled=_env_bool("SQUAWK_ALERTING_ENABLED", False),
            idotmatrix_ble_address=addr,
            idotmatrix_font_path=font,
            idotmatrix_render=render,
            idotmatrix_text_mode=_env_int("IDOTMATRIX_TEXT_MODE", 1),
            idotmatrix_font_size=max(8, _env_int("IDOTMATRIX_FONT_SIZE", 11)),
            idotmatrix_pixel_size=px,
            idotmatrix_fg_rgb=_env_rgb("IDOTMATRIX_FG", (255, 255, 255)),
            idotmatrix_bg_rgb=_env_rgb("IDOTMATRIX_BG", (0, 0, 0)),
            display_min_refresh_seconds=max(0.0, _env_float("DISPLAY_MIN_REFRESH_SECONDS", 4.0)),
            idotmatrix_ble_upload_cap=ble_upload_cap,
            idotmatrix_swap_fg_bg=_env_bool("IDOTMATRIX_SWAP_COLORS", False),
            idotmatrix_brightness_pct=idotmatrix_brightness_pct,
            idotmatrix_diy_reset=_env_bool("IDOTMATRIX_DIY_RESET", False),
            idotmatrix_diy_snap_colors=_env_bool("IDOTMATRIX_DIY_SNAP_COLORS", True),
            card_rotation_seconds=card_rot,
            aircraft_hold_seconds=max(5.0, _env_float("AIRCRAFT_HOLD_SECONDS", 60.0)),
            min_card_rotation_seconds=_env_float("MIN_CARD_ROTATION_SECONDS", 2.0),
            max_card_rotation_seconds=_env_float("MAX_CARD_ROTATION_SECONDS", 4.0),
            v3_enable_airline_colors=_env_bool("ENABLE_AIRLINE_COLORS", True),
            v3_default_text_rgb=_env_rgb("DEFAULT_TEXT_COLOR", (255, 255, 255)),
            v3_default_accent_rgb=_env_rgb("DEFAULT_ACCENT_COLOR", (180, 200, 255)),
            v3_alert_rgb=_env_rgb("ALERT_COLOR", (255, 80, 80)),
            v3_climb_rgb=_env_rgb("CLIMB_COLOR", (255, 191, 0)),
            v3_descent_rgb=_env_rgb("DESCENT_COLOR", (80, 200, 255)),
            v3_level_rgb=_env_rgb("LEVEL_COLOR", (120, 255, 120)),
            v3_unknown_airline_rgb=_env_rgb("UNKNOWN_AIRLINE_COLOR", (200, 200, 200)),
            enable_adsbdb_enrichment=_env_bool("ENABLE_ADSBDB_ENRICHMENT", False),
            adsbdb_api_base=_env_str("ADSBDB_API_BASE", "https://api.adsbdb.com").rstrip("/"),
            enrichment_cache_ttl_seconds=max(60.0, _env_float("ENRICHMENT_CACHE_TTL_SECONDS", 1800.0)),
            enrichment_refetch_interval_seconds=max(
                0.0, _env_float("ENRICHMENT_REFETCH_INTERVAL_SECONDS", 90.0)
            ),
            # Global spacing between completed enrichment fetches (each fetch may be 1–2 HTTP calls).
            # ADSBDB documents ~512 requests / rolling 60s; default stays far below that for a single display.
            enrichment_min_lookup_interval_seconds=max(
                0.0, _env_float("ENRICHMENT_MIN_LOOKUP_INTERVAL_SECONDS", 5.0)
            ),
            enrichment_http_timeout_seconds=max(0.5, _env_float("ENRICHMENT_HTTP_TIMEOUT_SECONDS", 3.0)),
            quiet_hours_enabled=_env_bool("QUIET_HOURS_ENABLED", False),
            quiet_hours_start_hour=max(0, min(23, _env_int("QUIET_HOURS_START_HOUR", 23))),
            quiet_hours_end_hour=max(0, min(23, _env_int("QUIET_HOURS_END_HOUR", 7))),
            quiet_hours_timezone=_env_str("QUIET_HOURS_TIMEZONE", ""),
            quiet_hours_poll_interval_seconds=max(
                1.0, _env_float("QUIET_HOURS_POLL_INTERVAL_SECONDS", 60.0)
            ),
            quiet_hours_brightness_pct=max(0, min(100, _env_int("QUIET_HOURS_BRIGHTNESS_PCT", 0))),
        )
