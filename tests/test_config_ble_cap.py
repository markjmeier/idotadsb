"""BLE DIY upload cap defaults when IDOTMATRIX_BLE_UPLOAD_CAP is unset."""

import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def _minimal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_SOURCE_URL", "http://localhost/aircraft.json")
    monkeypatch.setenv("DISPLAY_BACKEND", "mock")
    monkeypatch.delenv("IDOTMATRIX_BLE_UPLOAD_CAP", raising=False)


def test_ble_upload_cap_auto_64_when_pixel_64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IDOTMATRIX_PIXEL_SIZE", "64")
    s = Settings.from_env()
    assert s.idotmatrix_pixel_size == 64
    assert s.idotmatrix_ble_upload_cap == 64


def test_ble_upload_cap_auto_32_when_pixel_32(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IDOTMATRIX_PIXEL_SIZE", "32")
    s = Settings.from_env()
    assert s.idotmatrix_pixel_size == 32
    assert s.idotmatrix_ble_upload_cap == 32


def test_ble_upload_cap_explicit_overrides_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IDOTMATRIX_PIXEL_SIZE", "64")
    monkeypatch.setenv("IDOTMATRIX_BLE_UPLOAD_CAP", "32")
    s = Settings.from_env()
    assert s.idotmatrix_ble_upload_cap == 32
