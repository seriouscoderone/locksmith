# -*- encoding: utf-8 -*-
"""
locksmith.plugins.producer_licensing.pages module

The single lens page for Producer Licensing — slice 1.

Renders a thin domain-framing over the existing wallet primitives:
status of the issuer AID + registry, an "Issue License" button that
reuses IssueCredentialDialog, and a count of issued/held licenses.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from keri import help

from locksmith.applications import Application
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import LocksmithButton
from locksmith.ui.vault.credentials.issued.issue import IssueCredentialDialog

logger = help.ogler.getLogger(__name__)


class ProducerLicensingPage(QWidget):
    """First-person lens over the producer-licensing application."""

    def __init__(self, app: Any, manifest: Application, issuer_alias: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self.manifest = manifest
        self.issuer_alias = issuer_alias

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(colors.BACKGROUND_CONTENT))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT}; border: none;")
        scroll.viewport().setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")

        content = QWidget()
        content.setObjectName("producerLicensingContent")
        content.setStyleSheet(
            f"#producerLicensingContent {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
        )
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(18)

        content_layout.addWidget(self._build_header())
        content_layout.addWidget(self._build_status_section())
        content_layout.addWidget(self._build_actions_section())
        content_layout.addWidget(self._build_summary_section())
        content_layout.addStretch()

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_header(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel(self.manifest.name)
        title.setStyleSheet("font-size: 22px; font-weight: 600;")

        description = QLabel(self.manifest.description)
        description.setWordWrap(True)
        description.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 13px;")

        layout.addWidget(title)
        layout.addWidget(description)
        return wrapper

    def _build_status_section(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("plStatusFrame")
        frame.setStyleSheet(
            "#plStatusFrame { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        section_title = QLabel("Status")
        section_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(section_title)

        self._issuer_label = QLabel()
        self._issuer_label.setWordWrap(True)
        self._issuer_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(self._issuer_label)

        self._schema_label = QLabel()
        self._schema_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(self._schema_label)

        self._registry_label = QLabel()
        self._registry_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(self._registry_label)

        return frame

    def _build_actions_section(self) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._issue_button = LocksmithButton("Issue License")
        self._issue_button.clicked.connect(self._on_issue_clicked)
        layout.addWidget(self._issue_button)
        layout.addStretch()

        return wrapper

    def _build_summary_section(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("plSummaryFrame")
        frame.setStyleSheet(
            "#plSummaryFrame { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        section_title = QLabel("Licenses")
        section_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(section_title)

        self._issued_count_label = QLabel()
        self._issued_count_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(self._issued_count_label)

        self._held_count_label = QLabel()
        self._held_count_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(self._held_count_label)

        return frame

    # ------------------------------------------------------------------
    # State refresh
    # ------------------------------------------------------------------

    def on_show(self) -> None:
        """Called by VaultPage navigation; refresh state from the vault."""
        self._refresh()

    def _refresh(self) -> None:
        vault = getattr(self.app, "vault", None)
        if vault is None or vault.hby is None:
            self._issuer_label.setText("Issuer AID: vault not loaded")
            self._schema_label.setText("Schema: unknown")
            self._registry_label.setText("Registry: unknown")
            self._issue_button.setEnabled(False)
            self._issued_count_label.setText("Issued by me: —")
            self._held_count_label.setText("Held by me: —")
            return

        issuer_hab = self._find_issuer_hab(vault)
        if issuer_hab is None:
            self._issuer_label.setText(
                f"Issuer AID: not configured (looking for alias '{self.issuer_alias}')"
            )
            self._issue_button.setEnabled(False)
        else:
            self._issuer_label.setText(
                f"Issuer AID: <b>{issuer_hab.name}</b> ({issuer_hab.pre})"
            )

        schema_said = self._schema_said()
        if schema_said and vault.hby.db.schema.get(keys=(schema_said,)) is not None:
            self._schema_label.setText(f"Schema: <b>loaded</b> ({schema_said})")
        else:
            self._schema_label.setText("Schema: <b>not loaded</b>")
            self._issue_button.setEnabled(False)

        if schema_said and vault.rgy.registryByName(schema_said) is not None:
            self._registry_label.setText("Registry: <b>ready</b>")
        else:
            self._registry_label.setText("Registry: <b>not yet created</b>")
            self._issue_button.setEnabled(False)

        issued, held = self._count_credentials(vault, schema_said)
        self._issued_count_label.setText(f"Issued by me: <b>{issued}</b>")
        self._held_count_label.setText(f"Held by me: <b>{held}</b>")

    def _find_issuer_hab(self, vault: Any):
        """Look up the issuer Hab by alias. Returns None if not present."""
        for hab_pre, hab in vault.hby.habs.items():
            if hab.name == self.issuer_alias:
                return hab
        return None

    def _schema_said(self) -> str | None:
        """Read the saidified schema file's $id to know what to look for."""
        try:
            from pathlib import Path
            import json
            credential_def = self.manifest.credentials[0]
            schema_path = Path(__file__).parent / credential_def.schema_path
            return json.loads(schema_path.read_text()).get("$id") or None
        except Exception:
            logger.exception("Failed to read schema $id")
            return None

    def _count_credentials(self, vault: Any, schema_said: str | None) -> tuple[int, int]:
        """Count credentials of our schema in the Reger, split into issued-by-me / held-by-me.

        Same-vault wallets see both sets; the holder side relies on the Reger's
        subjs index (the same shortcut the Received page uses).
        """
        if not schema_said:
            return (0, 0)

        try:
            saids = list(vault.rgy.reger.schms.get(keys=(schema_said,)))
            creds = vault.rgy.reger.cloneCreds(saids, vault.hby.db)
        except Exception:
            logger.exception("Failed to read credentials for counting")
            return (0, 0)

        local_aids = set(vault.hby.habs.keys())
        issued = 0
        held = 0
        for c in creds:
            sad = c.get("sad", {})
            issuer = sad.get("i")
            attrs = sad.get("a", {}) or {}
            holder = attrs.get("i") if isinstance(attrs, dict) else None
            if issuer in local_aids:
                issued += 1
            if holder in local_aids:
                held += 1
        return (issued, held)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_issue_clicked(self) -> None:
        """Open the existing IssueCredentialDialog. The user picks ProducerLicense from the dropdown."""
        dialog = IssueCredentialDialog(app=self.app, parent=self)
        dialog.open()
