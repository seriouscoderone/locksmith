# -*- encoding: utf-8 -*-
"""Tests for the KERI-native `RevokeCredentialDoer` (HOA #3 credential
revocation, de-leaked from `keri_serviceaid`): revoking an already-issued
credential locally via Locksmith's own `Registrar` + keripy-core
`registry.revoke`/`credentialing.sendArtifacts`, then streaming the updated
TEL + issuer KEL to the holder over Locksmith's existing peer-aware
transport as a RAW TEL update -- NOT an IPEX exn.

Reuses `tests/integration/test_carrier_gate_e2e.py`'s proven, v1-pinned,
in-process issuance recipe (`_make_party`/`_issue`/`_admit`/`_disclose`) to
build a real DOI-issued, carrier_license-shaped credential the DOI itself
still holds in its own `reger` (issuers always retain what they issue,
independent of whether the holder has admitted it) -- so `revoke_env` needs
no admit-side plumbing at all. The "granting-style vault" (`extend`/
`signals`/`hby`/`rgy`/`db`) mirrors `test_exchange_roundtrip_e2e.py`'s
`GrantingVault`: a real `hio` `DoDoer` (real scheduling seam) + a real
`DoerSignalBridge` (real Qt signal), driven by a real virtual-time `Doist`.
"""
from types import SimpleNamespace

import pytest
from hio.base import doing

import locksmith.core.credentialing as credentialing_mod
from locksmith.core.credentialing import RevokeCredentialDoer
from locksmith.core.signals import DoerSignalBridge

from tests.integration.test_carrier_gate_e2e import (  # noqa: F401 (haberies)
    APP_SCHEMA_SAID,
    APPLICATION_ATTRS,
    LICENSE_ATTRS,
    LICENSE_SCHEMA_SAID,
    _admit,
    _disclose,
    _issue,
    _make_party,
    haberies,
)


class CapturePoster:
    instances = []
    def __init__(self, **kwa):
        self.kwa = kwa; self.sent = []; self.last_outcome = None
        CapturePoster.instances.append(self)
    def send(self, serder=None, attachment=None, **kwa):
        self.sent.append((serder, attachment))
    def deliver(self):
        return []


class RevokeVault(doing.DoDoer):
    """The DOI's vault while it REVOKES: the real scheduling seam
    (`extend`), a real Qt signal bridge, and the `hby`/`rgy`/`db` surface
    `RevokeCredentialDoer` reads off `app.vault` -- mirrors
    `test_exchange_roundtrip_e2e.py`'s `GrantingVault`."""

    def __init__(self, hby, rgy):
        self.hby = hby
        self.rgy = rgy
        self.db = None
        self.signals = DoerSignalBridge()
        super().__init__(doers=[], always=True)


def _drive(vault, doer):
    doist = doing.Doist(real=False, tock=0.03125)
    deeds = doist.enter(doers=[vault])
    try:
        vault.extend([doer])
        for _ in range(300):
            if doer.done:
                break
            doist.recur(deeds=deeds)
    finally:
        doist.exit(deeds=deeds)


@pytest.fixture
def revoke_env(qapp, haberies):
    """A DOI-issued, carrier_license-shaped credential the DOI's own `rgy`
    still holds (the issuer's copy), wrapped in a `RevokeVault`.

    Sequence (reuses `test_carrier_gate_e2e`'s recipe verbatim): the carrier
    self-issues + presents a `carrier_license_application`, resolving its KEL
    into the DOI's stores (needed for `Credentialer.create`'s recipient-known
    check); the DOI then issues the `carrier_license` (with its NI2I
    `application` edge) to the carrier. Only the DOI side is needed --
    `RevokeCredentialDoer` runs on the issuer, which always retains what it
    issued regardless of holder admit state.
    """
    hby_c, hab_c, rgy_c = _make_party("t3_revoke_carrier", b"t3_revoke_carrier01")
    haberies.append(hby_c)
    hby_d, hab_d, rgy_d = _make_party("t3_revoke_doi", b"t3_revoke_doi_012345")
    haberies.append(hby_d)

    app_said = _issue(
        hby_c, hab_c, rgy_c, schema_said=APP_SCHEMA_SAID,
        recipient=hab_c.pre, attributes=APPLICATION_ATTRS,
        registry_name="carrier-apps")
    # Presenting the application to the DOI both chain-verifies it DOI-side
    # (needed for the license's NI2I edge target) AND introduces the
    # carrier's KEL into hby_d.kevers (needed to issue TO it at all).
    _admit(hby_d, rgy_d, _disclose(hby_c, rgy_c, app_said))

    license_said = _issue(
        hby_d, hab_d, rgy_d, schema_said=LICENSE_SCHEMA_SAID,
        recipient=hab_c.pre, attributes=LICENSE_ATTRS,
        registry_name="doi-licenses",
        edges={"application": {"cred_said": app_said,
                               "schema_said": APP_SCHEMA_SAID, "op": "NI2I"}})

    vault = RevokeVault(hby_d, rgy_d)
    app = SimpleNamespace(vault=vault)
    return app, hby_d, hab_d, rgy_d, license_said, hab_c.pre


def test_revoke_doer_streams_rev_tel_over_poster(monkeypatch, revoke_env):
    # revoke_env: an issued-and-still-active license held by the DOI hby, with
    # a granting-style vault harness (extend/signals/hby/rgy/db). Recipient =
    # the carrier AID the license was issued to.
    app, hby_d, hab_d, rgy_d, license_said, carrier_pre = revoke_env
    CapturePoster.instances.clear()
    monkeypatch.setattr(credentialing_mod, "PeerAwarePoster", CapturePoster)
    events = []
    app.vault.signals.doer_event.connect(lambda n, t, d: events.append((n, t, d)))

    doer = RevokeCredentialDoer(app, credential_said=license_said)
    _drive(app.vault, doer)

    done = next((d for n, t, d in events
                if n == "RevokeCredentialDoer" and t == "credential_revoked"), None)
    failed = next((d for n, t, d in events
                  if n == "RevokeCredentialDoer" and t == "revoke_failed"), None)
    assert done is not None, f"revoke did not complete; revoke_failed={failed}"
    assert done["success"] is True
    assert done["credential_said"] == license_said
    assert done["recipient"] == carrier_pre
    # The credential's TEL was revoked locally.
    tever = rgy_d.reger.tevers[rgy_d.reger.cloneCred(said=license_said)[0].regid]
    assert tever.vcState(license_said).et in ("rev", "brv")
    # The rev TEL event went onto the wire (sendArtifacts streamed the full TEL).
    assert CapturePoster.instances, "revoke must use the poster seam"
    poster = CapturePoster.instances[-1]
    ilks = [s.ked.get("t") for s, _ in poster.sent if getattr(s, "ked", None)]
    assert "rev" in ilks or "brv" in ilks
