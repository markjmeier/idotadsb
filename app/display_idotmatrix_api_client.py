"""
iDotMatrix over BLE via the GitHub ``idotmatrix-api-client`` (import ``idotmatrix``).

Colors come entirely from our Pillow PNG (airline / motion / snap). The library’s
``upload_image_file`` re-opens the file and resizes with LANCZOS, which can smear
quantized pixels; we send exact-size RGB with ``ImageModule._send_diy_image_data`` instead.

Install: ``requirements.txt`` (GitHub idotmatrix-api-client). Do not install the unrelated PyPI package ``idotmatrix``.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile
import threading
from typing import Any

from PIL import Image as PilImage

from app.config import Settings
from app.display import Display, _AsyncLoopThread
from app.idotmatrix_diy import snap_png_for_upload
from app.matrix_canvas import render_lines_png, render_panel_view
from app.matrix_theme import MatrixColorProfile, snap_chrome_rgb_for_panel
from app.matrix_font import resolve_matrix_font_path
from app.panel_view import PanelView, panel_view_to_marquee
from app.text_grid import ble_static_character_capacity, ble_static_first_screen

logger = logging.getLogger(__name__)


def idotmatrix_panel_edge_pixels(configured_px: int) -> int:
    """Map configured IDOTMATRIX_PIXEL_SIZE to the nearest supported square panel edge."""
    if configured_px >= 48:
        return 64
    if configured_px >= 24:
        return 32
    return 16


def _idotmatrix_api_client_install_hint() -> str:
    return (
        "DISPLAY_BACKEND=idotmatrix_api_client needs GitHub idotmatrix-api-client. "
        "See requirements.txt (GitHub idotmatrix-api-client; avoid the PyPI package named idotmatrix)."
    )


_connection_manager_signal_patch_done = False


def _patch_connection_manager_signal_handlers_off_main_thread() -> None:
    """
    idotmatrix-api-client ConnectionManager.__init__ calls _setup_signal_handlers(), which uses
    loop.add_signal_handler() → signal.set_wakeup_fd. That API is only allowed on
    the main thread; our BLE asyncio loop runs on _AsyncLoopThread.

    Skip signal registration when ConnectionManager is constructed off the main thread.
    Process shutdown is still handled by the main thread (KeyboardInterrupt / app.main).
    """
    global _connection_manager_signal_patch_done
    if _connection_manager_signal_patch_done:
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
    _connection_manager_signal_patch_done = True


_gatt_noise_filter_installed = False


def _quiet_gatt_read_not_permitted_logs() -> None:
    """
    Library send_packets logs ERROR on read_gatt_char after some writes; many panels return
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


