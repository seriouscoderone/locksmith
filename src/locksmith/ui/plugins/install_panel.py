# -*- encoding: utf-8 -*-
"""
locksmith.ui.plugins.install_panel module

Inline two-step install widget embedded directly in PluginsPage.
Replaces the modal InstallSourceDialog + PluginTrustDialog pair so that
the dev-control harness can drive the install flow end-to-end without
blocking on dlg.exec().

Internal state:
  _mode ∈ {"source", "trust"}   — tracked to support set_source_mode() reset.

Public signals:
  cancelled       — user clicked Cancel (either mode).
  source_chosen   — user clicked Fetch in source mode; arg is SourceDescriptor.
  trusted         — user clicked Trust & install in trust mode; arg is plugin_id.

Public attributes exposed for tests (keep stable):
  -- source mode --
  github_radio, local_radio
  user_repo_input, local_path_input, ref_input
  error_label, fetch_button, cancel_button

  -- trust mode --
  trust_headline
  trust_warning                      — yellow callout at the top
  trust_author_value                 — QLabel for author (form row)
  trust_source_value                 — QLabel for source path/url (elided, tooltip=full)
  trust_commit_value                 — QLabel for commit hash or friendly text
  trust_capability_block
  trust_accept_button
  (cancel_button is shared across both modes; it lives on the source stack page
   and the trust stack page has its own trust_cancel_button, but cancel_button
   is the one on the source page — tests only call it in source mode)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from locksmith.plugins.installer import SourceDescriptor
from locksmith.ui.toolkit.widgets.buttons import (
    LocksmithButton,
    LocksmithInvertedButton,
    LocksmithRadioButton,
)


_GITHUB_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

_CAPABILITY_COPY = {
    "app.shortcut":       "install global keyboard shortcuts",
    "app.service":        "run background services",
    "window.full_access": "inspect / control the full main window",
    "vault.full_access":  "access vault internals and credentials",
    "fs.write":           "write to disk",
    "fs.read":            "read from disk",
    "net.listen":         "open a local listening socket",
    "net.connect":        "make outbound network connections",
}


class InstallPanel(QWidget):
    """Inline install widget: source picker (mode='source') → trust confirm (mode='trust')."""

    cancelled = Signal()
    source_chosen = Signal(SourceDescriptor)
    trusted = Signal(str)           # plugin_id

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("InstallPanel")
        self._mode = "source"
        self._pending_plugin_id: str | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_source_mode(self) -> None:
        """Switch to source picker and reset all inputs."""
        self._mode = "source"
        self.user_repo_input.clear()
        self.local_path_input.clear()
        self.ref_input.clear()
        self.github_radio.setChecked(True)
        self.error_label.setText("")
        self.fetch_button.setEnabled(False)
        self._stack.setCurrentIndex(0)

    def set_trust_mode(
        self,
        *,
        manifest_snapshot: dict[str, Any],
        source: dict[str, Any],
        commit: str,
    ) -> None:
        """Switch to trust confirm view, populating from the manifest and source."""
        self._mode = "trust"

        name = manifest_snapshot.get("name", manifest_snapshot.get("plugin_id", "<unnamed>"))
        version = manifest_snapshot.get("version", "")
        self._pending_plugin_id = manifest_snapshot.get("plugin_id", "")

        self.trust_headline.setText(f"── Trust '{name}' v{version}? ──")

        # Metadata form rows
        self.trust_author_value.setText(
            manifest_snapshot.get("author") or "(unknown)"
        )

        if source.get("type") == "github":
            full_src = f"github.com/{source.get('user_repo')}"
        else:
            full_src = source.get("path") or "(unknown)"
        self.trust_source_value.setText(self._elide(full_src, max_chars=64))
        self.trust_source_value.setToolTip(full_src)

        if commit and not commit.startswith("local:"):
            self.trust_commit_value.setText(commit[:7])
        else:
            self.trust_commit_value.setText("(local source — no commit)")

        # Description
        desc = manifest_snapshot.get("description", "")
        if desc:
            self._trust_desc_label.setText(f'“{desc}”')
            self._trust_desc_label.setVisible(True)
        else:
            self._trust_desc_label.setVisible(False)

        # Capabilities
        self.trust_capability_block.setHtml(
            self._capabilities_html(manifest_snapshot)
        )

        self._stack.setCurrentIndex(1)

    @staticmethod
    def _elide(text: str, max_chars: int) -> str:
        """Middle-elide a string to at most max_chars characters."""
        if len(text) <= max_chars:
            return text
        head = max_chars // 2 - 1
        tail = max_chars - head - 1
        return text[:head] + "…" + text[-tail:]

    def set_inline_error(self, text: str) -> None:
        """Render a red error message above the buttons in source mode."""
        self.error_label.setText(text)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Outer frame with top separator visual
        frame = QFrame()
        frame.setObjectName("InstallPanelFrame")
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet("""
    QFrame#InstallPanelFrame {
        border: 1px solid #DDDDDD;
        border-radius: 6px;
        background: #FAFAFA;
    }
    QFrame#InstallPanelFrame QLineEdit {
        background: #FFFFFF;
        color: #2D2F33;
        border: 1px solid #D0D5DD;
        border-radius: 4px;
        padding: 6px 8px;
        min-height: 24px;
    }
    QFrame#InstallPanelFrame QLineEdit:focus {
        border: 1px solid #007AFF;
    }
    QFrame#InstallPanelFrame QLineEdit:disabled {
        background: #EEEEEE;
        color: #888888;
    }
    QFrame#InstallPanelFrame QLabel {
        color: #2D2F33;
        background: transparent;
    }
