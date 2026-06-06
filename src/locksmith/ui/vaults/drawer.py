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
        # Compact outline style so it fits beside the "Vaults" title.
        self.new_instance_button = self._row_button("＋ New Instance", primary=False)
        self.new_instance_button.setObjectName("vaultDrawer.newInstanceButton")
        self.new_instance_button.clicked.connect(self._new_instance)
        drawer_header_layout.addWidget(
            self.new_instance_button, 0, Qt.AlignmentFlag.AlignVCenter
        )

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
        # Each row is a custom widget (setItemWidget) that fills the item
        # width; keep horizontal scrolling off so wide rows never bleed
        # past the drawer edge.
        self.vault_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.vault_list.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background: transparent;
            }}
            QListWidget::item {{
                margin: 2px 8px;
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
            # Re-enumerate on-disk vaults AND re-probe per-instance running
            # state every time the drawer opens. The drawer is built once at
            # startup, so without this an instance never sees vaults that
            # another instance created (or running-elsewhere state changes)
            # after construction. Probe cost for a handful of vaults is fine.
            self._refresh_vault_list()

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
        """Re-read the on-disk vaults + per-instance state, then rebuild rows.

        All cross-instance probes happen here, once, and the resulting
        ``(name, state)`` list is cached on ``self._vault_states`` so that
        keystroke filtering rebuilds rows WITHOUT re-probing.
        """
        # probe() spins a nested Qt event loop (QLocalSocket.waitForConnected);
        # do every probe here, up front, never interleaved with list mutation.
        self._vault_states = [
            (name, self._vault_state(name))
            for name in sorted(self.app.environments(), key=str.lower)
        ]
        query = self.search_field.text() if hasattr(self, "search_field") else ""
        self._rebuild_vault_rows(query)

    def _rebuild_vault_rows(self, query: str):
        """Rebuild the visible rows from the cached ``self._vault_states``,
        keeping only names matching ``query`` (prefix matches first, then
        substring matches).

        Full rebuild — NOT takeItem()/addItem() reordering. ``takeItem`` on an
        item carrying a ``setItemWidget`` row deletes that row widget in C++,
        so reordering items and reattaching a stashed widget pointer is a
        use-after-free (it segfaults in ``QListWidgetItem::data`` →
        ``getWrapperForQObject``). Rebuilding from scratch keeps widget
        ownership trivial: each refresh/filter creates fresh rows and releases
        the old ones, and no item ever references a freed widget.
        """
        q = (query or "").strip().lower()

        # QListWidget.clear() does NOT free widgets installed via
        # setItemWidget — release them explicitly first (otherwise they
        # accumulate, since the drawer rebuilds on every open/keystroke).
        for i in range(self.vault_list.count()):
            item = self.vault_list.item(i)
            row = self.vault_list.itemWidget(item)
            self.vault_list.removeItemWidget(item)
            if row is not None:
                row.setParent(None)
                row.deleteLater()
        self.vault_list.clear()

        # Rank matches: 0 = prefix (or no query), 1 = substring; drop non-matches.
        ranked = []
        for name, state in getattr(self, "_vault_states", []):
            name_lower = name.lower()
            if not q or name_lower.startswith(q):
                ranked.append((0, name_lower, name, state))
            elif q in name_lower:
                ranked.append((1, name_lower, name, state))
        # Stable: prefix group first, then substring group; alphabetical within.
        ranked.sort(key=lambda t: (t[0], t[1]))

        for _rank, _nl, name, state in ranked:
            # vault_name is also the item text so any text-based selector/filter
            # still resolves it; the row widget visually covers the text.
            item = QListWidgetItem(name)
            row = self._build_vault_row(name, state)
            item.setSizeHint(row.sizeHint())
            self.vault_list.addItem(item)
            self.vault_list.setItemWidget(item, row)

        match_count = len(ranked)
        if q and match_count == 0:
            self.empty_state_label.setText(f"No vaults match “{(query or '').strip()}”")
            self.empty_state_label.show()
            self.vault_list.hide()
        else:
            self.empty_state_label.hide()
            self.vault_list.show()

        logger.info(
            "VaultDrawer filter applied: query=%r matches=%d total=%d"
            % (q, match_count, len(getattr(self, "_vault_states", [])))
        )

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

    # Status dot colors per row state.
    _STATE_DOT = {"current": "#22C55E", "running": "#3B82F6", "idle": "#9CA3AF"}
    _STATE_TEXT = {
        "current": "Open in this instance",
        "running": "Running in another instance",
        "idle": "Not open",
    }

    def _build_vault_row(self, vault_name: str, state: str) -> QFrame:
        """Build the compact per-vault row widget for ``state``.

        Layout: a two-line left column (vault name + a small colored status
        line) and a right-aligned, compact action:
          - current: a "Close" button (closes the vault — replaces the old
            top-toolbar lock button now that the drawer is always reachable).
          - running: a "Switch to" button (raises the owning instance).
          - idle:    a split "Open" button with a ▾ menu ("Open in New Instance").
        """
        row = QFrame()
        row.setObjectName(f"vaultDrawer.row.{vault_name}")
        h = QHBoxLayout(row)
        h.setContentsMargins(14, 9, 12, 9)
        h.setSpacing(8)

        # Left: name + status, stacked.
        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        name_label = QLabel(vault_name)
        name_label.setStyleSheet(
            f"color: {colors.TEXT_PRIMARY}; font-size: 15px; font-weight: 600;"
        )
        name_col.addWidget(name_label)
        dot = self._STATE_DOT[state]
        status = QLabel(f'<span style="color:{dot};">●</span> {self._STATE_TEXT[state]}')
        status.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 11px;")
        name_col.addWidget(status)
        h.addLayout(name_col)
        h.addStretch()

        if state == "current":
            close_btn = self._row_button("Close", neutral=True)
            close_btn.setObjectName(f"vaultDrawer.close.{vault_name}")
            close_btn.clicked.connect(
                lambda _=False, v=vault_name: self._close_current_vault(v)
            )
            h.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        elif state == "running":
            switch_btn = self._row_button("Switch to", primary=False)
            switch_btn.setObjectName(f"vaultDrawer.switchTo.{vault_name}")
            switch_btn.clicked.connect(
                lambda _=False, v=vault_name: self._switch_to_running(v)
            )
            h.addWidget(switch_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        else:  # idle — split "Open" button + ▾ "Open in New Instance"
            split = QHBoxLayout()
            split.setSpacing(0)
            open_btn = self._row_button("Open", primary=True, side="left")
            open_btn.setObjectName(f"vaultDrawer.open.{vault_name}")
            open_btn.clicked.connect(
                lambda _=False, v=vault_name: self.show_open_vault_dialog(v)
            )
            split.addWidget(open_btn)

            more = QToolButton()
            more.setObjectName(f"vaultDrawer.openMenu.{vault_name}")
            more.setText("▾")
            more.setFixedHeight(30)
            more.setCursor(Qt.CursorShape.PointingHandCursor)
            more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            more.setStyleSheet(
                f"QToolButton {{ background-color: {colors.PRIMARY}; color: white; "
                f"border: none; border-top-right-radius: 6px; "
                f"border-bottom-right-radius: 6px; padding: 0 6px; "
                f"font-size: 12px; }}"
                f"QToolButton:hover {{ background-color: {colors.PRIMARY_HOVER}; }}"
                f"QToolButton::menu-indicator {{ image: none; }}"
            )
            menu = QMenu(more)
            act = menu.addAction("Open in New Instance")
            act.triggered.connect(
                lambda _=False, v=vault_name: self._open_in_new_instance(v)
            )
            more.setMenu(menu)
            split.addWidget(more)
            h.addLayout(split)

        return row

    def _row_button(self, text: str, primary: bool = True, side: str = "all",
                    neutral: bool = False):
        """A compact row-action button (smaller than the CTA LocksmithButton).

        ``primary`` = filled orange; otherwise an orange outline. ``neutral``
        overrides both with a muted gray outline (for non-primary actions like
        "Close" that shouldn't compete with the orange calls-to-action).
        ``side`` controls which corners are rounded so a button can sit flush
        against an attached ▾ menu button ("left" rounds only the left corners).
        """
        from PySide6.QtWidgets import QPushButton
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(30)
        if side == "left":
            radius = "border-top-left-radius: 6px; border-bottom-left-radius: 6px;"
        else:
            radius = "border-radius: 6px;"
        if neutral:
            base = (
                f"background-color: transparent; color: {colors.TEXT_SECONDARY}; "
                f"border: 1px solid {colors.BORDER_TABLE};"
            )
            hover = "background-color: rgba(0,0,0,0.05);"
        elif primary:
            base = (
                f"background-color: {colors.PRIMARY}; color: white; "
                f"border: 1px solid {colors.PRIMARY};"
            )
            hover = f"background-color: {colors.PRIMARY_HOVER}; border-color: {colors.PRIMARY_HOVER};"
        else:
            base = (
                f"background-color: transparent; color: {colors.PRIMARY}; "
                f"border: 1px solid {colors.PRIMARY};"
            )
            hover = f"background-color: rgba(234,88,12,0.08);"
        btn.setStyleSheet(
            f"QPushButton {{ {base} {radius} font-size: 12px; font-weight: 600; "
            f"padding: 4px 14px; }}"
            f"QPushButton:hover {{ {hover} }}"
        )
        return btn

    def _origin_xy(self) -> tuple[int, int]:
        """Top-left of the launching window, so a new instance can cascade
        off it (open offset rather than directly on top)."""
        return (self.parent.x(), self.parent.y())

    def _open_in_new_instance(self, vault_name: str) -> None:
        """Spawn a new OS process opened on ``vault_name``."""
        logger.info(f"instance.drawer.open_new vault={vault_name}")
        InstanceLauncher.launch_new(vault_name, origin_xy=self._origin_xy())

    def _switch_to_running(self, vault_name: str) -> None:
        """Ask the running owner of ``vault_name`` to raise its window."""
        logger.info(f"instance.drawer.switch_to vault={vault_name}")
        self.app.coordinator.request_raise(vault_name)

    def _new_instance(self) -> None:
        """Spawn a new OS process with no vault open."""
        logger.info("instance.drawer.new_instance")
        InstanceLauncher.launch_new(None, origin_xy=self._origin_xy())

    def _close_current_vault(self, vault_name: str) -> None:
        """Close the currently-open vault from the drawer (replaces the old
        top-toolbar lock button). Closes the drawer, then runs the window's
        standard lock/close flow (teardown + navigate home + reset title)."""
        logger.info(f"instance.drawer.close vault={vault_name}")
        if self.is_visible():
            self.toggle()
        self.parent.on_lock_vault()

    def _filter_vaults(self, query: str):
        """
        Filter the vault list to names containing ``query`` (case-insensitive).

        Prefix matches sort above non-prefix substring matches; non-matches
        are omitted. Empty-state label is shown when nothing matches. Rebuilds
        rows from the cached vault states (no probing) — see
        ``_rebuild_vault_rows`` for why this is a full rebuild rather than an
        in-place reorder.
        """
        self._rebuild_vault_rows(query)


    def show_create_vault_dialog(self):
        """Show the vault creation dialog."""
        dialog = CreateVaultDialog(parent=self.parent, config=self.app.config, app=self.app)
        # Destroy the dialog when it closes. Otherwise it lingers as a hidden
        # child of the main window, and a later create dialog produces duplicate
        # objectName'd widgets — selectors then resolve to the stale hidden one.
        # Safe here because the parent (main window) long outlives the dialog.
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

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
        # Destroy on close so repeated opens don't leave stale hidden
        # duplicates (same objectNames) parented to the main window.
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

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
        self.parent.toolbar.set_vault_name(vault_name)

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