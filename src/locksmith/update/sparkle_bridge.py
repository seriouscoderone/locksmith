"""macOS Sparkle 2.x bridge via PyObjC.

Sparkle is used as an *orchestrator only* — its native EdDSA verification
is OFF (no ``SUPublicEDKey`` in Info.plist). All trust flows through the
Python KERI verifier (``locksmith.update.verify.verify_artifact`` from
Phase 4).

**Why the gate runs at the pre-download veto.** Sparkle 2's only BOOL veto in
the ``SPUUpdaterDelegate`` protocol is
``updater:shouldProceedWithUpdate:updateCheck:error:`` (every post-download
hook — ``didDownloadUpdate``, ``willInstallUpdate`` — returns ``void`` and
cannot stop an install), and **no** hook in either ``SPUUpdaterDelegate`` or
``SPUUserDriver`` ever exposes the local staged/extracted artifact (Sparkle
keeps it inside its privileged installer). So we can't hash "the bytes Sparkle
is about to install". Instead, at the veto we hand the verifier closure the
artifact's *enclosure URL*; the closure (``apping._make_update_verifier_macos``)
downloads those bytes itself and runs the full ``verify_artifact`` pipeline
against the witnessed KEL. We return ``YES`` only if it passes.

Design:
  - ``SparkleVerifierDelegate`` is a Python class with a platform-neutral
    method (``shouldProceedWithUpdate(info, enclosure_url) -> bool``) that can
    be unit-tested without PyObjC.
  - ``make_objc_delegate`` returns a PyObjC ``NSObject`` subclass — declared
    conformant to ``SPUUpdaterDelegate`` so the ``BOOL``/``NSError**``
    marshaling is correct — that adapts the Objective-C protocol calls into
    the Python class. Only constructible on macOS with PyObjC available.

NOTE: the returned ObjC delegate MUST be retained for the app's lifetime —
``SPUStandardUpdaterController`` holds ``updaterDelegate`` as ``__weak``.
``init_sparkle`` returns it so the caller can keep a strong reference.
"""
from __future__ import annotations

import sys
from typing import Callable

from keri import help

logger = help.ogler.getLogger(__name__)


class SparkleVerifierDelegate:
    """Platform-neutral verification gate. Holds no Objective-C state.

    The PyObjC adapter calls ``shouldProceedWithUpdate`` at Sparkle's
    pre-download veto with the release metadata captured from the
    ``SUAppcastItem`` and the artifact's enclosure URL.
    """

    def __init__(
        self,
        *,
        verifier: Callable[[str, dict], bool],
        log_recorder: Callable[..., None],
        on_failure: Callable[[str], None],
    ):
        # ``verifier`` is ``(enclosure_url, release_info) -> bool``: it fetches
        # the artifact from the URL and runs the KERI verify pipeline.
        self._verifier = verifier
        self._log_recorder = log_recorder
        self._on_failure = on_failure

    def shouldProceedWithUpdate(self, info: dict, enclosure_url: str) -> bool:
        """Sparkle's pre-download veto. Returns True iff the verifier passes.

        On failure: records to the verification log and invokes ``on_failure``
        (which the UI layer uses to show the toast). There is no staged file to
        delete — Sparkle hasn't downloaded yet, and the verifier cleans up the
        copy it fetched.
        """
        info = info or {}
        version = info.get("version") or "unknown"
        logger.info(
            "[update] sparkle.verify_begin version=%s url=%s",
            version, enclosure_url,
        )

        try:
            ok = self._verifier(enclosure_url, info)
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

        logger.warning("[update] sparkle.verify_fail version=%s", version)
        self._log_recorder(
            version=version,
            status="failed",
            anchor_said=info.get("anchor_said"),
            artifact_sha256=info.get("artifact_sha256"),
        )
        self._on_failure(version)
        return False


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


def _release_info_from_item(item) -> dict:
    """Build the release-metadata dict from a SUAppcastItem (macOS only)."""
    return {
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


def _enclosure_url_from_item(item) -> str:
    """Read the remote download URL (the ``<enclosure url>``) off the item."""
    try:
        fu = item.fileURL()
        if fu is not None:
            return str(fu.absoluteString())
    except Exception:
        pass
    return ""


# --- macOS-only PyObjC layer ---

if sys.platform == "darwin":  # pragma: no cover - exercised on a real macOS build
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

    The caller MUST retain the returned object for the app's lifetime —
    Sparkle's ``updaterDelegate`` is ``__weak``.
    """
    if not _PYOBJC_AVAILABLE:
        return None

    import objc  # noqa: F811
    from Foundation import NSError, NSObject  # noqa: F811

    # Declare conformance to SPUUpdaterDelegate (registered when Sparkle.framework
    # was loaded by sparkle_init) so PyObjC uses the protocol's exact type
    # encodings — critical for the BOOL return + NSError** out-param of
    # shouldProceedWithUpdate. Without it PyObjC would infer an object return and
    # the veto would never marshal correctly.
    class_kwargs: dict = {}
    try:
        class_kwargs["protocols"] = [objc.protocolNamed("SPUUpdaterDelegate")]
    except Exception as exc:  # noqa: BLE001 - framework not loaded / name absent
        logger.error(
            "[update] sparkle.protocol_unavailable err=%s "
            "(delegate marshaling may be incorrect)", exc,
        )

    class _SparkleObjCDelegate(NSObject, **class_kwargs):
        # Sparkle calls: -updater:shouldProceedWithUpdate:updateCheck:error:
        # The only BOOL veto in the protocol; it fires BEFORE download.
        # With protocol conformance PyObjC passes the NSError** out-param as the
        # 4th positional arg (a writable holder); we return a bare BOOL and
        # populate error[0] on a block so Sparkle can surface a message.
        def updater_shouldProceedWithUpdate_updateCheck_error_(
            self, updater, item, updateCheck, error,
        ):
            info = _release_info_from_item(item)
            url = _enclosure_url_from_item(item)
            try:
                ok = bool(py_delegate.shouldProceedWithUpdate(info, url))
            except Exception as exc:  # noqa: BLE001 - never raise into ObjC
                logger.error("[update] sparkle.delegate_error err=%s", exc)
                ok = False
            if not ok and error is not None:
                try:
                    error[0] = NSError.errorWithDomain_code_userInfo_(
                        "LocksmithKERIVerification",
                        1,
                        {
                            "NSLocalizedDescription":
                                "Update blocked: KERI verification did not pass.",
                        },
                    )
                except Exception:  # noqa: BLE001 - error holder not writable
                    pass
            return ok

        # Sparkle calls: -updater:willDownloadUpdate:withRequest:
        # Verification already ran at the veto above; this is a liveness probe
        # confirming the (retained) delegate is actually being invoked.
        def updater_willDownloadUpdate_withRequest_(self, updater, item, request):
            logger.info(
                "[update] sparkle.will_download version=%s",
                _release_info_from_item(item).get("version"),
            )

    delegate = _SparkleObjCDelegate.alloc().init()
    return delegate
