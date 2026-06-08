"""Periodic update-check timer (spec §8.1).

Initial check 30s after launch, then every 4 hours. Emits
``check_requested`` on each tick; controller subscribes to it. Manual
"Check now" calls ``trigger_now()`` directly (bypasses the cadence but
still emits the same signal so all paths converge).
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from keri import help

logger = help.ogler.getLogger(__name__)

INITIAL_DELAY_MS = 30_000               # 30 seconds
CADENCE_MS = 4 * 60 * 60 * 1000         # 4 hours


class UpdateScheduler(QObject):
    """Emits ``check_requested`` on the configured cadence."""

    check_requested = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._initial_timer = QTimer(self)
        self._initial_timer.setSingleShot(True)
        self._initial_timer.timeout.connect(self._on_initial_fired)

        self._cadence_timer = QTimer(self)
        self._cadence_timer.timeout.connect(self._on_cadence_fired)

        self._enabled = False

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def start(self, initial_delay_ms_override: int | None = None) -> None:
        """Begin scheduling. Initial fire at INITIAL_DELAY_MS, then every CADENCE_MS."""
        delay = (
            initial_delay_ms_override
            if initial_delay_ms_override is not None
            else INITIAL_DELAY_MS
        )
        logger.info(
            "[update] scheduler.start initial_delay_ms=%d cadence_ms=%d",
            delay, CADENCE_MS,
        )
        self._enabled = True
        self._initial_timer.start(delay)

    def stop(self) -> None:
        logger.info("[update] scheduler.stop")
        self._enabled = False
        self._initial_timer.stop()
        self._cadence_timer.stop()

    def trigger_now(self) -> None:
        """Manual 'Check now' trigger — emits immediately."""
        logger.info("[update] scheduler.trigger_now")
        self.check_requested.emit()

    def _on_initial_fired(self) -> None:
        logger.info("[update] scheduler.initial_fired")
        self.check_requested.emit()
        self._cadence_timer.start(CADENCE_MS)

    def _on_cadence_fired(self) -> None:
        logger.info("[update] scheduler.cadence_fired")
        self.check_requested.emit()
