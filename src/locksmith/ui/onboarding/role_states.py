# -*- encoding: utf-8 -*-
"""Per-role onboarding status (HOA #4).

Pure derivation — no I/O, no Qt — over three inputs: the gate-shaped held
credentials, the holder's own sent /ipex/apply exns, and the EGF persona
catalog. Replaces the app-global derive_state, whose role-agnostic
first-match LICENSED/REVOKED scans could not represent holding role A while
applying for role B (the #2-flagged multi-role boundary).

TEL vocabulary ("active"/"revoked" from vcState et iss|bis / rev|brv) per
keri:acdc tel-registry; the ACTIVE predicate is exactly the plugin gate's
(schema + state + chain_verified) minus issuer pinning, which the gate owns.
"""
from enum import Enum
from typing import Any, Iterable


class RoleStatus(Enum):
    AVAILABLE = "available"
    PENDING = "pending"
    ACTIVE = "active"
    REVOKED = "revoked"


def _held_matches(held: Iterable[Any], schema_said: str, *, require_active: bool) -> bool:
    """True iff any held-credential view matches ``schema_said`` and is
    chain-verified. When ``require_active`` the view's ``state`` must be
    exactly ``"active"`` (the LICENSED check); otherwise only a
    ``"revoked"`` state disqualifies it (the PENDING check — application
    credentials aren't necessarily TEL-backed the same way a license is,
    so their state vocabulary isn't pinned to "active")."""
    for h in held:
        if h.schema_said != schema_said or not h.chain_verified:
            continue
        if require_active:
            if h.state == "active":
                return True
        else:
            if h.state != "revoked":
                return True
    return False


def _held_revoked(held: Iterable[Any], schema_said: str) -> bool:
    """True iff a chain-verified held credential of ``schema_said`` is in the
    revoked TEL state. Requires chain_verified (same as ``_held_matches``): a
    revoked credential stays in ``reger.saved``, so a genuinely-granted-then-
    revoked license still reads chain_verified=True — only an escrowed, never-
    verified credential fails this, which must NOT read as a revocation."""
    for h in held:
        if h.schema_said == schema_said and h.chain_verified and h.state == "revoked":
            return True
    return False


def derive_role_states(held, sent_applies, egf, *,
                       suppress_revoked_roles=frozenset()):
    """Map every EGF persona to its RoleStatus.

    Per-role precedence: ACTIVE > REVOKED > PENDING > AVAILABLE.
    ``suppress_revoked_roles`` is the per-role re-apply escape hatch (a TEL
    rev never removes the credential, so REVOKED would otherwise be sticky).
    PENDING = an outstanding sent apply for the role's grant schema
    (apply-mode), or a held application credential (form-mode, the
    submitted-application pattern).
    """
    states = {}
    for persona in egf.personas():
        grant = egf.credential(persona.onboarding.grant_credential_id)
        if _held_matches(held, grant.schema_said, require_active=True):
            states[persona.id] = RoleStatus.ACTIVE
        elif (_held_revoked(held, grant.schema_said)
                and persona.id not in suppress_revoked_roles):
            states[persona.id] = RoleStatus.REVOKED
        elif _role_pending(held, sent_applies, egf, grant):
            states[persona.id] = RoleStatus.PENDING
        else:
            states[persona.id] = RoleStatus.AVAILABLE
    return states


def _role_pending(held, sent_applies, egf, grant):
    if any(a.get("schema_said") == grant.schema_said for a in sent_applies):
        return True
    if grant.chained_from is not None:
        application = egf.credential(grant.chained_from)
        return _held_matches(held, application.schema_said,
                             require_active=False)
    return False
