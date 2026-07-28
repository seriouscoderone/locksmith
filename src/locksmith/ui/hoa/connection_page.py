# -*- encoding: utf-8 -*-
"""Connection diagnostics for a peeled HOA shell.

``HoaVaultPage`` registers none of the stock wallet pages, so an HOA build
has no peer-settings card, no paired-peers list, and no identifier page — and
there is no in-app log viewer. When a role request comes back with "the
administrator's application isn't reachable", the user's only diagnosis path
today is relaunching the ``.app`` from a terminal and reading ogler output.

This page is the minimum that makes the failure legible in the field:

  - is the listener actually up, and on what port;
  - what address this wallet is telling peers to dial back on, with a loud
    warning when that address is loopback or a wildcard (the failure that
    looks identical to "the other app isn't running");
  - each paired peer's endpoint and last probe outcome, straight from
    ``db.peerHealth`` — already written every cycle by ``PeerHealthMonitorDoer``,
    just never surfaced anywhere an HOA user can see.

It is read-only by design. Nothing here mutates settings: the advertised
address is discovered (``locksmith.peer.netaddr``) and overridden by
``$LOCKSMITH_ADVERTISED_HOST`` or the brand's ``[peer] advertised_host``, so a
text box here would be a fourth source of truth for no benefit.

``connection_snapshot`` is a pure function over the vault's databases so the
diagnosis is assertable without a live listener.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout,
    QWidget,
)
from keri import help

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.health import summarize_health_for_ui
from locksmith.peer.netaddr import ADVERTISED_HOST_ENV_VAR
from locksmith.ui import colors

logger = help.ogler.getLogger(__name__)

_DOT = {"green": "#22C55E", "amber": "#F59E0B", "red": "#DC2626"}
_DOT_GRAY = "#9CA3AF"


@dataclass(frozen=True)
class PeerStatus:
    aid: str
    label: str
    endpoint_url: str
    color: str
    status: str


@dataclass(frozen=True)
class ConnectionSnapshot:
    listening: bool = False
    bind_host: str = ""
    port: int | None = None
    advertised_host: str = ""
    advertised_is_routable: bool = False
    peers: list[PeerStatus] = field(default_factory=list)

    @property
    def advertised_url(self) -> str:
        if not self.advertised_host or self.port is None:
            return ""
        return f"tcp://{self.advertised_host}:{self.port}"


def _is_routable(host: str) -> bool:
    if not host or host.lower() in ("localhost", "localhost.localdomain", "*"):
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return True          # a DNS name — can't judge from here
    return not (addr.is_loopback or addr.is_unspecified)


def connection_snapshot(vault) -> ConnectionSnapshot:
    """Everything this page renders, read once from the vault's databases."""
    settings = vault.db.peerSettings.get(keys=("default",))
    server = getattr(getattr(vault, "peer_doer", None), "server", None)

    peers = []
    for rec in PeerAllowlist(vault.db).list():
        color, phrase = summarize_health_for_ui(
            vault.db.peerHealth.get(keys=(rec.aid,)))
        peers.append(PeerStatus(aid=rec.aid, label=rec.label,
                                endpoint_url=rec.endpoint_url,
                                color=color, status=phrase))

    if settings is None:
        return ConnectionSnapshot(peers=peers)
    return ConnectionSnapshot(
        listening=bool(server is not None and server.opened),
        bind_host=settings.bind_host,
        port=settings.port,
        advertised_host=settings.advertised_host,
        advertised_is_routable=_is_routable(settings.advertised_host),
        peers=peers,
    )


