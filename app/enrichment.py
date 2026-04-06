from __future__ import annotations

import json
import logging
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

try:
    import certifi
except ImportError:
    certifi = None  # type: ignore[misc, assignment]

from app.config import Settings

logger = logging.getLogger(__name__)


def _ssl_context_for_https() -> ssl.SSLContext | None:
    """
    macOS Python.org builds often hit CERTIFICATE_VERIFY_FAILED with urllib unless
    an explicit CA bundle is provided. certifi matches what requests uses.
    """
    if certifi is None:
        return None
    return ssl.create_default_context(cafile=certifi.where())


@dataclass
class EnrichmentData:
    # ICAO code (e.g. B738) or ADSBDB human "type" (e.g. "737 MAX 8") when the API provides it.
    aircraft_type: str | None = None
    route: str | None = None
    airline: str | None = None
    fetched_at: float | None = None

    def has_identity_card(self) -> bool:
        """True if ADSBDB gave anything worth showing on the Identity slot (route/type/airline)."""
        return any((self.aircraft_type, self.route, self.airline))

    def identity_two_lines(self) -> tuple[str, str] | None:
        """
        Identity card body (below callsign): two lines from type / route / airline.
        Order: type+route, else type+airline, else route+airline, else a single field (line2 only).
        """
        if not self.has_identity_card():
            return None
        t, r, a = self.aircraft_type, self.route, self.airline
        if t and r:
            return (t, r)
        if t and a:
            return (t, a)
        if r and a:
            return (r, a)
        if t:
            return (t, "")
        if r:
            return (r, "")
        if a:
            return (a, "")
        return None


def _route_and_airline_from_flightroute(fr: dict) -> tuple[str | None, str | None]:
    airline: str | None = None
    al = fr.get("airline")
    if isinstance(al, dict):
        name = al.get("name")
        if isinstance(name, str) and name.strip():
            airline = name.strip()[:48]
    route: str | None = None
    origin = fr.get("origin")
    dest = fr.get("destination")
    o_iata = None
    d_iata = None
    if isinstance(origin, dict):
        o_iata = origin.get("iata_code")
    if isinstance(dest, dict):
        d_iata = dest.get("iata_code")
    if (
        isinstance(o_iata, str)
        and o_iata.strip()
        and isinstance(d_iata, str)
        and d_iata.strip()
    ):
        route = f"{o_iata.strip().upper()}→{d_iata.strip().upper()}"
    return route, airline


def _parse_adsbdb_response(payload: object) -> EnrichmentData | None:
    """Parse combined aircraft + optional flightroute (GET /v0/aircraft/...)."""
    if not isinstance(payload, dict):
        return None
    resp = payload.get("response")
    if not isinstance(resp, dict):
        return None

    aircraft_type: str | None = None
    ac = resp.get("aircraft")
    if isinstance(ac, dict):
        raw_type = ac.get("type")
        raw_icao = ac.get("icao_type")
        if isinstance(raw_type, str) and raw_type.strip():
            # Prefer description (often easier than ICAO, e.g. "737 MAX 8" vs B38M). Keep API casing.
            aircraft_type = " ".join(raw_type.split())[:44]
        elif isinstance(raw_icao, str) and raw_icao.strip():
            aircraft_type = raw_icao.strip().upper()[:8]

    route: str | None = None
    airline: str | None = None
    fr = resp.get("flightroute")
    if isinstance(fr, dict):
        route, airline = _route_and_airline_from_flightroute(fr)

    if not any((aircraft_type, route, airline)):
        return None
    return EnrichmentData(
        aircraft_type=aircraft_type,
        route=route,
        airline=airline,
        fetched_at=time.monotonic(),
    )


def _parse_callsign_endpoint_response(payload: object) -> EnrichmentData | None:
    """Parse GET /v0/callsign/{callsign} (flightroute only, e.g. RPA3403 → ATL→EWR)."""
    if not isinstance(payload, dict):
        return None
    resp = payload.get("response")
    if not isinstance(resp, dict):
        return None
    fr = resp.get("flightroute")
    if not isinstance(fr, dict):
        return None
    route, airline = _route_and_airline_from_flightroute(fr)
    if not any((route, airline)):
        return None
    return EnrichmentData(
        aircraft_type=None,
        route=route,
        airline=airline,
        fetched_at=time.monotonic(),
    )


def _merge_enrichment(a: EnrichmentData | None, b: EnrichmentData | None) -> EnrichmentData | None:
    if a is None:
        return b
    if b is None:
        return a
    return EnrichmentData(
        aircraft_type=a.aircraft_type or b.aircraft_type,
        route=a.route or b.route,
        airline=a.airline or b.airline,
        fetched_at=time.monotonic(),
    )


