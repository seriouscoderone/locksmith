"""Vault settings: 'Direct peer mode' section (vault-level listener config)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QSpinBox, QVBoxLayout, QWidget,
)
from keri import help

from locksmith.core.instancing import find_free_port
from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.exposure import count_exposed
from locksmith.peer.health import summarize_health_for_ui
from locksmith.peer.reachability import check_reachable
from locksmith.peer.records import PeerModeSettings
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import LocksmithButton, LocksmithCopyButton
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
        self.status_label.setObjectName("peerSettingsSection.statusLabel")
        self.status_label.setStyleSheet(f"color: {colors.TEXT_SECONDARY};")
        row1.addWidget(self.status_label)
        row1.addSpacing(8)
        self.enabled_toggle = ToggleSwitch()
        self.enabled_toggle.setObjectName("peerSettingsSection.enabledToggle")
        row1.addWidget(self.enabled_toggle)
        card_layout.addLayout(row1)

        # Row 1b: Open-inbound (first-contact) toggle — config-gated,
        # default OFF. Lets an unpaired sender's first message through
        # gate 1 when its KEL is verifiable and it published a reachable
        # tcp loc, registering it as a peer for the reply path.
        row1b = QHBoxLayout()
        row1b.setSpacing(12)
        self.open_inbound_cb = QCheckBox(
            "Accept introductions from verified first-contact senders"
        )
        self.open_inbound_cb.setObjectName(
            "peerSettingsSection.openInboundCheckbox"
        )
        row1b.addWidget(self.open_inbound_cb)
        row1b.addStretch()
        card_layout.addLayout(row1b)

        # Row 2: Port + Bind
        row2 = QHBoxLayout()
        row2.setSpacing(20)
        row2.addWidget(QLabel("Listen on port"))
        self.port_spin = QSpinBox()
        self.port_spin.setObjectName("peerSettingsSection.portSpin")
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(5621)
        self.port_spin.setFixedWidth(110)
        row2.addWidget(self.port_spin)
        self.find_port_button = LocksmithButton("Find free port")
        self.find_port_button.setObjectName("peerSettingsSection.findPortButton")
        self.find_port_button.clicked.connect(self._on_find_free_port)
        row2.addWidget(self.find_port_button)
        row2.addSpacing(20)
        row2.addWidget(QLabel("Bind to interface"))
        self.bind_combo = QComboBox()
        self.bind_combo.setObjectName("peerSettingsSection.bindCombo")
        self.bind_combo.addItem("All interfaces (0.0.0.0)", "0.0.0.0")
        row2.addWidget(self.bind_combo, 1)
        card_layout.addLayout(row2)

        # Row 3: Advertised host
        row3 = QHBoxLayout()
        row3.setSpacing(20)
        row3.addWidget(QLabel("Advertise as"))
        self.advertised_combo = QComboBox()
        self.advertised_combo.setObjectName("peerSettingsSection.advertisedCombo")
        self.advertised_combo.setEditable(True)
        row3.addWidget(self.advertised_combo, 1)
        card_layout.addLayout(row3)

        # Apply
        apply_row = QHBoxLayout()
        apply_row.addStretch()
        self.apply_button = LocksmithButton("Save and restart listener")
        self.apply_button.setObjectName("peerSettingsSection.applyButton")
        self.apply_button.clicked.connect(self._on_apply)
        apply_row.addWidget(self.apply_button)
        card_layout.addLayout(apply_row)

        # No-AID-exposed banner. Shown only when the listener is on but
        # no identifiers have peer-role published — without at least one
        # exposed AID the listener accepts no inbound traffic, which is
        # a silent dead-end the user otherwise has no way to discover.
        self.exposure_banner = QLabel(
            "Listener is up, but no identifiers will accept inbound "
            "connections. Open an identifier and toggle "
            "“Expose over peer mode” to make it reachable."
        )
        self.exposure_banner.setObjectName("peer_exposure_banner")
        self.exposure_banner.setWordWrap(True)
        self.exposure_banner.setStyleSheet(
            f"background-color: #FEF3C7; color: #92400E; "
            f"border: 1px solid #FCD34D; border-radius: 8px; "
            f"padding: 10px 14px; margin-top: 14px; font-size: 12px;"
        )
        self.exposure_banner.setVisible(False)
        card_layout.addWidget(self.exposure_banner)

        layout.addWidget(card)

        # Populate detected interfaces (best-effort). The primary — the
        # address on the interface that owns the default route — goes first
        # and becomes the prefilled advertised host, because a blank field
        # is what gets published as an unreachable endpoint.
        from locksmith.peer.netaddr import detect_primary_host
        primary = detect_primary_host()
        for ip in ([primary] if primary else []) + [
                ip for ip in _detect_interface_ips() if ip != primary]:
            self.bind_combo.addItem(ip, ip)
            self.advertised_combo.addItem(ip, ip)
        if primary:
            self.advertised_combo.setCurrentText(primary)

        # --- This wallet's peer OOBIs ---
        # Pairing is symmetric — both wallets must add each other — but the only
        # place to COPY your own peer-OOBI was the View Identifier dialog on the
        # identifiers page. A peeled HOA build has no identifiers page, so it
        # could paste a peer's token and never hand out its own: pairable one
        # way only. This card is on the SHARED settings section deliberately, so
        # stock Locksmith gets the same one-click copy rather than the HOA
        # growing a private variant that drifts.
        layout.addSpacing(18)
        mine_header = QLabel("This wallet's peer OOBIs")
        mine_header.setFont(header_font)
        mine_header.setStyleSheet(f"color: {colors.TEXT_PRIMARY};")
        layout.addWidget(mine_header)
        mine_sub = QLabel(
            "Send one of these tokens to a peer; they paste it into their "
            "Pair new peer dialog. Each token carries the identifier's key "
            "state and signed endpoint — an address alone is not enough to "
            "verify who answers."
        )
        mine_sub.setWordWrap(True)
        mine_sub.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 12px; "
            f"margin-bottom: 10px;"
        )
        layout.addWidget(mine_sub)

        self.mine_list = QVBoxLayout()
        self.mine_list.setSpacing(8)
        mine_holder = QWidget()
        mine_holder.setObjectName("peerSettingsSection.myOobis")
        mine_holder.setLayout(self.mine_list)
        layout.addWidget(mine_holder)

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
        self.add_peer_button.setObjectName("peerSettingsSection.addPeerButton")
        self.add_peer_button.clicked.connect(self._on_add_peer)
        toolbar.addWidget(self.add_peer_button)
        toolbar.addStretch()
        peers_card_layout.addLayout(toolbar)

        self.peers_list = QListWidget()
        self.peers_list.setObjectName("peerSettingsSection.peersList")
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
        self._refresh_my_oobis()
        self._refresh_exposure_banner()

        # PeerHealthMonitorDoer updates db.peerHealth every ~60s. Re-paint
        # the list a few times a minute so the user sees fresh dots
        # without having to navigate away and back. Light: same query
        # path as _refresh_peers_list which is already O(peers).
        self._health_refresh_timer = QTimer(self)
        self._health_refresh_timer.setInterval(15_000)
        self._health_refresh_timer.timeout.connect(self._refresh_peers_list)
        self._health_refresh_timer.timeout.connect(self._refresh_my_oobis)
        # Same tick is enough to keep the no-AID-exposed banner in sync —
        # exposure state changes only when the user flips a per-AID toggle,
        # which is rare relative to network conditions.
        self._health_refresh_timer.timeout.connect(self._refresh_exposure_banner)
        self._health_refresh_timer.start()

    def _load(self) -> None:
        rec = self._vault.db.peerSettings.get(keys=("default",))
        if rec is None:
            # First-time setup: pick a free port so two concurrently open
            # vaults don't both grab the hardcoded 5621 default.
            self.port_spin.setValue(find_free_port(start=5621))
            return
        self.enabled_toggle.setChecked(rec.enabled)
        self.port_spin.setValue(rec.port)
        idx = self.bind_combo.findData(rec.bind_host)
        if idx >= 0:
            self.bind_combo.setCurrentIndex(idx)
        if rec.advertised_host:
            self.advertised_combo.setCurrentText(rec.advertised_host)
        self.open_inbound_cb.setChecked(rec.open_inbound)
        self._sync_status_from_doer()

    def _on_apply(self) -> None:
        rec = PeerModeSettings(
            enabled=self.enabled_toggle.isChecked(),
            port=self.port_spin.value(),
            bind_host=self.bind_combo.currentData() or "0.0.0.0",
            advertised_host=self.advertised_combo.currentText().strip(),
            open_inbound=self.open_inbound_cb.isChecked(),
        )
        self._vault.db.peerSettings.pin(keys=("default",), val=rec)
        logger.info(
            f"peer.settings.saved enabled={rec.enabled} port={rec.port} "
            f"bind={rec.bind_host} advertised={rec.advertised_host!r}"
        )
        self._vault.restart_peer_mode()
        self._sync_status_from_doer()
        self._refresh_exposure_banner()
        if rec.enabled:
            # Give the listener a beat to bind, then probe ourselves.
            # 500ms is enough for hio's TCPServer to flip self.opened
            # in the common path without making the user wait.
            QTimer.singleShot(500, lambda: self._run_reachability_self_test(rec))

    def _on_find_free_port(self) -> None:
        port = find_free_port(start=self.port_spin.value())
        self.port_spin.setValue(port)
        logger.info(f"peer.settings.free_port_suggested port={port}")

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

    def _refresh_my_oobis(self) -> None:
        """One copyable peer-OOBI per local identifier.

        Only EXPOSED identifiers get a token: `export_peer_blob` derives it from
        `hab.replyToOobi(role=peer)`, which is empty for an unexposed AID, so an
        unexposed one is reported as such rather than rendered as a broken
        button. Failures are shown inline per identifier — one bad hab must not
        blank the whole card.
        """
        from locksmith.peer.cesr_blob import export_peer_blob
        from locksmith.peer.exposure import is_aid_peer_exposed

        while self.mine_list.count():
            child = self.mine_list.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        hby = getattr(self._vault, "hby", None)
        if hby is None:
            return

        rows = 0
        for (ns, alias), pre in list(hby.db.names.getTopItemIter(keys=())):
            # Namespaced habs are INFRASTRUCTURE, not identities the user
            # manages: the `peer-listener` EID (ns="peer") owns the vault's
            # listener socket, and the turret's settings hab (ns="settings") is
            # likewise internal. `listener_eid.py` is explicit that surfacing
            # the listener as a user identity "would be a lie about what it
            # is" — and worse here, it would render as "not exposed for peer
            # mode", inviting the user to go expose a thing that must not be.
            # Same rule the Identifiers page applies (identifiers/list.py:106).
            if ns != "":
                continue
            hab = hby.habByName(alias)
            if hab is None:
                continue
            row = QHBoxLayout()
            label = QLabel(f"{alias}\n{pre}")
            label.setObjectName(f"peerSettingsSection.oobiIdentity.{alias}")
            label.setStyleSheet("font-family: monospace; font-size: 10px;")
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(label, 1)

            try:
                if not is_aid_peer_exposed(hby, pre):
                    raise ValueError("not exposed for peer mode")
                token = export_peer_blob(hab)
            except Exception as exc:  # noqa: BLE001 — surface, never blank the card
                note = QLabel(str(exc))
                note.setStyleSheet(
                    f"color: {colors.TEXT_MUTED}; font-style: italic; font-size: 11px;")
                note.setWordWrap(True)
                row.addWidget(note)
            else:
                # READABLE, not just copyable. The token used to exist solely
                # inside the copy button's clipboard payload, so the only way
                # to obtain this wallet's own OOBI was a human clicking Copy —
                # which made the HOA's pairing untestable end to end, and left
                # a user with no way to SEE what they were about to hand out.
                # Read-only and elided: the blob is long, and this is an
                # identifier to inspect and copy, never to edit.
                token_field = QLineEdit(token)
                token_field.setObjectName(f"peerSettingsSection.oobiToken.{alias}")
                token_field.setReadOnly(True)
                token_field.setCursorPosition(0)
                token_field.setStyleSheet(
                    "font-family: monospace; font-size: 10px;")
                row.addWidget(token_field, 2)

                copy_btn = LocksmithCopyButton()
                copy_btn.setObjectName(f"peerSettingsSection.copyOobi.{alias}")
                copy_btn.set_copy_content(token)
                row.addWidget(copy_btn)

            holder = QWidget()
            holder.setLayout(row)
            self.mine_list.addWidget(holder)
            rows += 1

        if rows == 0:
            empty = QLabel("No identifiers in this wallet yet.")
            empty.setStyleSheet(f"color: {colors.TEXT_MUTED}; font-style: italic;")
            self.mine_list.addWidget(empty)

    def _refresh_exposure_banner(self) -> None:
        """Show the no-AID-exposed warning only when:
          - the listener is meant to be running (enabled=True), AND
          - no AIDs in this vault have peer-role published in their KEL.
        Disabled-listener and zero-AID cases have other UX surfaces
        (the listener status line, the new-identifier flow) and don't
        need to be flagged here.
        """
        try:
            settings = self._vault.db.peerSettings.get(keys=("default",))
        except AttributeError:
            settings = None
        if settings is None or not settings.enabled:
            self.exposure_banner.setVisible(False)
            return
        if not getattr(self._vault, "hby", None):
            self.exposure_banner.setVisible(False)
            return
        exposed = count_exposed(self._vault.hby)
        # Hide if exposed >0 OR if there are no AIDs at all (nothing
        # actionable to suggest).
        any_habs = any(True for _ in self._vault.hby.habs)
        self.exposure_banner.setVisible(exposed == 0 and any_habs)

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
        # Parent to the top-level window, not self: the card's QSS contains
        # `QWidget { background-color: transparent; }`, which would cascade
        # into the dialog and erase the QLineEdit chrome (invisible inputs).
        dialog = AddPeerDialog(vault=self._vault, parent=self.window())
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
            health = self._vault.db.peerHealth.get(keys=(rec.aid,))
            color_key, health_phrase = summarize_health_for_ui(health)
            # No text on the item itself — setItemWidget below renders a
            # custom row, and Qt paints both the item text AND the widget
            # if text is set, producing overlapping labels.
            item = QListWidgetItem()
            item.setData(Qt.UserRole, rec.aid)
            self.peers_list.addItem(item)
            row_widget = self._build_peer_row(rec, short_aid, color_key, health_phrase)
            item.setSizeHint(row_widget.sizeHint())
            self.peers_list.setItemWidget(item, row_widget)
        self._empty_state_label.setVisible(self.peers_list.count() == 0)

    def _build_peer_row(self, rec, short_aid: str, color_key: str,
                        health_phrase: str) -> QFrame:
        """Render one row: colored status dot · primary text · muted secondary."""
        color = {
            "green": _STATUS_DOT_GREEN,
            "amber": _STATUS_DOT_AMBER,
            "red": _STATUS_DOT_RED,
        }.get(color_key, _STATUS_DOT_GRAY)
        row = QFrame()
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(10)
        dot = QFrame()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
        h.addWidget(dot, 0, Qt.AlignVCenter)
        # objectNames on the row labels are what make this row readable by a
        # test. The QListWidgetItem carries no text (see _refresh_peers_list),
        # so the visible label/AID/endpoint live only in these child QLabels —
        # without names, nothing can assert on what the user actually sees.
        # One widget per peer, so callers disambiguate with `occurrence`.
        primary = QLabel(f"{rec.label}   {short_aid}   {rec.endpoint_url}")
        primary.setObjectName("peerSettingsSection.peerRowPrimary")
        primary.setStyleSheet("font-weight: 500;")
        h.addWidget(primary, 0, Qt.AlignVCenter)
        h.addStretch()
        secondary = QLabel(health_phrase)
        secondary.setObjectName("peerSettingsSection.peerRowHealth")
        secondary.setStyleSheet("color: #6E7074; font-size: 11px;")
        h.addWidget(secondary, 0, Qt.AlignVCenter)
        return row


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
