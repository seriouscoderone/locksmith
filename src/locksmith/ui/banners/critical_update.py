"""Critical security-update banner (Phase 5 §8.2 / Task 11).

A persistent red strip at the top of LocksmithWindow that appears
ONLY when the update controller has decided a candidate release is
flagged ``is_critical`` in the appcast. It overrides the silent
install-on-quit behavior so the user knows a security release is
waiting and can act on it immediately rather than next quit.

Two affordances:
- "Install" button — emits ``install_requested`` (caller drives the
  bridge's download + install hand-off).
- Close (X) — emits ``dismissed`` (caller decides whether to suppress
  the banner for the session or treat the dismiss as defer).

State machine (the part this widget owns):
    hidden  --show_for_version(v)-->  visible(v)
    visible(v)  --dismiss()-->        hidden
    visible(v)  --install()-->        visible(v)  (signal only; caller hides)

The widget never re-renders itself based on prefs/policy — that's the
controller's job, and keeping the widget dumb makes the state machine
testable without QSettings or a controller fixture.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)
from keri import help

from locksmith.ui import colors

logger = help.ogler.getLogger(__name__)


class CriticalUpdateBanner(QWidget):
    """Red full-width strip for critical security updates.

    The widget is hidden at construction; call ``show_for_version(v)``
    to populate the version string and reveal it. ``hide_banner()``
    (or clicking the X) returns to the hidden state.
    """

    install_requested = Signal()
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("criticalUpdateBanner")

        self._current_version: str | None = None

        self.setStyleSheet(f"""
            #criticalUpdateBanner {{
                background-color: {colors.DANGER};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 12, 10)
        layout.setSpacing(12)

        self.message_label = QLabel("Critical security update available")
        self.message_label.setObjectName("criticalUpdateBanner.message")
        self.message_label.setStyleSheet(
            "color: white; font-size: 13px; font-weight: 600;"
        )
        layout.addWidget(self.message_label, stretch=1)

        self.install_button = QPushButton("Install now")
        self.install_button.setObjectName("criticalUpdateBanner.installButton")
        self.install_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_button.setStyleSheet(f"""
            QPushButton {{
                background-color: white;
                color: {colors.DANGER};
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {colors.BACKGROUND_HOVER}; }}
            QPushButton:pressed {{ background-color: {colors.BACKGROUND_NEUTRAL}; }}
        """)
        self.install_button.clicked.connect(self._on_install)
        layout.addWidget(self.install_button)

        self.dismiss_button = QPushButton("✕")
        self.dismiss_button.setObjectName("criticalUpdateBanner.dismissButton")
        self.dismiss_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dismiss_button.setFixedSize(28, 28)
        self.dismiss_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                font-size: 16px;
                font-weight: 700;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 40); border-radius: 4px; }
            QPushButton:pressed { background-color: rgba(255, 255, 255, 80); border-radius: 4px; }
        """)
        self.dismiss_button.clicked.connect(self._on_dismiss)
        layout.addWidget(self.dismiss_button)

        # Start hidden — the controller decides when we appear.
        self.hide()

    # ---- state machine ----------------------------------------------

    def show_for_version(self, version: str) -> None:
        """Populate the version and reveal the banner. Idempotent."""
        self._current_version = version
        self.message_label.setText(
            f"Critical security update available (v{version}) — Install now"
        )
        logger.info("[update] critical_banner.shown version=%s", version)
        self.show()

    def hide_banner(self) -> None:
        """Force-hide without emitting ``dismissed`` (controller-driven)."""
        self._current_version = None
        self.hide()

    @property
    def current_version(self) -> str | None:
        """Version the banner is currently displaying, or None if hidden."""
        return self._current_version

    # ---- internal handlers ------------------------------------------

    def _on_install(self) -> None:
        logger.info(
            "[update] critical_banner.install_clicked version=%s",
            self._current_version,
        )
        self.install_requested.emit()

    def _on_dismiss(self) -> None:
        logger.info(
            "[update] critical_banner.dismissed version=%s",
            self._current_version,
        )
        self._current_version = None
        self.hide()
        self.dismissed.emit()
