# -*- encoding: utf-8 -*-
"""
locksmith.ui.plugins.page module

Top-level Plugins page (Pages.PLUGINS). Lists installed plugins with
state badges; exposes Install / Uninstall / Exclude affordances.

Install and Uninstall both surface signals; the LocksmithWindow wires
those signals to handlers and to PluginInstaller calls.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from keri import help

from locksmith.plugins.installer import SourceDescriptor
from locksmith.ui.plugins.install_panel import InstallPanel
from locksmith.ui.toolkit.widgets import LocksmithButton, LocksmithInvertedButton

logger = help.ogler.getLogger(__name__)


class _ClickableFrame(QFrame):
    """A QFrame that emits a ``clicked`` signal on left mouse-button press.

    Also exposes a ``click()`` helper that emits the signal directly, mirroring
    the ``QAbstractButton.click()`` API so that test code can drive the tile
    with the same pattern as a QPushButton.
    """

    clicked = Signal()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def click(self) -> None:
        """Emit ``clicked`` — mirrors QPushButton.click() for test ergonomics."""
        self.clicked.emit()


_STATUS_COPY = {
    "loaded":           ("● Loaded",                "#1c8a3a"),
    "excluded":         ("○ Excluded (this wallet)", "#777"),
    "incompatible":     ("⚠ Incompatible",          "#a8770a"),
    "files_missing":    ("⚠ Files missing",         "#a8770a"),
    "failed":           ("⚠ Failed to load",        "#c8341c"),
    "pending_restart":  ("○ Pending restart",        "#a8770a"),
}


class PluginsContent(QWidget):
    """Data UI for the Plugins feature — owns rows, install panel, restart banner.

    Can be embedded in either the top-level PluginsPage host (logged-out) or the
    VaultPage content_stack (logged-in).  Two distinct instances are created; both
    read from app.plugin_manager and are refreshed whenever the manager changes.
    """

    install_requested = Signal(SourceDescriptor)   # user submitted Fetch
    install_trusted = Signal(str)                  # user clicked Trust&Install, arg is plugin_id
    uninstall_clicked = Signal(str)                # plugin_id
    exclude_toggled = Signal(str, bool)            # plugin_id, now_excluded
    restart_requested = Signal()                   # user clicked "Restart now"

    # Marker sub-classes used by tests to find specific widgets via findChildren().
    # Defined here so tests that construct PluginsContent directly can access them.
    class PluginNameLabel(QLabel):
        pass

    class StatusBadge(QLabel):
        pass

    class InTreeBadge(QLabel):
        pass

    class EmptyStateLabel(QLabel):
        pass

    def __init__(self, app: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self.setObjectName("PluginsContent")
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        # Restart-required banner (hidden by default). Layout:
        #   [⚠ icon-text]                 [Restart now]
        self._restart_banner = QFrame()
        self._restart_banner.setObjectName("PluginsRestartBanner")
        self._restart_banner.setStyleSheet(
            "QFrame#PluginsRestartBanner { "
            "  background: #fff4d6; "
            "  border: 1px solid #d6b15a; "
            "  border-radius: 4px; "
            "  padding: 4px; "
            "}"
            "QFrame#PluginsRestartBanner QLabel { "
            "  background: transparent; border: none; color: #5A4500; "
            "}"
        )
        banner_row = QHBoxLayout(self._restart_banner)
        banner_row.setContentsMargins(8, 4, 8, 4)
        banner_row.setSpacing(12)
        banner_label = QLabel("⚠ Restart required to finish applying changes.")
        banner_label.setWordWrap(True)
        banner_row.addWidget(banner_label, stretch=1)
        self._restart_button = LocksmithButton("Restart now")
        self._restart_button.clicked.connect(self.restart_requested.emit)
        banner_row.addWidget(self._restart_button)
        self._restart_banner.setVisible(False)
        outer.addWidget(self._restart_banner)

        # Plugin list — flat QVBoxLayout, no QScrollArea. With <=5-ish
        # plugins (the realistic case for Stage 1) the page has room. If
        # we ever ship a marketplace with dozens of plugins, this gets
        # wrapped in a QScrollArea then.
        # _list_container / _list_scroll attribute names preserved for
        # backwards-compat with existing tests.
        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setSpacing(12)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._list_scroll = self._list_container  # alias for legacy tests
        outer.addWidget(self._list_container)

        # Inline install panel (hidden by default).  Sits below the list;
        # when the tile is clicked the tile hides and this becomes visible.
        self._install_panel = InstallPanel()
        self._install_panel.setVisible(False)
        self._install_panel.cancelled.connect(self._on_panel_cancelled)
        self._install_panel.source_chosen.connect(self.install_requested)
        self._install_panel.trusted.connect(self.install_trusted)
        outer.addWidget(self._install_panel)

        # Dashed-border install tile — rendered as a sibling of the scroll area
        # so it always appears immediately below the last plugin card.
        self._install_button = self._make_install_tile()
        self._install_button.clicked.connect(self._on_install_button_clicked)
        outer.addWidget(self._install_button)

        # Absorb remaining vertical space so the list + tile don't float.
        outer.addStretch(1)

    def _make_install_tile(self) -> _ClickableFrame:
        """Return the dashed-border tile that replaces the old floating button."""
        tile = _ClickableFrame()
        tile.setObjectName("PluginInstallTile")
        tile.setStyleSheet(
            "QFrame#PluginInstallTile { "
            "  border: 2px dashed #BBBBBB; "
            "  border-radius: 6px; "
            "  background: transparent; "
            "  padding: 16px; "
            "}"
            "QFrame#PluginInstallTile:hover { "
            "  border-color: #888888; "
            "  background: #FAFAFA; "
            "}"
        )
        tile.setCursor(Qt.CursorShape.PointingHandCursor)
        tile.setMinimumHeight(64)

        layout = QHBoxLayout(tile)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel("+ Install plugin")
        label.setStyleSheet(
            "QLabel { color: #666666; font-size: 14px; font-weight: 500; "
            "background: transparent; border: none; }"
        )
        label.setObjectName("plugins_install_tile_label")
        layout.addWidget(label)
        return tile

    def _refresh(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        from locksmith.plugins import storage
        from locksmith.plugins.manager import PluginState

        states = list(self.app.plugin_manager.all_states())
        loaded_ids = {s.plugin_id for s in states}
        # Surface plugins installed on disk but not yet loaded by this
        # wallet instance — they need a restart to actually run, and the
        # user expects to see something here after Trust & install fires.
        try:
            index = storage.read_index()
        except Exception:
            index = {"plugins": []}
        for record in index.get("plugins", []):
            pid = record.get("plugin_id")
            if not pid or pid in loaded_ids:
                continue
            states.append(PluginState(
                plugin_id=pid,
                status="pending_restart",
                source=record.get("source", {}),
                manifest_snapshot=record.get("manifest_snapshot", {}),
            ))

        if not states:
            empty = self.EmptyStateLabel(
                "No plugins installed yet.\nClick + Install plugin to add one."
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color:#777; padding:32px;")
            self._list_layout.addWidget(empty)
            return

        for state in states:
            self._list_layout.addWidget(self._make_row(state))

    def _make_row(self, state) -> QWidget:
        card = QFrame()
        card.setObjectName("PluginRowCard")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet(
            "QFrame#PluginRowCard { border:1px solid #ddd; border-radius:6px; "
            "background:#fff; padding:12px; }"
        )
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        v = QVBoxLayout(card)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)

        snap = state.manifest_snapshot or {}
        name = snap.get("name", state.plugin_id)
        version = snap.get("version", "")
        desc = snap.get("description", "")

        top_row = QHBoxLayout()
        name_label = self.PluginNameLabel(name)
        name_label.setStyleSheet("font-weight:600; font-size:15px;")
        top_row.addWidget(name_label)
        if version:
            v_label = QLabel(f"v{version}")
            v_label.setStyleSheet("color:#777; padding-left:8px;")
            top_row.addWidget(v_label)
        if state.in_tree:
            in_tree = self.InTreeBadge("[ Built-in ]")
            in_tree.setStyleSheet("color:#777; padding-left:8px;")
            top_row.addWidget(in_tree)
        elif state.source:
            src = state.source
            if src.get("type") == "github":
                src_label = QLabel(f"from github:{src.get('user_repo', '?')}")
                src_label.setStyleSheet("color:#777; padding-left:8px;")
                top_row.addWidget(src_label)
        top_row.addStretch(1)
        v.addLayout(top_row)

        if desc:
            desc_label = QLabel(desc)
            desc_label.setStyleSheet("color:#444;")
            desc_label.setWordWrap(True)
            v.addWidget(desc_label)

        bottom_row = QHBoxLayout()
        text, color = _STATUS_COPY.get(state.status, ("?", "#888"))
        badge = self.StatusBadge(text)
        badge.setStyleSheet(f"color:{color}; font-weight:600;")
        bottom_row.addWidget(badge)
        if state.error and state.status in ("failed", "incompatible"):
            err = QLabel(state.error)
            err.setStyleSheet("color:#c8341c; font-style:italic; padding-left:8px;")
            err.setWordWrap(True)
            bottom_row.addWidget(err, stretch=1)
        bottom_row.addStretch(1)
        if state.in_tree:
            pass  # built-in plugins: no per-row actions
        elif state.status == "pending_restart":
            remove_btn = LocksmithInvertedButton("Remove pending install")
            remove_btn.clicked.connect(
                lambda _=False, pid=state.plugin_id:
                self.uninstall_clicked.emit(pid)
            )
            bottom_row.addWidget(remove_btn)
        else:
            # existing Exclude + Uninstall buttons
            exclude_btn = LocksmithInvertedButton(
                "Include on this wallet" if state.status == "excluded"
                else "Exclude on this wallet"
            )
            exclude_btn.clicked.connect(
                lambda _=False, pid=state.plugin_id, was=state.status == "excluded":
                self.exclude_toggled.emit(pid, not was)
            )
            bottom_row.addWidget(exclude_btn)
            uninstall_btn = LocksmithInvertedButton("Uninstall")
            uninstall_btn.clicked.connect(
                lambda _=False, pid=state.plugin_id:
                self.uninstall_clicked.emit(pid)
            )
            bottom_row.addWidget(uninstall_btn)
        v.addLayout(bottom_row)
        return card

    # ------------------------------------------------------------------
    # Install panel show/hide flow
    # ------------------------------------------------------------------

    def _on_install_button_clicked(self) -> None:
        self._install_panel.set_source_mode()
        self._install_panel.setVisible(True)
        self._install_button.setVisible(False)

    # Alias so the tile's signal can connect to the same method
    _on_install_tile_clicked = _on_install_button_clicked

    def _on_panel_cancelled(self) -> None:
        self._install_panel.setVisible(False)
        self._install_button.setVisible(True)

    def show_trust_step(
        self,
        *,
        manifest_snapshot: dict,
        source: dict,
        commit: str,
    ) -> None:
        """Advance the panel to trust-confirm view (panel is already visible)."""
        self._install_panel.set_trust_mode(
            manifest_snapshot=manifest_snapshot,
            source=source,
            commit=commit,
        )

    def show_install_error(self, message: str) -> None:
        """Render an inline error in source mode; panel stays open for retry."""
        self._install_panel.set_inline_error(message)

    def collapse_install_panel(self) -> None:
        """Hide the panel and show the install button (called after success)."""
        self._on_panel_cancelled()

    def set_restart_required(self, required: bool) -> None:
        self._restart_banner.setVisible(required)

    def on_show(self) -> None:
        self._refresh()


class PluginsPage(QWidget):
    """Top-level Plugins page host — shown when no vault is open (Pages.PLUGINS).

    Thin wrapper around PluginsContent that adds the back button and header label
    needed for the top-level navigation context.  All data signals are forwarded
    from the embedded PluginsContent, and test-compat attribute aliases keep the
    existing 25 visual tests working without change.
    """

    install_requested = Signal(SourceDescriptor)   # user submitted Fetch
    install_trusted = Signal(str)                  # user clicked Trust&Install, arg is plugin_id
    uninstall_clicked = Signal(str)                # plugin_id
    exclude_toggled = Signal(str, bool)            # plugin_id, now_excluded
    restart_requested = Signal()                   # user clicked "Restart now"

    # Re-export marker sub-classes so tests that reach in via
    # ``type(page).PluginNameLabel`` etc. continue to work.
    # These must be the exact same class objects as the ones PluginsContent
    # uses when it instantiates the labels — use direct aliases, not subclasses,
    # so findChildren(type(page).PluginNameLabel) matches the real instances.
    PluginNameLabel = PluginsContent.PluginNameLabel
    StatusBadge     = PluginsContent.StatusBadge
    InTreeBadge     = PluginsContent.InTreeBadge
    EmptyStateLabel = PluginsContent.EmptyStateLabel

    def __init__(self, app: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self.setObjectName("PluginsPage")
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        header = QLabel("Plugins")
        header.setStyleSheet("font-size: 22px; font-weight: 600;")
        outer.addWidget(header)

        # Embedded content widget — owns all data UI.
        self._content = PluginsContent(self.app, parent=self)
        outer.addWidget(self._content)

        # Forward signals from embedded content up to callers.
        self._content.install_requested.connect(self.install_requested.emit)
        self._content.install_trusted.connect(self.install_trusted.emit)
        self._content.uninstall_clicked.connect(self.uninstall_clicked.emit)
        self._content.exclude_toggled.connect(self.exclude_toggled.emit)
        self._content.restart_requested.connect(self.restart_requested.emit)

        # Test-compat aliases — existing tests reach in via these attribute names.
        self._install_button = self._content._install_button
        self._install_panel  = self._content._install_panel
        self._list_container = self._content._list_container
        self._list_scroll    = self._content._list_scroll
        self._restart_banner = self._content._restart_banner

    # ------------------------------------------------------------------
    # Public API forwarded to embedded content (window + tests use these)
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        self._content._refresh()

    def show_trust_step(self, **kw) -> None:
        self._content.show_trust_step(**kw)

    def show_install_error(self, message: str) -> None:
        self._content.show_install_error(message)

    def collapse_install_panel(self) -> None:
        self._content.collapse_install_panel()

    def set_restart_required(self, required: bool) -> None:
        self._content.set_restart_required(required)

    # ------------------------------------------------------------------
    # Toolbar / window protocol — every page implements this.
    # ------------------------------------------------------------------

    def get_toolbar_config(self) -> dict:
        return {
            "title": "Plugins",
            "show_back": False,
            # Vaults drawer is also available on Plugins — users can switch
            # vaults from anywhere.
            "show_vaults_button": True,
        }

    def on_show(self) -> None:
        self._content._refresh()

    def on_hide(self) -> None:
        pass
