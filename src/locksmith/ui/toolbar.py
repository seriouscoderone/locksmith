# -*- encoding: utf-8 -*-
"""
locksmith.ui.toolbar module

This module contains the toolbar component for the Locksmith application.
"""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QToolBar, QLabel, QPushButton
from hio.base import doing
from keri import help

from locksmith.peer.exposure import count_exposed
from locksmith.ui import colors
from locksmith.ui.toolkit.utils import create_spacer, load_scaled_pixmap
from locksmith.ui.toolkit.widgets import HoverIconButton

logger = help.ogler.getLogger(__name__)


class LocksmithToolbar(QToolBar):
    """
    Custom toolbar for Locksmith application.
    Handles dynamic button states based on app state/page.
    """

    # Signals for toolbar actions
    vaults_clicked = Signal()
    lock_clicked = Signal()
    home_clicked = Signal()
    notifications_clicked = Signal()
    plugins_clicked = Signal()

    def __init__(self, app, parent=None):
        """
        Initialize the Locksmith toolbar.

        Parameters:
            app: Application instance.
            parent: Parent widget (typically the main window).
        """
        super().__init__("Main Toolbar", parent)

        self.app = app
        self.setMovable(False)
        self.setFloatable(False)
        self.notifications_button_doer = None
        self._apply_styles()

        # Build toolbar for homepage (default)
        self._build_homepage_toolbar()

    def _apply_styles(self):
        """Apply stylesheet to toolbar."""
        self.setStyleSheet(f"""
            QToolBar {{
                background-color: {colors.TOOLBAR_DARK};
                border-bottom: 1px solid {colors.BORDER_NEUTRAL};
                padding: 4px;
                spacing: 4px;
            }}
            QToolButton {{
                background-color: transparent;
                padding: 4px 2px;
                margin: 2px;
                border-radius: 4px;
                border: none;
            }}
            QToolButton:hover {{
                background-color: {colors.BACKGROUND_NEUTRAL};
            }}
            QToolButton:pressed {{
                background-color: {colors.BACKGROUND_NEUTRAL_HOVER};
            }}
        """)

    def _build_homepage_toolbar(self):
        """Build toolbar layout for homepage."""
        self.addWidget(create_spacer(8))

        # Add clickable favicon icon (navigates to home)
        favicon_button = QPushButton()
        favicon_button.setFixedSize(36, 36)
        favicon_pixmap = load_scaled_pixmap(":/assets/custom/SymbolLogo.svg", 28, 28)
        favicon_button.setIcon(QIcon(favicon_pixmap))
        favicon_button.setIconSize(QSize(28, 28))
        favicon_button.setToolTip("Go to Home")
        favicon_button.setCursor(Qt.CursorShape.PointingHandCursor)
        favicon_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)
        favicon_button.clicked.connect(self.home_clicked.emit)
        self.addWidget(favicon_button)

        self.addWidget(create_spacer(6))
        from locksmith.core.branding import brand
        text_label = QLabel(brand().display_name)
        text_label.setStyleSheet(f"color: {colors.WHITE};")
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)

        text_label.setFont(font)
        self.addWidget(text_label)

        self.vault_name_label = QLabel("")
        self.vault_name_label.setObjectName("toolbar.vaultNameLabel")
        self.vault_name_label.setStyleSheet(f"color: {colors.WHITE};")
        vault_name_font = QFont()
        vault_name_font.setPointSize(16)
        self.vault_name_label.setFont(vault_name_font)
        self.addWidget(self.vault_name_label)

        # Add spacer to push next items to the right
        self.addWidget(create_spacer(expanding=True))

        # Peer-mode network-presence indicator. Always-visible at-a-
        # glance status for the direct peer listener, so the user
        # doesn't have to drill into Settings to see whether their
        # vault is reachable. Hidden until a vault opens — there's no
        # peer state to report otherwise.
        self.peer_indicator = QLabel()
        self.peer_indicator.setObjectName("toolbar_peer_indicator")
        self.peer_indicator.setFixedSize(14, 14)
        self.peer_indicator.setStyleSheet(
            "background-color: #9CA3AF; border-radius: 7px; margin: 0 4px;"
        )
        self.peer_indicator.setToolTip("Peer mode: disabled")
        self.peer_indicator.setVisible(False)
        self.peer_indicator_action = self.addWidget(self.peer_indicator)
        self.addWidget(create_spacer(4))
        # Poll vault state every 5s. The peer doer's bind state changes
        # only on Apply, but exposure count and reachability shift
        # over longer timescales; 5s feels live without burning cycles.
        self._peer_indicator_timer = QTimer(self)
        self._peer_indicator_timer.setInterval(5_000)
        self._peer_indicator_timer.timeout.connect(self._refresh_peer_indicator)
        self._peer_indicator_timer.start()

        # Plugins button — leftmost tool; visible in both logged-out
        # and logged-in states.
        self.plugins_button = HoverIconButton(
            icon_normal="assets/material-icons/extension.svg",
            icon_hover="assets/material-icons/extension-hover.svg",
            tooltip="Plugins"
        )
        self.plugins_button.setObjectName("toolbar_plugins_button")
        self.plugins_button.clicked.connect(self.plugins_clicked.emit)
        self.plugins_action = self.addWidget(self.plugins_button)

        # Notifications button (with dropdown) - initially hidden
        self.notifications_button = NotificationsButton(self.app, self)
        self.notifications_button.clicked.connect(self.notifications_clicked.emit)
        self.notifications_action = self.addWidget(self.notifications_button)
        self.notifications_action.setVisible(False)  # Hidden by default

        # Settings button with hover effect
        self.settings_button = HoverIconButton(
            icon_normal="assets/material-icons/settings.svg",
            icon_hover="assets/material-icons/settings-hover.svg",
            tooltip="Settings"
        )
        self.settings_button.clicked.connect(self.show_settings_dialog)
        self.settings_action = self.addWidget(self.settings_button)

        # Vaults button with hover effect
        self.vaults_button = HoverIconButton(
            icon_normal="assets/material-icons/vault-drawer.svg",
            icon_hover="assets/material-icons/vault-drawer-hover.svg",
            tooltip="Vaults"
        )
        self.vaults_button.setObjectName("toolbar.vaultsButton")
        self.vaults_button.clicked.connect(self.vaults_clicked.emit)
        self.vaults_action = self.addWidget(self.vaults_button)

        # Lock button (close vault) - initially hidden
        self.lock_button = HoverIconButton(
            icon_normal="assets/material-icons/lock.svg",
            icon_hover="assets/material-icons/lock-hover.svg",
            tooltip="Close Vault"
        )
        self.lock_button.clicked.connect(self.lock_clicked.emit)
        self.lock_action = self.addWidget(self.lock_button)
        self.lock_action.setVisible(False)  # Hidden by default

        self.addWidget(create_spacer(6))

    def set_vault_name(self, name: str | None) -> None:
        """Show the open vault's name in the toolbar (window identity).

        Empty when no vault is open. Also the test-observability hook for
        the active vault (selector: toolbar.vaultNameLabel).
        """
        if hasattr(self, "vault_name_label"):
            self.vault_name_label.setText(name or "")

    def set_vaults_active(self, active: bool):
        """
        Set the active state of the vaults button.

        Args:
            active: True to show as active, False for normal state.
        """
        if hasattr(self, 'vaults_button'):
            self.vaults_button.set_active(active)

    def set_plugins_active(self, active: bool):
        """Set the active state of the Plugins toolbar button."""
        if hasattr(self, 'plugins_button'):
            self.plugins_button.set_active(active)

    def _refresh_peer_indicator(self) -> None:
        """Compute current peer-mode state and reflect it in the dot.

        States:
          gray    — no vault open OR listener disabled.
          green   — listener bound + at least one AID exposed (fully usable).
          amber   — listener bound but no AIDs exposed (silent dead-end).
          red     — listener supposed to be running but didn't bind.

        Aligns with the diagnostic banner on the Settings card so the
        toolbar dot and the banner never disagree.
        """
        vault = getattr(self.app, "vault", None)
        if vault is None or not getattr(vault, "hby", None):
            self.peer_indicator.setVisible(False)
            return
        self.peer_indicator.setVisible(True)
        try:
            settings = vault.db.peerSettings.get(keys=("default",))
        except AttributeError:
            settings = None
        if settings is None or not settings.enabled:
            self._set_peer_indicator("#9CA3AF", "Peer mode: disabled")
            return
        doer = getattr(vault, "peer_doer", None)
        bound = (doer is not None and doer.server is not None
                 and doer.server.opened)
        if not bound:
            self._set_peer_indicator(
                "#DC2626",
                "Peer mode: listener failed to bind. Check the Settings "
                "page — port may already be in use.",
            )
            return
        exposed = count_exposed(vault.hby)
        port = doer.server.ha[1] if doer.server.ha else "?"
        if exposed == 0:
            self._set_peer_indicator(
                "#F59E0B",
                f"Peer mode: listening on port {port}, but no identifiers "
                f"are exposed for inbound peer connections.",
            )
        else:
            noun = "identifier" if exposed == 1 else "identifiers"
            self._set_peer_indicator(
                "#22C55E",
                f"Peer mode: listening on port {port}; {exposed} {noun} "
                f"exposed for direct peer connections.",
            )

    def _set_peer_indicator(self, color: str, tooltip: str) -> None:
        self.peer_indicator.setStyleSheet(
            f"background-color: {color}; border-radius: 7px; margin: 0 4px;"
        )
        self.peer_indicator.setToolTip(tooltip)

    def update_for_config(self, config: dict):
        """
        Update toolbar buttons based on configuration from current page.

        Args:
            config (dict): Dictionary with button visibility settings:
                - show_vaults_button (bool)
                - show_lock_button (bool)
                - show_notifications_button (bool)
                - show_settings_button (bool)
        """
        # Update vaults button visibility
        if hasattr(self, 'vaults_action'):
            self.vaults_action.setVisible(config.get('show_vaults_button', True))

        # Update lock button visibility
        if hasattr(self, 'lock_action'):
            self.lock_action.setVisible(config.get('show_lock_button', False))

        # Update notifications button visibility
        if hasattr(self, 'notifications_action'):
            if config.get('show_notifications_button', False):
                self.notifications_button.activate()
                self.notifications_action.setVisible(True)
                self.notifications_button_doer = NotificationButtonDoer(self.notifications_button)
                if self.notifications_button_doer not in self.app.vault.doers:
                    self.app.vault.extend([self.notifications_button_doer])
            else:
                self.notifications_button.deactivate()
                self.notifications_action.setVisible(False)

        # Update settings button visibility
        if hasattr(self, 'settings_action'):
            self.settings_action.setVisible(config.get('show_settings_button', True))


    def show_settings_dialog(self):
        """Open the application Settings dialog (toolbar entry).

        App-wide settings: Updates, Defaults for new vaults, About.
        Per-vault settings live in the vault sidebar Settings entry.
        """
        from locksmith.ui.dialogs.app_settings import AppSettingsDialog
        dialog = AppSettingsDialog(app=self.app, parent=self.parent())
        dialog.open()



