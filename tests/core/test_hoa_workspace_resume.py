"""A peeled HOA build must always land the user in a workspace.

Regression suite for the blank-home-page bug: the launch path only acted when
the machine had ZERO vaults (``not app.environments()``), which is false on
every launch after the first — and false from the very first launch when the
shared ``~/.keri`` base already holds an unrelated vault. Neither branch fired,
nothing opened a vault, and because a peeled build has no vault chooser the
window sat on an empty HomePage with just the brand logo.

The fix resolves the brand's OWN workspace (``hoa_workspace_vault``) and adds a
resume branch, so the outcome is always one of: resume / first-run setup /
silent bootstrap — never "nothing".
"""
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QCoreApplication, QSettings

from locksmith.core.bootstrapping import (
    hoa_workspace_vault,
    remember_workspace_vault,
    remembered_workspace_vault,
)


@pytest.fixture(autouse=True)
def qsettings_in_memory(tmp_path):
    """Point QSettings at a temp ini so tests never touch real user prefs."""
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QCoreApplication.setOrganizationName("LocksmithTest")
    QCoreApplication.setApplicationName("LocksmithTest")
    yield


def _app(*envs):
    app = MagicMock()
    app.environments.return_value = list(envs)
    return app


def _brand(default_vault_name="Default", **over):
    b = MagicMock()
    b.default_vault_name = default_vault_name
    for k, v in over.items():
        setattr(b, k, v)
    return b


# --- hoa_workspace_vault resolution ------------------------------------------

def test_unrelated_vaults_do_not_count_as_this_brands_workspace():
    """THE bug, at the unit level. The user's real disk state held three
    vaults, none of them Usurance's — so this is a genuine first run for the
    brand and must report "no workspace" (-> first-run setup)."""
    app = _app("Carrier", "usurance-custody", "Utah State")
    assert hoa_workspace_vault(app, _brand("Default")) is None


def test_resolves_the_brand_default_when_it_exists():
    app = _app("Carrier", "Default")
    assert hoa_workspace_vault(app, _brand("Default")) == "Default"


def test_remembered_workspace_wins_over_the_brand_default():
    """The workspace name is user-chosen at first run (SetupPage), so a renamed
    workspace must still resume instead of creating a second one."""
    remember_workspace_vault("My Workspace")
    app = _app("Default", "My Workspace")
    assert hoa_workspace_vault(app, _brand("Default")) == "My Workspace"


def test_stale_remembered_workspace_is_ignored():
    """A record pointing at a deleted vault must not win, or resume would try
    to open something that isn't there."""
    remember_workspace_vault("Deleted Workspace")
    app = _app("Default")
    assert hoa_workspace_vault(app, _brand("Default")) == "Default"


def test_no_vaults_at_all_means_no_workspace():
    assert hoa_workspace_vault(_app(), _brand("Default")) is None


def test_workspace_memory_round_trips():
    assert remembered_workspace_vault() is None
    remember_workspace_vault("Default")
    assert remembered_workspace_vault() == "Default"


# --- the launch dispatcher ----------------------------------------------------
#
# Called unbound with a stub `self`: constructing a real LocksmithWindow needs a
# live QApplication + full plugin discovery, which the existing bootstrap tests
# deliberately avoid (see their source-inspection docstrings).

def _win(app, brand_cfg):
    from locksmith.ui.window import LocksmithWindow

    win = MagicMock()
    win.app = app
    win._resume_or_bootstrap_hoa = (
        lambda: LocksmithWindow._resume_or_bootstrap_hoa(win)
    )
    win._brand_cfg = brand_cfg
    return win


def _run(monkeypatch, app, brand_cfg):
    monkeypatch.setattr("locksmith.ui.window.brand", lambda: brand_cfg)
    win = _win(app, brand_cfg)
    win._resume_or_bootstrap_hoa()
    return win


def test_existing_workspace_is_resumed_not_recreated(monkeypatch):
    app = _app("Default")
    app.vault = None
    app.name = None
    win = _run(monkeypatch, app, _brand("Default", onboarding_enabled=True))

    win.open_vault_targeted.assert_called_once_with("Default")
    win._show_first_run_setup.assert_not_called()
    win._run_default_bootstrap.assert_not_called()


def test_already_open_workspace_just_navigates(monkeypatch):
    """No second passcode prompt when the bootstrap already opened it."""
    app = _app("Default")
    app.vault = MagicMock()
    app.name = "Default"
    win = _run(monkeypatch, app, _brand("Default", onboarding_enabled=True))

    win.open_vault_targeted.assert_not_called()
    win.nav_manager.navigate_to.assert_called_once()


def test_no_workspace_shows_first_run_setup_for_onboarding_brand(monkeypatch):
    """The user's exact case: unrelated vaults present, none of them ours."""
    app = _app("Carrier", "Utah State")
    app.vault = None
    win = _run(monkeypatch, app, _brand("Default", onboarding_enabled=True))

    win._show_first_run_setup.assert_called_once()
    win.open_vault_targeted.assert_not_called()
    win._run_default_bootstrap.assert_not_called()


def test_no_workspace_silently_bootstraps_a_non_onboarding_brand(monkeypatch):
    app = _app("Carrier")
    app.vault = None
    win = _run(monkeypatch, app, _brand("Default", onboarding_enabled=False))

    win._run_default_bootstrap.assert_called_once()
    win._show_first_run_setup.assert_not_called()


def test_dispatcher_always_takes_exactly_one_branch(monkeypatch):
    """The blank page came from "no branch fired". For every combination an HOA
    brand can present, something must happen."""
    cases = [
        (["Default"], True), (["Default"], False),
        (["Other"], True), (["Other"], False),
        ([], True), ([], False),
    ]
    for envs, onboarding in cases:
        app = _app(*envs)
        app.vault = None
        app.name = None
        win = _run(
            monkeypatch, app, _brand("Default", onboarding_enabled=onboarding)
        )
        acted = (
            win.open_vault_targeted.called
            or win._show_first_run_setup.called
            or win._run_default_bootstrap.called
        )
        assert acted, f"no branch fired for envs={envs} onboarding={onboarding}"
