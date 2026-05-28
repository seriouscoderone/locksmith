"""Add Peer dialog — paste an OOBI URL, resolve, insert into allowlist.

Uses the same async ResolveOobiDoer pattern as Add Remote Identifier:
the dialog kicks off a doer in the vault's doist, listens for the
doer's events via the vault's signal bridge, and either inserts the
PeerRecord into the allowlist (success) or surfaces an error.

Never call blocking resolve helpers from a Qt click handler — they
deadlock the same doist that's supposed to do the resolving.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout,
)
from keri import help, kering

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerRecord

logger = help.ogler.getLogger(__name__)


class AddPeerDialog(QDialog):
    peer_added = Signal()

    def __init__(self, vault, parent=None):
        super().__init__(parent=parent)
        self._vault = vault
        self._allowlist = PeerAllowlist(vault.db)
        self._pending_aid: str | None = None  # AID we're trying to resolve
        self._signal_connected = False
        self.setWindowTitle("Pair a new peer")
        self._build()

    def _build(self) -> None:
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        intro = QLabel(
            "Paste the peer's OOBI URL. Ask the other wallet to copy its "
            "Peer OOBI from the identifier detail page."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        oobi_label = QLabel("Peer OOBI URL")
        oobi_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(oobi_label)
        self.oobi_input = QLineEdit()
        self.oobi_input.setObjectName("peer_dialog_oobi_input")
        self.oobi_input.setPlaceholderText(
            "https://witness.example.com/oobi/EAID.../peer/EWIT..."
        )
        layout.addWidget(self.oobi_input)

        endpoint_label = QLabel("Peer's TCP endpoint")
        endpoint_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        layout.addWidget(endpoint_label)
        endpoint_help = QLabel(
            "The tcp://host:port the peer is listening on. The OOBI verifies "
            "the AID; the endpoint tells this wallet where to send messages. "
            "On a LAN/VPN, the peer's wallet shows this in its peer-mode "
            "settings."
        )
        endpoint_help.setWordWrap(True)
        endpoint_help.setStyleSheet("color: #6E7074; font-size: 11px;")
        layout.addWidget(endpoint_help)
        self.endpoint_input = QLineEdit()
        self.endpoint_input.setObjectName("peer_dialog_endpoint_input")
        self.endpoint_input.setPlaceholderText("tcp://192.168.1.42:5621")
        layout.addWidget(self.endpoint_input)

        label_label = QLabel("Nickname for this peer")
        label_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        layout.addWidget(label_label)
        self.label_input = QLineEdit()
        self.label_input.setObjectName("peer_dialog_label_input")
        self.label_input.setPlaceholderText("e.g. Alice's laptop")
        layout.addWidget(self.label_input)

        self.status_label = QLabel("")
        self.status_label.setObjectName("peer_dialog_status")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #6E7074; margin-top: 8px;")
        layout.addWidget(self.status_label)

        self.error_label = QLabel("")
        self.error_label.setObjectName("peer_dialog_error")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #DC2626; margin-top: 4px;")
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.pair_button = buttons.button(QDialogButtonBox.Ok)
        if self.pair_button is not None:
            self.pair_button.setText("Pair")
            self.pair_button.setObjectName("peer_dialog_pair_button")
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        if cancel_btn is not None:
            cancel_btn.setObjectName("peer_dialog_cancel_button")
        buttons.accepted.connect(self._on_pair_clicked)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_pair_clicked(self) -> None:
        from locksmith.core.remoting import ResolveOobiDoer

        url = self.oobi_input.text().strip()
        endpoint = self.endpoint_input.text().strip()
        if not url:
            self.error_label.setText("OOBI URL is required.")
            return
        if not endpoint:
            self.error_label.setText(
                "Peer's TCP endpoint is required (e.g. tcp://192.168.1.42:5621)."
            )
            return
        if not endpoint.startswith("tcp://"):
            self.error_label.setText(
                "Endpoint must start with tcp:// (e.g. tcp://192.168.1.42:5621)."
            )
            return
        try:
            aid = self._parse_peer_oobi(url)
        except OobiResolutionError as e:
            self.error_label.setText(str(e))
            return
        if self._allowlist.contains(aid):
            self.error_label.setText("This peer is already paired with this vault.")
            return

        self._pending_endpoint = endpoint

        app = self._app()
        if app is None or app.vault is None:
            self.error_label.setText("Vault not available.")
            return

        # Wire up doer-event listener exactly once
        if not self._signal_connected and hasattr(app.vault, "signals"):
            app.vault.signals.doer_event.connect(self._on_doer_event)
            self._signal_connected = True

        self._pending_aid = aid
        self.error_label.setText("")
        self.status_label.setText(
            "Resolving OOBI through the witness — this may take a few seconds…"
        )
        if self.pair_button is not None:
            self.pair_button.setEnabled(False)

        doer = ResolveOobiDoer(
            app=app,
            pre=aid,
            oobi=url,
            alias=None,
            tag="peer",
            signal_bridge=app.vault.signals if hasattr(app.vault, "signals") else None,
        )
        app.vault.extend([doer])

    def _parse_peer_oobi(self, url: str) -> str:
        path = urlparse(url).path  # /oobi/<aid>/peer/<eid>
        parts = [p for p in path.split("/") if p]
        if len(parts) < 3 or parts[0] != "oobi" or parts[2] != "peer":
            raise OobiResolutionError(
                "not_peer_oobi",
                "This OOBI is for a different role (witness, mailbox, or "
                "controller). Ask the peer for their peer-role OOBI.",
            )
        return parts[1]

    def _on_doer_event(self, doer_name: str, event_type: str, data: dict) -> None:
        if doer_name != "ResolveOobiDoer":
            return
        if self._pending_aid is None or data.get("pre") != self._pending_aid:
            return

        if event_type == "oobi_resolved":
            self._finalize_pairing()
        elif event_type in ("oobi_resolution_failed", "oobi_resolution_timeout"):
            reason = (
                "Timed out reaching the witness"
                if event_type == "oobi_resolution_timeout"
                else data.get("error") or "OOBI resolution failed"
            )
            self._reset_pair_button()
            self.status_label.setText("")
            self.error_label.setText(
                f"Couldn't verify this peer's key history: {reason}. "
                f"Try resolving again, or ask the peer to resend."
            )
            self._pending_aid = None

    def _finalize_pairing(self) -> None:
        aid = self._pending_aid
        endpoint = getattr(self, "_pending_endpoint", None)
        if aid is None or not endpoint:
            return
        # Prefer the endpoint from the peer's KEL (locs Komer) if the
        # witness propagated the role authorization. Most witnesses
        # today don't, so we fall back to the user-provided endpoint.
        loc = self._vault.hby.db.locs.get(keys=(aid, kering.Schemes.tcp))
        endpoint_url = loc.url if (loc is not None and loc.url) else endpoint
        self._allowlist.add(PeerRecord(
            aid=aid,
            label=self.label_input.text().strip() or aid[:12],
            endpoint_url=endpoint_url,
            paired_at=datetime.now(timezone.utc).isoformat(),
        ))
        self._pending_aid = None
        self._pending_endpoint = None
        self.peer_added.emit()
        self.accept()

    def _reset_pair_button(self) -> None:
        if self.pair_button is not None:
            self.pair_button.setEnabled(True)

    def _app(self):
        app = getattr(self._vault, "app", None)
        if app is None:
            app = getattr(self._vault, "_app", None)
        return app


class OobiResolutionError(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
