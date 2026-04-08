from app.airline_colors import AIRLINE_COLORS, extract_airline_prefix, resolve_airline_accent_rgb
from app.enrichment import (
    EnrichmentData,
    _merge_enrichment,
    _parse_adsbdb_response,
    _parse_callsign_endpoint_response,
    _ssl_context_for_https,
)
from app.v3_logic import v3_active_card


def test_ssl_context_uses_certifi_when_available() -> None:
    """Avoid macOS urllib CERTIFICATE_VERIFY_FAILED against public HTTPS APIs."""
    ctx = _ssl_context_for_https()
    assert ctx is not None


def test_extract_airline_prefix() -> None:
    assert extract_airline_prefix("UAL2215") == "UAL"
    assert extract_airline_prefix("BAW173") == "BAW"
    assert extract_airline_prefix("") is None


def test_resolve_airline_accent() -> None:
    unknown = (200, 200, 200)
    assert resolve_airline_accent_rgb("UAL1", unknown_rgb=unknown, enable=True) == AIRLINE_COLORS["UAL"]
    # Feeders often use IATA (UA…) while the palette keys ICAO (UAL).
    assert resolve_airline_accent_rgb("UA204", unknown_rgb=unknown, enable=True) == AIRLINE_COLORS["UAL"]
    assert resolve_airline_accent_rgb("ZZZ999", unknown_rgb=unknown, enable=True) == unknown
    assert resolve_airline_accent_rgb("UAL1", unknown_rgb=unknown, enable=False) == unknown


def test_v3_active_card_no_enrichment_is_live() -> None:
    assert v3_active_card(100.0, 0.0, 3.0, None) == "live"


def test_v3_active_card_alternates_with_enrichment() -> None:
    en = EnrichmentData(aircraft_type="A320", route="EWR→ORD", airline="United")
    assert en.has_identity_card()
    assert v3_active_card(0.0, 0.0, 3.0, en) == "live"
    assert v3_active_card(3.0, 0.0, 3.0, en) == "identity"
    assert v3_active_card(6.0, 0.0, 3.0, en) == "live"


def test_v3_active_card_alternates_with_single_enrichment_field() -> None:
    en = EnrichmentData(aircraft_type="B738", route=None, airline=None)
    assert en.has_identity_card()
    assert en.identity_two_lines() == ("B738", "")
    assert v3_active_card(3.0, 0.0, 3.0, en) == "identity"


def test_parse_callsign_endpoint_rpa3403_shape() -> None:
    """Live API shape: GET /v0/callsign/rpa3403 → origin/destination iata_code."""
    payload = {
        "response": {
            "flightroute": {
                "callsign": "RPA3403",
                "airline": {"name": "Republic Airlines", "icao": "RPA"},
                "origin": {"iata_code": "ATL"},
                "destination": {"iata_code": "EWR"},
            }
        }
    }
    out = _parse_callsign_endpoint_response(payload)
    assert out is not None
    assert out.route == "ATL→EWR"
    assert out.airline is not None and "Republic" in out.airline


def test_parse_adsbdb_sample() -> None:
    payload = {
        "response": {
            "aircraft": {"icao_type": "A320", "type": "A320"},
            "flightroute": {
                "airline": {"name": "United Airlines"},
                "origin": {"iata_code": "EWR"},
                "destination": {"iata_code": "ORD"},
            },
        }
    }
    out = _parse_adsbdb_response(payload)
    assert out is not None
    assert out.aircraft_type == "A320"
    assert out.route == "EWR→ORD"
    assert "United" in (out.airline or "")


def test_parse_adsbdb_prefers_human_type_over_icao() -> None:
    payload = {
        "response": {
            "aircraft": {"icao_type": "B38M", "type": "737 MAX 8"},
            "flightroute": {
                "airline": {"name": "Spirit Airlines"},
                "origin": {"iata_code": "FLL"},
                "destination": {"iata_code": "ORD"},
            },
        }
    }
    out = _parse_adsbdb_response(payload)
    assert out is not None
    assert out.aircraft_type == "737 MAX 8"
    assert "Spirit" in (out.airline or "")


def test_enrichment_identity_lines() -> None:
    en = EnrichmentData(aircraft_type="B738", airline="Southwest")
    assert en.identity_two_lines() == ("B738", "Southwest")


def test_enrichment_identity_single_type_only() -> None:
    en = EnrichmentData(aircraft_type="E75L", route=None, airline=None)
    assert en.has_identity_card()
    assert en.identity_two_lines() == ("E75L", "")


def test_merge_enrichment_fresh_route_wins_over_stale_cache() -> None:
    """Cache updates must not preserve an old flight's route when ADSBDB returns a new one."""
    stale = EnrichmentData(aircraft_type="B738", route="LIH→SFO", airline="United")
    fresh = EnrichmentData(aircraft_type="B738", route="AUS→EWR", airline="United")
    merged = _merge_enrichment(fresh, stale)
    assert merged.route == "AUS→EWR"
    # Anti-pattern: old first keeps stale route forever after refetch.
    assert _merge_enrichment(stale, fresh).route == "LIH→SFO"


def test_merge_enrichment_fresh_without_type_keeps_tail_from_cache() -> None:
    """Callsign-only fetch may omit type; keep cached aircraft_type."""
    prev = EnrichmentData(aircraft_type="B38M", route="EWR→ORD", airline=None)
    cs_only = EnrichmentData(aircraft_type=None, route="AUS→EWR", airline="United")
    merged = _merge_enrichment(cs_only, prev)
    assert merged.aircraft_type == "B38M"
    assert merged.route == "AUS→EWR"
