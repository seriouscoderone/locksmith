"""Tests for locksmith.core.bootstrapping — first-run default vault + AID.

Brand-gated: only brands with a non-empty ``default_vault_name`` (the
``usurance`` HOA brand) auto-create a vault + witnessless AID on first run.
The default Locksmith brand (``default_vault_name == ""``) must never
bootstrap, and a vault that already exists on disk must never be touched.
"""
import inspect
from unittest.mock import MagicMock

from locksmith.core.bootstrapping import bootstrap_default_environment


def _brand(**over):
    b = MagicMock()
    b.default_vault_name = "Carrier"
    b.default_passcode = ""
    b.default_aid_alias = "carrier"
    b.default_witnesses = []
    b.default_toad = 0
    for k, v in over.items():
        setattr(b, k, v)
    return b


def test_noop_when_the_brands_own_workspace_already_exists():
    """The guard is workspace-scoped: the vault this brand would create is
    already there, so leave it alone (ui/window.py resumes it instead)."""
    app = MagicMock()
    app.environments.return_value = ["Carrier"]
    assert bootstrap_default_environment(app, _brand()) is False
    app.open_vault.assert_not_called()
    app.coordinator.claim.assert_not_called()


def test_bootstraps_even_when_unrelated_vaults_exist(monkeypatch):
    """Regression: the guard used to be ``if app.environments()`` — ANY vault
    on the machine made the HOA believe it was already set up. environments()
    reads a SHARED ~/.keri base, so a vault from another brand (or a test
    vault) suppressed the bootstrap; nothing opened a vault, and the peeled
    build — which has no vault chooser — stranded the user on a blank page.
    """
    app = MagicMock()
    # Exactly the user's disk state: three unrelated vaults, no "Carrier".
    app.environments.return_value = ["Utah State", "usurance-custody", "Other"]

    monkeypatch.setattr(
        "locksmith.core.bootstrapping.open_hby",
        lambda **kw: (MagicMock(), MagicMock()),
    )
    monkeypatch.setattr(
        "locksmith.core.bootstrapping.create_identifier", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "locksmith.core.bootstrapping.remember_workspace_vault", lambda *a, **kw: None
    )

    assert bootstrap_default_environment(app, _brand()) is True
    app.open_vault.assert_called_once()


def test_default_locksmith_brand_never_bootstraps():
    """The bare (non-HOA) Brand() carries default_vault_name == "" and must
    never bootstrap, even on an otherwise-fresh install (empty environments()).
    This is a second, function-internal gate in addition to the ui/window.py
    call-site guard — belt and suspenders for the brand-gating requirement."""
    from locksmith.core.branding import Brand

    app = MagicMock()
    app.environments.return_value = []
    assert bootstrap_default_environment(app, Brand()) is False
    app.open_vault.assert_not_called()
    app.coordinator.claim.assert_not_called()


def test_creates_vault_and_witnessless_aid_on_first_run(monkeypatch):
    app = MagicMock()
    app.environments.return_value = []

    open_calls = {}
    created = {}

    def fake_open_hby(**kw):
        open_calls.update(kw)
        return MagicMock(), MagicMock()

    def fake_create_identifier(app, alias, **kw):
        created.update(alias=alias, toad=kw.get("toad"), wits=kw.get("wits"))

    monkeypatch.setattr("locksmith.core.bootstrapping.open_hby", fake_open_hby)
    monkeypatch.setattr(
        "locksmith.core.bootstrapping.create_identifier", fake_create_identifier
    )

    assert bootstrap_default_environment(app, _brand()) is True

    app.coordinator.claim.assert_called_once_with("Carrier")
    app.open_vault.assert_called_once()
    assert open_calls["name"] == "Carrier"
    assert open_calls["bran"] == ""  # empty default_passcode -> unencrypted vault

    assert created["alias"] == "carrier"
    assert created["toad"] == "0"
    assert created["wits"] == []


def test_nonempty_default_passcode_produces_nonempty_bran(monkeypatch):
    """default_passcode "" -> bran "" (unencrypted). A brand that DOES set a
    passcode must get a real stretched bran, not the empty-string fast path."""
    app = MagicMock()
    app.environments.return_value = []
    open_calls = {}

    def fake_open_hby(**kw):
        open_calls.update(kw)
        return MagicMock(), MagicMock()

    monkeypatch.setattr("locksmith.core.bootstrapping.open_hby", fake_open_hby)
    monkeypatch.setattr(
        "locksmith.core.bootstrapping.create_identifier", lambda *a, **k: None
    )

    bootstrap_default_environment(app, _brand(default_passcode="a-real-passcode"))
    assert open_calls["bran"] != ""