class HoaConnectionPage(QWidget):
    """Read-only listener/peer diagnostics. Registered as the "connection"
    page by ``HoaShellPlugin`` (same conditional-registration idiom as
    "home" and "notifications")."""

    def __init__(self, vault_provider, parent=None):
        """`vault_provider` is called on every refresh and may return None:
        this page is registered at ``on_vault_ui_ready`` time, before any
        vault has been opened (same contract as the onboarding home page's
        ``held_provider``)."""
        super().__init__(parent=parent)
        self._vault_provider = vault_provider
        self._build()
        self.refresh()
        # PeerHealthMonitorDoer rewrites db.peerHealth every ~60s; repaint a
        # few times a minute so a user staring at this page while debugging
        # sees state change without navigating away and back. Same cadence
        # (and same rationale) as the stock peer settings card.
        self._timer = QTimer(self)
        self._timer.setInterval(15_000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    # -- construction -----------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(8)

        header = QLabel("Connection")
        font = QFont(); font.setBold(True); font.setPointSize(16)
        header.setFont(font)
        header.setStyleSheet(f"color: {colors.TEXT_PRIMARY};")
        layout.addWidget(header)

        sub = QLabel(
            "How this workspace is reachable, and whether the people it "
            "talks to are reachable back. Share this screen when reporting "
            "a connection problem."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(sub)
        layout.addSpacing(10)

        self.listener_label = QLabel()
        self.listener_label.setObjectName("hoaConnectionPage.listenerLabel")
        self.listener_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.listener_label)

        self.advertised_label = QLabel()
        self.advertised_label.setObjectName("hoaConnectionPage.advertisedLabel")
        self.advertised_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.advertised_label)

        self.warning_label = QLabel()
        self.warning_label.setObjectName("hoaConnectionPage.warningLabel")
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet(
            "background-color: #FEF3C7; color: #92400E; "
            "border: 1px solid #FCD34D; border-radius: 8px; "
            "padding: 10px 14px; margin-top: 10px; font-size: 12px;")
        self.warning_label.setVisible(False)
        layout.addWidget(self.warning_label)

        layout.addSpacing(16)
        peers_header = QLabel("Who this workspace can reach")
        pf = QFont(); pf.setBold(True); pf.setPointSize(13)
        peers_header.setFont(pf)
        peers_header.setStyleSheet(f"color: {colors.TEXT_PRIMARY};")
        layout.addWidget(peers_header)

        self.peers_list = QListWidget()
        self.peers_list.setObjectName("hoaConnectionPage.peersList")
        self.peers_list.setStyleSheet("QListWidget { border: 0; }")
        layout.addWidget(self.peers_list)

        self.empty_label = QLabel(
            "Nothing paired yet. The workspace pairs with its administrator "
            "automatically the first time it opens.")
        self.empty_label.setObjectName("hoaConnectionPage.emptyLabel")
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 12px; padding: 8px;")
        layout.addWidget(self.empty_label)
        layout.addStretch()

    # -- rendering --------------------------------------------------------
    def refresh(self) -> None:
        vault = self._vault_provider()
        snap = ConnectionSnapshot() if vault is None else connection_snapshot(vault)

        if snap.listening:
            self.listener_label.setText(
                f"Listening on {snap.bind_host}:{snap.port}")
        elif snap.port:
            self.listener_label.setText(
                f"Not listening (configured for port {snap.port})")
        else:
            self.listener_label.setText("Not listening — no peer settings yet")

        self.advertised_label.setText(
            f"Peers are told to reach this workspace at "
            f"{snap.advertised_url or 'nothing — no address advertised'}")

        self.warning_label.setVisible(
            bool(snap.port) and not snap.advertised_is_routable)
        self.warning_label.setText(
            f"This workspace is advertising "
            f"“{snap.advertised_host or 'no address'}”, which only means "
            f"“this same computer”. Anyone on another machine will see "
            f"“isn't reachable” when they try to reach you. Set "
            f"{ADVERTISED_HOST_ENV_VAR} to an address they can reach, then "
            f"restart.")

        self.peers_list.clear()
        for peer in snap.peers:
            item = QListWidgetItem()
            row = self._peer_row(peer)
            item.setSizeHint(row.sizeHint())
            self.peers_list.addItem(item)
            self.peers_list.setItemWidget(item, row)
        self.empty_label.setVisible(not snap.peers)

    def _peer_row(self, peer: PeerStatus) -> QFrame:
        row = QFrame()
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(10)
        dot = QFrame()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(
            f"background-color: {_DOT.get(peer.color, _DOT_GRAY)}; "
            f"border-radius: 5px;")
        h.addWidget(dot, 0, Qt.AlignVCenter)
        primary = QLabel(f"{peer.label}   {peer.endpoint_url}")
        primary.setStyleSheet("font-weight: 500;")
        h.addWidget(primary, 0, Qt.AlignVCenter)
        h.addStretch()
        secondary = QLabel(peer.status)
        secondary.setStyleSheet("color: #6E7074; font-size: 11px;")
        h.addWidget(secondary, 0, Qt.AlignVCenter)
        return row
