# -*- encoding: utf-8 -*-
"""Tests for ``bootstrap_default_environment``'s keyword overrides (Task 4).

These extend Task 5's brand-gated bootstrap (``tests/core/test_bootstrapping.py``,
left untouched as a regression suite) with the parameters the first-run
``SetupPage`` needs: a user-chosen vault name and an explicit (possibly
empty/unencrypted) passcode, both of which must win over the brand's
``[bootstrap]`` defaults.

Distinction that must hold exactly:
  * ``vault_name=None`` (default)              -> use ``brand_cfg.default_vault_name``
  * ``passcode=None``   (default)               -> use ``brand_cfg.default_passcode``
  * ``passcode=""``     (explicit empty string) -> unencrypted vault (``bran=""``),
    even when the brand itself carries a non-empty ``default_passcode``.

Also covers the brand-guard relaxation: the function must bootstrap when
EITHER the brand carries a non-empty ``default_vault_name`` OR the caller
passes a non-empty ``vault_name`` override — an onboarding brand's ``brand.toml``
carries an empty ``default_vault_name`` (the user picks the name at
first-run), so the override alone must be sufficient to pass the guard.
"""
import inspect
from unittest.mock import MagicMock, patch

from locksmith.core.bootstrapping import bootstrap_default_environment


def _brand():
    b = MagicMock()
    b.default_vault_name = "Carrier"
    b.default_passcode = ""
    b.default_aid_alias = "carrier"
    b.default_witnesses = []
    b.default_toad = 0
    return b


@patch("locksmith.core.bootstrapping.create_identifier")
@patch("locksmith.core.bootstrapping.open_hby", return_value=(MagicMock(), MagicMock()))
def test_overrides_win_over_brand(mock_open, _mock_ci):
    app = MagicMock()
    app.environments.return_value = []
    assert bootstrap_default_environment(
        app, _brand(), vault_name="My Workspace", passcode="hunter2!"
    ) is True
    assert mock_open.call_args.kwargs["name"] == "My Workspace"
    assert mock_open.call_args.kwargs["bran"] != ""  # stretched from the user passcode


@patch("locksmith.core.bootstrapping.create_identifier")
@patch("locksmith.core.bootstrapping.open_hby", return_value=(MagicMock(), MagicMock()))
def test_none_means_brand_default_empty_means_unencrypted(mock_open, _mock_ci):
    app = MagicMock()
    app.environments.return_value = []
    bootstrap_default_environment(app, _brand(), passcode="")
    assert mock_open.call_args.kwargs["bran"] == ""


@patch("locksmith.core.bootstrapping.create_identifier")
@patch("locksmith.core.bootstrapping.open_hby", return_value=(MagicMock(), MagicMock()))
def test_vault_name_override_alone_passes_the_brand_guard(mock_open, _mock_ci):
    """A brand with NO default_vault_name (a non-HOA-bootstrap brand.toml, e.g.
    an onboarding brand where the vault name is user-chosen, not baked in)
    must still bootstrap when the caller supplies a vault_name override —
    the guard is EITHER brand default OR override, not brand default alone."""
    app = MagicMock()
    app.environments.return_value = []
    from locksmith.core.branding import Brand

    assert bootstrap_default_environment(
        app, Brand(), vault_name="My Workspace", passcode=""
    ) is True
    assert mock_open.call_args.kwargs["name"] == "My Workspace"


def test_neither_brand_default_nor_override_still_declines():
    """Belt-and-suspenders: with no brand default AND no override, the
    guard must still decline (a plain non-onboarding, non-HOA brand with no
    overrides passed must never bootstrap)."""
    from locksmith.core.branding import Brand

    app = MagicMock()
    app.environments.return_value = []
    assert bootstrap_default_environment(app, Brand()) is False
    app.open_vault.assert_not_called()


def test_onboarding_branch_uses_deferred_setup_page_scheduling():
    """Source-inspection regression guard for the ui/window.py wiring
    (mirrors ``tests/core/test_bootstrapping.py::
    test_wired_after_on_app_started_deferred_and_brand_gated`` — a real
    windowed launch needs a live QApplication + full plugin discovery, out
    of scope for a fast/hermetic unit test and banned by this host's
    test-run rules for anything instancing-shaped).

    Verifies:
      (a) the onboarding first-run branch (``brand().onboarding_enabled``)
          is present and scheduled via ``QTimer.singleShot`` to
          ``_show_first_run_setup`` (not called inline);
      (b) the existing silent-bootstrap ``elif`` branch is untouched:
          still guarded by ``default_vault_name`` and still deferred via
          ``QTimer.singleShot`` to ``_run_default_bootstrap`` — non-onboarding
          brands keep the exact Task 5 behavior;
      (c) both are wired after ``on_app_started()``, same ordering
          discipline as Task 5.

    Both branches now live in the ``_resume_or_bootstrap_hoa`` dispatcher that
    ``__init__`` schedules, so the deferral/ordering is asserted on that single
    scheduling point and the branch structure on the dispatcher's own source.
    """
    from locksmith.ui.window import LocksmithWindow

    source = inspect.getsource(LocksmithWindow.__init__)

    app_started_idx = source.index("on_app_started(")

    dispatch_idx = source.index("_resume_or_bootstrap_hoa")
    assert dispatch_idx > app_started_idx, (
        "the HOA first-run dispatcher must be wired after on_app_started()"
    )
    preceding = source[max(0, dispatch_idx - 400):dispatch_idx]
    assert "QTimer.singleShot" in preceding, (
        "the HOA dispatcher must be deferred via QTimer.singleShot, "
        "not invoked inline in __init__"
    )

    dispatch = inspect.getsource(LocksmithWindow._resume_or_bootstrap_hoa)

    onboarding_idx = dispatch.index("onboarding_enabled")
    setup_idx = dispatch.index("_show_first_run_setup")
    boot_idx = dispatch.index("_run_default_bootstrap")
    assert onboarding_idx < boot_idx, (
        "the onboarding branch must be checked before the silent-bootstrap branch"
    )
    assert "default_vault_name" in dispatch, (
        "the silent-bootstrap branch must stay guarded by brand().default_vault_name"
    )

    # The two creation branches must be mutually exclusive (if/elif), not two
    # independent ifs that could both fire for the same brand.
    between = dispatch[setup_idx:boot_idx]
    assert "elif" in between, (
        "the silent-bootstrap branch must be an elif off the onboarding branch"
    )

    # And neither may fire when the brand's workspace already exists — the
    # resume branch must return before them.
    assert "hoa_workspace_vault(" in dispatch, (
        "the dispatcher must resolve the brand's existing workspace first"
    )
