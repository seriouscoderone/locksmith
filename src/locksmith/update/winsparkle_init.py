"""Windows WinSparkle initialization (called from apping.py on win32)."""
from __future__ import annotations

import sys
from typing import Callable

from keri import help

from locksmith.update.winsparkle_bridge import (
    WinSparkleVerifierGate, load_winsparkle_dll,
    CAN_SHUTDOWN_CB, SHUTDOWN_REQUEST_CB,
)

logger = help.ogler.getLogger(__name__)

def _appcast_url() -> bytes:
    from locksmith.core.branding import brand
    return brand().appcast_windows_xml.encode()


def init_winsparkle(
    *,
    verifier: Callable[[str, dict], bool],
    log_recorder: Callable[..., None],
    on_failure: Callable[[str], None],
):
    """Initialize WinSparkle.

    Returns ``(dll_handle, gate, callbacks_tuple)`` — all must be retained
    by the caller to keep ctypes callbacks alive (Python will free the
    CFUNCTYPE wrappers otherwise and WinSparkle will segfault). On
    non-Windows returns ``(None, None, None)``.
    """
    if sys.platform != "win32":
        return None, None, None

    dll = load_winsparkle_dll()
    if dll is None:
        return None, None, None

    gate = WinSparkleVerifierGate(
        verifier=verifier,
        log_recorder=log_recorder,
        on_failure=on_failure,
    )

    def _can_shutdown_cb() -> int:
        return 1 if gate.can_shutdown_and_install() else 0

    def _shutdown_request_cb() -> None:
        logger.info("[update] winsparkle.shutdown_requested")
        # No-op here; WinSparkle proceeds with relaunch after this returns.

    c_can_shutdown = CAN_SHUTDOWN_CB(_can_shutdown_cb)
    c_shutdown_req = SHUTDOWN_REQUEST_CB(_shutdown_request_cb)

    appcast_url = _appcast_url()
    dll.win_sparkle_set_appcast_url(appcast_url)
    dll.win_sparkle_set_dsa_pub_pem(None)            # disable signature check
    dll.win_sparkle_set_can_shutdown_callback(c_can_shutdown)
    dll.win_sparkle_set_shutdown_request_callback(c_shutdown_req)
    dll.win_sparkle_init()
    logger.info(
        "[update] winsparkle.initialized appcast=%s", appcast_url.decode(),
    )

    callbacks = (c_can_shutdown, c_shutdown_req)
    return dll, gate, callbacks
