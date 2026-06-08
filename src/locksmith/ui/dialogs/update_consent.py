"""First-launch update consent dialog (Phase 5 §8.5 / Task 9).

One-time modal asking the user whether Locksmith may check for updates
automatically. Honest about what the network call does: fetches an
appcast over HTTPS, no telemetry, no tracking, no per-install
identifiers. The user can flip the answer later via Settings -> Updates.

The dialog is purely presentational + prefs-bound: it writes
``UpdatePrefs.consent_seen`` after either button is clicked, and writes
``UpdatePrefs.check_automatically`` only when "Allow" is clicked.
Wiring (when to open it, what to do next) lives in the bootstrap
caller, which listens for ``accepted`` / ``declined``.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from keri import help

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog
from locksmith.update.prefs import UpdatePrefs

logger = help.ogler.getLogger(__name__)


_HEADLINE = "Allow Locksmith to check for updates automatically?"
_BODY = (
    "Locksmith can periodically check keri.host for new releases and "
    "install them when you quit the app. Each release is cryptographically "
    "verified against the publisher's KERI key event log before it is "
    "installed — Locksmith refuses to install an artifact that does not "
    "match a witnessed anchor."
)
_PRIVACY = (
    "No telemetry, no tracking, no per-install identifiers. The check "
    "fetches a small public appcast over HTTPS and nothing else. You can "
    "change this any time in Settings → Updates."
)


class UpdateConsentDialog(LocksmithDialog):
    """Two-button consent dialog. ``consent_accepted`` / ``consent_declined``
    signals let the bootstrap kick off (or skip) the controller's first check.
    (They are named off ``accepted``/``rejected`` to avoid colliding with the
    built-in QDialog signals of those names.)

    Both buttons set ``UpdatePrefs.consent_seen = True`` so the dialog
    does not re-appear on subsequent launches. Only "Allow" sets
    ``UpdatePrefs.check_automatically = True``; "Not now" leaves the
    pref untouched (default is True at the QSettings level, so the
    caller is responsible for forcing it to False on decline).
    """

    # Renamed off ``accepted`` / ``rejected`` to avoid shadowing the
    # built-in QDialog signals of the same name (QDialog.accept() emits
    # accepted on the C++ side, which would double-fire our handler).
    consent_accepted = Signal()
    consent_declined = Signal()

    def __init__(
        self,
        prefs: UpdatePrefs | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._prefs = prefs or UpdatePrefs()
        content = self._build_content()
        buttons = self._build_buttons()
        super().__init__(
            parent=parent,
            title="Automatic Updates",
            content=content,
            buttons=buttons,
            show_overlay=True,
            show_close_button=False,
        )
        self.setObjectName("updateConsentDialog")

    # ---- layout ---------------------------------------------------------

    def _build_content(self) -> QWidget:
        wrap = QWidget()
        wrap.setMinimumWidth(520)
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(14)

        headline = QLabel(_HEADLINE)
        headline.setObjectName("updateConsentDialog.headline")
        headline.setWordWrap(True)
        headline.setStyleSheet(
            f"color: {colors.TEXT_DARK}; font-size: 16px; font-weight: 600;"
        )
        layout.addWidget(headline)

        body = QLabel(_BODY)
        body.setObjectName("updateConsentDialog.body")
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.PlainText)
        body.setStyleSheet(
            f"color: {colors.TEXT_PRIMARY}; font-size: 13px;"
        )
        layout.addWidget(body)

        privacy = QLabel(_PRIVACY)
        privacy.setObjectName("updateConsentDialog.privacy")
        privacy.setWordWrap(True)
        privacy.setTextFormat(Qt.TextFormat.PlainText)
        privacy.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 12px;"
        )
        layout.addWidget(privacy)

        return wrap

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addStretch(1)

        self.not_now_button = QPushButton("Not now")
        self.not_now_button.setObjectName("updateConsentDialog.notNowButton")
        self.not_now_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.not_now_button.setStyleSheet(f"""
            QPushButton {{
                padding: 10px 22px;
                background-color: transparent;
                color: {colors.TEXT_PRIMARY};
                border: 1px solid {colors.BORDER};
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{ background-color: {colors.BACKGROUND_HOVER}; }}
            QPushButton:pressed {{ background-color: {colors.BACKGROUND_NEUTRAL}; }}
        """)
        self.not_now_button.clicked.connect(self._on_decline)
        row.addWidget(self.not_now_button)

        self.allow_button = QPushButton("Allow")
        self.allow_button.setObjectName("updateConsentDialog.allowButton")
        self.allow_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.allow_button.setDefault(True)
        self.allow_button.setStyleSheet(f"""
            QPushButton {{
                padding: 10px 24px;
                background-color: {colors.PRIMARY};
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {colors.PRIMARY_HOVER}; }}
            QPushButton:pressed {{ background-color: {colors.PRIMARY_PRESSED}; }}
        """)
        self.allow_button.clicked.connect(self._on_accept)
        row.addWidget(self.allow_button)
        return row

    # ---- behaviour ------------------------------------------------------

    def _on_accept(self) -> None:
        self._prefs.check_automatically = True
        self._prefs.consent_seen = True
        logger.info("[update] consent.accepted check_automatically=True")
        self.consent_accepted.emit()
        self.accept()

    def _on_decline(self) -> None:
        # Leave check_automatically at its existing (default) value but
        # mark consent_seen so we don't ask again. The caller decides
        # whether to force-disable auto-check on decline; we don't
        # second-guess that policy here.
        self._prefs.consent_seen = True
        logger.info("[update] consent.declined")
        self.consent_declined.emit()
        self.reject()

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def should_show(prefs: UpdatePrefs | None = None) -> bool:
        """True only on first launch — caller decides whether to open us."""
        p = prefs or UpdatePrefs()
        return p.consent_seen is False
