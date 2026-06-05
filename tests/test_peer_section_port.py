"""TDD: first-time peer-mode setup defaults to a free port; Find free port button works.

These tests exercise PeerSettingsSection in isolation using a minimal stub
vault (no real LMDB).  PeerAllowlist is patched out because it requires a
real LocksmithBaser; the patch is test-only and does not weaken any
production path.
"""
import socket
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from locksmith.ui.vault.settings.peer_section import PeerSettingsSection


def _vault_with_no_saved_settings():
    db = SimpleNamespace()
    db.peerSettings = MagicMock()
    db.peerSettings.get.return_value = None          # first-time setup
    db.peerHealth = MagicMock()
    db.peerHealth.get.return_value = None
    vault = SimpleNamespace(db=db, hby=None, peer_doer=None)
    return vault


def _make_section(vault):
    """Construct PeerSettingsSection with PeerAllowlist patched to return []."""
    with patch(
        "locksmith.ui.vault.settings.peer_section.PeerAllowlist"
    ) as mock_allowlist_cls:
        mock_allowlist_cls.return_value.list.return_value = []
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
