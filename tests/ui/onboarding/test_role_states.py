# -*- encoding: utf-8 -*-
"""derive_role_states: per-role status map — the multi-role resolution of
the old app-global derive_state (which short-circuited on the first
LICENSED persona and could not represent ACTIVE(A)+PENDING(B))."""
from dataclasses import dataclass

from keri_serviceaid.egf.documents import CredentialEntry, Onboarding, Role

from locksmith.ui.onboarding.role_states import RoleStatus, derive_role_states

SCHEMA_A = "E" + "A" * 43   # actuary_role
SCHEMA_P = "E" + "P" * 43   # product_designer_role
SCHEMA_FORM_GRANT = "E" + "G" * 43
SCHEMA_FORM_APP = "E" + "F" * 43


@dataclass(frozen=True)
class Held:
    schema_said: str
    issuer_aid: str = "E" + "B" * 43
    state: str = "active"
    chain_verified: bool = True
    said: str = "E" + "C" * 43
    revoked_at: str | None = None


class FakeEgf:
    """Duck-typed EgfDocument over real serviceaid dataclasses."""

    def __init__(self):
        self._roles = [
            Role(id="actuary", display_name="Actuarial", kind="person",
                 description="", onboarding=Onboarding("actuary_role")),
            Role(id="product_designer", display_name="IPD", kind="person",
                 description="",
                 onboarding=Onboarding("product_designer_role")),
            Role(id="carrier_like", display_name="FormMode", kind="organization",
                 description="",
                 onboarding=Onboarding("form_grant", "E" + "M" * 43, "submit")),
        ]
        self._creds = {
            "actuary_role": CredentialEntry(
                id="actuary_role", name="", schema_said=SCHEMA_A,
                issuer_role="admin", holder_role="actuary",
                disclosure_mode="full", chained_from=None, self_issued=False),
            "product_designer_role": CredentialEntry(
                id="product_designer_role", name="", schema_said=SCHEMA_P,
                issuer_role="admin", holder_role="product_designer",
                disclosure_mode="full", chained_from=None, self_issued=False),
            "form_grant": CredentialEntry(
                id="form_grant", name="", schema_said=SCHEMA_FORM_GRANT,
                issuer_role="admin", holder_role="carrier_like",
                disclosure_mode="full", chained_from="form_app",
                self_issued=False),
            "form_app": CredentialEntry(
                id="form_app", name="", schema_said=SCHEMA_FORM_APP,
                issuer_role="carrier_like", holder_role="carrier_like",
                disclosure_mode="full", chained_from=None, self_issued=True),
        }

    def personas(self):
        return [r for r in self._roles if r.onboarding is not None]

    def role(self, role_id):
        """Task 10 addition: ``OnboardingHomePage._on_card_request`` needs
        ``egf.role(role_id)`` to decide apply-mode vs form-mode routing —
        mirrors ``EgfDocument.role``'s own linear-scan shape."""
        return next(r for r in self._roles if r.id == role_id)

    def credential(self, cred_id):
        return self._creds[cred_id]


def _apply(schema_said, dt="2026-07-21T00:00:00+00:00"):
    return {"said": "E" + "S" * 43, "schema_said": schema_said,
            "recipient": "E" + "B" * 43, "message": "", "dt": dt}


def test_all_available_when_nothing_held_or_applied():
    states = derive_role_states([], [], FakeEgf())
    assert states == {"actuary": RoleStatus.AVAILABLE,
                      "product_designer": RoleStatus.AVAILABLE,
                      "carrier_like": RoleStatus.AVAILABLE}


def test_active_plus_pending_coexist():
    """THE #2 boundary case: licensed for A while applying for B."""
    states = derive_role_states([Held(SCHEMA_A)], [_apply(SCHEMA_P)], FakeEgf())
    assert states["actuary"] is RoleStatus.ACTIVE
    assert states["product_designer"] is RoleStatus.PENDING


def test_two_actives_coexist():
    states = derive_role_states([Held(SCHEMA_A), Held(SCHEMA_P)], [], FakeEgf())
    assert states["actuary"] is RoleStatus.ACTIVE
    assert states["product_designer"] is RoleStatus.ACTIVE


def test_revoked_only_that_role():
    held = [Held(SCHEMA_A, state="revoked"), Held(SCHEMA_P)]
    states = derive_role_states(held, [], FakeEgf())
    assert states["actuary"] is RoleStatus.REVOKED
    assert states["product_designer"] is RoleStatus.ACTIVE


def test_active_beats_revoked_for_same_role():
    """Re-granted after an old revoke: an active instance wins."""
    held = [Held(SCHEMA_A, state="revoked"), Held(SCHEMA_A, state="active")]
    assert derive_role_states(held, [], FakeEgf())["actuary"] is RoleStatus.ACTIVE


def test_pending_after_apply_then_active_after_grant():
    egf = FakeEgf()
    assert derive_role_states([], [_apply(SCHEMA_A)], egf)["actuary"] \
        is RoleStatus.PENDING
    assert derive_role_states([Held(SCHEMA_A)], [_apply(SCHEMA_A)], egf)["actuary"] \
        is RoleStatus.ACTIVE


def test_unverified_or_wrongstate_credential_is_not_active():
    assert derive_role_states([Held(SCHEMA_A, chain_verified=False)], [],
                              FakeEgf())["actuary"] is RoleStatus.AVAILABLE
    assert derive_role_states([Held(SCHEMA_A, state="unknown")], [],
                              FakeEgf())["actuary"] is RoleStatus.AVAILABLE


def test_suppress_revoked_enables_per_role_reapply():
    held = [Held(SCHEMA_A, state="revoked")]
    states = derive_role_states(held, [], FakeEgf(),
                                suppress_revoked_roles=frozenset({"actuary"}))
    assert states["actuary"] is RoleStatus.AVAILABLE
    # and with a fresh apply outstanding it shows PENDING, not REVOKED
    states = derive_role_states(held, [_apply(SCHEMA_A)], FakeEgf(),
                                suppress_revoked_roles=frozenset({"actuary"}))
    assert states["actuary"] is RoleStatus.PENDING


def test_form_mode_pending_via_held_application():
    """Carrier-pattern roles stay supported: a held (self-issued) application
    credential marks PENDING even with no sent apply exn."""
    held = [Held(SCHEMA_FORM_APP)]
    assert derive_role_states(held, [], FakeEgf())["carrier_like"] \
        is RoleStatus.PENDING
