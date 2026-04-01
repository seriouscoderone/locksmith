# -*- encoding: utf-8 -*-
"""
locksmith.plugins.kerifoundation.plugin module

KERI Foundation plugin — provides witness provisioning and registration
flows for Lock wallet users.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, QEvent, QObject
from keri import help

from locksmith.plugins.base import PluginBase, WitnessProviderPlugin
from locksmith.ui.vault.menu import MenuButton, MenuSpacer
from locksmith.ui.toolkit.widgets.buttons import BackButton

from locksmith.plugins.kerifoundation.db.basing import KFBaser
from locksmith.plugins.kerifoundation.witnesses.list import WitnessOverviewPage
from locksmith.plugins.kerifoundation.witnesses.provision import WitnessProvisionPage
from locksmith.plugins.kerifoundation.watchers.list import WatcherListPage
from locksmith.plugins.kerifoundation.watchers.register import WatcherRegisterPage

logger = help.ogler.getLogger(__name__)


class KeriFoundationPlugin(PluginBase, WitnessProviderPlugin):
    """KERI Foundation witness/watcher provider plugin.

    No account gate — clicking the sidebar entry goes straight to
    the witness overview.  Users select an identifier, provision and
    register witnesses, then receive TOTP QR codes for their
    authenticator app.
    """

    @property
    def plugin_id(self) -> str:
        return "kerifoundation"

    def initialize(self, app: Any) -> None:
        self._app = app
        self._db = None
        self._wit_btn = None
        self._wat_btn = None

        # Build pages
        self._witness_overview = WitnessOverviewPage(app)
        self._witness_provision = WitnessProvisionPage(app)
        self._watcher_list = WatcherListPage(app)
        self._watcher_register = WatcherRegisterPage(app)

        # Wire internal signals
        self._wire_internal_signals()

        logger.info("KeriFoundationPlugin initialized")

    def _wire_internal_signals(self):
        """Connect page signals for navigation."""
        # Overview "Add Witnesses" → provision page
        self._witness_overview.add_witnesses_requested.connect(self._on_add_witnesses)

        # Provision page done/cancel → back to overview
        self._witness_provision.completed.connect(self._on_provision_completed)
        self._witness_provision.cancelled.connect(self._on_provision_cancelled)

    def _on_add_witnesses(self, hab_pre):
        """Navigate to the provision page for a specific identifier."""
        self._witness_provision.set_identifier(hab_pre)
        self._navigate("kf_provision")
        self._witness_provision.on_show()

    def _on_provision_completed(self):
        """Return to witness overview after successful provisioning."""
        self._navigate("kf_witnesses")
        self._witness_overview.on_show()
        self._set_active_nav(self._wit_btn)

    def _on_provision_cancelled(self):
        """Return to witness overview on cancel."""
        self._navigate("kf_witnesses")
        self._witness_overview.on_show()
        self._set_active_nav(self._wit_btn)

    def _set_active_nav(self, active_btn):
        """Highlight the active nav button and deactivate the others."""
        for btn in (self._wit_btn, self._wat_btn):
            if btn is not None:
                btn.set_active(btn is active_btn)

    def _navigate(self, page_key):
        """Show a page by its key via the VaultPage."""
        vault_page = getattr(self._app, "_vault_page", None)
        if vault_page is not None:
            vault_page._show_page(page_key)

    def on_vault_opened(self, vault: Any) -> None:
        self._db = KFBaser(name=f"kf_{vault.hby.name}", reopen=True)
        self._witness_overview.set_db(self._db)
        self._witness_provision.set_db(self._db)
        logger.info(f"KF plugin DB opened for vault '{vault.hby.name}'")

    def on_vault_closed(self, vault: Any) -> None:
        if self._db:
            self._db.close()
            self._db = None
        self._witness_overview.set_db(None)
        self._witness_provision.set_db(None)
        logger.info("KF plugin DB closed")

    def get_menu_entry(self) -> MenuButton:
        icon = QIcon(":/assets/custom/SymbolLogo.svg")
        return MenuButton(icon=icon, label="KERI Foundation")

    def get_menu_section(self) -> list[QWidget]:
        items = []

        # Back button
        back = BackButton(dark_mode=False)
        items.append(back)

        # Logo + label (clickable → navigate to default page)
        logo_widget = self._build_logo_widget()
        logo_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self._logo_click_filter = self._make_logo_click_filter()
        logo_widget.installEventFilter(self._logo_click_filter)
        items.append(logo_widget)

        # Spacer
        items.append(MenuSpacer(15))

        # Witnesses nav button
        self._wit_btn = MenuButton(
            icon=QIcon(":/assets/material-icons/witness1.svg"),
            label="Witnesses",
        )
        self._wit_btn.clicked.connect(lambda: self._navigate("kf_witnesses"))
        self._wit_btn.clicked.connect(lambda: self._witness_overview.on_show())
        self._wit_btn.clicked.connect(lambda: self._set_active_nav(self._wit_btn))
        items.append(self._wit_btn)

        # Watchers nav button
        self._wat_btn = MenuButton(
            icon=QIcon(":/assets/material-icons/watcher.svg"),
            label="Watchers",
        )
        self._wat_btn.clicked.connect(lambda: self._navigate("kf_watchers"))
        self._wat_btn.clicked.connect(lambda: self._watcher_list.on_show())
        self._wat_btn.clicked.connect(lambda: self._set_active_nav(self._wat_btn))
        items.append(self._wat_btn)

        return items

    def _make_logo_click_filter(self):
        """Create a QObject event filter for the clickable logo."""
        plugin = self

        class _LogoClickFilter(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.MouseButtonRelease:
                    plugin._navigate("kf_witnesses")
                    plugin._witness_overview.on_show()
                    plugin._set_active_nav(plugin._wit_btn)
                    return True
                return False

        return _LogoClickFilter()

    def get_pages(self) -> dict[str, QWidget]:
        return {
            "kf_witnesses": self._witness_overview,
            "kf_provision": self._witness_provision,
            "kf_watchers": self._watcher_list,
            "kf_watcher_register": self._watcher_register,
        }

    def get_witness_batches(self, vault: Any, hab_pre: str) -> Any | None:
        """Return batch groupings for KF witnesses belonging to this hab."""
        if not self._db:
            return None

        batches = self._db.witBatches.get(keys=(hab_pre,))
        if batches and batches.batches:
            return batches
        return None

    def get_witness_state(self, vault: Any, wit_eid: str) -> Any | None:
        if not self._db:
            return None
        for (_, eid), record in self._db.witnesses.getItemIter(keys=()):
            if eid == wit_eid:
                return record
        return None

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _build_logo_widget(self):
        """Build a small logo + text widget for the plugin submenu header."""
        widget = QWidget()
        widget.setFixedHeight(72)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 8, 12, 4)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        icon_label = QLabel()
        pixmap = QPixmap(":/assets/custom/SymbolLogo.svg")
        if not pixmap.isNull():
            icon_label.setPixmap(pixmap.scaled(
                40, 40,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        text_label = QLabel("KERI Foundation")
        text_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #333;")
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text_label)

        return widget
