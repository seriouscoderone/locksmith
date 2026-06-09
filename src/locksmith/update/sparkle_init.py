"""macOS Sparkle 2.x initialization.

Called once from ``locksmith.core.apping.LocksmithApplication`` on Darwin
after the main window is constructed. Creates an
``SPUStandardUpdaterController``, attaches our delegate, and lets the
``UpdateController`` drive checks on its own cadence (Sparkle's built-in
auto-check is disabled via Info.plist ``SUEnableAutomaticChecks=False``).
"""
from __future__ import annotations

import sys
from typing import Callable

from keri import help

from locksmith.update.sparkle_bridge import (
    SparkleVerifierDelegate, make_objc_delegate,
)

logger = help.ogler.getLogger(__name__)

APPCAST_URL = "https://releases.keri.host/appcast/v1/macos.json"


def init_sparkle(
    *,
    verifier: Callable[[str, dict], bool],
    log_recorder: Callable[..., None],
    on_failure: Callable[[str], None],
):
    """Construct the Sparkle controller + delegate.

    Returns ``(controller, py_delegate)``. The caller MUST keep both
    references alive for the lifetime of the app (PyObjC will tear them
    down otherwise). On non-macOS, returns ``(None, None)``.
    """
    if sys.platform != "darwin":
        return None, None

    try:
        from Sparkle import SPUStandardUpdaterController
    except ImportError as exc:
        logger.error("[update] sparkle.import_failed err=%s", exc)
        return None, None

    py_delegate = SparkleVerifierDelegate(
        verifier=verifier,
        log_recorder=log_recorder,
        on_failure=on_failure,
    )
    objc_delegate = make_objc_delegate(py_delegate)

    # startingUpdater=False — we drive checks from our scheduler instead.
    controller = (
        SPUStandardUpdaterController
        .alloc()
        .initWithStartingUpdater_updaterDelegate_userDriverDelegate_(
            False, objc_delegate, None,
        )
    )
    logger.info(
        "[update] sparkle.initialized appcast=%s", APPCAST_URL,
    )
    return controller, py_delegate
