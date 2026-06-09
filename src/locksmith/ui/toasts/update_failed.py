"""Update-failed toast (Phase 5 §9.2 / Task 12).

Lower-right transient notification that fires when KERI verification
rejects a downloaded artifact. Spec §9 forbids any "Install anyway"
affordance — verification failure is terminal for that artifact, full
stop. The toast is purely informational + a click target into the
``VerificationLogDialog`` for users who want to inspect why.

Style + lifecycle mirror ``locksmith.ui.toolkit.widgets.toast.NotificationToast``:
- Lower-right of the parent window
- Fade-out animation
- Auto-dismiss after ~10s
- Single visible instance (caller is responsible for not stacking)

Spec §9.2 also requires generic copy that does not leak version
numbers or hash details to the toast surface. The version is stored
internally so the click handler can pass it to the verification log
dialog, but the user-facing label stays generic.
"""
from __future__ import annotations

from PySide6.QtCore import (
    Qt,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    Signal,
)
from PySide6.QtGui import QCursor, QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)
from keri import help

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import LocksmithIconButton

logger = help.ogler.getLogger(__name__)


# 10s per the user's spec — longer than the generic notification toast
# (5s) because the message is more consequential.
_AUTO_DISMISS_MS = 10_000


class UpdateFailedToast(QFrame):
    """Click-to-investigate toast for a rejected update.

    Signals:
        clicked: emitted when the user clicks the body of the toast.
            The bootstrap wires this to open the VerificationLogDialog
            with the failed ``VerificationResult``.
        closed: emitted when the toast disappears (auto-dismiss or
            user X). Useful for the controller to clear its "one toast
            visible" guard.
    """

    clicked = Signal()
    closed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("updateFailedToast")
        self._version: str | None = None

        self.setFixedSize(380, 96)

        # Match NotificationToast's frameless top-level pattern so the
        # toast paints over the main window without being clipped.
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        # Opacity for fade-out (mirrors NotificationToast)
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity_effect)
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(300)
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.fade_animation.finished.connect(self._on_fade_finished)

        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.fade_out)

        self._setup_ui()

    # ---- layout ------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)

        self.headline_label = QLabel("Update couldn't be verified")
        self.headline_label.setObjectName("updateFailedToast.headline")
        self.headline_label.setStyleSheet(
            f"color: {colors.DANGER}; font-size: 14px; font-weight: 700;"
        )
        top.addWidget(self.headline_label)
        top.addStretch()

        self.close_button = LocksmithIconButton(
            icon_path=":/assets/material-icons/close.svg",
            tooltip="Dismiss",
            icon_size=18,
        )
        self.close_button.setObjectName("updateFailedToast.closeButton")
        self.close_button.clicked.connect(self._on_close_clicked)
        top.addWidget(self.close_button)

        layout.addLayout(top)

        self.body_label = QLabel(
            "Click for details from the verification log."
        )
        self.body_label.setObjectName("updateFailedToast.body")
        self.body_label.setStyleSheet(
            f"color: {colors.TEXT_PRIMARY}; font-size: 12px;"
        )
        self.body_label.setWordWrap(True)
        layout.addWidget(self.body_label)

    # ---- public API --------------------------------------------------

    def show_for_version(self, version: str) -> None:
        """Reveal the toast, attaching ``version`` for the click handler.

        Idempotent within a single visible instance: if already shown,
        the version is updated but the toast does not re-animate.
        """
        self._version = version
        logger.info("[update] toast.update_failed.shown version=%s", version)
        if not self.isVisible():
            self.opacity_effect.setOpacity(1.0)
            self.show()
            self.raise_()
        # Restart the 10s timer on each show — covers the case of the
        # toast being re-armed for a second failed update before the
        # first 10s elapsed.
        self.dismiss_timer.start(_AUTO_DISMISS_MS)

    @property
    def current_version(self) -> str | None:
        """Version most recently attached to the toast (for click handler)."""
        return self._version

    def fade_out(self) -> None:
        """Begin the fade-out animation. Auto-called by the timer."""
        self.dismiss_timer.stop()
        self.fade_animation.start()

    # ---- event handlers ---------------------------------------------

    def mousePressEvent(self, event):  # noqa: N802 — Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            logger.info(
                "[update] toast.update_failed.clicked version=%s",
                self._version,
            )
            self.clicked.emit()
        super().mousePressEvent(event)

    def _on_close_clicked(self) -> None:
        # Suppress click-through to the body so dismissing via X does
        # not also fire ``clicked`` and open the verification log.
        self.dismiss_timer.stop()
        self.hide()
        self.closed.emit()

    def _on_fade_finished(self) -> None:
        self.hide()
        self.opacity_effect.setOpacity(1.0)
        self.closed.emit()

    # ---- positioning -------------------------------------------------

    def position_in_parent(self, parent_width: int, parent_height: int) -> None:
        """Place the toast in the parent window's lower-right corner.

        Caller passes the parent geometry so the toast does not need
        to inspect its parent (keeps it testable without a window).
        """
        if not self.parent():
            return
        margin = 20
        x = parent_width - self.width() - margin
        y = parent_height - self.height() - margin
        global_pos = self.parent().mapToGlobal(self.parent().rect().topLeft())
        self.move(global_pos.x() + x, global_pos.y() + y)

    # ---- painting ----------------------------------------------------

    def paintEvent(self, event):  # noqa: N802 — Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect(), 6, 6)
        painter.fillPath(path, QColor(colors.BACKGROUND_ERROR))
        painter.setPen(QColor(colors.DANGER_LIGHT))
        painter.drawPath(path)
