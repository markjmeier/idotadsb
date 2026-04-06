from app.models import Aircraft
from app.panel_view import PanelView


def test_visual_fingerprint_ignores_rssi_jitter() -> None:
    a = Aircraft(hex="a", flight="ZZ1", altitude_ft=18050, speed_kt=450.0, track_deg=91.0, rssi=-5.1)
    b = Aircraft(hex="a", flight="ZZ1", altitude_ft=18020, speed_kt=448.0, track_deg=90.0, rssi=-18.9)
    va = PanelView("flight", a, None).visual_fingerprint()
    vb = PanelView("flight", b, None).visual_fingerprint()
    assert va == vb


def test_critical_fingerprint_changes_with_hex() -> None:
    a = PanelView("flight", Aircraft(hex="a", seen_s=1.0), None)
    b = PanelView("flight", Aircraft(hex="b", seen_s=1.0), None)
    assert a.critical_fingerprint() != b.critical_fingerprint()


def test_visual_updates_when_alt_band_changes() -> None:
    low = PanelView("flight", Aircraft(hex="x", altitude_ft=18100, seen_s=1.0), None).visual_fingerprint()
    high = PanelView("flight", Aircraft(hex="x", altitude_ft=18900, seen_s=1.0), None).visual_fingerprint()
    assert low != high
