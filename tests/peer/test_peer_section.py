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
