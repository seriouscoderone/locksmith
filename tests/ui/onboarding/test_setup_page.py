# -*- encoding: utf-8 -*-
"""Tests for SetupPage — the first-run workspace-setup UI shown to
onboarding-enabled HOA brands in place of the silent default bootstrap
(Task 4). Constructed directly with no parent window, matching the
pattern other standalone toolkit-widget tests use (see
tests/ui/vault/test_hoa_page.py) — SetupPage only reads/writes its own
child widgets, it doesn't need ``self.parent_window`` for these behaviors.
"""
from locksmith.ui.onboarding.setup_page import SetupPage


def test_submit_blocked_until_valid(qtbot):
    page = SetupPage(default_name="Carrier")
    qtbot.addWidget(page)
    assert not page.submit_btn.isEnabled()  # empty passcode, no ack
    page.passcode.setText("abc123xyz")
    page.confirm.setText("abc123xy")
    assert not page.submit_btn.isEnabled()  # mismatch
    page.confirm.setText("abc123xyz")
    assert page.submit_btn.isEnabled()


def test_empty_passcode_requires_acknowledgment(qtbot):
    page = SetupPage(default_name="Carrier")
    qtbot.addWidget(page)
    assert not page.submit_btn.isEnabled()
    page.no_passcode_ack.setChecked(True)
    assert page.submit_btn.isEnabled()


def test_submit_emits_name_and_passcode(qtbot):
    page = SetupPage(default_name="Carrier")
    qtbot.addWidget(page)
    page.name.setText("My Workspace")
    page.passcode.setText("s3cretpass")
    page.confirm.setText("s3cretpass")
    with qtbot.waitSignal(page.setup_submitted) as sig:
        page.submit_btn.click()
    assert sig.args == ["My Workspace", "s3cretpass"]


def test_default_name_prefills_the_name_field(qtbot):
    """The name field prefills from brand().default_vault_name (passed in
    as default_name) so the user isn't forced to retype the brand's
    suggested workspace name — they can accept it or change it."""
    page = SetupPage(default_name="Carrier")
    qtbot.addWidget(page)
    assert page.name.text() == "Carrier"


def test_toolbar_config_hides_vault_controls(qtbot):
    """First-run setup has no vault yet — the vault-drawer and lock
    controls the toolbar would otherwise show don't apply."""
    page = SetupPage(default_name="Carrier")
    qtbot.addWidget(page)
    config = page.get_toolbar_config()
    assert config["show_vaults_button"] is False
    assert config["show_lock_button"] is False