""")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(20, 16, 20, 16)
        frame_layout.setSpacing(12)

        self._stack = QStackedWidget()
        frame_layout.addWidget(self._stack)

        self._stack.addWidget(self._build_source_page())
        self._stack.addWidget(self._build_trust_page())
        self._stack.setCurrentIndex(0)

        outer.addWidget(frame)

    def _build_source_page(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(10)

        header = QLabel("── Install plugin ──")
        header.setStyleSheet("font-size:16px; font-weight:600; color:#333;")
        vbox.addWidget(header)

        # GitHub radio + input
        self.github_radio = LocksmithRadioButton("GitHub  user/repo")
        self.github_radio.setChecked(True)
        self.github_radio.toggled.connect(self._on_source_kind_changed)
        vbox.addWidget(self.github_radio)

        gh_row = QHBoxLayout()
        gh_row.addSpacing(28)
        self.user_repo_input = QLineEdit()
        self.user_repo_input.setPlaceholderText("e.g. seriouscoderone/locksmith-dev-control")
        self.user_repo_input.textChanged.connect(self._revalidate)
        gh_row.addWidget(self.user_repo_input)
        vbox.addLayout(gh_row)

        # Local radio + input
        self.local_radio = LocksmithRadioButton("Local path")
        self.local_radio.toggled.connect(self._on_source_kind_changed)
        vbox.addWidget(self.local_radio)

        loc_row = QHBoxLayout()
        loc_row.addSpacing(28)
        self.local_path_input = QLineEdit()
        self.local_path_input.setPlaceholderText("/path/to/plugin/clone")
        self.local_path_input.setEnabled(False)
        self.local_path_input.textChanged.connect(self._revalidate)
        loc_row.addWidget(self.local_path_input)
        vbox.addLayout(loc_row)

        # Branch/ref form row
        ref_form = QFormLayout()
        ref_form.setContentsMargins(0, 0, 0, 0)
        self.ref_input = QLineEdit()
        self.ref_input.setPlaceholderText("(defaults to default branch HEAD)")
        ref_form.addRow("Branch/ref (optional):", self.ref_input)
        vbox.addLayout(ref_form)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color:#c8341c;")
        self.error_label.setWordWrap(True)
        vbox.addWidget(self.error_label)

        # Button row
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = LocksmithInvertedButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel)
        button_row.addWidget(self.cancel_button)
        self.fetch_button = LocksmithButton("Fetch")
        self.fetch_button.setEnabled(False)
        self.fetch_button.clicked.connect(self._on_fetch)
        button_row.addWidget(self.fetch_button)
        vbox.addLayout(button_row)

        return page

    def _build_trust_page(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(10)

        # 1. Warning callout — top of the trust container so it's read first.
        self.trust_warning = QLabel(
            "⚠  Plugins run with full wallet permissions. "
            "Only install plugins you trust."
        )
        self.trust_warning.setWordWrap(True)
        self.trust_warning.setStyleSheet(
            "QLabel { background:#FFF4D6; padding:10px 14px; "
            "border:1px solid #D6B15A; border-radius:6px; "
            "color:#5A4500; font-weight:600; }"
        )
        vbox.addWidget(self.trust_warning)

        # 2. Headline.
        self.trust_headline = QLabel("")
        self.trust_headline.setStyleSheet("font-size:16px; font-weight:600; color:#333;")
        self.trust_headline.setWordWrap(True)
        vbox.addWidget(self.trust_headline)

        # 3. Metadata key-value table.
        def _meta_value(monospace: bool = False) -> QLabel:
            lab = QLabel("")
            lab.setWordWrap(False)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            style = "QLabel { color:#2D2F33; "
            if monospace:
                style += "font-family:'SF Mono','Menlo',monospace; "
            style += "}"
            lab.setStyleSheet(style)
            return lab

        def _meta_key(text: str) -> QLabel:
            lab = QLabel(text)
            lab.setStyleSheet("QLabel { color:#666666; }")
            return lab

        self.trust_author_value = _meta_value()
        self.trust_source_value = _meta_value()
        self.trust_commit_value = _meta_value(monospace=True)

        meta_layout = QFormLayout()
        meta_layout.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )
        meta_layout.setFormAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        meta_layout.setSpacing(4)
        meta_layout.setContentsMargins(0, 4, 0, 4)
        meta_layout.addRow(_meta_key("Author"), self.trust_author_value)
        meta_layout.addRow(_meta_key("Source"), self.trust_source_value)
        meta_layout.addRow(_meta_key("Commit"), self.trust_commit_value)
        vbox.addLayout(meta_layout)

        # 4. Description quote.
        self._trust_desc_label = QLabel("")
        self._trust_desc_label.setWordWrap(True)
        self._trust_desc_label.setStyleSheet("color:#222; padding:6px 0;")
        self._trust_desc_label.setVisible(False)
        vbox.addWidget(self._trust_desc_label)

        # 5. Capability lead-in label.
        vbox.addWidget(QLabel("This plugin requests:"))

        # 6. Capability block.
        self.trust_capability_block = QTextBrowser()
        self.trust_capability_block.setReadOnly(True)
        self.trust_capability_block.setOpenLinks(False)
        self.trust_capability_block.setStyleSheet(
            "QTextBrowser { background: #FFFFFF; color: #2D2F33; "
            "border: 1px solid #D0D5DD; border-radius: 4px; padding: 8px; }"
        )
        self.trust_capability_block.document().setDefaultStyleSheet(
            "li { color: #2D2F33; margin: 4px 0; } "
            ".detail { color: #666666; padding-left: 18px; display: block; }"
        )
        self.trust_capability_block.setMaximumHeight(160)
        self.trust_capability_block.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        vbox.addWidget(self.trust_capability_block)

        # 7. Button row.
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        trust_cancel = LocksmithInvertedButton("Cancel")
        trust_cancel.clicked.connect(self._on_cancel)
        button_row.addWidget(trust_cancel)
        # Double-ampersand escapes Qt's mnemonic so the label renders as
        # "Trust & install" instead of "Trust  install".
        self.trust_accept_button = LocksmithButton("Trust && install")
        self.trust_accept_button.clicked.connect(self._on_trust_accept)
        button_row.addWidget(self.trust_accept_button)
        vbox.addLayout(button_row)

        return page

    # ------------------------------------------------------------------
    # Source-mode validation
    # ------------------------------------------------------------------

    def _on_source_kind_changed(self) -> None:
        gh_active = self.github_radio.isChecked()
        self.user_repo_input.setEnabled(gh_active)
        self.local_path_input.setEnabled(not gh_active)
        self._revalidate()

    def _revalidate(self) -> None:
        ok, err = self._validate()
        self.error_label.setText(err)
        self.fetch_button.setEnabled(ok)

    def _validate(self) -> tuple[bool, str]:
        if self.github_radio.isChecked():
            text = self.user_repo_input.text().strip()
            if not text:
                return False, ""
            if not _GITHUB_RE.match(text):
                return False, (
                    "user/repo must be in the format owner/name "
                    "(letters, digits, dot, underscore, dash)."
                )
            return True, ""
        text = self.local_path_input.text().strip()
        if not text:
            return False, ""
        path = Path(text)
        if not path.exists():
            return False, f"path does not exist: {path}"
        if not (path / "locksmith-plugin.toml").exists():
            return False, f"no locksmith-plugin.toml in {path}"
        return True, ""

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_fetch(self) -> None:
        ref = self.ref_input.text().strip() or None
        if self.github_radio.isChecked():
            src = SourceDescriptor(
                type="github",
                user_repo=self.user_repo_input.text().strip(),
                ref=ref,
            )
        else:
            src = SourceDescriptor(
                type="local",
                path=self.local_path_input.text().strip(),
            )
        self.source_chosen.emit(src)

    def _on_trust_accept(self) -> None:
        pid = self._pending_plugin_id or ""
        self.trusted.emit(pid)

    def _on_cancel(self) -> None:
        self.cancelled.emit()

    # ------------------------------------------------------------------
    # Capability HTML (shared copy from old trust_dialog)
    # ------------------------------------------------------------------

    def _capabilities_html(self, snap: dict[str, Any]) -> str:
        caps = snap.get("capabilities", []) or []
        detail = snap.get("capabilities_detail", {}) or {}
        if not caps:
            return "<i>No capabilities declared.</i>"
        rows = []
        for cap in caps:
            copy = _CAPABILITY_COPY.get(cap, f"{cap} <i>(unrecognized)</i>")
            rows.append(f"<li>{copy}")
            if cap in detail:
                rows[-1] += (
                    f"<br><span class='detail'>"
                    f"&#x21B3; {detail[cap]}</span>"
                )
            rows[-1] += "</li>"
        return "<ul style='margin:0; padding-left:18px;'>" + "".join(rows) + "</ul>"
