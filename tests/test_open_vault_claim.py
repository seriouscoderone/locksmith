from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtWidgets import QWidget

from locksmith.core.instancing import InstanceCoordinator
from locksmith.ui.vaults import open as open_module
from locksmith.ui.vaults.open import OpenVaultDialog


def _make_dialog(qapp, tmp_path, coordinator):
    parent = QWidget()
    parent.app = SimpleNamespace(coordinator=coordinator)
    config = SimpleNamespace(base=str(tmp_path), salt=None)
    with patch.object(open_module.otping, "has_otp_configured", return_value=False):
        return OpenVaultDialog(vault_name="treasurer", parent=parent, config=config), parent


def test_open_vault_aborts_when_vault_owned_elsewhere(qapp, tmp_path):
    owner = InstanceCoordinator(base=str(tmp_path))
    owner.claim("treasurer")  # vault already open in "another instance"
    this_instance = InstanceCoordinator(base=str(tmp_path))
    dialog, parent = _make_dialog(qapp, tmp_path, this_instance)
    try:
        with patch.object(open_module, "keystore_exists", return_value=True), \
             patch.object(open_module, "open_hby") as open_hby, \
             patch.object(dialog, "show_error") as show_error:
            dialog.open_vault()
            open_hby.assert_not_called()       # never touched the keystore
            show_error.assert_called_once()    # surfaced "already open elsewhere"
    finally:
        owner.release_all()
        this_instance.release_all()
        dialog.close()
        parent.close()


def test_open_vault_claims_when_unowned(qapp, tmp_path):
    this_instance = InstanceCoordinator(base=str(tmp_path))
    dialog, parent = _make_dialog(qapp, tmp_path, this_instance)
    try:
        with patch.object(open_module, "keystore_exists", return_value=True), \
             patch.object(open_module, "is_vault_encrypted", return_value=False), \
             patch.object(open_module, "open_hby", return_value=("vault", "qtask")) as open_hby:
            parent.app.open_vault = lambda **kw: None
            dialog.open_vault()
            open_hby.assert_called_once()                       # proceeded to open
            assert this_instance.probe("treasurer") is True    # claim is held
    finally:
        this_instance.release_all()
        dialog.close()
        parent.close()


def test_open_vault_releases_claim_when_open_fails(qapp, tmp_path):
    this_instance = InstanceCoordinator(base=str(tmp_path))
    dialog, parent = _make_dialog(qapp, tmp_path, this_instance)
    try:
        with patch.object(open_module, "keystore_exists", return_value=True), \
             patch.object(open_module, "is_vault_encrypted", return_value=False), \
             patch.object(open_module, "open_hby", side_effect=ValueError("boom")), \
             patch.object(dialog, "show_error") as show_error:
            dialog.open_vault()
            show_error.assert_called_once()                     # surfaced the failure
            assert this_instance.probe("treasurer") is False   # claim was released
    finally:
        this_instance.release_all()
        dialog.close()
        parent.close()
