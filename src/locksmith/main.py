"""Locksmith entrypoint.

The first thing this module does is install a libsodium loader. `keri`
imports `pysodium` at import time, and pysodium's __init__ raises
ValueError("Unable to find libsodium") if `ctypes.util.find_library`
returns None — which it does inside a frozen, notarized .app because
the system has no libsodium and DYLD_LIBRARY_PATH is stripped by the
hardened runtime. So before any keri import we (a) load the bundled
dylib via ctypes, and (b) patch find_library so pysodium picks it up
through its normal path.
"""
import ctypes
import ctypes.util
import os
import platform
import sys
from pathlib import Path


def _bundled_libsodium_path() -> str | None:
    """Return absolute path to the right libsodium binary inside the
    PyInstaller bundle, or None when running unfrozen (dev mode)."""
    if not getattr(sys, "frozen", False):
        return None
    appdir = sys._MEIPASS  # PyInstaller onedir: .app/Contents/Frameworks (mac) or app dir (win)
    system = platform.system()
    if system == "Darwin":
        arch = platform.processor()
        if arch == "x86_64":
            sodium_lib = "libsodium.26.x86_64.dylib"
        elif arch in ("arm", "arm64", "aarch64"):
            sodium_lib = "libsodium.23.arm.dylib"
        else:
            raise OSError(f"Unsupported architecture: {arch}")
        return str(Path(appdir) / "libsodium" / sodium_lib)
    if system == "Windows":
        # PyInstaller drops bundled DLLs alongside the exe (_internal/ on
        # onedir, root on onefile). pysodium's ctypes.util.find_library
        # returns None inside a frozen Windows app because Windows resolves
        # DLLs via the Activation Context, not LD-style search paths.
        # We bake libsodium.dll into the bundle via the spec's `binaries`
        # and search both the _internal dir and the appdir for it.
        candidates = [
            Path(appdir) / "libsodium.dll",
            Path(appdir) / "_internal" / "libsodium.dll",
            Path(sys.executable).parent / "libsodium.dll",
            Path(sys.executable).parent / "_internal" / "libsodium.dll",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return None
    return None


def _bootstrap_libsodium() -> None:
    bundled = _bundled_libsodium_path()
    if bundled is None:
        return  # dev mode (or platform without bundled libsodium)
    if not os.path.exists(bundled):
        raise FileNotFoundError(f"bundled libsodium missing: {bundled}")

    # Pre-load so the library is in the address space.
    ctypes.cdll.LoadLibrary(bundled)

    # pysodium calls ctypes.util.find_library('sodium') at *import* time.
    # In a frozen bundle find_library returns None (no /usr/local/lib or
    # %WINDIR%\System32\libsodium.dll), so we override it to point at our
    # bundled binary BEFORE pysodium loads.
    _orig_find_library = ctypes.util.find_library

    def _find_library(name: str):
        if name in ("sodium", "libsodium"):
            return bundled
        return _orig_find_library(name)

    ctypes.util.find_library = _find_library


def _bootstrap_ssl_certs() -> None:
    """Point OpenSSL's default verify path at certifi's bundled CA file.

    A frozen PyInstaller app ships its own OpenSSL whose baked-in default CA
    paths point at the BUILD machine — absent on the user's machine — so the
    DEFAULT ssl context (``ssl.create_default_context()``, which keri/hio's
    TCP-TLS clients use for every witness/mailbox HTTPS connection) raises
    ``CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`` and the
    vault's background tasks die on open (the vault-crash backstop then closes
    the vault). ``update/verify.py`` already passes ``certifi.where()`` explicitly
    for the update path; the vault/keri path uses the process default context, so
    set ``SSL_CERT_FILE`` (which OpenSSL reads for its default verify path) once at
    startup — before any keri import. No-op unfrozen (a source checkout's OpenSSL
    CA paths are valid) and never overrides a caller-set value.
    """
    if not getattr(sys, "frozen", False):
        return
    try:
        import certifi
        cafile = certifi.where()
    except Exception:  # noqa: BLE001 - never block startup on cert setup
        return
    if os.path.exists(cafile):
        os.environ.setdefault("SSL_CERT_FILE", cafile)


if platform.system() in ("Darwin", "Windows"):
    _bootstrap_libsodium()
    _bootstrap_ssl_certs()

# ---- safe to import the rest of the world now ---------------------------
import asyncio
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen
from keri import help
from qasync import QEventLoop

FORMAT = "%(asctime)s [%(name)s] %(levelname)-8s %(message)s"


def _make_splash() -> QSplashScreen | None:
    """A Qt splash shown during the (slow) main-window construction.

    Replaces PyInstaller's Tcl/Tk ``Splash()`` resource, which can't run inside
    a macOS ``.app`` (so the splash had been dropped on macOS) and DPI-rescales
    on Windows (the "moves and shrinks" jank). A ``QSplashScreen`` is DPI-correct
    and works on every platform, so the splash is back on macOS and stable on
    Windows. Returns ``None`` when the art is missing (no splash, never crash).
    """
    try:
        pixmap = QPixmap(":/assets/custom/SplashScreen.png")
        if pixmap.isNull():
            logger.warning("splash art not found at :/assets/custom/SplashScreen.png; skipping splash")
            return None
        return QSplashScreen(pixmap, Qt.WindowType.WindowStaysOnTopHint)
    except Exception as exc:  # noqa: BLE001 - a splash must never block startup
        logger.warning("splash init failed: %s; skipping", exc)
        return None
LOG_LEVEL = "INFO"

help.ogler.level = logging.getLevelName(LOG_LEVEL)
baseFormatter = logging.Formatter(FORMAT)
baseFormatter.default_msec_format = None
help.ogler.baseConsoleHandler.setFormatter(baseFormatter)

# Attach a rotating file handler under the per-OS app data dir so that
# update-path log lines ([update] …, native_updater.*, winsparkle.*) land
# on disk.  On Windows, GUI apps have no console stderr, so this is the
# only way to diagnose WinSparkle failures post-hoc.
from locksmith.update.file_logging import setup_file_logging as _setup_file_logging
_diag_log_path = _setup_file_logging()

logger = help.ogler.getLogger(__name__)
logger.info("file_logging.started path=%s", _diag_log_path)


def parse_vault_arg(argv: list[str]) -> str | None:
    """Return the value of ``--vault <name>`` from argv, or None."""
    if "--vault" in argv:
        i = argv.index("--vault")
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def parse_window_pos(argv: list[str]) -> tuple[int, int] | None:
    """Return the ``--win-pos X,Y`` top-left position from argv, or None.

    Used by the cascade: a launched instance opens offset from the window
    that spawned it so both are visible at once.
    """
    if "--win-pos" in argv:
        i = argv.index("--win-pos")
        if i + 1 < len(argv):
            try:
                x_str, y_str = argv[i + 1].split(",")
                return (int(x_str), int(y_str))
            except ValueError:
                return None
    return None


if __name__ == "__main__":
    # Pre-empt Qt initialisation entirely for the verifier CLI path. The
    # standalone --verify-update path is a no-UI mode anyone can run on a
    # downloaded artifact; it must not spin up the wallet window.
    if any(
        arg == "--verify-update" or arg.startswith("--verify-update=")
        for arg in sys.argv[1:]
    ):
        from locksmith.update.cli import run as run_verify
        sys.exit(run_verify(sys.argv[1:]))

    if len(sys.argv) > 1 and sys.argv[1] == "--mcp-server":
        logger.info("MCP server mode detected")
        logger.info(f"sys.argv: {sys.argv}")
        logger.info(f"sys.executable: {sys.executable}")
        logger.info(f"Frozen: {getattr(sys, 'frozen', False)}")

    from locksmith.ui.styles import set_global_styles
    from locksmith.core.configing import LocksmithConfig
    from locksmith.ui.window import LocksmithWindow

    app = QApplication(sys.argv)
    set_global_styles(app)

    # Show the splash BEFORE the (slow) window construction so it covers the
    # launch gap on every platform, then process events once to paint it now.
    splash = _make_splash()
    if splash is not None:
        splash.show()
        app.processEvents()

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    config = LocksmithConfig.get_instance()
    window = LocksmithWindow(config)

    target_vault = parse_vault_arg(sys.argv)
    if target_vault and window.app.coordinator.request_raise(target_vault):
        # Another instance already owns this vault — raise it and exit
        # before showing our window, so there's no flash/Dock bounce.
        if splash is not None:
            splash.close()
        logger.info(f"instance.startup.focused_existing vault={target_vault}")
        sys.exit(0)

    window.show()

    # Hand the splash off to the now-visible window (closes it cleanly).
    if splash is not None:
        splash.finish(window)

    # Cascade: if launched from another instance, open offset from it so both
    # windows are visible (set after show so the move sticks on all platforms).
    win_pos = parse_window_pos(sys.argv)
    if win_pos is not None:
        window.move(*win_pos)
        logger.info(
            f"instance.startup.window_pos requested=({win_pos[0]},{win_pos[1]}) "
            f"actual=({window.x()},{window.y()})"
        )

    if target_vault:
        logger.info(f"instance.startup.opening vault={target_vault}")
        window.open_vault_targeted(target_vault)

    with loop:
        sys.exit(loop.run_forever())
