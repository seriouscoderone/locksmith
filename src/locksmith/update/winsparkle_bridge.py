"""Windows WinSparkle 0.8+ bridge via ctypes.

WinSparkle has no true "pre-install verification" hook, and — unlike Sparkle's
SUAppcastItem — its callbacks (``can_shutdown``, ``did_find_update``, ...) are
ALL no-arg: WinSparkle 0.8.3 never hands the app the staged artifact, its URL,
or even the version. Its lifecycle:
    1. ``win_sparkle_check_update_with_ui()`` / ``*_without_ui()``
    2. download into WinSparkle's own staging dir (never exposed)
    3. ready to install — calls the "can shutdown?" callback
    4. relaunches the installer (which closes the app)

We hook step 3 — ``win_sparkle_set_can_shutdown_callback`` — as the gate.
Because WinSparkle exposes nothing, the ``verifier`` is a NO-ARG closure
(``apping._make_update_verifier_windows``) that SELF-fetches the appcast,
self-downloads the MSI from its enclosure URL, and runs the KERI verifier
against the witnessed KEL — mirroring the macOS pre-download self-download
approach. It returns ``(ok, version)``. Returning FALSE from the C callback
prevents WinSparkle from launching the MSI installer.

Trust: the OS verifies the Azure-Authenticode-signed MSI it installs (so DSA is
DISABLED via ``win_sparkle_set_dsa_pub_pem(NULL)``); KERI independently verifies
the published artifact + no-downgrade + witnessed anchor. The double-fetch
(verify our copy / WinSparkle installs its copy) is the same accepted gap as
macOS, covered by Authenticode.

Limitation (v1, VM-confirm): WinSparkle's ``can_shutdown`` semantics are "can we
gracefully exit?" — on a FALSE return the update stays staged and WinSparkle may
not re-offer that version until the next check.

NOTE: ``can_shutdown`` is NOT called on the main thread — the gate must be
thread-safe. The verifier (file + network + KERI) is; ``on_failure`` routes
through a Qt queued signal.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import CFUNCTYPE, c_int, c_char_p
from typing import Callable

from keri import help

logger = help.ogler.getLogger(__name__)


# Callback signatures (WinSparkle uses cdecl on Windows).
CAN_SHUTDOWN_CB = CFUNCTYPE(c_int)
SHUTDOWN_REQUEST_CB = CFUNCTYPE(None)
ERROR_CB = CFUNCTYPE(None)


class WinSparkleVerifierGate:
    """Platform-neutral verification gate run inside WinSparkle's can_shutdown
    C callback. ``verifier`` is a no-arg closure returning ``(ok, version)``
    that self-fetches + self-downloads + verifies (WinSparkle gives us nothing).
    """

    def __init__(
        self,
        *,
        verifier: Callable[[], tuple[bool, str]],
        log_recorder: Callable[..., None],
        on_failure: Callable[[str], None],
    ):
        self._verifier = verifier
        self._log_recorder = log_recorder
        self._on_failure = on_failure

    def can_shutdown_and_install(self) -> bool:
        """Hooked into WinSparkle's can-shutdown callback. MUST NOT raise —
        it runs in WinSparkle's C land off the main thread."""
        logger.info("[update] winsparkle.verify_begin")
        try:
            ok, version = self._verifier()
        except Exception as exc:  # noqa: BLE001 - C callback must never raise
            logger.error("[update] winsparkle.verify_error err=%s", exc)
            self._on_failure("unknown")
            return False

        version = version or "unknown"
        if ok:
            logger.info("[update] winsparkle.verify_pass version=%s", version)
            self._log_recorder(version=version, status="verified")
            return True

        logger.warning("[update] winsparkle.verify_fail version=%s", version)
        self._log_recorder(version=version, status="failed")
        self._on_failure(version)
        return False


# --- ctypes layer (Windows-only) ---

def load_winsparkle_dll(dll_path: str | None = None):
    """Load WinSparkle.dll. Returns the CDLL handle, or None on non-Windows."""
    if sys.platform != "win32":
        return None
    candidate = dll_path or "WinSparkle.dll"
    try:
        dll = ctypes.cdll.LoadLibrary(candidate)
    except OSError as exc:
        logger.error(
            "[update] winsparkle.load_failed path=%s err=%s",
            candidate, exc,
        )
        return None

    # Declare prototypes.
    dll.win_sparkle_set_appcast_url.argtypes = [c_char_p]
    dll.win_sparkle_set_appcast_url.restype = None
    dll.win_sparkle_set_dsa_pub_pem.argtypes = [c_char_p]
    dll.win_sparkle_set_dsa_pub_pem.restype = None
    dll.win_sparkle_set_can_shutdown_callback.argtypes = [CAN_SHUTDOWN_CB]
    dll.win_sparkle_set_can_shutdown_callback.restype = None
    dll.win_sparkle_set_shutdown_request_callback.argtypes = [SHUTDOWN_REQUEST_CB]
    dll.win_sparkle_set_shutdown_request_callback.restype = None
    dll.win_sparkle_init.argtypes = []
    dll.win_sparkle_init.restype = None
    dll.win_sparkle_cleanup.argtypes = []
    dll.win_sparkle_cleanup.restype = None
    dll.win_sparkle_check_update_with_ui.argtypes = []
    dll.win_sparkle_check_update_with_ui.restype = None
    dll.win_sparkle_check_update_without_ui.argtypes = []
    dll.win_sparkle_check_update_without_ui.restype = None
    logger.info("[update] winsparkle.dll_loaded path=%s", candidate)
    return dll
