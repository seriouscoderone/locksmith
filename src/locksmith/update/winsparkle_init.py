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


def _app_details() -> tuple[str, str, str]:
    """``(company, app_name, current_version)`` for WinSparkle.

    The frozen .exe ships with no VERSIONINFO (``version_file=None`` in the
    spec — the MSI carries version metadata, not the exe), so WinSparkle cannot
    infer the running version. We set it explicitly from ``build_info`` or every
    update check misfires (no version to compare against the appcast).
    """
    from locksmith.build_info import LOCKSMITH_VERSION
    from locksmith.core.branding import brand
    b = brand()
    return (b.org_name, b.display_name, LOCKSMITH_VERSION)


def init_winsparkle(
    *,
    verifier: Callable[[], tuple[bool, str]],
    log_recorder: Callable[..., None],
    on_failure: Callable[[str], None],
    on_shutdown_request: Callable[[], None] | None = None,
):
    """Initialize WinSparkle.

    Returns ``(dll_handle, gate, callbacks_tuple)`` — all must be retained
    by the caller to keep ctypes callbacks alive (Python will free the
    CFUNCTYPE wrappers otherwise and WinSparkle will segfault). On
    non-Windows returns ``(None, None, None)``.

    ``on_shutdown_request`` is invoked when WinSparkle has launched the
    installer and needs the app to terminate so the MSI can replace the running
    exe. It MUST gracefully quit the app — a no-op leaves the exe locked, so the
    installer retries and flickers error/progress dialogs until the user closes
    the app by hand. Called OFF the main thread, so the impl must marshal the
    quit to the main thread.
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
        if on_shutdown_request is not None:
            try:
                on_shutdown_request()
            except Exception as exc:  # noqa: BLE001 - C callback must never raise
                logger.error(
                    "[update] winsparkle.shutdown_request_error err=%s", exc
                )

    c_can_shutdown = CAN_SHUTDOWN_CB(_can_shutdown_cb)
    c_shutdown_req = SHUTDOWN_REQUEST_CB(_shutdown_request_cb)

    appcast_url = _appcast_url()
    company, app_name, version = _app_details()
    # Set the current version BEFORE init (exe has no VERSIONINFO for WinSparkle
    # to read). NOTE: we deliberately do NOT call win_sparkle_set_dsa_pub_pem —
    # passing NULL to "disable" it derefs null and crashes init (it parses the
    # PEM string); leaving it unset means no DSA key, so WinSparkle does no
    # signature verification. KERI is the sole content trust (verified in the
    # can_shutdown gate); Windows Authenticode pins the installed MSI.
    dll.win_sparkle_set_app_details(company, app_name, version)
    dll.win_sparkle_set_appcast_url(appcast_url)
    dll.win_sparkle_set_can_shutdown_callback(c_can_shutdown)
    dll.win_sparkle_set_shutdown_request_callback(c_shutdown_req)
    dll.win_sparkle_init()
    logger.info(
        "[update] winsparkle.initialized appcast=%s version=%s",
        appcast_url.decode(), version,
    )

    callbacks = (c_can_shutdown, c_shutdown_req)
    return dll, gate, callbacks
