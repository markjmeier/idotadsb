"""
One-shot check: connect to iDotMatrix over BLE and send text (idotmatrix-api-client).

On the Pi (Bluetooth enabled), after:
  pip install -r requirements-ble-api-client.txt

From repo root:
  DISPLAY_BACKEND=idotmatrix_api_client python -m app.poc_display

Optional: IDOTMATRIX_BLE_ADDRESS=xx:xx:... if you have multiple devices.
"""

from __future__ import annotations

import logging
import sys
import time

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

from app.config import Settings
from app.display import BACKEND_IDOTMATRIX_API_CLIENT, create_display


def main() -> int:
    if load_dotenv is not None:
        load_dotenv()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    s = Settings.from_env()
    if s.display_backend != BACKEND_IDOTMATRIX_API_CLIENT:
        print(
            f"Set DISPLAY_BACKEND={BACKEND_IDOTMATRIX_API_CLIENT} (GitHub idotmatrix-api-client).",
            file=sys.stderr,
        )
        return 1

    try:
        from idotmatrix.client import IDotMatrixClient  # noqa: F401
    except ImportError:
        print(
            "FAIL: idotmatrix-api-client not installed. Run:\n"
            "  pip install -r requirements-ble-api-client.txt",
            file=sys.stderr,
        )
        return 1

    d = create_display(s)

    print("Connecting (first matching iDotMatrix unless IDOTMATRIX_BLE_ADDRESS is set)...")
    try:
        d.connect()
        if hasattr(d, "is_connected") and not d.is_connected:
            print(
                "FAIL: Bluetooth connect did not complete (see logs above).",
                file=sys.stderr,
            )
            print(
                "Check: Bluetooth on, device in range, "
                "IDOTMATRIX_BLE_ADDRESS if multiple devices.",
                file=sys.stderr,
            )
            return 1
        d.show_text("POC\nOK")
        print("Sent test text; leave it scrolling a few seconds...")
        time.sleep(4)
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    finally:
        d.close()

    print("OK: display probe finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
