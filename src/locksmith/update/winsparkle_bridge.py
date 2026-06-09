"""Windows WinSparkle 0.8+ bridge via ctypes.

WinSparkle has no true "pre-install verification" hook. Its lifecycle:
    1. ``win_sparkle_check_update_with_ui()`` / ``*_without_ui()``
    2. download into Sparkle staging dir
    3. ready to install — calls the "can shutdown?" callback
    4. relaunches the installer (which closes the app)

We hook step 3 — ``win_sparkle_set_can_shutdown_callback`` — to invoke
the Python KERI verifier. Returning FALSE from that callback prevents
WinSparkle from launching the MSI installer.

Limitation: WinSparkle's ``can_shutdown_callback`` semantics are
"can we gracefully exit?" rather than "should we install?". On a
FALSE return the update simply stays in the staging directory; on
next launch WinSparkle won't re-trigger the same artifact (it remembers
the version was "downloaded"). We treat this as acceptable for v1 and
document it in the verification log dialog.

Signature verification is DISABLED via ``win_sparkle_set_dsa_pub_pem(NULL)``.
KERI is the sole trust mechanism (spec §3).
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import CFUNCTYPE, c_int, c_char_p
from pathlib import Path
from typing import Callable

from keri import help

logger = help.ogler.getLogger(__name__)


# Callback signatures (WinSparkle uses cdecl on Windows).
CAN_SHUTDOWN_CB = CFUNCTYPE(c_int)
SHUTDOWN_REQUEST_CB = CFUNCTYPE(None)
ERROR_CB = CFUNCTYPE(None)


class WinSparkleVerifierGate:
    """Platform-neutral verification gate; mirrors SparkleVerifierDelegate.

    Lifecycle:
      - WinSparkle (or a thin appcast adapter) calls ``set_release_info``
        once the candidate metadata is known.
      - WinSparkle stages the download and calls ``set_staged_path``.
      - WinSparkle invokes ``can_shutdown_and_install`` via the C callback
        before launching the MSI.
    """

    def __init__(
        self,
        *,
        verifier: Callable[[str, dict], bool],
        log_recorder: Callable[..., None],
        on_failure: Callable[[str], None],
    ):
        self._verifier = verifier
        self._log_recorder = log_recorder
        self._on_failure = on_failure
        self._release_info: dict = {}
        self._staged_path: str | None = None

    def set_release_info(self, info: dict) -> None:
        self._release_info = info or {}

    def set_staged_path(self, path: str | None) -> None:
        self._staged_path = path

    def can_shutdown_and_install(self) -> bool:
        """Hooked into WinSparkle's can-shutdown callback."""
        if not self._staged_path:
            logger.warning("[update] winsparkle.no_staged_path_at_install")
            return False
        version = self._release_info.get("version", "unknown")
        logger.info(
            "[update] winsparkle.verify_begin version=%s", version,
        )

        try:
            ok = self._verifier(self._staged_path, self._release_info)
        except Exception as exc:
            logger.error(
                "[update] winsparkle.verify_error version=%s err=%s",
                version, exc,
            )
            ok = False

        if ok:
            logger.info(
                "[update] winsparkle.verify_pass version=%s", version,
            )
            self._log_recorder(
                version=version, status="verified",
                anchor_said=self._release_info.get("anchor_said"),
                artifact_sha256=self._release_info.get("artifact_sha256"),
            )
            return True

        logger.warning(
            "[update] winsparkle.verify_fail version=%s", version,
        )
        self._log_recorder(
            version=version, status="failed",
            anchor_said=self._release_info.get("anchor_said"),
            artifact_sha256=self._release_info.get("artifact_sha256"),
        )
        try:
            p = Path(self._staged_path)
            if p.exists():
                p.unlink()
        except OSError as exc:
            logger.warning(
                "[update] winsparkle.cleanup_failed path=%s err=%s",
                self._staged_path, exc,
            )
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
