"""Paired peers page: list, add, unpair, test connection."""
from __future__ import annotations

import socket
from urllib.parse import urlparse

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget,
)
from keri import help

from locksmith.peer.allowlist import PeerAllowlist

logger = help.ogler.getLogger(__name__)


class PairedPeersPage(QWidget):
    def __init__(self, vault, parent=None):
        super().__init__(parent=parent)
        self._vault = vault
        self._allowlist = PeerAllowlist(vault.db)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Paired peers")
        title.setStyleSheet("font-weight: 600; font-size: 16px;")
        layout.addWidget(title)

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("+ Add peer")
        self.add_button.clicked.connect(self._on_add)
        toolbar.addWidget(self.add_button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

    def refresh(self) -> None:
        self.list_widget.clear()
        for rec in self._allowlist.list():
            item = QListWidgetItem(
                f"{rec.label}  —  {rec.aid}  —  {rec.endpoint_url}"
            )
            item.setData(Qt.UserRole, rec.aid)
            self.list_widget.addItem(item)

    def unpair(self, aid: str) -> None:
        self._allowlist.remove(aid)

    def _on_add(self) -> None:
        from locksmith.ui.vault.peers.add_dialog import AddPeerDialog
        dialog = AddPeerDialog(vault=self._vault, parent=self)
        dialog.peer_added.connect(self.refresh)
        dialog.open()

    def test_connection(self, aid: str, timeout: float = 3.0) -> bool:
        rec = self._allowlist.get(aid)
        if rec is None or not rec.endpoint_url:
            return False
        try:
            up = urlparse(rec.endpoint_url)
            with socket.create_connection((up.hostname, up.port), timeout=timeout):
                logger.info(
                    f"peer.test.ok aid={aid} endpoint={rec.endpoint_url}"
                )
                return True
        except (OSError, socket.timeout) as e:
            logger.info(
                f"peer.test.failed aid={aid} endpoint={rec.endpoint_url} err={e}"
            )
            return False