class AdsbdbEnricher:
    """
    Optional ADSBDB lookup (version3spec / ADSBDB enrichment v1).
    Fetches run in a daemon thread; get_cached() never blocks on HTTP.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[EnrichmentData | None, float]] = {}
        self._fail_until: dict[str, float] = {}
        self._inflight: set[str] = set()
        self._last_network_mono: float = 0.0
        # Last callsign (normalized) used when writing cache for this hex — refetch if feed changes callsign.
        self._cached_callsign: dict[str, str] = {}

    def get_cached(self, hex_lower: str) -> EnrichmentData | None:
        """Return cached enrichment if TTL valid, else None."""
        if not self._settings.enable_adsbdb_enrichment:
            return None
        key = hex_lower.strip().lower()
        now = time.monotonic()
        with self._lock:
            ent = self._cache.get(key)
            if ent is None:
                return None
            data, expiry = ent
            if now > expiry:
                del self._cache[key]
                return None
        return data

    def schedule_fetch(self, hex_lower: str, callsign: str | None) -> None:
        if not self._settings.enable_adsbdb_enrichment:
            return
        key = hex_lower.strip().lower()
        if not key:
            return
        cs_norm = (callsign or "").strip().upper()
        ttl = self._settings.enrichment_cache_ttl_seconds
        now = time.monotonic()
        with self._lock:
            if key in self._inflight:
                return
            if self._fail_until.get(key, 0) > now:
                return
            hit = self._cache.get(key)
            if hit is not None and now <= hit[1]:
                data, _exp = hit
                ref = self._settings.enrichment_refetch_interval_seconds
                callsign_mismatch = self._cached_callsign.get(key) != cs_norm
                # Negative cache (data is None): always allow a new fetch — do not freeze retries for TTL.
                stale = (
                    data is None
                    or callsign_mismatch
                    or (
                        ref > 0
                        and data is not None
                        and data.fetched_at is not None
                        and (now - data.fetched_at) >= ref
                    )
                )
                if not stale:
                    return
            self._inflight.add(key)

        def run() -> None:
            try:
                min_gap = self._settings.enrichment_min_lookup_interval_seconds
                if min_gap > 0:
                    while True:
                        with self._lock:
                            wait = min_gap - (time.monotonic() - self._last_network_mono)
                        if wait <= 0:
                            break
                        time.sleep(min(wait, 0.25))
                data = self._fetch_blocking(key, callsign)
                with self._lock:
                    self._last_network_mono = time.monotonic()
                    self._cached_callsign[key] = cs_norm
                    prev = self._cache.get(key)
                    if data is None:
                        if prev is not None and prev[0] is not None:
                            old_d, old_exp = prev
                            self._cache[key] = (old_d, max(old_exp, time.monotonic() + ttl))
                        else:
                            self._cache[key] = (None, time.monotonic() + ttl)
                    else:
                        if prev is not None and prev[0] is not None:
                            data = _merge_enrichment(prev[0], data)
                        self._cache[key] = (data, time.monotonic() + ttl)
                if data is not None:
                    logger.debug(
                        "adsbdb %s → type=%r route=%r airline=%r",
                        key[:8],
                        data.aircraft_type,
                        data.route,
                        (data.airline or "")[:40] if data.airline else None,
                    )
            except Exception as e:
                logger.warning("adsbdb fetch failed for %s: %s", key[:8], e)
                logger.debug("adsbdb fetch detail for %s", key, exc_info=True)
                fail_ttl = min(300.0, ttl)
                with self._lock:
                    self._fail_until[key] = time.monotonic() + fail_ttl
            finally:
                with self._lock:
                    self._inflight.discard(key)

        threading.Thread(target=run, name=f"adsbdb-{key[:6]}", daemon=True).start()

    def _http_get_json(self, url: str) -> dict | None:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        timeout = self._settings.enrichment_http_timeout_seconds
        ctx = _ssl_context_for_https()
        open_kw: dict = {"timeout": timeout}
        if urllib.parse.urlparse(url).scheme == "https" and ctx is not None:
            open_kw["context"] = ctx
        try:
            with urllib.request.urlopen(req, **open_kw) as r:
                raw = r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            raise
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return out if isinstance(out, dict) else None

    def _fetch_blocking(self, hex_lower: str, callsign: str | None) -> EnrichmentData | None:
        """
        Prefer GET /v0/aircraft/{hex}?callsign=... (type + route when available).
        If route or airline is still missing and we have a callsign, GET /v0/callsign/{callsign}
        (see https://api.adsbdb.com/v0/callsign/rpa3403).
        """
        base = self._settings.adsbdb_api_base
        path = f"{base}/v0/aircraft/{urllib.parse.quote(hex_lower)}"
        if callsign and callsign.strip():
            path += f"?callsign={urllib.parse.quote(callsign.strip())}"
        logger.debug("adsbdb GET %s", path)
        payload = self._http_get_json(path)
        data_a = _parse_adsbdb_response(payload) if payload is not None else None

        cs = (callsign or "").strip()
        if cs:
            need_callsign_lookup = data_a is None or data_a.route is None or data_a.airline is None
            if need_callsign_lookup:
                cs_path = f"{base}/v0/callsign/{urllib.parse.quote(cs.lower())}"
                cs_payload = self._http_get_json(cs_path)
                data_c = _parse_callsign_endpoint_response(cs_payload) if cs_payload is not None else None
                data_a = _merge_enrichment(data_a, data_c)

        return data_a

    def get_enrichment(self, hex_lower: str, callsign: str | None) -> EnrichmentData | None:
        """Spec-shaped API: returns cache only (network is via schedule_fetch)."""
        return self.get_cached(hex_lower)
