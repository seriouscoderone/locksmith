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


def test_noop_when_a_vault_already_exists():
    app = MagicMock()
    app.environments.return_value = ["existing"]
    assert bootstrap_default_environment(app, _brand()) is False
    app.open_vault.assert_not_called()


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
      (a) the bootstrap call appears AFTER the on_app_started() call in
          __init__'s source, so plugin discovery + on_app_started run first;
      (b) it's scheduled via QTimer.singleShot rather than called inline;
      (c) it's guarded by brand().default_vault_name so only HOA brands
          opt in and the default Locksmith brand is unaffected.
    """
    from locksmith.ui.window import LocksmithWindow

    source = inspect.getsource(LocksmithWindow.__init__)

    app_started_idx = source.index("on_app_started(")
    boot_idx = source.index("bootstrap_default_environment(")
    assert boot_idx > app_started_idx, (
        "bootstrap_default_environment must be wired after on_app_started()"
    )

    preceding = source[max(0, boot_idx - 400):boot_idx]
    assert "QTimer.singleShot" in preceding, (
        "bootstrap_default_environment must be deferred via QTimer.singleShot, "
        "not invoked inline in __init__"
    )
    assert "default_vault_name" in preceding, (
        "bootstrap_default_environment must be guarded by brand().default_vault_name"
    )
