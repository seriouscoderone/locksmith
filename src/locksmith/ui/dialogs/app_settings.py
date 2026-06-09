"""Application-wide Settings dialog — opened from the toolbar Settings button.

Holds app-wide concerns (Updates, Defaults for new vaults, About). The
per-vault Settings sidebar entry holds per-vault concerns (Peer Mode,
Danger Zone, Browser Plugin). See plan
``docs/superpowers/plans/2026-06-09-settings-two-surface-refactor.md``.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from keri import help

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import LocksmithButton
from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog

logger = help.ogler.getLogger(__name__)


class AppSettingsDialog(LocksmithDialog):
    """Modal app-settings dialog.

    Args:
        app: The LocksmithApplication (or a SimpleNamespace stub in tests).
            ``app.update_controller`` is read when wiring the Updates
            section; ``None`` is tolerated for tests / pre-init states.
        parent: Parent QWidget (the main window).
    """

    def __init__(self, *, app: Any | None = None, parent: QWidget | None = None) -> None:
        self._app = app

        # Title row uses a styled QLabel rather than the dialog's default
        # title bar, matching the existing show_settings_dialog convention.
        title_content = QLabel("Settings")
        title_content.setObjectName("appSettingsDialog.titleLabel")
        title_content.setStyleSheet(f"font-size: 24px; color: {colors.TEXT_DARK};")

        # Body: a scrollable column that section widgets will be added to.
        self._body = QWidget()
        self._body.setObjectName("appSettingsDialog.body")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(20, 10, 20, 10)
        self._body_layout.setSpacing(20)
        self._body_layout.addStretch()  # bottom spacer; widgets insert above

        scroll = QScrollArea()
        scroll.setObjectName("appSettingsDialog.scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._body)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        self._close_button = LocksmithButton("Close")
        self._close_button.setObjectName("appSettingsDialog.closeButton")
        button_layout.addStretch()
        button_layout.addWidget(self._close_button)

        super().__init__(
            parent=parent,
            title="Settings",
            title_content=title_content,
            show_close_button=True,
            show_title_divider=False,
            content=scroll,
            buttons=button_layout,
        )
        self.setObjectName("appSettingsDialog")
        self.setFixedSize(720, 650)

        self._close_button.clicked.connect(self.accept)

        self._mount_sections()

    def _mount_sections(self) -> None:
        """Compose the section widgets into the dialog body."""
        from locksmith.ui.dialogs.defaults_settings_widget import (
            DefaultsSettingsWidget,
        )
        from locksmith.ui.vault.settings.updates_widget import (
            UpdatesSettingsWidget,
        )

        self._defaults_widget = DefaultsSettingsWidget()
        self._insert_section(self._defaults_widget)

        ctrl = getattr(self._app, "update_controller", None) if self._app else None
        self._updates_widget = UpdatesSettingsWidget(
            prefs=ctrl.prefs if ctrl else None,
        )
        if ctrl is not None:
            self._updates_widget.set_check_now_callback(ctrl.check_now)

        def _on_view_log() -> None:
            # Walk up to the top-level LocksmithWindow and open its
            # dialog via the same handler the Help menu uses.
            top = self.window()
            handler = getattr(top, "_on_show_verification_log_clicked", None)
            if handler is not None:
                handler()
        self._updates_widget.set_view_log_callback(_on_view_log)
        self._insert_section(self._updates_widget)

    def _insert_section(self, widget: QWidget) -> None:
        """Insert a section widget above the trailing stretch."""
        # stretch is the last item; insert before it
        last_index = self._body_layout.count() - 1
        self._body_layout.insertWidget(last_index, widget)
