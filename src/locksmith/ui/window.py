# -*- encoding: utf-8 -*-
"""
locksmith.ui.window module

This module contains the main window for the Locksmith application.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QStackedWidget,
)
from keri import help

from locksmith.core.apping import LocksmithApplication
from locksmith.core.configing import LocksmithConfig
from locksmith.ui.home import HomePage
from locksmith.ui.navigation import NavigationManager, Pages
from locksmith.ui.toolbar import LocksmithToolbar
from locksmith.ui.toolkit.widgets.toast import NotificationToast
from locksmith.ui.vault.page import VaultPage
from locksmith.ui.vaults.drawer import VaultDrawer

logger = help.ogler.getLogger(__name__)


class LocksmithWindow(QMainWindow):
    """
    Main application window.

    Handles composition of components, navigation management,
    and delegates functionality to specialized components.
    """

    def __init__(self, config: LocksmithConfig | None = None):
        """
        Initialize the main window.

        Args:
            config: Application configuration.
        """
        super().__init__()

        self.app = LocksmithApplication(config=config)

        # Staged-install tracking: set to plugin_id between install() and trust.
        self._pending_trust_install: str | None = None

        # Window setup
        self.setWindowTitle("Locksmith")
        self.setMinimumSize(1280, 1024)

        # Create navigation manager
        self.nav_manager = NavigationManager(self)
        self.nav_manager.page_changed.connect(self.on_page_changed)

        # Create and add toolbar
        self.toolbar = LocksmithToolbar(self.app, self)
        self.toolbar.settings_clicked.connect(self.on_settings)
        self.toolbar.vaults_clicked.connect(self.on_vaults)
        self.toolbar.lock_clicked.connect(self.on_lock_vault)
        self.toolbar.home_clicked.connect(self.on_home)
        self.toolbar.notifications_clicked.connect(self.on_notifications)
        self.toolbar.plugins_clicked.connect(self.on_plugins)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create stacked widget for pages (not StackAll mode)
        self.main_stack = QStackedWidget()
        self.main_stack.setContentsMargins(0, 0, 0, 0)

        # Create pages
        from locksmith.ui.plugins.page import PluginsPage
        self.pages = {}
        self.pages[Pages.HOME] = HomePage(self)
        self.pages[Pages.PLUGINS] = PluginsPage(self.app, self)
        self.pages[Pages.VAULT] = VaultPage(self)

        # Wire PluginsPage signals
        plugins_page = self.pages[Pages.PLUGINS]
        plugins_page.install_requested.connect(self._handle_install_requested)
        plugins_page.install_trusted.connect(self._handle_install_trusted)
        plugins_page.uninstall_clicked.connect(self._handle_uninstall)
        plugins_page.exclude_toggled.connect(self._handle_exclude_toggle)
        plugins_page.restart_requested.connect(self._handle_restart_requested)
        # Cancel: page collapses its panel, window rolls back pre-trust installs.
        plugins_page._install_panel.cancelled.connect(self._handle_install_cancelled)

        # Store VaultPage reference for plugin access
        vault_page = self.pages[Pages.VAULT]
        self.app._vault_page = vault_page

        # Wire the vault-hosted PluginsContent signals to the same handlers as
        # the top-level PluginsPage so install/uninstall/exclude work from both
        # surfaces.
        vault_plugins = vault_page.get_plugins_content()
        if vault_plugins is not None:
            vault_plugins.install_requested.connect(self._handle_install_requested)
            vault_plugins.install_trusted.connect(self._handle_install_trusted)
            vault_plugins.uninstall_clicked.connect(self._handle_uninstall)
            vault_plugins.exclude_toggled.connect(self._handle_exclude_toggle)
            vault_plugins.restart_requested.connect(self._handle_restart_requested)
            vault_plugins._install_panel.cancelled.connect(self._handle_install_cancelled)

        # Discover plugins from the index + entry-points and call initialize on each.
        self.app.plugin_manager.discover()
        # Register vault-plugin pages and menus into the VaultPage.
        self.app.plugin_manager.discover_and_initialize_vault_ui(
            vault_page, vault_page.nav_menu,
        )

        # Add pages to stack
        for page in self.pages.values():
            self.main_stack.addWidget(page)

        # Add stack to layout
        main_layout.addWidget(self.main_stack)

        # Create vault drawer (homepage-specific, overlays on top)
        self.vault_drawer = VaultDrawer(self, self.toolbar)
        self.vault_drawer.drawer_opened.connect(lambda: self.toolbar.set_vaults_active(True))
        self.vault_drawer.drawer_closed.connect(lambda: self.toolbar.set_vaults_active(False))

        # Toast notification tracking (only one toast at a time)
        self.current_toast: NotificationToast | None = None
        self._toast_signal_connected = False

        # Start on home page
        self.nav_manager.navigate_to(Pages.HOME)

        # Run app-lifecycle hooks for any AppPlugin instances loaded above.
        # Done last so plugins see a fully-constructed window.
        self.app.plugin_manager.on_app_started(window=self)

        logger.info("LocksmithHome initialized")

    def on_page_changed(self, page_name: str, params: dict):
        """
        Handle page change from NavigationManager.

        Args:
            page_name (str): Name of the page to show
            params (dict): Parameters for the page
        """
        try:
            page_enum = Pages(page_name)
            page = self.pages.get(page_enum)

            if page is None:
                logger.error(f"Page not found: {page_name}")
                return

            logger.info(f"Switching to page: {page_name} with params: {params}")

            # Get the current page (to call on_hide)
            current_page = self.main_stack.currentWidget()
            if current_page and hasattr(current_page, 'on_hide'):
                current_page.on_hide()

            # Switch to new page
            self.main_stack.setCurrentWidget(page)

            # Update toolbar configuration
            toolbar_config = page.get_toolbar_config()
            logger.info(f"Toolbar config: {toolbar_config}")
            self.toolbar.update_for_config(toolbar_config)

            # Sync Plugins toolbar button active state.
            self.toolbar.set_plugins_active(page_enum == Pages.PLUGINS)

            # Update page-specific UI elements
            self._update_page_ui(page_enum)

            # Call on_show for new page
            if hasattr(page, 'on_show'):
                page.on_show(**params)

        except ValueError:
            logger.error(f"Invalid page name: {page_name}")

    def _update_page_ui(self, page: Pages):
        """
        Update page-specific UI elements (drawers, menus, etc.).

        Args:
            page (Pages): The page being shown
        """
        if page == Pages.HOME:
            # Home page: vault drawer is available
            self.vault_drawer.show_drawer_widgets()
            # Ensure drawer is properly positioned after showing
            self.vault_drawer.handle_resize(
                self.width(),
                self.height(),
                self.toolbar.height()
            )
            # Disconnect toast signals when leaving vault
            self._disconnect_toast_signals()

        elif page == Pages.PLUGINS:
            # Plugins page (top-level): vault drawer is available so users
            # can switch vaults from anywhere. Same geometry as home.
            self.vault_drawer.show_drawer_widgets()
            self.vault_drawer.handle_resize(
                self.width(),
                self.height(),
                self.toolbar.height()
            )
            self._disconnect_toast_signals()

        elif page == Pages.VAULT:
            # Vault page: hide vault drawer (nav menu is in VaultPage)
            self.vault_drawer.hide_drawer_widgets()
            # Connect toast signals when vault is active
            self._connect_toast_signals()

    def _connect_toast_signals(self):
        """Connect to vault signals for toast notifications."""
        if not self._toast_signal_connected and self.app.vault:
            try:
                self.app.vault.signals.doer_event.connect(self._on_notification_event)
                self._toast_signal_connected = True
                logger.info("Connected to vault notification signals")
            except Exception as e:
                logger.exception(f"Error connecting toast signals: {e}")

    def _disconnect_toast_signals(self):
        """Disconnect from vault signals."""
        if self._toast_signal_connected and self.app.vault:
            try:
                self.app.vault.signals.doer_event.disconnect(self._on_notification_event)
                self._toast_signal_connected = False
                logger.info("Disconnected from vault notification signals")
            except Exception as e:
                logger.exception(f"Error disconnecting toast signals: {e}")

    def _on_notification_event(self, doer_name: str, event_type: str, data: dict):
        """
        Handle notification events from the vault.

        Args:
            doer_name: Name of the doer that emitted the event
            event_type: Type of event
            data: Event data dictionary
        """
        if doer_name == "NotificationToast" and event_type == "new_notification":
            # Show the toast with notification details
            datetime = data.get('datetime', '')
            message = data.get('message', 'New notification')
            pending_count = data.get('pending_count', 1)

            self.show_notification_toast(datetime, message, pending_count)

    def resizeEvent(self, event):
        """
        Handle window resize - delegate to components.

        Args:
            event: Resize event.
        """
        super().resizeEvent(event)

        # Always update vault drawer positioning to keep geometry in sync
        # even when drawer is hidden (ensures correct positioning when shown later)
        if hasattr(self, 'vault_drawer'):
            self.vault_drawer.handle_resize(
                self.width(),
                self.height(),
                self.toolbar.height()
            )

        # Reposition toast if it exists and is visible
        if self.current_toast and self.current_toast.isVisible():
            self.current_toast.position_in_parent(
                self.width(),
                self.height(),
                self.toolbar.height()
            )

    def on_plugins(self) -> None:
        """Handle plugins button click.

        When a vault is open AND we are on the vault page, show Plugins as a
        vault sub-page (sidebar persists, toolbar config stays vault-config).
        When logged out OR on Pages.HOME/PLUGINS top-level, use the existing
        top-level toggle behavior.
        """
        vault_page = self.pages.get(Pages.VAULT)
        if (
            self.app.is_vault_open
            and self.main_stack.currentWidget() is vault_page
        ):
            vault_page.show_plugins()
            return

        # Existing toggle behavior for top-level (no vault open).
        if self.nav_manager.get_current_page() == Pages.PLUGINS:
            if self.nav_manager.can_navigate_back():
                self.nav_manager.go_back()
            else:
                self.nav_manager.navigate_to(Pages.HOME)
            return
        self.nav_manager.navigate_to(Pages.PLUGINS)

    def on_settings(self):
        """Handle settings button click."""
        logger.info("Settings clicked")
        # Settings dialog is shown by toolbar
        pass

    def on_vaults(self):
        """Handle vaults button click - delegate to drawer."""
        logger.info("Vaults clicked")
        self.vault_drawer.toggle()

    def on_lock_vault(self):
        """Handle lock button click - close vault and return to home."""
        logger.info("Lock button clicked - closing vault")

        # Disconnect toast signals before closing vault
        self._disconnect_toast_signals()

        # Close any visible toast
        if self.current_toast:
            self.current_toast.close_toast()

        # Close the vault (cleanup QtTask, etc.)
        self.app.close_vault()

        # Clear navigation stack (we're going back to home, not "back" navigation)
        self.nav_manager.clear_navigation_stack()

        # Navigate to home page
        self.nav_manager.navigate_to(Pages.HOME)

        # Reset title
        self.setWindowTitle("Locksmith")

    def on_home(self):
        """Handle home icon click - close vault if open and navigate to home."""
        logger.info("Home icon clicked")

        # If a vault is open, close it first
        if self.app.is_vault_open:
            # Disconnect toast signals before closing vault
            self._disconnect_toast_signals()

            # Close any visible toast
            if self.current_toast:
                self.current_toast.close_toast()

            self.app.close_vault()

        # Clear navigation stack
        self.nav_manager.clear_navigation_stack()

        # Navigate to home page
        self.nav_manager.navigate_to(Pages.HOME)

    def show_notification_toast(self, datetime: str, message: str, pending_notifications: int):
        """
        Show a notification toast in the lower right corner.

        Only one toast can be shown at a time. If a toast is already visible,
        it will be closed before showing the new one.

        Args:
            datetime: The datetime string to display
            message: The notification message text
            pending_notifications: Number of pending notifications
        """
        # Close existing toast if any
        if self.current_toast:
            self.current_toast.close_toast()
            self.current_toast.deleteLater()
            self.current_toast = None

        # Create new toast
        self.current_toast = NotificationToast(datetime, message, pending_notifications, self)

        # Connect signals
        self.current_toast.clicked.connect(self._on_toast_clicked)
        self.current_toast.closed.connect(self._on_toast_closed)

        # Position and show
        self.current_toast.position_in_parent(
            self.width(),
            self.height(),
            self.toolbar.height()
        )
        self.current_toast.show_toast()

        logger.info(f"Notification toast shown: {message[:50]}...")

    def _on_toast_clicked(self):
        """Handle toast click - navigate to notification screen."""
        logger.info("Toast clicked - navigating to notifications page")

        # Close the toast
        if self.current_toast:
            self.current_toast.close_toast()

        # Navigate to vault page if not already there
        current_page = self.main_stack.currentWidget()
        vault_page = self.pages.get(Pages.VAULT)

        if vault_page and current_page != vault_page:
            self.nav_manager.navigate_to(Pages.VAULT)

        # Show notifications page
        if vault_page:
            vault_page.show_notifications()

    def _on_toast_closed(self):
        """Handle toast closed - cleanup reference."""
        if self.current_toast:
            self.current_toast.deleteLater()
            self.current_toast = None
        logger.info("Toast closed")

    def on_notifications(self):
        """Handle notifications button click - show notifications page in vault."""
        logger.info("Notifications button clicked")

        # Only show notifications if we're on the vault page
        vault_page = self.pages.get(Pages.VAULT)
        if vault_page and self.main_stack.currentWidget() == vault_page:
            vault_page.show_notifications()

    def _handle_restart_requested(self) -> None:
        """Restart the wallet — close vault, spawn a new process, quit this one."""
        import sys
        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QApplication

        logger.info("plugin.restart.initiated")

        # Best-effort close-vault before relaunch. Plugin lifecycle hooks
        # (on_app_stopping + service.stop) fire in closeEvent which Qt will
        # invoke as part of QApplication.quit() below.
        if self.app.vault is not None:
            try:
                self.app.close_vault()
            except Exception:
                logger.exception("plugin.restart.close_vault_failed")

        # Spawn a new instance of ourselves with the same launch line. The
        # `-m locksmith.main` form is used because that's how the wallet is
        # currently launched in development; a frozen-binary path goes
        # through sys.argv directly.
        if getattr(sys, "frozen", False):
            QProcess.startDetached(sys.executable, sys.argv[1:])
        else:
            QProcess.startDetached(sys.executable, ["-m", "locksmith.main"] + sys.argv[1:])
        logger.info("plugin.restart.spawned_new_process")

        # Quit this instance. Qt will call closeEvent on the window, which
        # already calls plugin_manager.on_app_stopping().
        QApplication.quit()

    # ------------------- Plugin install/uninstall/exclude handlers ---

    def _refresh_all_plugin_views(self, restart_required: bool | None = True) -> None:
        """Refresh both the top-level PluginsPage and the vault sub-page PluginsContent.

        ``restart_required`` semantics:
        - True  → turn the banner on.
        - False → clear the banner.
        - None  → leave the banner state alone (just re-render rows).
        """
        surfaces = [self.pages[Pages.PLUGINS]]
        vault_page = self.pages.get(Pages.VAULT)
        if vault_page is not None and hasattr(vault_page, "get_plugins_content"):
            content = vault_page.get_plugins_content()
            if content is not None:
                surfaces.append(content)
        for surface in surfaces:
            surface._refresh()
            if restart_required is not None:
                surface.set_restart_required(restart_required)

    def _surface_for_signal(self):
        """Return the PluginsPage / PluginsContent that emitted the current signal.

        Falls back to the top-level page if the sender can't service the API
        (e.g. tests calling these handlers directly with no signal context).
        """
        s = self.sender()
        if s is not None and hasattr(s, "show_trust_step"):
            return s
        return self.pages[Pages.PLUGINS]

    def _handle_install_requested(self, source) -> None:
        from locksmith.plugins.installer import InstallError, PluginInstaller
        surface = self._surface_for_signal()
        installer = PluginInstaller()
        try:
            record = installer.install(source)
        except InstallError as e:
            # Stay in source mode, render error inline. No popup.
            surface.show_install_error(str(e))
            return
        surface.show_trust_step(
            manifest_snapshot=record["manifest_snapshot"],
            source=record["source"],
            commit=record["commit"],
        )
        # Cache the staged record so we can roll it back if the user cancels trust.
        self._pending_trust_install = record["plugin_id"]

    def _handle_install_trusted(self, plugin_id: str) -> None:
        logger.info("plugin.trust.accepted plugin_id=%s", plugin_id)
        self._pending_trust_install = None
        self._surface_for_signal().collapse_install_panel()
        self._refresh_all_plugin_views(restart_required=True)

    def _handle_install_cancelled(self) -> None:
        # The page already collapsed its panel before emitting this.
        # If we have a pending trust-stage install, roll it back.
        from locksmith.plugins.installer import InstallError, PluginInstaller
        pid = self._pending_trust_install
        if pid:
            try:
                PluginInstaller().uninstall(pid)
            except InstallError:
                logger.exception("plugin.rollback_failed plugin_id=%s", pid)
            self._pending_trust_install = None
            # Rollback restored on-disk state to match the running manager —
            # no pending changes, clear the restart banner.
            self._refresh_all_plugin_views(restart_required=False)
        else:
            # Source-mode cancel: nothing changed on disk, leave banner alone.
            self._refresh_all_plugin_views(restart_required=None)

    def _handle_uninstall(self, plugin_id: str) -> None:
        from locksmith.plugins.installer import InstallError, PluginInstaller
        try:
            PluginInstaller().uninstall(plugin_id)
        except InstallError as e:
            self._show_error("Uninstall failed", str(e))
            return
        self._refresh_all_plugin_views(restart_required=True)

    def _handle_exclude_toggle(self, plugin_id: str, now_excluded: bool) -> None:
        from pathlib import Path
        from locksmith.plugins import storage
        keri_base = Path(getattr(self.app.config, "base", None) or (Path.home() / ".keri"))
        current = storage.read_enable_list(keri_base)
        excluded = set(current.get("excluded", []))
        if now_excluded:
            excluded.add(plugin_id)
        else:
            excluded.discard(plugin_id)
        storage.write_enable_list(keri_base, {"format": 1, "excluded": sorted(excluded)})
        self._refresh_all_plugin_views(restart_required=True)

    def _show_error(self, title: str, message: str) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, title, message)

    # ------------------- Window lifecycle ----------------------------

    def closeEvent(self, event) -> None:
        try:
            self.app.plugin_manager.on_app_stopping()
        except Exception:
            logger.exception("plugin.on_app_stopping.dispatch_failed")
        super().closeEvent(event)