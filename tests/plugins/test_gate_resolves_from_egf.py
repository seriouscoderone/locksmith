# -*- encoding: utf-8 -*-
"""A role gate must trust the ECOSYSTEM's authority, not a compiled-in AID.

All three role-plugins shipped with `issuer_aids=[USURANCE_ADMIN_AID]` — a
literal usurance AID in framework source (actuary/plugin.py:26). No ecosystem
could override it, so the gate asked "was this issued by Usurance's operator?"
rather than "by the authority MY ecosystem trusts for this role?". That makes
the framework undeployable by anyone else, and it is why an HOA spawned against
a test ecosystem still demanded the real admin's credentials.
"""
from dataclasses import dataclass

import pytest

from locksmith.plugins.credential_gate import (
    RequiredCredential, gate_satisfied, resolve_from_egf,
)

REAL = "EGjm-X1JMz-yKFeumEZ9meSVNvnV8VTXmjJMlyBVMMTO"
MINE = "E" + "M" * 43


@dataclass
class _Entry:
    id: str
    schema_said: str
    issuer_role: str


@dataclass
class _Auth:
    role_id: str
    aid: str
    phase: str = "production"


class _Egf:
    def __init__(self, entries, auths):
        self._e, self._a = entries, auths

    def all_credentials(self):
        return self._e

    def authorities(self, role_id, context=None, accept_phases=("production",)):
        return [a for a in self._a
                if a.role_id == role_id and a.phase in tuple(accept_phases)]


def _req():
    return RequiredCredential(schema_said="ESCHEMA", issuer_aids=[REAL],
                              credential_id="actuary_role")


def test_the_gate_is_repointed_at_the_ecosystems_authority():
    egf = _Egf([_Entry("actuary_role", "ESCHEMA", "admin")],
               [_Auth("admin", MINE)])
    out = resolve_from_egf(_req(), egf)

    assert out.issuer_aids == [MINE], (
        "the gate still trusts the compiled-in AID — a different deployment "
        "could never open it")
    assert REAL not in out.issuer_aids


def test_the_schema_comes_from_the_catalog_too():
    egf = _Egf([_Entry("actuary_role", "EOTHERSCHEMA", "admin")],
               [_Auth("admin", MINE)])
    assert resolve_from_egf(_req(), egf).schema_said == "EOTHERSCHEMA"


def test_a_role_nobody_occupies_does_not_widen_the_gate():
    """An issuer_role with no authority in an accepted phase must leave the
    gate as declared, not empty it — an empty issuer set trusts nobody, but
    silently swapping to one hides an ecosystem defect behind a dead gate."""
    egf = _Egf([_Entry("actuary_role", "ESCHEMA", "admin")], [])
    assert resolve_from_egf(_req(), egf).issuer_aids == [REAL]


def test_an_unreadable_egf_never_opens_a_gate():
    class _Boom:
        def all_credentials(self):
            raise RuntimeError("bundle corrupt")

        def authorities(self, *a, **k):
            raise RuntimeError("bundle corrupt")

    assert resolve_from_egf(_req(), _Boom()).issuer_aids == [REAL]
    assert resolve_from_egf(_req(), None).issuer_aids == [REAL]


def test_a_plugin_with_no_catalog_id_is_untouched():
    egf = _Egf([_Entry("actuary_role", "ESCHEMA", "admin")], [_Auth("admin", MINE)])
    bare = RequiredCredential(schema_said="ESCHEMA", issuer_aids=[REAL])
    assert resolve_from_egf(bare, egf) is bare


def test_the_resolved_gate_actually_admits_the_ecosystems_credential():
    """End of the chain: a credential from MY authority opens the gate, and one
    from the shipped authority no longer does."""
    @dataclass
    class _Held:
        schema_said: str
        issuer_aid: str
        state: str = "active"
        chain_verified: bool = True

    egf = _Egf([_Entry("actuary_role", "ESCHEMA", "admin")], [_Auth("admin", MINE)])
    req = resolve_from_egf(_req(), egf)

    assert gate_satisfied([_Held("ESCHEMA", MINE)], req) is True
    assert gate_satisfied([_Held("ESCHEMA", REAL)], req) is False


@pytest.mark.parametrize("plugin_mod,cred_id", [
    ("locksmith.plugins.cuo.plugin", "cuo_role"),
    ("locksmith.plugins.actuary.plugin", "actuary_role"),
    ("locksmith.plugins.product_designer.plugin", "product_designer_role"),
])
def test_every_role_plugin_names_its_catalog_entry(plugin_mod, cred_id):
    """Without a catalog id the plugin can never be re-pointed, and its
    compiled-in AID silently remains the trust root."""
    import importlib

    mod = importlib.import_module(plugin_mod)
    plugin = next(v for v in vars(mod).values()
                  if isinstance(v, type)
                  and getattr(v, "required_credential", None) is not None)
    assert plugin.required_credential.credential_id == cred_id
