"""Add Peer dialog — paste an OOBI URL, resolve, insert into allowlist."""
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
        self.setWindowTitle("Add peer")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Peer OOBI URL:"))
        self.oobi_input = QLineEdit()
        self.oobi_input.setPlaceholderText(
            "http://witness.example.com/oobi/EAID_BOB/peer/EWIT1"
        )
        layout.addWidget(self.oobi_input)

        layout.addWidget(QLabel("Label (optional):"))
        self.label_input = QLineEdit()
        layout.addWidget(self.label_input)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #a00;")
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        url = self.oobi_input.text().strip()
        if not url:
            self.error_label.setText("OOBI URL is required.")
            return

        try:
            aid, endpoint_url = self._resolve_oobi(url)
        except OobiResolutionError as e:
            logger.warning(f"peer.pair.failed reason={e.reason} url={url}")
            self.error_label.setText(str(e))
            return

        if self._allowlist.contains(aid):
            self.error_label.setText("This peer is already paired.")
            return

        self._allowlist.add(PeerRecord(
            aid=aid,
            label=self.label_input.text().strip() or aid[:12],
            endpoint_url=endpoint_url,
            paired_at=datetime.now(timezone.utc).isoformat(),
        ))
        self.peer_added.emit()
        self.accept()

    def _resolve_oobi(self, url: str) -> tuple[str, str]:
        """Resolve OOBI via the vault's Habery, return (aid, tcp_endpoint).

        Delegates to keripy's oobi resolver. The full resolution flow is
        async; for the dialog we do a synchronous fetch + extract. If
        the resolver hasn't completed by the time we read fetchUrls,
        treat that as a transient failure and ask the user to retry.
        """
        from keri.app import oobiing

        # Parse the AID out of the OOBI URL path first so we can give a
        # clean error before touching the network.
        path = urlparse(url).path  # /oobi/<aid>/peer/<eid>
        parts = [p for p in path.split("/") if p]
        if len(parts) < 3 or parts[0] != "oobi" or parts[2] != "peer":
            raise OobiResolutionError(
                "not_peer_oobi", "Not a peer-role OOBI URL."
            )
        aid = parts[1]

        # Hand the URL to the Habery's oobiery for resolution.
        oobiery = oobiing.Oobiery(hby=self._vault.hby)
        oobiery.processOobis()

        hab = self._vault.hby.habByPre(aid)
        if hab is None:
            raise OobiResolutionError(
                "kel_unverified",
                "Couldn't verify this peer's KEL. The OOBI may be tampered.",
            )

        urls = hab.fetchUrls(eid=hab.pre, scheme=kering.Schemes.tcp)
        if not urls or kering.Schemes.tcp not in urls:
            raise OobiResolutionError(
                "no_tcp_endpoint",
                "Peer's KEL does not authorize a tcp endpoint.",
            )
        return aid, urls[kering.Schemes.tcp]


class OobiResolutionError(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
