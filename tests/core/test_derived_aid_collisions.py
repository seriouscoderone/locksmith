"""Two vaults must not mint the same AID.

Salty key creation derives from ``(salt, stem)``: the stem comes from the hab's
alias and the salt, when a call site doesn't pass one, is the keystore's *root*
salt (``keeping.Manager.incept``, ``rooted=True`` -> ``salt = self.salt``). So
"same salt + same alias" is "same key pair", and for a transferable AID that
means two vaults writing two different KELs under one prefix — duplicity, the
failure class KERI exists to prevent.

Every HOA vault uses one alias (the brand's ``default_aid_alias``, "default"),
so the only thing standing between two installs and a colliding identity is the
salt. These tests answer, empirically and per path, whether it does.

They run against real Haberies built with the exact arguments Locksmith passes
(``core/habbing.open_hby``: ``salt=config.salt``) and mint through real
production code. A mock would assert nothing about a derivation.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from keri import kering
from keri.app import habbing
from keri.core import signing

from locksmith.core.bootstrapping import bootstrap_default_environment
from locksmith.core.configing import LocksmithConfig
from locksmith.core.habbing import create_identifier

#: What ``open_hby`` turns ``config.salt`` into for every Locksmith vault. The
#: config default is the hardcoded literal "0123456789abcdef" (configing.py:72)
#: and ``open_hby`` special-cases exactly that string into raw bytes.
LOCKSMITH_ROOT_SALT = signing.Salter(raw=b"0123456789abcdef").qb64

#: The brand's ``default_aid_alias`` for the HOA builds — every install's
#: default identity answers to this one name.
DEFAULT_ALIAS = "default"


def _mint_default_aid(hby, alias, salt):
    """Mint ``alias`` through the real ``create_identifier`` salty branch.

    ``delegation_type="local"`` with no ``delpre`` is the one synchronous branch
    (core/habbing.py:540-560) — the async ``InceptDoer`` path needs a running
    Doist. The derivation under test (``Salter(raw=salt)`` -> ``makeHab``) is the
    same code either way.
    """
    app = MagicMock()
    app.vault.hby = hby
    result = create_identifier(
        app, alias=alias, key_type="salty", salt=salt, delegation_type="local",
    )
    assert result["success"], result["message"]
    return result["pre"]


def _vault(name, bran):
    """A Habery with the arguments ``open_hby`` really passes."""
    return habbing.openHby(
        name=name, temp=True, bran=bran, salt=LOCKSMITH_ROOT_SALT,
        version=kering.Vrsn_1_0,
    )


def _brand(**over):
    b = MagicMock()
    b.default_vault_name = "Workspace"
    b.default_passcode = ""
    b.default_aid_alias = DEFAULT_ALIAS
    b.default_witnesses = []
    b.default_toad = 0
    for k, v in over.items():
        setattr(b, k, v)
    return b


def _bootstrap_capturing_aid_salt(monkeypatch, passcode):
    """Run the real first-run bootstrap; return the salt it minted the AID with.

    The salt is the whole ballgame: whatever ``bootstrap_default_environment``
    hands ``create_identifier`` is what decides whether two installs collide.
    """
    captured = {}
    app = MagicMock()
    app.environments.return_value = []
    monkeypatch.setattr(
        "locksmith.core.bootstrapping.open_hby",
        lambda **kw: (MagicMock(), MagicMock()),
    )
    monkeypatch.setattr(
        "locksmith.core.bootstrapping.remember_workspace_vault", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "locksmith.core.bootstrapping.create_identifier",
        lambda app, alias, key_type="salty", **kw: captured.update(
            salt=kw.get("salt"), alias=alias
        ),
    )
    assert bootstrap_default_environment(app, _brand(default_passcode=passcode)) is True
    return captured


# --------------------------------------------------------------------------
# The two questions the audit had to answer empirically.
# --------------------------------------------------------------------------


def test_two_vaults_with_an_empty_passcode_get_different_default_aids(monkeypatch):
    """Usurance's ``default_passcode`` is "" — an unencrypted vault. An empty
    passcode means an empty ``bran``, so nothing about the *user* varies between
    two installs: same brand, same alias, same hardcoded root salt. If the AID
    salt were derived from any of those, every HOA install on earth would share
    one identity.
    """
    salts = [
        _bootstrap_capturing_aid_salt(monkeypatch, "")["salt"] for _ in range(2)
    ]
    assert salts[0] != salts[1], (
        f"both bootstraps minted the default AID from the same salt {salts[0]!r}"
    )

    pres = []
    for name, salt in zip(("emptyone", "emptytwo"), salts):
        with _vault(name, bran="") as hby:
            pres.append(_mint_default_aid(hby, DEFAULT_ALIAS, salt))
    assert pres[0] != pres[1], (
        f"two empty-passcode vaults minted the same default AID {pres[0]} — "
        f"two KELs under one prefix is duplicity"
    )


def test_two_vaults_sharing_one_passcode_get_different_default_aids(monkeypatch):
    """The written-down-company-passcode scenario: an operator sets up several
    machines from one passcode on a sticky note. Same passcode, same brand, same
    ``default_aid_alias`` — and per keripy the Habery's ``bran`` stretches to the
    keystore's *aeid* (encryption), never to the signing-key salt, so the
    passcode cannot save this. Only a per-install random salt can.
    """
    shared = "A" * 21
    salts = [
        _bootstrap_capturing_aid_salt(monkeypatch, shared)["salt"] for _ in range(2)
    ]
    assert salts[0] != salts[1], (
        f"both bootstraps minted the default AID from the same salt {salts[0]!r}"
    )

    pres = []
    for name, salt in zip(("sharedone", "sharedtwo"), salts):
        with _vault(name, bran=shared) as hby:
            pres.append(_mint_default_aid(hby, DEFAULT_ALIAS, salt))
    assert pres[0] != pres[1], (
        f"two vaults sharing passcode {shared!r} minted the same default AID "
        f"{pres[0]} — two KELs under one prefix is duplicity"
    )


def test_the_default_aid_salt_is_not_derived_from_the_passcode(monkeypatch):
    """A passcode-derived identity would be a *recovery feature* — "type your
    passcode on a new machine, get your AID back" — and Locksmith does not offer
    one. Pin that it doesn't, because the difference is invisible until two
    installs collide: the salt must not be a function of the passcode.
    """
    a = _bootstrap_capturing_aid_salt(monkeypatch, "A" * 21)["salt"]
    b = _bootstrap_capturing_aid_salt(monkeypatch, "A" * 21)["salt"]
    c = _bootstrap_capturing_aid_salt(monkeypatch, "B" * 21)["salt"]
    assert a != b and a != c, (
        "the default AID's salt tracks the passcode — two installs typing the "
        "same passcode would mint the same transferable identity"
    )


# --------------------------------------------------------------------------
# Why the salt has to be passed explicitly: the root salt is shared by every
# vault, so any call site that omits one is derivable from the alias alone.
# --------------------------------------------------------------------------


def test_the_locksmith_root_salt_is_a_hardcoded_constant():
    """``config.salt`` is the literal "0123456789abcdef" (configing.py:72) and
    ``open_hby`` feeds it to every Habery it opens. It is not random and not
    passcode-derived, so it is the *same value in every Locksmith vault on every
    machine* — which is why a hab minted without an explicit salt collides across
    vaults regardless of passcode. The UI's resalt button
    (``defaults_settings_widget``) mutates an in-memory singleton only.
    """
    assert LocksmithConfig().salt == "0123456789abcdef"


def test_a_hab_minted_without_an_explicit_salt_collides_across_vaults():
    """The shape to never ship: ``makeHab(name=alias)`` with no salt.

    Both vaults inherit the hardcoded root salt, so the stem (the alias) is the
    only input left and two independent vaults mint one prefix. This is exactly
    how the peer listener collided (``peer/listener_eid.py``, fixed by minting
    with ``Salter().qb64``). Asserted as *equal* on purpose: this documents the
    hazard, so if keripy's derivation ever stops being deterministic this test
    fails and the rule in
    ``docs/superpowers/specs/2026-07-28-aid-salt-derivation-rule.md`` needs
    revisiting.
    """
    pres = []
    for name in ("rootone", "roottwo"):
        with _vault(name, bran="A" * 21) as hby:
            hab = hby.makeHab(name="shared-alias", version=kering.Vrsn_1_0)
            pres.append(hab.pre)
    assert pres[0] == pres[1], (
        "root-salt derivation is no longer deterministic across vaults — the "
        "documented rule assumes it is"
    )


def test_the_same_vault_name_does_not_save_an_alias_derived_hab():
    """``core/vaulting.py`` names the turret hab ``f"plugin-{hby.name}"``, which
    reads like it varies per vault — it varies per vault *name*. Two machines
    each holding a vault called "Workspace" (a brand default) mint the identical
    prefix.
    """
    pres = []
    for _ in range(2):
        with _vault("Workspace", bran="A" * 21) as hby:
            hab = hby.makeHab(
                name=f"plugin-{hby.name}", ns="settings", version=kering.Vrsn_1_0,
            )
            pres.append(hab.pre)
    assert pres[0] == pres[1], (
        "expected the alias-derived turret hab to collide across same-named vaults"
    )


# --------------------------------------------------------------------------
# Rule 1: infrastructure habs mint with a fresh random salt.
# docs/superpowers/specs/2026-07-28-aid-salt-derivation-rule.md
# --------------------------------------------------------------------------


def test_the_turret_settings_hab_does_not_collide_across_same_named_vaults():
    """The turret's ``ns="settings"`` hab is infrastructure, and its alias is
    ``f"plugin-{hby.name}"`` — so two machines whose vault carries the brand's
    default name used to mint one prefix. Same shape as the peer listener bug.
    """
    from locksmith.core.vaulting import ensure_turret_settings_hab

    pres = []
    for _ in range(2):
        with _vault("Workspace", bran="A" * 21) as hby:
            pres.append(ensure_turret_settings_hab(hby, f"plugin-{hby.name}").pre)
    assert pres[0] != pres[1], (
        f"two same-named vaults minted the same turret settings hab {pres[0]}"
    )


def test_the_turret_settings_hab_is_stable_across_reopens():
    """A random salt must not mean a *new* identifier every launch — the keys
    persist, so re-asking returns the same hab."""
    from locksmith.core.vaulting import ensure_turret_settings_hab

    with _vault("stableturret", bran="A" * 21) as hby:
        first = ensure_turret_settings_hab(hby, "plugin-stableturret")
        second = ensure_turret_settings_hab(hby, "plugin-stableturret")
        assert first.pre == second.pre


def test_the_kf_onboarding_auth_hab_does_not_collide_across_vaults():
    """The hidden onboarding auth principal is infrastructure (``ns=`` non-empty,
    non-transferable). Its alias carries a uuid4 today, so it is unique *by
    accident* — shorten the alias or seed the uuid and two vaults collide, with
    no test failing. The rule wants it safe by construction.
    """
    from locksmith.plugins.kerifoundation.db.basing import KFAccountRecord
    from locksmith.plugins.kerifoundation.onboarding.service import KFOnboardingService

    pres = []
    for name in ("kfone", "kftwo"):
        with _vault(name, bran="A" * 21) as hby:
            app = MagicMock()
            app.vault.hby = hby
            svc = KFOnboardingService(
                app=app, db=MagicMock(), boot_client=MagicMock(),
                witness_registrar=MagicMock(),
            )
            hab, created = svc._load_or_create_onboarding_hab(record=KFAccountRecord())
            assert created is True
            assert hab.kever.prefixer.transferable is False
            pres.append(hab.pre)

    # The uuid4 alias already varies, so this passes either way; what it pins is
    # that the salt is explicit. Verified by mutation: dropping `salt=` from the
    # call site while forcing one alias makes both vaults mint one prefix.
    assert pres[0] != pres[1]


def test_the_kf_onboarding_auth_hab_passes_an_explicit_random_salt():
    """The load-bearing assertion for the site above.

    With the alias held fixed — the thing that varies incidentally — the only
    protection left is the salt. Two vaults must still differ.
    """
    from locksmith.plugins.kerifoundation.db.basing import KFAccountRecord
    from locksmith.plugins.kerifoundation.onboarding.service import KFOnboardingService

    pres = []
    for name in ("kffixedone", "kffixedtwo"):
        with _vault(name, bran="A" * 21) as hby:
            app = MagicMock()
            app.vault.hby = hby
            svc = KFOnboardingService(
                app=app, db=MagicMock(), boot_client=MagicMock(),
                witness_registrar=MagicMock(),
            )
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    "locksmith.plugins.kerifoundation.onboarding.service.uuid4",
                    lambda: MagicMock(hex="deadbeefcafe0000"),
                )
                hab, _ = svc._load_or_create_onboarding_hab(record=KFAccountRecord())
            pres.append(hab.pre)
    assert pres[0] != pres[1], (
        f"with a fixed alias both vaults minted the same hidden auth AID "
        f"{pres[0]} — the call site is relying on the uuid, not on a salt"
    )