class IDotMatrixApiClientDisplay(Display):
    """BLE display using IDotMatrixClient + upload_image_file."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._runner = _AsyncLoopThread()
        self._connected = False
        self._client: Any = None
        self._render_px = idotmatrix_panel_edge_pixels(settings.idotmatrix_pixel_size)
        self._quiet_hours_active = False
        self._brightness_before_quiet: int | None = None

    def _have_api_client(self) -> bool:
        try:
            from idotmatrix.client import IDotMatrixClient  # noqa: F401

            return True
        except ImportError:
            logger.error(_idotmatrix_api_client_install_hint())
            return False

    async def _async_disconnect(self) -> None:
        c = self._client
        self._client = None
        if c is not None:
            try:
                await c.disconnect()
            except Exception as e:
                logger.debug("BLE disconnect: %s", e)

    async def _async_connect(self) -> None:
        _patch_connection_manager_signal_handlers_off_main_thread()
        _quiet_gatt_read_not_permitted_logs()
        from idotmatrix.client import IDotMatrixClient
        from idotmatrix.modules.image import ImageMode
        from idotmatrix.screensize import ScreenSize

        await self._async_disconnect()

        s = self._settings
        edge = idotmatrix_panel_edge_pixels(s.idotmatrix_pixel_size)
        self._render_px = edge
        if s.idotmatrix_pixel_size != edge:
            logger.info(
                "idotmatrix-api-client: IDOTMATRIX_PIXEL_SIZE=%s → %s×%s device profile",
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
        if b is not None and not self._quiet_hours_active:
            await client.set_brightness(int(b))

        if s.idotmatrix_diy_reset:
            await client.image.set_mode(ImageMode.DisableDIY)
            await asyncio.sleep(0.1)
        await client.image.set_mode(ImageMode.EnableDIY)
        await asyncio.sleep(0.25)

        self._client = client

    def connect(self) -> None:
        if not self._have_api_client():
            self._connected = False
            return
        self._runner.start()
        try:
            self._runner.run_coro(self._async_connect(), timeout=60.0)
            self._connected = True
            logger.info("IDotMatrixApiClientDisplay: connected (%s×%s)", self._render_px, self._render_px)
        except Exception as e:
            logger.warning("IDotMatrixApiClientDisplay connect failed (will retry on send): %s", e)
            self._connected = False
            self._client = None

    def _canvas_fg_bg(self) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        s = self._settings
        fg, bg = s.idotmatrix_fg_rgb, s.idotmatrix_bg_rgb
        if s.idotmatrix_swap_fg_bg:
            return bg, fg
        return fg, bg

    def _prepare_png(
        self,
        png_raw: bytes,
        chrome_rgb: tuple[int, int, int] | None = None,
    ) -> bytes:
        s = self._settings
        if not s.idotmatrix_diy_snap_colors:
            return png_raw
        return snap_png_for_upload(png_raw, s, chrome_rgb)

    async def _async_upload_png(
        self,
        png_raw: bytes,
        chrome_rgb: tuple[int, int, int] | None = None,
    ) -> None:
        from idotmatrix.util import image_utils

        client = self._client
        if client is None:
            raise RuntimeError("iDotMatrix client not connected")

        png = self._prepare_png(png_raw, chrome_rgb)
        bg = self._settings.idotmatrix_bg_rgb
        edge = self._render_px
        path: str | None = None
        try:
            with PilImage.open(io.BytesIO(png)) as im:
                im = im.convert("RGB")
                if im.size == (edge, edge):
                    # Avoid upload_image_file → PIL LANCZOS resize (washes out DIY snap colors).
                    rgb = bytearray(im.tobytes())
                    await asyncio.sleep(0.02)
                    await client.image._send_diy_image_data(rgb)
                    return

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

    def _upload_png(
        self,
        png_raw: bytes,
        chrome_rgb: tuple[int, int, int] | None = None,
    ) -> bool:
        async def _go() -> None:
            await self._async_upload_png(png_raw, chrome_rgb)

        try:
            self._runner.run_coro(_go(), timeout=45.0)
            return True
        except Exception as e:
            logger.warning("IDotMatrixApiClientDisplay upload failed: %s", e)
            self._connected = False
            try:
                self._runner.run_coro(self._async_connect(), timeout=60.0)
                self._connected = True
                self._runner.run_coro(_go(), timeout=45.0)
                return True
            except Exception as e2:
                logger.warning("IDotMatrixApiClientDisplay reconnect failed: %s", e2)
                return False

    async def _async_set_brightness_clamped(self, pct: int) -> None:
        client = self._client
        if client is None:
            return
        b = max(5, min(100, int(pct)))
        await client.set_brightness(b)

    async def _async_upload_black_frame(self) -> None:
        client = self._client
        if client is None:
            raise RuntimeError("iDotMatrix client not connected")
        edge = self._render_px
        rgb = bytearray(edge * edge * 3)
        await asyncio.sleep(0.02)
        await client.image._send_diy_image_data(rgb)

    async def _async_enter_quiet_hours(self) -> None:
        s = self._settings
        self._brightness_before_quiet = s.idotmatrix_brightness_pct
        q = s.quiet_hours_brightness_pct
        night = 5 if q <= 0 else max(5, min(100, q))
        try:
            await self._async_set_brightness_clamped(night)
        except Exception as e:
            logger.debug("quiet hours set brightness: %s", e)
        try:
            await self._async_upload_black_frame()
        except Exception as e:
            logger.warning("quiet hours black frame failed: %s", e)

    async def _async_exit_quiet_hours(self) -> None:
        rb = self._brightness_before_quiet
        self._brightness_before_quiet = None
        if rb is not None and self._client is not None:
            try:
                await self._async_set_brightness_clamped(int(rb))
            except Exception as e:
                logger.debug("restore brightness after quiet hours: %s", e)

    def set_quiet_hours_active(self, active: bool) -> None:
        if active == self._quiet_hours_active:
            return
        if not self._runner.is_running:
            try:
                self._runner.start()
            except Exception as e:
                logger.error("BLE thread start failed: %s", e)
                return

        async def _go() -> None:
            if active:
                self._quiet_hours_active = True
                await self._async_enter_quiet_hours()
            else:
                await self._async_exit_quiet_hours()
                self._quiet_hours_active = False

        try:
            self._runner.run_coro(_go(), timeout=45.0)
        except Exception as e:
            logger.warning("set_quiet_hours_active(%s): %s", active, e)
            if active:
                self._quiet_hours_active = False

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
                raise RuntimeError("iDotMatrix client not connected")

            flat_one_line = self._flatten(flat)
            if s.idotmatrix_text_mode == 0:
                screen = ble_static_first_screen(flat_one_line, panel_edge_px=px)
                static_cap = ble_static_character_capacity(px)
                if len(flat_one_line) > len(screen):
                    logger.debug(
                        "BLE text static: %s×%s holds ~%s chars; first screen only",
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
            return self._upload_png(png_raw, None)

        try:
            self._runner.run_coro(_go_text(), timeout=45.0)
            return True
        except Exception as e:
            logger.warning("IDotMatrixApiClientDisplay text failed: %s", e)
            self._connected = False
            try:
                self._runner.run_coro(self._async_connect(), timeout=60.0)
                self._connected = True
                self._runner.run_coro(_go_text(), timeout=45.0)
                return True
            except Exception as e2:
                logger.warning("IDotMatrixApiClientDisplay reconnect failed: %s", e2)
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
            profile = MatrixColorProfile.from_settings(s)
            png_raw = render_panel_view(
                view,
                self._render_px,
                font_path,
                fg=fg,
                bg=bg,
                alert_panel=alert,
                color_profile=profile,
            )
            chrome = snap_chrome_rgb_for_panel(s, view, alert_panel=alert)
            self._upload_png(png_raw, chrome)
            return
        line = panel_view_to_marquee(view)
        self.show_alert(line) if alert else self.show_text(line)

    def clear(self) -> None:
        self.show_text(" ")

    def close(self) -> None:
        if self._quiet_hours_active and self._runner.is_running:
            try:

                async def _restore() -> None:
                    await self._async_exit_quiet_hours()

                self._runner.run_coro(_restore(), timeout=15.0)
            except Exception as e:
                logger.debug("BLE close quiet restore: %s", e)
            self._quiet_hours_active = False
        if self._client is not None and self._runner.is_running:
            try:
                self._runner.run_coro(self._async_disconnect(), timeout=15.0)
            except Exception as e:
                logger.debug("BLE close: %s", e)
        self._runner.stop()

    @property
    def is_connected(self) -> bool:
        return self._connected
