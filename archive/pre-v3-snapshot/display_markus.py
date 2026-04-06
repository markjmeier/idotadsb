"""
iDotMatrix via markusressel/idotmatrix-api-client (same stack as alloy-sparkline).

PyPI ``idotmatrix`` (derkalle4-style) uses ``ConnectionManager`` + module ``conn`` injection.
The markus fork exposes ``IDotMatrixClient`` and ``image.upload_image_file()`` — the pattern
that reliably drives 64×64 DIY updates in https://github.com/marinnedea/alloy-sparkline .

Install: see requirements-ble-markus.txt (uninstall PyPI idotmatrix first).
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import threading
from typing import Any

from app.config import Settings
from app.display import Display, _AsyncLoopThread
from app.idotmatrix_diy import snap_png_to_fg_bg
from app.matrix_canvas import render_lines_png, render_panel_view
from app.matrix_font import resolve_matrix_font_path
from app.panel_view import PanelView, panel_view_to_marquee
from app.text_grid import ble_static_character_capacity, ble_static_first_screen

logger = logging.getLogger(__name__)


def markus_render_edge_pixels(configured_px: int) -> int:
    """Map configured IDOTMATRIX_PIXEL_SIZE to the nearest supported square panel edge."""
    if configured_px >= 48:
        return 64
    if configured_px >= 24:
        return 32
    return 16


def _markus_install_hint() -> str:
    return (
        "DISPLAY_BACKEND=idotmatrix_markus needs markusressel/idotmatrix-api-client "
        "(not PyPI idotmatrix). Example: pip uninstall -y idotmatrix && "
        "pip install 'git+https://github.com/markusressel/idotmatrix-api-client.git'. "
        "See requirements-ble-markus.txt."
    )


_markus_signal_handlers_patched = False


def _patch_markus_connection_manager_signal_handlers() -> None:
    """
    markus ConnectionManager.__init__ calls _setup_signal_handlers(), which uses
    loop.add_signal_handler() → signal.set_wakeup_fd. That API is only allowed on
    the main thread; our BLE asyncio loop runs on _AsyncLoopThread.

    Skip signal registration when ConnectionManager is constructed off the main thread.
    Process shutdown is still handled by the main thread (KeyboardInterrupt / app.main).
    """
    global _markus_signal_handlers_patched
    if _markus_signal_handlers_patched:
        return
    try:
        from idotmatrix.connection_manager import ConnectionManager
    except ImportError:
        return
    orig = ConnectionManager._setup_signal_handlers

    def _safe_setup_signal_handlers(self: object) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        orig(self)

    ConnectionManager._setup_signal_handlers = _safe_setup_signal_handlers  # type: ignore[method-assign]
    _markus_signal_handlers_patched = True


_gatt_noise_filter_installed = False


def _quiet_markus_gatt_read_not_permitted_logs() -> None:
    """
    markus send_packets logs ERROR on read_gatt_char after some writes; many panels return
    GATT Read Not Permitted while still accepting the write — safe to hide from the console.
    """
    global _gatt_noise_filter_installed
    if _gatt_noise_filter_installed:
        return

    class _Filter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return "Read Not Permitted" not in record.getMessage()

    logging.getLogger("idotmatrix.connection_manager").addFilter(_Filter())
    _gatt_noise_filter_installed = True


class MarkusIDotMatrixDisplay(Display):
    """BLE display using IDotMatrixClient + upload_image_file (alloy-sparkline style)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._runner = _AsyncLoopThread()
        self._connected = False
        self._client: Any = None
        self._render_px = markus_render_edge_pixels(settings.idotmatrix_pixel_size)

    def _have_markus_client(self) -> bool:
        try:
            from idotmatrix.client import IDotMatrixClient  # noqa: F401

            return True
        except ImportError:
            logger.error(_markus_install_hint())
            return False

    async def _async_disconnect(self) -> None:
        c = self._client
        self._client = None
        if c is not None:
            try:
                await c.disconnect()
            except Exception as e:
                logger.debug("Markus disconnect: %s", e)

    async def _async_connect(self) -> None:
        _patch_markus_connection_manager_signal_handlers()
        _quiet_markus_gatt_read_not_permitted_logs()
        from idotmatrix.client import IDotMatrixClient
        from idotmatrix.modules.image import ImageMode
        from idotmatrix.screensize import ScreenSize

        await self._async_disconnect()

        s = self._settings
        edge = markus_render_edge_pixels(s.idotmatrix_pixel_size)
        self._render_px = edge
        if s.idotmatrix_pixel_size != edge:
            logger.info(
                "Markus backend: IDOTMATRIX_PIXEL_SIZE=%s → %s×%s device profile",
                s.idotmatrix_pixel_size,
                edge,
                edge,
            )

        if edge == 64:
            screen_size = ScreenSize.SIZE_64x64
        elif edge == 32:
            screen_size = ScreenSize.SIZE_32x32
        else:
            screen_size = ScreenSize.SIZE_16x16

        client = IDotMatrixClient(
            screen_size=screen_size,
            mac_address=s.idotmatrix_ble_address,
        )
        await client.connect()

        b = s.idotmatrix_brightness_pct
        if b is not None:
            await client.set_brightness(int(b))

        if s.idotmatrix_diy_reset:
            await client.image.set_mode(ImageMode.DisableDIY)
            await asyncio.sleep(0.1)
        await client.image.set_mode(ImageMode.EnableDIY)
        await asyncio.sleep(0.25)

        self._client = client

    def connect(self) -> None:
        if not self._have_markus_client():
            self._connected = False
            return
        self._runner.start()
        try:
            self._runner.run_coro(self._async_connect(), timeout=60.0)
            self._connected = True
            logger.info("MarkusIDotMatrixDisplay: connected (%s×%s)", self._render_px, self._render_px)
        except Exception as e:
            logger.warning("MarkusIDotMatrixDisplay connect failed (will retry on send): %s", e)
            self._connected = False
            self._client = None

    def _canvas_fg_bg(self) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        s = self._settings
        fg, bg = s.idotmatrix_fg_rgb, s.idotmatrix_bg_rgb
        if s.idotmatrix_swap_fg_bg:
            return bg, fg
        return fg, bg

    def _prepare_png(self, png_raw: bytes) -> bytes:
        s = self._settings
        if not s.idotmatrix_diy_snap_colors:
            return png_raw
        fg, bg = self._canvas_fg_bg()
        return snap_png_to_fg_bg(png_raw, fg, bg)

    async def _async_upload_png(self, png_raw: bytes) -> None:
        from idotmatrix.util import image_utils

        client = self._client
        if client is None:
            raise RuntimeError("Markus client not connected")

        png = self._prepare_png(png_raw)
        bg = self._settings.idotmatrix_bg_rgb
        path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(png)
                path = tmp.name
            await asyncio.sleep(0.02)
            await client.image.upload_image_file(
                path,
                resize_mode=image_utils.ResizeMode.FIT,
                palletize=False,
                background_color=bg,
            )
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    def _upload_png(self, png_raw: bytes) -> bool:
        async def _go() -> None:
            await self._async_upload_png(png_raw)

        try:
            self._runner.run_coro(_go(), timeout=45.0)
            return True
        except Exception as e:
            logger.warning("MarkusIDotMatrixDisplay upload failed: %s", e)
            self._connected = False
            try:
                self._runner.run_coro(self._async_connect(), timeout=60.0)
                self._connected = True
                self._runner.run_coro(_go(), timeout=45.0)
                return True
            except Exception as e2:
                logger.warning("MarkusIDotMatrixDisplay reconnect failed: %s", e2)
                return False

    def _flatten(self, text: str) -> str:
        return "  ".join(line.strip() for line in text.splitlines() if line.strip())

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
        px = self._render_px

        async def _go_text() -> None:
            from idotmatrix.modules.text import TextColorMode, TextMode

            client = self._client
            if client is None:
                raise RuntimeError("Markus client not connected")

            flat_one_line = self._flatten(flat)
            if s.idotmatrix_text_mode == 0:
                screen = ble_static_first_screen(flat_one_line, panel_edge_px=px)
                static_cap = ble_static_character_capacity(px)
                if len(flat_one_line) > len(screen):
                    logger.debug(
                        "Markus BLE text static: %s×%s holds ~%s chars; first screen only",
                        px,
                        px,
                        static_cap,
                    )
                payload = screen
                mode = TextMode.REPLACE
                speed = 0
            else:
                payload = flat_one_line
                mode = TextMode.MARQUEE
                speed = 95

            bg: tuple[int, int, int] | None
            if s.idotmatrix_bg_rgb == (0, 0, 0):
                bg = None
            else:
                bg = s.idotmatrix_bg_rgb

            await client.text.show_text(
                payload,
                font_path=font_path,
                font_size=s.idotmatrix_font_size,
                text_mode=mode,
                speed=speed,
                text_color_mode=TextColorMode.RGB,
                text_color=s.idotmatrix_fg_rgb,
                text_bg_color=bg,
            )

        if s.idotmatrix_render == "canvas":
            fg, bg = self._canvas_fg_bg()
            png_raw = render_lines_png(
                lines,
                px,
                font_path,
                fg=fg,
                bg=bg,
            )
            return self._upload_png(png_raw)

        try:
            self._runner.run_coro(_go_text(), timeout=45.0)
            return True
        except Exception as e:
            logger.warning("MarkusIDotMatrixDisplay text failed: %s", e)
            self._connected = False
            try:
                self._runner.run_coro(self._async_connect(), timeout=60.0)
                self._connected = True
                self._runner.run_coro(_go_text(), timeout=45.0)
                return True
            except Exception as e2:
                logger.warning("MarkusIDotMatrixDisplay reconnect failed: %s", e2)
                return False

    def show_text(self, text: str) -> None:
        if not self._runner.is_running:
            try:
                self._runner.start()
            except Exception as e:
                logger.error("BLE thread start failed: %s", e)
                return
        self._send_flat_text(text)

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
                self._render_px,
                font_path,
                fg=fg,
                bg=bg,
            )
            self._upload_png(png_raw)
            return
        line = panel_view_to_marquee(view)
        self.show_alert(line) if alert else self.show_text(line)

    def clear(self) -> None:
        self.show_text(" ")

    def close(self) -> None:
        if self._client is not None and self._runner.is_running:
            try:
                self._runner.run_coro(self._async_disconnect(), timeout=15.0)
            except Exception as e:
                logger.debug("Markus close: %s", e)
        self._runner.stop()

    @property
    def is_connected(self) -> bool:
        return self._connected
