import socket

import pytest

from locksmith.peer.records import PeerModeSettings
from locksmith.ui.vault.settings.peer_section import PeerSettingsSection


class _StubVault:
    def __init__(self, baser):
        self.db = baser
        self.peer_doer = None
        self._restarts = 0

    def restart_peer_mode(self):
        self._restarts += 1


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_section_loads_existing_settings(qapp, baser):
    baser.peerSettings.pin(keys=("default",), val=PeerModeSettings(enabled=True, port=5621))
    vault = _StubVault(baser)
    section = PeerSettingsSection(vault=vault)
    assert section.enabled_toggle.isChecked() is True
    assert section.port_spin.value() == 5621


def test_first_time_setup_prefills_the_detected_primary_address(qapp, baser,
                                                                monkeypatch):
    """With no stored settings the advertised field used to come up blank,
    and a blank advertised host is what ends up published as an unreachable
    endpoint. Prefill what the wallet would auto-detect anyway."""
    monkeypatch.setattr(
        "locksmith.peer.netaddr.detect_primary_host", lambda: "192.168.1.20")
    section = PeerSettingsSection(vault=_StubVault(baser))
    assert section.advertised_combo.currentText() == "192.168.1.20"


def test_stored_advertised_host_is_not_overwritten_by_detection(qapp, baser,
                                                                monkeypatch):
    monkeypatch.setattr(
        "locksmith.peer.netaddr.detect_primary_host", lambda: "192.168.1.20")
    baser.peerSettings.pin(keys=("default",), val=PeerModeSettings(
        enabled=True, port=5621, advertised_host="admin.usurance.com"))
    section = PeerSettingsSection(vault=_StubVault(baser))
    assert section.advertised_combo.currentText() == "admin.usurance.com"


def test_toggle_writes_settings(qapp, baser):
    vault = _StubVault(baser)
    section = PeerSettingsSection(vault=vault)
    section.enabled_toggle.setChecked(True)
    section.port_spin.setValue(_free_port())
    section.apply_button.click()

    saved = baser.peerSettings.get(keys=("default",))
    assert saved is not None
    assert saved.enabled is True
    assert vault._restarts == 1


def test_status_line_reflects_listener_state(qapp, baser):
    vault = _StubVault(baser)
    section = PeerSettingsSection(vault=vault)
    section.update_status("Listening on 0.0.0.0:5621")
    assert "5621" in section.status_label.text()
