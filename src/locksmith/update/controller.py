"""Top-level update controller (cross-platform).

Owns the update prefs (auto-check toggle, first-launch consent, last-seen
version) and the check cadence (UpdateScheduler). Discovery + download +
install are driven by the native Sparkle/WinSparkle frameworks; this
controller simply triggers the native check on a manual "Check now"
(``check_now``) or on a scheduled tick (when auto-check is enabled), via
the injected ``on_check`` callback.

UI signal:
    - ``verification_failed(str)`` — emitted (via ``report_verification_failed``)
      when the native KERI gate rejects a downloaded artifact (str = version).
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Signal
from keri import help

from locksmith.update.prefs import UpdatePrefs
from locksmith.update.scheduler import UpdateScheduler

logger = help.ogler.getLogger(__name__)


class UpdateController(QObject):
    """Owns update prefs + cadence; routes checks to the native updater."""

    verification_failed = Signal(str)  # version string

    def __init__(
        self,
        *,
        prefs: UpdatePrefs | None = None,
        scheduler: UpdateScheduler | None = None,
        on_check: Callable[[], None] | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.prefs = prefs or UpdatePrefs()
        self.scheduler = scheduler or UpdateScheduler(self)
        self._on_check = on_check or (lambda: None)
        self.scheduler.check_requested.connect(self._on_scheduled_tick)

    def start(self) -> None:
        if self.prefs.check_automatically:
            logger.info("[update] controller.start check_automatically=True")
            self.scheduler.start()
        else:
            logger.info("[update] controller.start check_automatically=False (idle)")

    def stop(self) -> None:
        self.scheduler.stop()

    def check_now(self) -> None:
        """Manual 'Check now' — always fires (bypasses the auto-check pref)."""
        logger.info("[update] controller.check_now (manual)")
        self._on_check()

    def report_verification_failed(self, version: str) -> None:
        logger.warning("[update] controller.verification_failed version=%s", version)
        self.verification_failed.emit(version)

    def _on_scheduled_tick(self) -> None:
        if not self.prefs.check_automatically:
            logger.info("[update] controller.tick_skipped (auto disabled)")
            return
        logger.info("[update] controller.tick → native check")
        self._on_check()
