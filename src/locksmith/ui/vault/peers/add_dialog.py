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

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout,
)
from keri import help, kering

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerRecord
from locksmith.ui import colors

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
        # Pin a light theme — the raw QDialog otherwise inherits the
        # system appearance and shows up as a near-black dialog against
        # the rest of the (light) Locksmith UI. LocksmithDialog handles
        # this on its own; this one is a plain QDialog.
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {colors.BACKGROUND_CONTENT};
            }}
            QLabel {{
                color: {colors.TEXT_PRIMARY};
                background-color: transparent;
            }}
            QLineEdit {{
                background-color: {colors.WHITE};
                color: {colors.TEXT_PRIMARY};
                border: 1px solid {colors.BORDER_TABLE};
                border-radius: 6px;
                padding: 6px 8px;
            }}
            QLineEdit:focus {{
                border: 1px solid {colors.PRIMARY};
            }}
            QPushButton {{
                color: {colors.TEXT_PRIMARY};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        intro = QLabel(
            "Paste either a witness-served OOBI URL or a witness-less "
            "peer-OOBI blob (starting with `locksmith-peer-oobi:v1:`) "
            "copied from the other wallet's identifier detail page."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        oobi_label = QLabel("Peer OOBI URL or blob")
        oobi_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(oobi_label)
        self.oobi_input = QLineEdit()
        self.oobi_input.setObjectName("addPeerDialog.oobiInput")
        self.oobi_input.setPlaceholderText(
            "https://witness.example.com/oobi/… or locksmith-peer-oobi:v1:…"
        )
        layout.addWidget(self.oobi_input)

        endpoint_label = QLabel("Peer's TCP endpoint")
        endpoint_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        layout.addWidget(endpoint_label)
        endpoint_help = QLabel(
            "The tcp://host:port the peer is listening on. Optional — the "
            "endpoint normally comes from the OOBI itself (embedded in a "
            "witness-less blob, or served by the witness when the peer has "
            "published their role authorization). Fill this in only as a "
            "manual override (e.g. an on-LAN address that differs from the "
            "advertised one, or when the witness is unreachable)."
        )
        endpoint_help.setWordWrap(True)
        endpoint_help.setStyleSheet("color: #6E7074; font-size: 11px;")
        layout.addWidget(endpoint_help)
        self.endpoint_input = QLineEdit()
        self.endpoint_input.setObjectName("addPeerDialog.endpointInput")
        self.endpoint_input.setPlaceholderText("tcp://192.168.1.42:5621")
        layout.addWidget(self.endpoint_input)

        label_label = QLabel("Nickname for this peer")
        label_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        layout.addWidget(label_label)
        self.label_input = QLineEdit()
        self.label_input.setObjectName("addPeerDialog.labelInput")
        self.label_input.setPlaceholderText("e.g. Alice's laptop")
        layout.addWidget(self.label_input)

        self.status_label = QLabel("")
        self.status_label.setObjectName("addPeerDialog.statusLabel")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #6E7074; margin-top: 8px;")
        layout.addWidget(self.status_label)

        self.error_label = QLabel("")
        self.error_label.setObjectName("addPeerDialog.errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #DC2626; margin-top: 4px;")
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.pair_button = buttons.button(QDialogButtonBox.Ok)
        if self.pair_button is not None:
            self.pair_button.setText("Pair")
            self.pair_button.setObjectName("addPeerDialog.pairButton")
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        if cancel_btn is not None:
            cancel_btn.setObjectName("addPeerDialog.cancelButton")
        buttons.accepted.connect(self._on_pair_clicked)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_pair_clicked(self) -> None:
        from locksmith.core.remoting import ResolveOobiDoer
        from locksmith.peer.cesr_blob import (
            PeerBlobError, import_peer_blob, is_peer_blob,
        )

        url = self.oobi_input.text().strip()
        endpoint = self.endpoint_input.text().strip()
        if not url:
            self.error_label.setText(
                "Paste either a peer OOBI URL or a witness-less peer-OOBI blob."
            )
            return

        # Witness-less path: blob carries KEL + role auth + endpoint.
        # No witness round-trip needed and no separate endpoint entry.
        if is_peer_blob(url):
            try:
                aid = import_peer_blob(self._vault.hby, url)
            except PeerBlobError as e:
                logger.warning(
                    f"peer.pair.failed reason={e.reason} kind=blob"
                )
                self.error_label.setText(str(e))
                return
            if self._allowlist.contains(aid):
                self.error_label.setText(
                    "This peer is already paired with this vault."
                )
                return
            # Endpoint comes from the blob itself (locs Komer is now
            # populated). If the user also typed one, prefer theirs
            # (override / on-network address).
            from keri import kering
            loc = self._vault.hby.db.locs.get(keys=(aid, kering.Schemes.tcp))
            endpoint_url = endpoint if endpoint else (loc.url if loc else "")
            if not endpoint_url:
                self.error_label.setText(
                    "Blob parsed but no tcp endpoint is published. "
                    "Provide a TCP endpoint manually."
                )
                return
            label = self.label_input.text().strip() or aid[:12]
            self._allowlist.add(PeerRecord(
                aid=aid,
                label=label,
                endpoint_url=endpoint_url,
                paired_at=datetime.now(timezone.utc).isoformat(),
            ))
            # Also register the AID as a known remote identifier so it
            # shows up in places that consume vault.org.list() (e.g. the
            # Issue Credential recipient dropdown). The witness-served
            # OOBI path gets this for free via ResolveOobiDoer; the
            # blob path doesn't, so do it explicitly.
            try:
                from keri import help as keri_help
                self._vault.org.update(aid, {
                    "alias": label,
                    "last-refresh": keri_help.nowIso8601(),
                })
            except Exception as e:  # noqa: BLE001
                logger.warning(f"peer.pair.org_upsert_failed aid={aid} err={e}")
            self.peer_added.emit()
            self.accept()
            return

        # URL path: witness-served OOBI. Endpoint is optional — if the peer
        # has published their role+loc rpys to their witness, the resolve
        # below will populate hby.db.locs and _finalize_pairing will read
        # the endpoint from there. The manual field stays as an override.
        if endpoint and not endpoint.startswith("tcp://"):
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

    # Up to ~2.5s of poll attempts (every 250ms). The ResolveOobiDoer
    # fires oobi_resolved as soon as the AID lands in hby.kevers, but
    # Revery may still be processing /loc/scheme rpys from the same
    # response — db.locs can lag by a few ticks of the doist.
    _LOC_POLL_INTERVAL_MS = 250
    _LOC_POLL_MAX_ATTEMPTS = 10

    def _finalize_pairing(self, attempts_remaining: int | None = None) -> None:
        if attempts_remaining is None:
            attempts_remaining = self._LOC_POLL_MAX_ATTEMPTS
        # Bail if the user closed the dialog while we were polling.
        if not self.isVisible():
            self._pending_aid = None
            return
        aid = self._pending_aid
        if aid is None:
            return
        # Endpoint resolution order: manual override (typed in field) wins,
        # else the rpy-populated locs Komer (works when the peer published
        # role+loc rpys to their witness — see PublishPeerRoleDoer).
        manual = getattr(self, "_pending_endpoint", None) or None
        loc = self._vault.hby.db.locs.get(keys=(aid, kering.Schemes.tcp))
        from_kel = loc.url if (loc is not None and loc.url) else None
        endpoint_url = manual or from_kel
        if not endpoint_url and attempts_remaining > 0:
            QTimer.singleShot(
                self._LOC_POLL_INTERVAL_MS,
                lambda: self._finalize_pairing(attempts_remaining - 1),
            )
            return
        if not endpoint_url:
            self._reset_pair_button()
            self.status_label.setText("")
            self.error_label.setText(
                "OOBI verified but no tcp endpoint is published for this "
                "peer. Either ask the peer to enable peer-mode exposure on "
                "their identifier, or fill in the endpoint field manually."
            )
            self._pending_aid = None
            return
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