def test_identifier_creation_failure_is_logged_but_still_returns_true(monkeypatch):
    """create_identifier's own internal try/except means it returns a
    {'success': False, ...} dict rather than raising. The vault WAS created
    and opened this run regardless, so bootstrap still reports True — only
    the identifier step failed, and that's logged, not swallowed silently."""
    app = MagicMock()
    app.environments.return_value = []

    monkeypatch.setattr(
        "locksmith.core.bootstrapping.open_hby",
        lambda **kw: (MagicMock(), MagicMock()),
    )
    monkeypatch.setattr(
        "locksmith.core.bootstrapping.create_identifier",
        lambda *a, **k: {"success": False, "message": "boom"},
    )

    assert bootstrap_default_environment(app, _brand()) is True
    app.open_vault.assert_called_once()


def test_claim_denied_does_not_open_vault(monkeypatch):
    """If another process already owns this (freshly-named) vault, bootstrap
    must not call open_hby/open_vault at all."""
    app = MagicMock()
    app.environments.return_value = []
    app.coordinator.claim.return_value = False

    called = {"open": False}

    def fake_open_hby(**kw):
        called["open"] = True
        return MagicMock(), MagicMock()

    monkeypatch.setattr("locksmith.core.bootstrapping.open_hby", fake_open_hby)

    assert bootstrap_default_environment(app, _brand()) is False
    assert called["open"] is False
    app.open_vault.assert_not_called()


def test_open_failure_returns_false_and_releases_claim(monkeypatch):
    """A failure opening the freshly-created vault must release the claim
    and report False rather than raising out of the deferred QTimer slot."""
    app = MagicMock()
    app.environments.return_value = []

    def raise_open(**kw):
        raise RuntimeError("boom")

    monkeypatch.setattr("locksmith.core.bootstrapping.open_hby", raise_open)

    assert bootstrap_default_environment(app, _brand()) is False
    app.open_vault.assert_not_called()
    app.coordinator.release.assert_called_once_with("Carrier")


def test_wired_after_on_app_started_deferred_and_brand_gated():
    """Regression guard for the ui/window.py wiring (source-inspection only —
    constructing a real LocksmithWindow needs a live QApplication + full
    plugin discovery, which is out of scope for a fast/hermetic unit test and
    banned by this host's test-run rules for anything instancing-shaped).

    Verifies:
      (a) the deferred bootstrap slot is scheduled AFTER the
          on_app_started() call in __init__'s source, so plugin discovery +
          on_app_started run first;
      (b) it's scheduled via QTimer.singleShot rather than called inline;
      (c) it's brand-gated so only HOA brands opt in and the default
          Locksmith brand is unaffected;
      (d) ``_run_default_bootstrap`` (factored out so Task 5b's
          True->navigate wiring is unit-testable — see
          ``tests/ui/test_window_bootstrap_nav.py``) calls
          bootstrap_default_environment.

    ``__init__`` now schedules the single ``_resume_or_bootstrap_hoa``
    dispatcher, which picks resume / setup / silent-bootstrap; the silent
    branch reaching ``_run_default_bootstrap`` is asserted there.
    """
    from locksmith.ui.window import LocksmithWindow

    source = inspect.getsource(LocksmithWindow.__init__)

    app_started_idx = source.index("on_app_started(")
    boot_idx = source.index("_resume_or_bootstrap_hoa")
    assert boot_idx > app_started_idx, (
        "the deferred bootstrap slot must be wired after on_app_started()"
    )

    preceding = source[max(0, boot_idx - 400):boot_idx]
    assert "QTimer.singleShot" in preceding, (
        "the bootstrap slot must be deferred via QTimer.singleShot, "
        "not invoked inline in __init__"
    )
    assert "peel_core_pages" in preceding or "default_vault_name" in preceding, (
        "the bootstrap slot must be brand-gated (HOA brands only)"
    )

    dispatch_source = inspect.getsource(LocksmithWindow._resume_or_bootstrap_hoa)
    assert "_run_default_bootstrap" in dispatch_source, (
        "the dispatcher must still reach the silent-bootstrap slot"
    )

    slot_source = inspect.getsource(LocksmithWindow._run_default_bootstrap)
    assert "bootstrap_default_environment(" in slot_source, (
        "_run_default_bootstrap must call bootstrap_default_environment"
    )
