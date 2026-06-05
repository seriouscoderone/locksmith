# -*- encoding: utf-8 -*-
"""
locksmith.ui.home.vaults module

This module contains the VaultDrawer component for managing vaults.
"""
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QRect, QSize
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QLabel, QGraphicsOpacityEffect, QHBoxLayout, \
    QListWidgetItem, QListWidget, QMenu, QToolButton
from keri import help

from locksmith.core.instancing import InstanceLauncher
from locksmith.ui import colors
from locksmith.ui.toolkit.utils import load_scaled_pixmap, create_spacer
from locksmith.ui.toolkit.widgets import LocksmithButton
from locksmith.ui.toolkit.widgets.fields import LocksmithLineEdit
from locksmith.ui.vaults.create import CreateVaultDialog
from locksmith.ui.vaults.open import OpenVaultDialog

if TYPE_CHECKING:
    from locksmith.ui.window import LocksmithWindow

logger = help.ogler.getLogger(__name__)

class VaultDrawer(QWidget):
    """
    Vault drawer that slides in from the right with overlay.
    Manages its own animation and state.
    """

    # Signals
    drawer_opened = Signal()
    drawer_closed = Signal()

    def __init__(self, parent: "LocksmithWindow", toolbar_ref):
        """
        Initialize the VaultDrawer.

        Args:
            parent: Parent window (needed for positioning).
            toolbar_ref: Reference to toolbar (needed for height calculations).
        """
        super().__init__(parent)

        self.parent = parent
        self.toolbar_ref = toolbar_ref
        self.drawer_visible = False
        self.drawer_width = 330
        self.app = self.parent.app
        self._overlay_animation_connected = False  # Track connection state

        # Create components
        self._create_overlay()
        self._create_drawer_widget()

    def _create_overlay(self):
        """Create a semi-transparent overlay that appears behind the drawer."""
        self.drawer_overlay = QFrame(self.parent)
        self.drawer_overlay.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 150);
            }
        """)
        self.drawer_overlay.hide()

        # Ensure overlay stays below toolbar
        self.drawer_overlay.setWindowFlag(Qt.WindowType.SubWindow)

        # Make overlay clickable to close drawer
        self.drawer_overlay.mousePressEvent = lambda event: self.toggle()

        # Position overlay to cover everything except toolbar
        toolbar_height = self.toolbar_ref.height()
        self.drawer_overlay.setGeometry(
            0,
            toolbar_height,
            self.parent.width(),
            self.parent.height() - toolbar_height
        )

        # Create opacity effect for fade animation
        self.overlay_opacity = QGraphicsOpacityEffect(self.drawer_overlay)
        self.drawer_overlay.setGraphicsEffect(self.overlay_opacity)

        # Create fade animation
        self.overlay_animation = QPropertyAnimation(self.overlay_opacity, b"opacity")
        self.overlay_animation.setDuration(300)  # Match drawer animation duration
        self.overlay_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _create_drawer_widget(self):
        """Create the vault drawer that slides in from the right."""
        # Create drawer widget
        self.vault_drawer = QFrame(self.parent)
        self.vault_drawer.setStyleSheet(f"""
            QFrame {{
                background-color: {colors.BACKGROUND_WINDOW};
                border-top-left-radius: 16px;
                border-bottom-left-radius: 16px;
            }}
            QFrame#vault-header-divider {{
                background-color: {colors.DIVIDER};
                max-height: 3px;
            }}
        """)

        # Drawer layout
        drawer_layout = QVBoxLayout(self.vault_drawer)
        drawer_layout.setContentsMargins(0, 16, 0, 16)
        drawer_layout.setSpacing(0)

        # Title
        drawer_header_layout = QHBoxLayout()
        drawer_header_layout.addWidget(create_spacer(12))
        drawer_header_layout.setContentsMargins(10, 10, 16, 10)
        drawer_header_layout.setSpacing(10)


        favicon_label = QLabel()
        favicon_pixmap = load_scaled_pixmap(":/assets/custom/SymbolLogo.svg", 36, 36)
        favicon_label.setPixmap(favicon_pixmap)
        drawer_header_layout.addWidget(favicon_label)

        title_label = QLabel("Vaults")
        title_label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {colors.TEXT_PRIMARY};")
        drawer_header_layout.addWidget(title_label)
        drawer_header_layout.addStretch()

        # "＋ New Instance" button — spawns a fresh process with no vault open.
        self.new_instance_button = LocksmithButton("＋ New Instance")
        self.new_instance_button.setObjectName("vaultDrawer.newInstanceButton")
        self.new_instance_button.clicked.connect(self._new_instance)
        drawer_header_layout.addWidget(self.new_instance_button)

        drawer_layout.addLayout(drawer_header_layout)

        # Add a horizontal divider
        divider = QFrame()
        divider.setObjectName("vault-header-divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        drawer_layout.addWidget(divider)

        # Search filter input
        search_row = QHBoxLayout()
        search_row.setContentsMargins(12, 8, 12, 8)
        self.search_field = LocksmithLineEdit(
            placeholder_text="Search vaults",
            leading_icon=":/assets/material-icons/search.svg",
        )
        self.search_field.setClearButtonEnabled(True)
        self.search_field.textChanged.connect(self._filter_vaults)
        search_row.addWidget(self.search_field)
        drawer_layout.addLayout(search_row)

        # Empty-state label (shown when filter has zero matches)
        self.empty_state_label = QLabel("")
        self.empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_label.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 14px; padding: 16px;"
        )
        self.empty_state_label.hide()
        drawer_layout.addWidget(self.empty_state_label)

        # New vault button in its own list widget with custom styling
        new_vault_button_container = QListWidget()
        new_vault_button_container.setObjectName("vaultDrawer.newVaultButton")
        new_vault_button_container.setIconSize(QSize(30, 30))
        new_vault_button_container.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background: transparent;
            }}
            QListWidget::item {{
                border-radius: 8px;
                padding: 10px;
                padding-left: 6px;
            }}
            QListWidget::item:hover {{
                background-color: {colors.BACKGROUND_COLLAPSIBLE_HOVER};
            }}

        """)
        new_vault_button = QListWidgetItem(QIcon(":/assets/material-icons/add.svg"), "Initialize New Vault")
        new_vault_button_font = QFont()
        new_vault_button_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
        new_vault_button_font.setPointSize(16)
        new_vault_button.setFont(new_vault_button_font)
        new_vault_button_container.addItem(new_vault_button)
        new_vault_button_container.setFixedHeight(54)  # icon(36) + padding(24*2) + spacing(10)
        new_vault_button_container.setCursor(Qt.CursorShape.PointingHandCursor)
        new_vault_button_container.clicked.connect(self.show_create_vault_dialog)
        drawer_layout.addWidget(new_vault_button_container)


        # Create vault list widget (store as instance variable for refreshing)
        self.vault_list = QListWidget()
        self.vault_list.setObjectName("vaultDrawer.vaultList")
        self.vault_list.setIconSize(QSize(36, 36))
        self.vault_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vault_list.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background: transparent;
            }}
            QListWidget::item {{
                padding: 12px;
                padding-left: 24px;
                border-radius: 8px;
            }}
            QListWidget::item:hover {{
                background-color: {colors.BACKGROUND_COLLAPSIBLE_HOVER};
            }}
        """)

        # NOTE: whole-row click-to-open wiring was removed here. Each row now
        # renders its own state-appropriate action buttons (Open / Switch to /
        # ▾ menu) via setItemWidget, which own the actions. Connecting
        # itemClicked -> open would double-fire / conflict with those buttons,
        # so the row-click handler is intentionally not wired up.

        # Populate vault list
        self._refresh_vault_list()

        drawer_layout.addWidget(self.vault_list)


        # Set drawer dimensions
        self.vault_drawer.setFixedWidth(self.drawer_width)

        # Position drawer off-screen to the right initially
        window_width = self.parent.width()
        window_height = self.parent.height()
        toolbar_height = self.toolbar_ref.height()

        self.vault_drawer.setGeometry(
            window_width,  # Start off-screen to the right
            toolbar_height,
            self.drawer_width,
            window_height - toolbar_height
        )

        # Create animation for sliding
        self.drawer_animation = QPropertyAnimation(self.vault_drawer, b"geometry")
        self.drawer_animation.setDuration(300)  # 300ms animation
        self.drawer_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Show the drawer widget (but positioned off-screen)
        self.vault_drawer.show()

    def toggle(self):
        """Toggle drawer open/closed with animations."""
        window_width = self.parent.width()
        window_height = self.parent.height()
        toolbar_height = self.toolbar_ref.height()

        # Disconnect previous animation handler if connected
        if self._overlay_animation_connected:
            self.overlay_animation.finished.disconnect()
            self._overlay_animation_connected = False

        if self.drawer_visible:
            # Slide out (hide)
            start_rect = QRect(
                window_width - self.drawer_width,
                toolbar_height,
                self.drawer_width,
                window_height - toolbar_height
            )
            end_rect = QRect(
                window_width,  # Off screen to the right
                toolbar_height,
                self.drawer_width,
                window_height - toolbar_height
            )
            self.drawer_visible = False

            # Fade out overlay
            self.overlay_animation.setStartValue(1.0)
            self.overlay_animation.setEndValue(0.0)

            # Hide overlay after animation completes
            self.overlay_animation.finished.connect(self.drawer_overlay.hide)
            self._overlay_animation_connected = True
            self.overlay_animation.start()

            # Emit signal
            self.drawer_closed.emit()
        else:
            # Slide in (show)
            start_rect = QRect(
                window_width,
                toolbar_height,
                self.drawer_width,
                window_height - toolbar_height
            )
            end_rect = QRect(
                window_width - self.drawer_width,  # On screen
                toolbar_height,
                self.drawer_width,
                window_height - toolbar_height
            )
            self.drawer_visible = True

            # Show overlay and fade in
            self.drawer_overlay.show()
            self.drawer_overlay.raise_()  # Bring overlay to front

            # Ensure toolbar stays on top
            self.toolbar_ref.raise_()

            self.vault_drawer.raise_()    # Bring drawer above overlay

            self.overlay_animation.setStartValue(0.0)
            self.overlay_animation.setEndValue(1.0)
            self.overlay_animation.start()

            # Emit signal
            self.drawer_opened.emit()

        self.drawer_animation.setStartValue(start_rect)
        self.drawer_animation.setEndValue(end_rect)
        self.drawer_animation.start()

    def handle_resize(self, window_width: int, window_height: int, toolbar_height: int):
        """
        Reposition drawer and overlay on window resize.

        Args:
            window_width: Current window width.
            window_height: Current window height.
            toolbar_height: Current toolbar height.
        """
        # Update overlay size
        self.drawer_overlay.setGeometry(
            0,
            toolbar_height,
            window_width,
            window_height - toolbar_height
        )

        if self.drawer_visible:
            # Drawer is visible, keep it on screen
            self.vault_drawer.setGeometry(
                window_width - self.drawer_width,
                toolbar_height,
                self.drawer_width,
                window_height - toolbar_height
            )
        else:
            # Drawer is hidden, keep it off screen
            self.vault_drawer.setGeometry(
                window_width,
                toolbar_height,
                self.drawer_width,
                window_height - toolbar_height
            )

    def is_visible(self) -> bool:
        """
        Check if drawer is currently visible.

        Returns:
            True if drawer is visible, False otherwise.
        """
        return self.drawer_visible

    def hide_drawer_widgets(self):
        """
        Hide the drawer and overlay widgets completely.
        Used when navigating away from pages that use the drawer.
        """
        # Close the drawer if it's open
        if self.drawer_visible:
            self.toggle()

        # Explicitly hide the drawer widgets
        self.drawer_overlay.hide()
        self.vault_drawer.hide()

    def show_drawer_widgets(self):
        """
        Show the drawer widgets (but keep drawer closed).
        Used when navigating to pages that use the drawer.
        """
        # Clear any prior filter query on each drawer-show.
        if hasattr(self, "search_field"):
            self.search_field.clear()

        # Refresh the vault list to pick up any changes (e.g., deleted vaults)
        self._refresh_vault_list()

        # Don't show overlay (it's only shown when drawer is toggled open)
        # But show the drawer frame (positioned off-screen, ready to slide in)
        self.vault_drawer.show()

    def _refresh_vault_list(self):
        """Refresh the vault list with per-instance state and actions.

        Each row uses a custom widget (state badge + state-appropriate
        buttons) via ``setItemWidget``. The item's TEXT is still set to
        ``vault_name`` so ``_filter_vaults`` (which reads ``item.text()``)
        keeps working unchanged — the text is hidden behind the row widget.
        """
        # QListWidget.clear() does NOT free widgets installed via
        # setItemWidget — they stay parented to the list's viewport and
        # accumulate on every refresh (the drawer refreshes on every open).
        # Release them explicitly before clearing. Safe when the list is empty.
        for i in range(self.vault_list.count()):
            item = self.vault_list.item(i)
            row = self.vault_list.itemWidget(item) or item.data(Qt.ItemDataRole.UserRole)
            self.vault_list.removeItemWidget(item)
            if row is not None:
                row.setParent(None)
                row.deleteLater()
            item.setData(Qt.ItemDataRole.UserRole, None)
        self.vault_list.clear()

        # Sort vaults alphabetically so the prefix/substring grouping in
        # _filter_vaults produces a stable order within each group.
        for vault_name in sorted(self.app.environments(), key=str.lower):
            state = self._vault_state(vault_name)
            # Keep vault_name as the item text so the search filter still
            # matches on it; the row widget visually covers the text.
            item = QListWidgetItem(vault_name)
            row = self._build_vault_row(vault_name, state)
            item.setSizeHint(row.sizeHint())
            # Stash the row widget on the item itself. _filter_vaults reorders
            # by takeItem()/addItem(), which drops the setItemWidget binding;
            # it reattaches from this stored reference afterward.
            item.setData(Qt.ItemDataRole.UserRole, row)
            self.vault_list.addItem(item)
            self.vault_list.setItemWidget(item, row)

        # Re-apply the active filter so add/delete don't desync the visible list.
        query = self.search_field.text() if hasattr(self, "search_field") else ""
        self._filter_vaults(query)

    def _vault_state(self, vault_name: str) -> str:
        """Classify a vault row: 'current', 'running', or 'idle'.

        Reads ``app.name`` (the vault open in THIS instance) and
        ``app.coordinator`` (cross-instance liveness). Both are read
        defensively so the drawer still renders during early construction —
        or under test stubs — before coordination state exists, degrading to
        'idle' rather than raising.
        """
        if getattr(self.app, "name", None) == vault_name:
            return "current"
        coordinator = getattr(self.app, "coordinator", None)
        if coordinator is None:
            logger.debug("instance.drawer.no_coordinator vault=%s", vault_name)
        elif coordinator.probe(vault_name):
            return "running"
        return "idle"

    def _build_vault_row(self, vault_name: str, state: str) -> QFrame:
        """Build the per-vault row widget for ``state``.

        - current: name + "● Open in this instance" badge + "current" tag.
        - running: name + "◆ Running in another instance" badge + Switch to.
        - idle:    name + "Not open" badge + split Open button (Open + ▾ menu).
        """
        row = QFrame()
        row.setObjectName(f"vaultDrawer.row.{vault_name}")
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(8)

        name_col = QVBoxLayout()
        name_label = QLabel(vault_name)
        name_font = QFont()
        name_font.setPointSize(14)
        name_label.setFont(name_font)
        name_col.addWidget(name_label)
        status = QLabel({
            "current": "● Open in this instance",
            "running": "◆ Running in another instance",
            "idle": "Not open",
        }[state])
        status.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 11px;")
        name_col.addWidget(status)
        h.addLayout(name_col)
        h.addStretch()

        if state == "current":
            tag = QLabel("current")
            tag.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 11px;")
            h.addWidget(tag)
        elif state == "running":
            switch_btn = LocksmithButton("Switch to")
            switch_btn.setObjectName(f"vaultDrawer.switchTo.{vault_name}")
            switch_btn.clicked.connect(
                lambda _=False, v=vault_name: self._switch_to_running(v)
            )
            h.addWidget(switch_btn)
        else:  # idle — split button: Open ▾ Open in New Instance
            open_btn = LocksmithButton("Open")
            open_btn.setObjectName(f"vaultDrawer.open.{vault_name}")
            open_btn.clicked.connect(
                lambda _=False, v=vault_name: self.show_open_vault_dialog(v)
            )
            h.addWidget(open_btn)

            more = QToolButton()
            more.setObjectName(f"vaultDrawer.openMenu.{vault_name}")
            more.setText("▾")
            more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(more)
            act = menu.addAction("Open in New Instance")
            act.triggered.connect(
                lambda _=False, v=vault_name: self._open_in_new_instance(v)
            )
            more.setMenu(menu)
            h.addWidget(more)

        return row

    def _open_in_new_instance(self, vault_name: str) -> None:
        """Spawn a new OS process opened on ``vault_name``."""
        logger.info(f"instance.drawer.open_new vault={vault_name}")
        InstanceLauncher.launch_new(vault_name)

    def _switch_to_running(self, vault_name: str) -> None:
        """Ask the running owner of ``vault_name`` to raise its window."""
        logger.info(f"instance.drawer.switch_to vault={vault_name}")
        self.app.coordinator.request_raise(vault_name)

    def _new_instance(self) -> None:
        """Spawn a new OS process with no vault open."""
        logger.info("instance.drawer.new_instance")
        InstanceLauncher.launch_new(None)

    def _filter_vaults(self, query: str):
        """
        Filter the vault list to names containing ``query`` (case-insensitive).

        Prefix matches sort above non-prefix substring matches; non-matches
        are hidden. Empty-state label is shown when nothing matches.
        """
        q = query.strip().lower()

        # First pass: assign a sort key (0=prefix, 1=substring, 2=hidden) per item.
        annotated: list[tuple[int, str, QListWidgetItem]] = []
        for i in range(self.vault_list.count()):
            item = self.vault_list.item(i)
            name_lower = item.text().lower()
            if not q:
                rank = 0
            elif name_lower.startswith(q):
                rank = 0
            elif q in name_lower:
                rank = 1
            else:
                rank = 2
            annotated.append((rank, item.text().lower(), item))

        # Stable sort: prefix matches first, then substring matches, then hidden.
        # Within each group preserve the alphabetical order set in _refresh_vault_list.
        annotated.sort(key=lambda t: (t[0], t[1]))

        # Re-order rows by taking items out and re-adding in the new sequence.
        # takeItem clears selection and ownership cleanly.
        self.vault_list.blockSignals(True)
        for i in range(self.vault_list.count() - 1, -1, -1):
            self.vault_list.takeItem(i)
        match_count = 0
        for rank, _name, item in annotated:
            self.vault_list.addItem(item)
            # takeItem() above dropped the setItemWidget binding; reattach the
            # row widget stashed on the item in _refresh_vault_list so the
            # instance-aware row (badge + buttons) survives filtering/reordering.
            row = item.data(Qt.ItemDataRole.UserRole)
            if row is not None:
                self.vault_list.setItemWidget(item, row)
            if rank == 2:
                item.setHidden(True)
            else:
                item.setHidden(False)
                match_count += 1
        self.vault_list.blockSignals(False)

        # Empty-state label
        if q and match_count == 0:
            self.empty_state_label.setText(f"No vaults match “{query}”")
            self.empty_state_label.show()
            self.vault_list.hide()
        else:
            self.empty_state_label.hide()
            self.vault_list.show()

        logger.info(
            f"VaultDrawer filter applied: query={query!r} matches={match_count} "
            f"total={self.vault_list.count()}"
        )


    def show_create_vault_dialog(self):
        """Show the vault creation dialog."""
        dialog = CreateVaultDialog(parent=self.parent, config=self.app.config, app=self.app)

        # Connect the vault_created signal to refresh the list (persistent vaults)
        dialog.vault_created.connect(self._on_vault_created)
        # Connect the vault_opened signal for temp vaults (auto-navigate)
        dialog.vault_opened.connect(self._on_vault_opened)

        dialog.show()

    def show_open_vault_dialog(self, vault_name: str):
        """
        Show the open vault dialog.

        Args:
            vault_name: Name of the vault to open
        """
        dialog = OpenVaultDialog(
            vault_name=vault_name,
            parent=self.parent,
            config=self.app.config,
        )

        # Connect vault_opened signal to close drawer and navigate
        dialog.vault_opened.connect(self._on_vault_opened)

        dialog.show() # Using show here to avoid overlay

    def _on_vault_opened(self, vault_name: str):
        """
        Handle vault opening completion.

        Args:
            vault_name (str): Name of the opened vault
        """

        # Close the drawer
        if self.is_visible():
            self.toggle()

        self.parent.setWindowTitle(f"Locksmith | {vault_name}")

        # Navigate to vault page
        from locksmith.ui.navigation import Pages
        self.parent.nav_manager.navigate_to(Pages.VAULT, vault_name=vault_name)

    def _on_vault_created(self, vault_name: str):
        """
        Handle vault creation completion.

        Args:
            vault_name (str): Name of the newly created vault
        """
        # Refresh the vault list
        self._refresh_vault_list()

        # Automatically open the login dialog for the newly created vault
        self.show_open_vault_dialog(vault_name)