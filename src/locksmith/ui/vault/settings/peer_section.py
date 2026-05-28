"""Vault settings: 'Direct peer mode' section (vault-level listener config)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QVBoxLayout,
)
from keri import help

from locksmith.peer.records import PeerModeSettings

logger = help.ogler.getLogger(__name__)


class PeerSettingsSection(QFrame):
    """Vault-level listener controls: on/off, port, bind interface, advertised host."""

    def __init__(self, vault, parent=None):
        super().__init__(parent=parent)
        self._vault = vault
        self._build()
        self._load()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Direct peer mode")
        title.setStyleSheet("font-weight: 600; font-size: 14px;")
        layout.addWidget(title)

        self.enabled_toggle = QCheckBox("Enable peer-mode listener")
        layout.addWidget(self.enabled_toggle)

        row = QHBoxLayout()
        row.addWidget(QLabel("Port:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(5621)
        row.addWidget(self.port_spin)

        row.addWidget(QLabel("Bind:"))
        self.bind_combo = QComboBox()
        self.bind_combo.addItem("All interfaces (0.0.0.0)", "0.0.0.0")
        row.addWidget(self.bind_combo)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Advertised host:"))
        self.advertised_combo = QComboBox()
        self.advertised_combo.setEditable(True)
        row2.addWidget(self.advertised_combo)
        layout.addLayout(row2)

        self.status_label = QLabel("Stopped")
        self.status_label.setStyleSheet("color: #666;")
        layout.addWidget(self.status_label)

        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._on_apply)
        layout.addWidget(self.apply_button)

        # Populate detected interfaces (best-effort)
        for ip in _detect_interface_ips():
            self.bind_combo.addItem(ip, ip)
            self.advertised_combo.addItem(ip, ip)

    def _load(self) -> None:
        rec = self._vault.db.peerSettings.get(keys=("default",))
        if rec is None:
            return
        self.enabled_toggle.setChecked(rec.enabled)
        self.port_spin.setValue(rec.port)
        idx = self.bind_combo.findData(rec.bind_host)
        if idx >= 0:
            self.bind_combo.setCurrentIndex(idx)
        if rec.advertised_host:
            self.advertised_combo.setCurrentText(rec.advertised_host)

    def _on_apply(self) -> None:
        rec = PeerModeSettings(
            enabled=self.enabled_toggle.isChecked(),
            port=self.port_spin.value(),
            bind_host=self.bind_combo.currentData() or "0.0.0.0",
            advertised_host=self.advertised_combo.currentText().strip(),
        )
        self._vault.db.peerSettings.pin(keys=("default",), val=rec)
        logger.info(
            f"peer.settings.saved enabled={rec.enabled} port={rec.port} "
            f"bind={rec.bind_host} advertised={rec.advertised_host!r}"
        )
        self._vault.restart_peer_mode()

    def update_status(self, text: str) -> None:
        self.status_label.setText(text)


def _detect_interface_ips() -> list[str]:
    """Best-effort list of host IPs the user might want to advertise."""
    import socket as _socket
    ips: list[str] = []
    try:
        host = _socket.gethostname()
        for info in _socket.getaddrinfo(host, None, _socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except _socket.gaierror:
        pass
    return ips
