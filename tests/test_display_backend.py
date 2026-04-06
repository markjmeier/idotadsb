"""create_display routing (mock vs idotmatrix-api-client; legacy idotmatrix ignored)."""

from app.display import MockDisplay, create_display
from app.display_idotmatrix_api_client import IDotMatrixApiClientDisplay
from tests.test_filter import _settings


def test_create_display_mock() -> None:
    d = create_display(_settings(display_backend="mock"))
    assert isinstance(d, MockDisplay)


def test_create_display_idotmatrix_api_client() -> None:
    d = create_display(_settings(display_backend="idotmatrix_api_client"))
    assert isinstance(d, IDotMatrixApiClientDisplay)


def test_create_display_legacy_idotmatrix_falls_back_to_mock() -> None:
    d = create_display(_settings(display_backend="idotmatrix"))
    assert isinstance(d, MockDisplay)
