"""Vault settings: 'Direct peer mode' section (vault-level listener config)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QSpinBox, QVBoxLayout,
)
from keri import help

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.reachability import check_reachable
from locksmith.peer.records import PeerModeSettings
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import LocksmithButton
from locksmith.ui.toolkit.widgets.toggle import ToggleSwitch

logger = help.ogler.getLogger(__name__)


_STATUS_DOT_GRAY = "#9CA3AF"
_STATUS_DOT_GREEN = "#22C55E"
_STATUS_DOT_AMBER = "#F59E0B"
_STATUS_DOT_RED = "#DC2626"


class PeerSettingsSection(QFrame):
    """Vault-level listener controls: on/off, port, bind interface, advertised host.

    Visual language follows ``_create_general_settings_section`` — bold
    14pt header, gray subheader, white rounded card with 24px radius and
    25px padding, transparent child widgets.
    """

    def __init__(self, vault, parent=None):
        super().__init__(parent=parent)
        self._vault = vault
        self._build()
        self._load()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QLabel("Direct peer connections")
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(14)
        header.setFont(header_font)
        header.setStyleSheet(f"color: {colors.TEXT_PRIMARY};")
        layout.addWidget(header)

        subheader = QLabel(
            "Let other paired wallets reach this vault directly over your "
            "LAN or VPN. KERI messages travel peer-to-peer; mailbox is used "
            "as a fallback when a peer is offline."
        )
        subheader.setWordWrap(True)
        subheader.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 12px; "
            f"margin-bottom: 10px;"
        )
        layout.addWidget(subheader)

        # Card container
        card = QFrame()
        card.setObjectName("peerSettingsCard")
        card.setStyleSheet(f"""
            #peerSettingsCard {{
                background-color: {colors.WHITE};
                border: 1px solid {colors.BORDER_TABLE};
                border-radius: 24px;
            }}
            QWidget {{ background-color: transparent; }}
            QLabel {{ color: {colors.TEXT_PRIMARY}; }}
            QSpinBox, QComboBox {{
                padding: 6px 10px;
                border: 1px solid {colors.BORDER_TABLE};
                border-radius: 8px;
                min-height: 24px;
                color: {colors.TEXT_PRIMARY};
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(25, 25, 25, 25)
        card_layout.setSpacing(16)

        # Row 1: Accept-connections toggle + status dot
        row1 = QHBoxLayout()
        row1.setSpacing(12)
        label = QLabel("Accept direct connections from paired peers")
        label.setStyleSheet(f"color: {colors.TEXT_PRIMARY}; font-weight: 500;")
        row1.addWidget(label)
        row1.addStretch()
        self.status_dot = QFrame()
        self.status_dot.setFixedSize(10, 10)
        self.status_dot.setStyleSheet(
            f"background-color: {_STATUS_DOT_GRAY}; border-radius: 5px;"
        )
        row1.addWidget(self.status_dot)
        self.status_label = QLabel("Listener stopped")
        self.status_label.setObjectName("peer_status_label")
        self.status_label.setStyleSheet(f"color: {colors.TEXT_SECONDARY};")
        row1.addWidget(self.status_label)
        row1.addSpacing(8)
        self.enabled_toggle = ToggleSwitch()
        self.enabled_toggle.setObjectName("peer_enabled_toggle")
        row1.addWidget(self.enabled_toggle)
        card_layout.addLayout(row1)

        # Row 2: Port + Bind
        row2 = QHBoxLayout()
        row2.setSpacing(20)
        row2.addWidget(QLabel("Listen on port"))
        self.port_spin = QSpinBox()
        self.port_spin.setObjectName("peer_port_spin")
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(5621)
        self.port_spin.setFixedWidth(110)
        row2.addWidget(self.port_spin)
        row2.addSpacing(20)
        row2.addWidget(QLabel("Bind to interface"))
        self.bind_combo = QComboBox()
        self.bind_combo.setObjectName("peer_bind_combo")
        self.bind_combo.addItem("All interfaces (0.0.0.0)", "0.0.0.0")
        row2.addWidget(self.bind_combo, 1)
        card_layout.addLayout(row2)

        # Row 3: Advertised host
        row3 = QHBoxLayout()
        row3.setSpacing(20)
        row3.addWidget(QLabel("Advertise as"))
        self.advertised_combo = QComboBox()
        self.advertised_combo.setObjectName("peer_advertised_combo")
        self.advertised_combo.setEditable(True)
        row3.addWidget(self.advertised_combo, 1)
        card_layout.addLayout(row3)

        # Apply
        apply_row = QHBoxLayout()
        apply_row.addStretch()
        self.apply_button = LocksmithButton("Save and restart listener")
        self.apply_button.setObjectName("peer_apply_button")
        self.apply_button.clicked.connect(self._on_apply)
        apply_row.addWidget(self.apply_button)
        card_layout.addLayout(apply_row)

        layout.addWidget(card)

        # Populate detected interfaces (best-effort)
        for ip in _detect_interface_ips():
            self.bind_combo.addItem(ip, ip)
            self.advertised_combo.addItem(ip, ip)

        # --- Paired peers card ---
        layout.addSpacing(18)
        peers_header = QLabel("Paired peers")
        peers_header.setFont(header_font)
        peers_header.setStyleSheet(f"color: {colors.TEXT_PRIMARY};")
        layout.addWidget(peers_header)
        peers_sub = QLabel(
            "Wallets you can exchange KERI messages with directly. "
            "Pairing is one-way per side — both wallets must add each other."
        )
        peers_sub.setWordWrap(True)
        peers_sub.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 12px; "
            f"margin-bottom: 10px;"
        )
        layout.addWidget(peers_sub)

        peers_card = QFrame()
        peers_card.setObjectName("peersCard")
        peers_card.setStyleSheet(f"""
            #peersCard {{
                background-color: {colors.WHITE};
                border: 1px solid {colors.BORDER_TABLE};
                border-radius: 24px;
            }}
            QWidget {{ background-color: transparent; }}
            QListWidget {{ border: 0; }}
        """)
        peers_card_layout = QVBoxLayout(peers_card)
        peers_card_layout.setContentsMargins(25, 25, 25, 25)
        peers_card_layout.setSpacing(12)

        toolbar = QHBoxLayout()
        self.add_peer_button = LocksmithButton("Pair new peer")
        self.add_peer_button.setObjectName("peer_add_button")
        self.add_peer_button.clicked.connect(self._on_add_peer)
        toolbar.addWidget(self.add_peer_button)
        toolbar.addStretch()
        peers_card_layout.addLayout(toolbar)

        self.peers_list = QListWidget()
        self.peers_list.setObjectName("peer_list")
        self.peers_list.setMaximumHeight(180)
        peers_card_layout.addWidget(self.peers_list)
        self._empty_state_label = QLabel(
            "No paired peers yet. Pair a peer to exchange KERI messages "
            "directly over your LAN or VPN — no mailbox required."
        )
        self._empty_state_label.setWordWrap(True)
        self._empty_state_label.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 12px; padding: 8px;"
        )
        peers_card_layout.addWidget(self._empty_state_label)
        layout.addWidget(peers_card)

        self._refresh_peers_list()

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
        self._sync_status_from_doer()

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
        self._sync_status_from_doer()
        if rec.enabled:
            # Give the listener a beat to bind, then probe ourselves.
            # 500ms is enough for hio's TCPServer to flip self.opened
            # in the common path without making the user wait.
            QTimer.singleShot(500, lambda: self._run_reachability_self_test(rec))

    def _run_reachability_self_test(self, rec: PeerModeSettings) -> None:
        # Only meaningful if the listener actually came up — if it didn't,
        # the user already sees the "Couldn't bind" red dot and a TCP
        # connect probe just produces a noisier duplicate of that signal.
        doer = getattr(self._vault, "peer_doer", None)
        if doer is None or doer.server is None or not doer.server.opened:
            return
        # Probe the advertised address. If the user left it blank we
        # surface the invalid_host result so they know to fill it in.
        result = check_reachable(rec.advertised_host, rec.port, timeout=1.5)
        if result.ok:
            self._set_status(
                "green",
                f"Listening on {rec.bind_host}:{rec.port} · advertised "
                f"{rec.advertised_host}:{rec.port} is reachable",
            )
        else:
            self._set_status("amber", result.message)

    def _sync_status_from_doer(self) -> None:
        doer = getattr(self._vault, "peer_doer", None)
        if doer is None or doer.server is None:
            self._set_status("gray", "Listener stopped")
            return
        host = self._vault.db.peerSettings.get(keys=("default",))
        host_str = host.bind_host if host else "0.0.0.0"
        if doer.server.opened:
            port = doer.server.ha[1] if doer.server.ha else "?"
            self._set_status("green", f"Listening on {host_str}:{port}")
        else:
            self._set_status("red", "Couldn't bind — port in use")

    def _set_status(self, color_key: str, text: str) -> None:
        color = {
            "green": _STATUS_DOT_GREEN,
            "amber": _STATUS_DOT_AMBER,
            "red": _STATUS_DOT_RED,
        }.get(color_key, _STATUS_DOT_GRAY)
        self.status_dot.setStyleSheet(
            f"background-color: {color}; border-radius: 5px;"
        )
        self.status_label.setText(text)

    def update_status(self, text: str) -> None:
        """Backward-compat hook for callers that only set status text."""
        self.status_label.setText(text)

    def _on_add_peer(self) -> None:
        from locksmith.ui.vault.peers.add_dialog import AddPeerDialog
        dialog = AddPeerDialog(vault=self._vault, parent=self)
        dialog.peer_added.connect(self._refresh_peers_list)
        dialog.open()

    def _refresh_peers_list(self) -> None:
        self.peers_list.clear()
        try:
            records = PeerAllowlist(self._vault.db).list()
        except AttributeError:
            return
        for rec in records:
            short_aid = f"{rec.aid[:4]}…{rec.aid[-4:]}" if len(rec.aid) > 12 else rec.aid
            item = QListWidgetItem(
                f"{rec.label}   {short_aid}   {rec.endpoint_url}"
            )
            item.setData(Qt.UserRole, rec.aid)
            self.peers_list.addItem(item)
        self._empty_state_label.setVisible(self.peers_list.count() == 0)


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