class NotificationsButton(HoverIconButton):
    """Notifications icon button with mailbox dropdown menu."""

    def __init__(self, app, parent=None):
        """
        Initialize the NotificationsButton.

        Parameters:
            app: Application instance
            parent: Parent widget
        """
        self.app = app

        # Icon setup
        self.icon_empty_normal = ":/assets/material-icons/notifications.svg"
        self.icon_empty_hover = ":/assets/material-icons/notifications_hover.svg"
        self.icon_unread_normal = ":/assets/material-icons/notifications_blue_dot.svg"
        self.icon_unread_hover = ":/assets/material-icons/notifications_blue.svg"

        super().__init__(self.icon_empty_normal, self.icon_empty_hover, "Notifications")

    def activate(self):

        if self.app.vault:
            self.app.vault.signals.doer_event.connect(self._on_doer_event)

            message_count = 0
            for _, note in self.app.vault.notifier.noter.notes.getTopItemIter():
                if not note.read:
                    message_count += 1

            if message_count > 0:
                self.setIcon(QIcon(self.icon_unread_normal))
                self.icon_normal = self.icon_unread_normal
                self.icon_hover = self.icon_unread_hover
            else:
                self.setIcon(QIcon(self.icon_empty_normal))
                self.icon_normal = self.icon_empty_normal
                self.icon_hover = self.icon_empty_hover

    def deactivate(self):
        # self.app.vault.signals.doer_event.disconnect(self._on_doer_event)
        pass

    def _on_doer_event(self, doer_name: str, event_type: str, data: dict):
        """
        Handle doer events from the signal bridge.

        Args:
            doer_name: Name of the doer that emitted the event
            event_type: Type of event
            data: Event data dictionary
        """
        # Handle key state update completion
        if doer_name == "MailboxListener":
            self.activate()

class NotificationButtonDoer(doing.Doer):
    """Doer for changing icon based on presence of unread mailbox notifications"""

    def __init__(self, button: NotificationsButton, signal_bridge=None, **kwa):
        """
        Initialize the NotificationButtonDoer.

        Args:
            signal_bridge: Optional DoerSignalBridge instance for emitting Qt signals
            button: NotificationsButton instance to monitor
        """
        super().__init__(tock=5.0, **kwa)  # Run every 5 second
        self.button = button
        self.signal_bridge = signal_bridge

    def enter(self, **kwa):
        """Called when doer starts."""
        logger.info(f"Entering NotificationButtonDoer")

    def recur(self, tyme):
        """Called every tock (5 second)."""
        self.button.activate()
        return False

    def exit(self):
        """Called when doer exits."""
        logger.info(f"Exiting NotificationButtonDoer")