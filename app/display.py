from __future__ import annotations

import asyncio
import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Coroutine
from typing import Any, Optional, TypeVar

from app.config import Settings
from app.panel_view import PanelView

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

BACKEND_IDOTMATRIX_API_CLIENT = "idotmatrix_api_client"


class Display(ABC):
    """Abstract display sink (console mock or Bluetooth hardware)."""

    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def show_text(self, text: str) -> None:
        ...

    @abstractmethod
    def show_alert(self, text: str) -> None:
        ...

    @abstractmethod
    def clear(self) -> None:
        ...

    @abstractmethod
    def show_panel(self, view: PanelView, *, alert: bool = False) -> None:
        """Structured flight card / alert / idle (see displayspec.md)."""
        ...

    def set_quiet_hours_active(self, active: bool) -> None:
        """Dim or blank hardware during local quiet hours; restore when ``active`` is False."""
        return None

    def close(self) -> None:
        """Release resources (optional)."""
        return None


class MockDisplay(Display):
    """Logs payloads to the logger at INFO (for dev / headless Pi)."""

    def connect(self) -> None:
        logger.info("MockDisplay: connected")

    def show_text(self, text: str) -> None:
        logger.info("MockDisplay text:\n%s", text)

    def show_alert(self, text: str) -> None:
        logger.info("MockDisplay ALERT:\n%s", text)

    def clear(self) -> None:
        logger.info("MockDisplay: clear")

    def show_panel(self, view: PanelView, *, alert: bool = False) -> None:
        from app.panel_view import panel_view_mock_text

        tag = "ALERT panel" if alert else "panel"
        logger.info("MockDisplay %s:\n%s", tag, panel_view_mock_text(view))

    def set_quiet_hours_active(self, active: bool) -> None:
        logger.info("MockDisplay quiet_hours=%s", active)


class _AsyncLoopThread:
    """Runs a dedicated asyncio event loop for BLE (API client backend)."""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._started = threading.Event()
        self._error: Optional[BaseException] = None

    def start(self) -> None:
        if self._thread is not None:
            return

        def runner() -> None:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                self._started.set()
                loop.run_forever()
            except BaseException as e:
                self._error = e
                self._started.set()

        self._thread = threading.Thread(target=runner, name="idotmatrix-async", daemon=True)
        self._thread.start()
        if not self._started.wait(timeout=10.0):
            raise TimeoutError("async BLE thread failed to start")
        if self._error is not None:
            raise self._error
        if self._loop is None:
            raise RuntimeError("async loop not initialized")

    def run_coro(self, coro: Coroutine[Any, Any, _T], *, timeout: float = 30.0) -> _T:
        loop = self._loop
        if loop is None:
            raise RuntimeError("loop not running")
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        return fut.result(timeout=timeout)

    @property
    def is_running(self) -> bool:
        return self._loop is not None and self._loop.is_running()

    def stop(self) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return

        def _stop() -> None:
            loop.stop()

        loop.call_soon_threadsafe(_stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)


def create_display(settings: Settings) -> Display:
    backend = settings.display_backend
    if backend == BACKEND_IDOTMATRIX_API_CLIENT:
        from app.display_idotmatrix_api_client import IDotMatrixApiClientDisplay

        return IDotMatrixApiClientDisplay(settings)
    if backend == "idotmatrix":
        logger.warning(
            "DISPLAY_BACKEND=idotmatrix (removed legacy PyPI stack) is ignored; "
            "use idotmatrix_api_client (requirements.txt) or mock."
        )
        return MockDisplay()
    if backend == "mock":
        return MockDisplay()
    logger.warning("unknown DISPLAY_BACKEND=%r; using mock", backend)
    return MockDisplay()
