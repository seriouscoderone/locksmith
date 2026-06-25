"""macOS Sparkle 2.x initialization.

Called once from ``locksmith.core.apping.LocksmithApplication`` on Darwin
after the main window is constructed. Creates an
``SPUStandardUpdaterController``, attaches our delegate, and lets the
``UpdateController`` drive checks on its own cadence (Sparkle's built-in
auto-check is disabled via Info.plist ``SUEnableAutomaticChecks=False``).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from keri import help

from locksmith.update.sparkle_bridge import (
    SparkleVerifierDelegate, make_objc_delegate,
)

logger = help.ogler.getLogger(__name__)

def _appcast_url() -> str:
    from locksmith.core.branding import brand
    return brand().appcast_macos_xml


def _sparkle_framework_path() -> Path | None:
    """Locate the bundled Sparkle.framework.

    Frozen .app: ``<app>/Contents/Frameworks/Sparkle.framework`` — build-macos.sh
    copies it there after PyInstaller (outside the collect, so it is NOT under
    ``sys._MEIPASS``). Dev: the repo's ``packaging/macos/Sparkle.framework`` if
    present. Returns ``None`` if no framework is found.
    """
    if getattr(sys, "frozen", False):
        contents = Path(sys.executable).resolve().parent.parent  # <app>/Contents
        cand = contents / "Frameworks" / "Sparkle.framework"
        if cand.is_dir():
            return cand
    repo_fw = (
        Path(__file__).resolve().parents[3]
        / "packaging" / "macos" / "Sparkle.framework"
    )
    return repo_fw if repo_fw.is_dir() else None


def _load_sparkle_class():
    """Load the bundled Sparkle.framework via PyObjC and return
    ``SPUStandardUpdaterController``.

    There is no ``pyobjc-framework-Sparkle`` on PyPI (Sparkle is third-party),
    so ``from Sparkle import ...`` never resolves — that was the long-standing
    bug that left the macOS updater uninitialized. Instead, dlopen the bundled
    framework with ``objc.loadBundle`` (PyObjC IS bundled) and look the class up
    from the Objective-C runtime. Raises on any failure (objc missing, framework
    absent, or class not registered).
    """
    import objc

    fw = _sparkle_framework_path()
    if fw is None:
        raise ModuleNotFoundError("Sparkle.framework not found in app bundle")
    objc.loadBundle("Sparkle", {}, bundle_path=str(fw))
    return objc.lookUpClass("SPUStandardUpdaterController")


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
        SPUStandardUpdaterController = _load_sparkle_class()
    except Exception as exc:  # noqa: BLE001 — objc missing, framework absent, or class not found
        logger.error("[update] sparkle.load_failed err=%s", exc)
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
        "[update] sparkle.initialized appcast=%s", _appcast_url(),
    )
    return controller, py_delegate
