"""Top-level update controller (cross-platform).

Wires together: scheduler + decision tree + prefs + (later) platform bridge.
The actual platform-specific updater (Sparkle / WinSparkle) is plugged in
via ``set_bridge()`` so unit tests can drive the controller without
PyObjC/ctypes.

UI signals (consumed by the main session's UI stage):
    - ``action_decided(UpdateDecision)``  fires after every successful check
    - ``check_failed(str)``               fires when fetch fails
    - ``verification_failed(str)``        fires when KERI verification rejects
                                          a downloaded artifact (str = version)
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal
from keri import help

from locksmith.update.decision import (
    Release, UpdateAction, UpdateDecision,
)
from locksmith.update.prefs import UpdatePrefs
from locksmith.update.scheduler import UpdateScheduler

logger = help.ogler.getLogger(__name__)


class UpdateController(QObject):
    """Cross-platform update orchestrator.

    The bridge (Sparkle / WinSparkle) drives the actual download and the
    OS-installer hand-off. The controller owns the *decision* about
    whether a candidate is shown to the user at all, *gates* installation
    on KERI verification, and exposes a uniform signal surface to the
    UI layer that lands in a later task.
    """

    action_decided = Signal(object)        # UpdateDecision
    check_failed = Signal(str)             # error message
    verification_failed = Signal(str)      # version string

    def __init__(
        self,
        *,
        current_version: str,
        platform: str,
        prefs: UpdatePrefs | None = None,
        scheduler: UpdateScheduler | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.current_version = current_version
        self.platform = platform
        self.prefs = prefs or UpdatePrefs()
        self.scheduler = scheduler or UpdateScheduler(self)
        self.scheduler.check_requested.connect(self._on_check_requested)

        self._bridge = None  # set by sparkle_init / winsparkle_init

        # Override-able for tests:
        self._fetch_latest_release: Callable[[], Optional[Release]] = (
            self._default_fetch_release
        )

    def start(self) -> None:
        """Begin scheduled checks if prefs allow."""
        if self.prefs.check_automatically:
            logger.info("[update] controller.start check_automatically=True")
            self.scheduler.start()
        else:
            logger.info(
                "[update] controller.start check_automatically=False (idle)"
            )

    def stop(self) -> None:
        self.scheduler.stop()

    def check_now(self) -> None:
        """Manual 'Check now' entry point — bypasses auto-check pref."""
        logger.info("[update] controller.check_now (manual)")
        self.scheduler.trigger_now()

    def set_bridge(self, bridge) -> None:
        """Inject platform-specific Sparkle/WinSparkle bridge.

        The bridge is expected to expose:
          - ``fetch_latest_release() -> Release | None``
          - (callbacks plugged in at bridge init time)
        """
        self._bridge = bridge

    def report_verification_failed(self, version: str) -> None:
        """Called by the platform bridge after KERI verification rejects an
        artifact. Forwards to the UI layer via the ``verification_failed``
        signal so a toast can be shown.
        """
        logger.warning(
            "[update] controller.verification_failed version=%s", version,
        )
        self.verification_failed.emit(version)

    # --- internals ---

    def _on_check_requested(self) -> None:
        if not self.prefs.check_automatically:
            logger.info("[update] controller.check_skipped (auto disabled)")
            return
        try:
            release = self._fetch_latest_release()
        except Exception as exc:  # network/parse error
            logger.warning("[update] controller.fetch_failed err=%s", exc)
            self.check_failed.emit(str(exc))
            return

        if release is None:
            logger.info("[update] controller.fetch_returned_none")
            return

        decision = UpdateDecision.evaluate(
            current_version=self.current_version,
            release=release,
        )
        logger.info(
            "[update] controller.action_decided action=%s candidate=%s",
            decision.action.value, release.version,
        )
        self.action_decided.emit(decision)

    def _default_fetch_release(self) -> Release | None:
        """Hook into the bridge's appcast fetch.

        The bridge is the canonical source because Sparkle/WinSparkle both
        own their own appcast download loop (we don't second-guess them
        with a parallel fetch).
        """
        if self._bridge is None:
            return None
        return self._bridge.fetch_latest_release()
