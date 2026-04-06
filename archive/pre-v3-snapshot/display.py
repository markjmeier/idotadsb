from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import threading
from abc import ABC, abstractmethod
from collections.abc import Coroutine
from typing import Any, Optional, TypeVar

from app.config import Settings
from app.idotmatrix_diy import (
    diy_upload_pixel_size,
    resize_png_to_square,
    snap_png_to_fg_bg,
)
from app.matrix_canvas import render_lines_png, render_panel_view
from app.matrix_font import resolve_matrix_font_path
from app.panel_view import PanelView, panel_view_to_marquee
from app.text_grid import ble_static_character_capacity, ble_static_first_screen

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


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


class _AsyncLoopThread:
    """Runs a dedicated asyncio event loop for bleak (Bluetooth)."""

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


class IDotMatrixDisplay(Display):
    """
    iDotMatrix over BLE via optional `idotmatrix` + `bleak` (install separately).
    Auto-reconnects each send if the device drops.

    The PyPI ``idotmatrix`` modules each construct their own ``ConnectionManager``
    reference; the known-good pattern (see `display_server.py` in
    `ariatron/iDotMatrix-Python-Flight-Tracker`) is to reuse the **same** manager
    from ``connectBySearch`` / ``connectByAddress`` by assigning ``module.conn =
    connection_manager`` before ``Text`` / ``Common`` / ``Image`` calls.
    `markusressel/idotmatrix-api-client` does the same idea via ``IDotMatrixClient``
    passing one connection manager into every module.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._runner = _AsyncLoopThread()
        self._connected = False
        # Populated after successful BLE connect; injected into idotmatrix modules.
        self._ble_conn: Any = None
        # After first DIY setMode(1) this session; avoid repeating screenOn/setMode on every frame (beeps).
        self._diy_mode_ready: bool = False

    def connect(self) -> None:
        try:
            import idotmatrix  # noqa: F401
        except ImportError as e:
            logger.error("idotmatrix not installed; pip install idotmatrix (or use DISPLAY_BACKEND=mock): %s", e)
            self._connected = False
            return

        self._runner.start()
        try:
            self._runner.run_coro(self._async_connect(), timeout=60.0)
            self._connected = True
            logger.info("IDotMatrixDisplay: connected")
        except Exception as e:
            logger.warning("IDotMatrixDisplay connect failed (will retry on send): %s", e)
            self._connected = False
            self._ble_conn = None

    def _bind_ble_conn(self, *modules: Any) -> None:
        """Attach the connected manager so DIY/Text use the same BLE session."""
        conn = self._ble_conn
        if conn is None:
            return
        for m in modules:
            m.conn = conn

    async def _async_connect(self) -> None:
        from idotmatrix.connectionManager import ConnectionManager
        from idotmatrix.modules.common import Common

        self._diy_mode_ready = False
        conn = ConnectionManager()
        addr = self._settings.idotmatrix_ble_address
        if addr:
            await conn.connectByAddress(addr)
        else:
            await conn.connectBySearch()
        self._ble_conn = conn
        common = Common()
        common.conn = conn
        await common.screenOn()
        b = self._settings.idotmatrix_brightness_pct
        if b is not None:
            await common.setBrightness(b)

    def _flatten(self, text: str) -> str:
        return "  ".join(line.strip() for line in text.splitlines() if line.strip())

    def _canvas_fg_bg(self) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        s = self._settings
        fg, bg = s.idotmatrix_fg_rgb, s.idotmatrix_bg_rgb
        if s.idotmatrix_swap_fg_bg:
            return bg, fg
        return fg, bg

    def _maybe_downscale_and_upload_png(self, png_raw: bytes, render_px: int) -> bool:
        s = self._settings
        upload_px = diy_upload_pixel_size(render_px, ble_cap=s.idotmatrix_ble_upload_cap)
        png = (
            png_raw
            if upload_px == render_px
            else resize_png_to_square(png_raw, upload_px)
        )
        fg, bg = self._canvas_fg_bg()
        if s.idotmatrix_diy_snap_colors:
            png = snap_png_to_fg_bg(png, fg, bg)
        if s.idotmatrix_diy_data_format == "raw_rgb":
            logger.info(
                "DIY canvas: %s×%s (%s B PNG → raw RGB stream; IDOTMATRIX_DIY_FORMAT=raw_rgb)",
                upload_px,
                upload_px,
                len(png),
            )
        elif upload_px != render_px:
            logger.info(
                "DIY image: rendered %s×%s, uploading %s×%s (idotmatrix BLE limit)",
                render_px,
                render_px,
                upload_px,
                upload_px,
            )
        else:
            logger.info(
                "DIY image: uploading %s×%s PNG (%s bytes, png_pypi)",
                upload_px,
                upload_px,
                len(png),
            )

        async def _go() -> None:
            import asyncio

            from idotmatrix.modules.image import Image as IdmImage

            path: str | None = None
            try:
                im = IdmImage()
                self._bind_ble_conn(im)
                conn = self._ble_conn
                if conn is None:
                    raise RuntimeError(
                        "iDotMatrix BLE connection missing; connect first or set IDOTMATRIX_BLE_ADDRESS"
                    )

                if not self._diy_mode_ready:
                    if s.idotmatrix_diy_reset:
                        await im.setMode(0)
                        await asyncio.sleep(0.1)
                    ok_mode = await im.setMode(1)
                    if ok_mode is False:
                        raise RuntimeError("Image.setMode(DIY) returned False")
                    await asyncio.sleep(0.25)
                    self._diy_mode_ready = True
                else:
                    await asyncio.sleep(0.02)

                if s.idotmatrix_diy_data_format == "raw_rgb":
                    from app.diy_ble import (
                        build_diy_payload_from_rgb,
                        diy_send_payload,
                        png_bytes_to_rgb_bytes,
                    )

                    rgb = png_bytes_to_rgb_bytes(png, upload_px)
                    pl = build_diy_payload_from_rgb(rgb)
                    await diy_send_payload(conn, pl)
                else:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        tmp.write(png)
                        path = tmp.name
                    ok_up = await im.uploadProcessed(path, pixel_size=upload_px)
                    if ok_up is False:
                        await asyncio.sleep(0.15)
                        ok_up = await im.uploadProcessed(path, pixel_size=upload_px)
                    if ok_up is False:
                        raise RuntimeError("Image.uploadProcessed returned False")
            finally:
                if path:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

        try:
            self._runner.run_coro(_go(), timeout=45.0)
            return True
        except Exception as e:
            logger.warning("IDotMatrixDisplay send failed: %s", e)
            self._connected = False
            try:
                self._runner.run_coro(self._async_connect(), timeout=60.0)
                self._connected = True
                self._runner.run_coro(_go(), timeout=45.0)
                return True
            except Exception as e2:
                logger.warning("IDotMatrixDisplay reconnect failed: %s", e2)
                return False

    def _send_flat_text(self, flat: str) -> bool:
        font_path = resolve_matrix_font_path(self._settings.idotmatrix_font_path)
        if not font_path:
            logger.error(
                "No usable font for iDotMatrix. Set IDOTMATRIX_FONT_PATH to a .ttf/.otf "
                "or install DejaVu/Liberation fonts on the Pi."
            )
            return False

        lines = [ln.strip() for ln in flat.splitlines()]
        s = self._settings

        async def _go_text() -> None:
            from idotmatrix.modules.text import Text

            t = Text()
            self._bind_ble_conn(t)
            flat_one_line = self._flatten(flat)
            text_mode = s.idotmatrix_text_mode
            px = s.idotmatrix_pixel_size
            static_cap = ble_static_character_capacity(px)
            if text_mode == 0:
                # Static: one 16×32 glyph grid (e.g. 8 chars on 64×64). Do not switch to marquee —
                # fit the first word-wrapped screen so the panel stays still (see text_grid).
                screen = ble_static_first_screen(flat_one_line, panel_edge_px=px)
                if len(flat_one_line) > len(screen):
                    logger.debug(
                        "BLE text static: %s×%s holds ~%s chars; showing first screen only "
                        "(set IDOTMATRIX_TEXT_MODE=1 for full-line marquee, or RENDER=canvas for full card)",
                        px,
                        px,
                        static_cap,
                    )
                text_payload = screen
                text_speed = 0
            else:
                text_payload = flat_one_line
                text_speed = 95
            kwargs = {
                "text": text_payload,
                "text_mode": text_mode,
                "speed": text_speed,
                "text_color_mode": 1,
                "text_color": s.idotmatrix_fg_rgb,
                "text_bg_mode": 1 if s.idotmatrix_bg_rgb != (0, 0, 0) else 0,
                "text_bg_color": s.idotmatrix_bg_rgb,
                "font_path": font_path,
                "font_size": s.idotmatrix_font_size,
            }
            ok = await t.setMode(**kwargs)
            if ok is False:
                raise RuntimeError("Text.setMode returned False")

        if s.idotmatrix_render == "canvas":
            fg, bg = self._canvas_fg_bg()
            png_raw = render_lines_png(
                lines,
                s.idotmatrix_pixel_size,
                font_path,
                fg=fg,
                bg=bg,
            )
            return self._maybe_downscale_and_upload_png(png_raw, s.idotmatrix_pixel_size)

        try:
            self._runner.run_coro(_go_text(), timeout=45.0)
            return True
        except Exception as e:
            logger.warning("IDotMatrixDisplay send failed: %s", e)
            self._connected = False
            try:
                self._runner.run_coro(self._async_connect(), timeout=60.0)
                self._connected = True
                self._runner.run_coro(_go_text(), timeout=45.0)
                return True
            except Exception as e2:
                logger.warning("IDotMatrixDisplay reconnect failed: %s", e2)
                return False

    def show_text(self, text: str) -> None:
        if not self._runner.is_running:
            try:
                self._runner.start()
            except Exception as e:
                logger.error("BLE thread start failed: %s", e)
                return
        # Do not flatten here: canvas needs newlines; text mode flattens inside _send_flat_text.
        self._send_flat_text(text)

    def try_send(self, text: str) -> bool:
        """
        Like show_text but returns False if the payload could not be sent
        (used by poc_display and diagnostics).
        """
        if not self._runner.is_running:
            try:
                self._runner.start()
            except Exception as e:
                logger.error("BLE thread start failed: %s", e)
                return False
        return self._send_flat_text(text)

    def show_alert(self, text: str) -> None:
        self.show_text(text)

    def show_panel(self, view: PanelView, *, alert: bool = False) -> None:
        if not self._runner.is_running:
            try:
                self._runner.start()
            except Exception as e:
                logger.error("BLE thread start failed: %s", e)
                return
        s = self._settings
        if s.idotmatrix_render == "canvas":
            font_path = resolve_matrix_font_path(s.idotmatrix_font_path)
            if not font_path:
                logger.error("No font for panel canvas; set IDOTMATRIX_FONT_PATH")
                return
            fg, bg = self._canvas_fg_bg()
            png_raw = render_panel_view(
                view,
                s.idotmatrix_pixel_size,
                font_path,
                fg=fg,
                bg=bg,
            )
            self._maybe_downscale_and_upload_png(png_raw, s.idotmatrix_pixel_size)
            return
        line = panel_view_to_marquee(view)
        self.show_alert(line) if alert else self.show_text(line)

    def clear(self) -> None:
        self.show_text(" ")

    def close(self) -> None:
        self._runner.stop()

    @property
    def is_connected(self) -> bool:
        return self._connected


def create_display(settings: Settings) -> Display:
    backend = settings.display_backend
    if backend == "idotmatrix_markus":
        from app.display_markus import MarkusIDotMatrixDisplay

        return MarkusIDotMatrixDisplay(settings)
    if backend == "idotmatrix":
        return IDotMatrixDisplay(settings)
    if backend == "mock":
        return MockDisplay()
    logger.warning("unknown DISPLAY_BACKEND=%r; using mock", backend)
    return MockDisplay()
