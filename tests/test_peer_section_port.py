"""TDD: first-time peer-mode setup defaults to a free port; Find free port button works.

These tests exercise PeerSettingsSection in isolation using a minimal stub
vault (no real LMDB).  PeerAllowlist is patched out because it requires a
real LocksmithBaser; the patch is test-only and does not weaken any
production path.
"""
import socket
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QMainWindow

from locksmith.peer.records import PeerRecord
from locksmith.ui.vault.settings.peer_section import PeerSettingsSection


def _vault_with_no_saved_settings():
    db = SimpleNamespace()
    db.peerSettings = MagicMock()
    db.peerSettings.get.return_value = None          # first-time setup
    db.peerHealth = MagicMock()
    db.peerHealth.get.return_value = None
    vault = SimpleNamespace(db=db, hby=None, peer_doer=None)
    return vault


def _make_section(vault, peers=()):
    """Construct PeerSettingsSection with PeerAllowlist patched."""
    with patch(
        "locksmith.ui.vault.settings.peer_section.PeerAllowlist"
    ) as mock_allowlist_cls:
        mock_allowlist_cls.return_value.list.return_value = list(peers)
        section = PeerSettingsSection(vault)
    return section


def test_first_time_setup_defaults_to_a_free_port(qapp):
    vault = _vault_with_no_saved_settings()
    section = _make_section(vault)
    try:
        port = section.port_spin.value()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("", port))  # must be bindable
    finally:
        section.deleteLater()


def test_find_free_port_button_updates_spin(qapp):
    vault = _vault_with_no_saved_settings()
    section = _make_section(vault)
    try:
        section.port_spin.setValue(5621)
        section._on_find_free_port()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("", section.port_spin.value()))  # bindable
    finally:
        section.deleteLater()


def test_paired_peer_row_has_no_text_overlay(qapp):
    """The custom row widget is mounted via setItemWidget; the QListWidgetItem
    must NOT also carry text() — Qt paints both and the result is jumbled
    overlapping labels."""
    vault = _vault_with_no_saved_settings()
    peer = PeerRecord(
        aid="ECnJ7jhAxjrduHkIKS_ml56bqPuIJIvSw-i0mpZR_P8p",
        label="Bob",
        endpoint_url="tcp://127.0.0.1:5622",
        paired_at="2026-06-09T00:00:00+00:00",
    )
    section = _make_section(vault, peers=[peer])
    try:
        assert section.peers_list.count() == 1
        item = section.peers_list.item(0)
        assert item.text() == ""
        assert section.peers_list.itemWidget(item) is not None
    finally:
        section.deleteLater()


def test_add_peer_dialog_parented_to_top_window_not_section(qapp):
    """The card's `QWidget { background-color: transparent; }` cascades to
    child dialogs and erases QLineEdit chrome. Parent the dialog to the
    top-level window instead so the section's QSS does not leak."""
    vault = _vault_with_no_saved_settings()
    section = _make_section(vault)
    win = QMainWindow()
    win.setCentralWidget(section)
    try:
        with patch(
            "locksmith.ui.vault.peers.add_dialog.AddPeerDialog"
        ) as mock_dialog_cls:
            mock_dialog_cls.return_value.open = MagicMock()
            section._on_add_peer()
        assert mock_dialog_cls.called
        _, kwargs = mock_dialog_cls.call_args
        assert kwargs["parent"] is win, (
            "Dialog parent must be the top-level window, not the QSS-poisoned "
            "PeerSettingsSection"
        )
    finally:
        win.deleteLater()
