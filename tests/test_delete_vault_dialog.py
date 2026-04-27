from types import SimpleNamespace

from PySide6.QtWidgets import QDialog

from locksmith.ui.vault.settings.delete_dialog import DeleteVaultDialog


def test_delete_vault_dialog_stays_open_when_delete_fails(qapp):
    app = SimpleNamespace(delete_vault=lambda vault_name: False)
    dialog = DeleteVaultDialog(vault_name="test-vault", app=app)
    emitted = []
    dialog.vault_deleted.connect(emitted.append)

    dialog.vault_name_input.setText("test-vault")
    dialog._do_delete()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert emitted == []
    assert dialog.delete_btn.isEnabled()
    assert "Failed to delete vault" in dialog.error_label.text()


def test_delete_vault_dialog_emits_after_success(qapp):
    calls = []
    app = SimpleNamespace(delete_vault=lambda vault_name: calls.append(vault_name) or True)
    dialog = DeleteVaultDialog(vault_name="test-vault", app=app)
    emitted = []
    dialog.vault_deleted.connect(emitted.append)

    dialog.vault_name_input.setText("test-vault")
    dialog._do_delete()

    assert calls == ["test-vault"]
    assert emitted == ["test-vault"]
    assert dialog.result() == QDialog.DialogCode.Accepted
