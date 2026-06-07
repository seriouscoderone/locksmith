from types import SimpleNamespace
from locksmith.ui.toolbar import LocksmithToolbar


def test_set_vault_name_updates_label(qapp):
    app = SimpleNamespace(vault=None, name=None)
    tb = LocksmithToolbar(app)
    try:
        assert tb.vault_name_label.text() == ""
        tb.set_vault_name("treasurer")
        assert tb.vault_name_label.text() == "treasurer"
        tb.set_vault_name(None)
        assert tb.vault_name_label.text() == ""
    finally:
        tb.deleteLater()
