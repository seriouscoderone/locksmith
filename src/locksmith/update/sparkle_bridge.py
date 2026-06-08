"""macOS Sparkle 2.x bridge via PyObjC.

Sparkle is used as an *orchestrator only* — its native EdDSA verification
is OFF (no ``SUPublicEDKey`` in Info.plist). All trust flows through the
Python KERI verifier (``locksmith.update.verify.verify_artifact`` from
Phase 4) which we call in
``updater:shouldProceedWithInstallForUpdate:withDownloadedPath:``.

Design:
  - ``SparkleVerifierDelegate`` is a Python class with platform-neutral
    methods (``shouldProceedWithInstall(staged_path) -> bool``) that can
    be unit-tested without PyObjC.
  - ``make_objc_delegate`` returns a PyObjC ``NSObject`` subclass that
    adapts the Sparkle Objective-C protocol calls into the Python class.
    Only constructible on macOS with PyObjC available.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from keri import help

logger = help.ogler.getLogger(__name__)


class SparkleVerifierDelegate:
    """Platform-neutral verification gate. Holds no Objective-C state.

    The PyObjC adapter calls ``willDownloadUpdate`` to feed the release
    metadata captured from the SUAppcastItem, then ``shouldProceedWithInstall``
    once Sparkle has downloaded the artifact to a staging path.
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
        # ``_captured_release_info`` is populated by willDownloadUpdate from
        # the SUAppcastItem the Sparkle delegate receives, then read in
        # shouldProceedWithInstall.
        self._captured_release_info: dict | None = None
        self._staged_path: str | None = None

    def willDownloadUpdate(self, release_info: dict) -> None:
        logger.info(
            "[update] sparkle.will_download_update version=%s",
            release_info.get("version"),
        )
        self._captured_release_info = release_info

    def didDownloadUpdate(self, staged_path: str) -> None:
        logger.info(
            "[update] sparkle.did_download_update path=%s", staged_path,
        )
        self._staged_path = staged_path

    def shouldProceedWithInstall(self, staged_path: str) -> bool:
        """Called between download and install. Returns True iff verifier passes.

        On failure: deletes the staged file, records to verification log,
        invokes ``on_failure`` callback (which the UI layer uses to show
        the toast).
        """
        info = self._captured_release_info or {}
        version = info.get("version", "unknown")
        logger.info("[update] sparkle.verify_begin version=%s", version)

        try:
            ok = self._verifier(staged_path, info)
        except Exception as exc:
            logger.error(
                "[update] sparkle.verify_error version=%s err=%s",
                version, exc,
            )
            ok = False

        if ok:
            logger.info("[update] sparkle.verify_pass version=%s", version)
            self._log_recorder(
                version=version,
                status="verified",
                anchor_said=info.get("anchor_said"),
                artifact_sha256=info.get("artifact_sha256"),
            )
            return True

        logger.warning(
            "[update] sparkle.verify_fail version=%s", version,
        )
        self._log_recorder(
            version=version,
            status="failed",
            anchor_said=info.get("anchor_said"),
            artifact_sha256=info.get("artifact_sha256"),
        )
        # Best-effort delete; ignore errors (Sparkle owns the lifecycle).
        try:
            p = Path(staged_path)
            if p.exists():
                p.unlink()
        except OSError as exc:
            logger.warning(
                "[update] sparkle.cleanup_failed path=%s err=%s",
                staged_path, exc,
            )
        self._on_failure(version)
        return False


# --- macOS-only PyObjC layer ---

if sys.platform == "darwin":  # pragma: no cover - exercised by integration test
    try:
        import objc                                       # noqa: F401
        from Foundation import NSObject                   # noqa: F401
        _PYOBJC_AVAILABLE = True
    except ImportError:
        _PYOBJC_AVAILABLE = False
else:
    _PYOBJC_AVAILABLE = False


def make_objc_delegate(py_delegate: SparkleVerifierDelegate):
    """Return an NSObject adapter forwarding Sparkle callbacks into ``py_delegate``.

    Returns ``None`` on non-macOS or when PyObjC isn't available; in
    practice the macOS bundle always has PyObjC.
    """
    if not _PYOBJC_AVAILABLE:
        return None

    import objc  # noqa: F811
    from Foundation import NSObject  # noqa: F811

    class _SparkleObjCDelegate(NSObject):
        def init(self):
            self = objc.super(_SparkleObjCDelegate, self).init()
            return self

        # Sparkle calls: -updater:willDownloadUpdate:withRequest:
        def updater_willDownloadUpdate_withRequest_(self, updater, item, request):
            info = {
                "version": (
                    str(item.displayVersionString())
                    if hasattr(item, "displayVersionString")
                    else None
                ),
                "anchor_said": _info_from_item(item, "SUAnchorSAID"),
                "artifact_sha256": _info_from_item(item, "SUArtifactSHA256"),
                "anchor_url": _info_from_item(item, "SUAnchorURL"),
                "is_major": _info_from_item(item, "SUIsMajor") == "true",
                "is_critical": _info_from_item(item, "SUIsCritical") == "true",
            }
            py_delegate.willDownloadUpdate(info)

        # Sparkle calls: -updater:didDownloadUpdate:
        def updater_didDownloadUpdate_(self, updater, item):
            # Sparkle doesn't directly expose the staged path here;
            # we capture it in shouldProceedWithInstall via the downloadedPath
            # argument. Record a placeholder for traceability.
            py_delegate.didDownloadUpdate("(captured-on-install)")

        # Sparkle calls:
        #   -updater:shouldProceedWithInstallForUpdate:withDownloadedPath:
        def updater_shouldProceedWithInstallForUpdate_withDownloadedPath_(
            self, updater, item, downloadedPath,
        ):
            path = str(downloadedPath)
            return py_delegate.shouldProceedWithInstall(path)

    delegate = _SparkleObjCDelegate.alloc().init()
    return delegate


def _info_from_item(item, key: str) -> str | None:
    """Read a non-standard SUAppcastItem key set via custom appcast XML.

    Sparkle 2 exposes arbitrary properties through ``propertiesDictionary``.
    """
    try:
        props = item.propertiesDictionary()
        v = props.objectForKey_(key)
        return str(v) if v is not None else None
    except Exception:
        return None
