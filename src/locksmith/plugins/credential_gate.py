# -*- encoding: utf-8 -*-
"""
locksmith.plugins.credential_gate module

Declarative credential-gate for role-plugins: a plugin declares what
credential unlocks it (``RequiredCredential``), and ``gate_satisfied``
decides whether a held credential set satisfies that gate.

Pure logic only — no KERI I/O, no vault access. Callers are responsible
for supplying already-verified credential state (see ``held_credentials``
shape below).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class RequiredCredential:
    """Declares the credential gate a role-plugin requires.

    ``schema_said`` is the ACDC schema SAID the credential must match.
    ``issuer_aids`` is the set of trusted issuer AIDs (e.g. a DOI). The
    credential's TEL state must equal ``required_state`` (default
    "active").

    ``credential_id`` names the entry in the ecosystem's EGF credential
    catalog (e.g. "actuary_role"). When set, ``resolve_from_egf`` derives
    ``schema_said`` and ``issuer_aids`` from that catalog instead of trusting
    the literals here -- which is what lets a role-plugin serve ANY deployment
    of this framework rather than only the one whose AID is compiled in. The
    literals remain the no-EGF fallback.
    """

    schema_said: str
    issuer_aids: list[str] = field(default_factory=list)
    required_state: str = "active"
    credential_id: str = ""


def resolve_from_egf(req: RequiredCredential, egf_doc,
                     accept_phases=("production",)) -> RequiredCredential:
    """``req`` with its schema and trusted issuers taken from the EGF.

    Returns ``req`` unchanged when it names no catalog entry, when there is no
    EGF, or when the ecosystem does not describe that credential -- a gate must
    never become MORE permissive because governance could not be read.

    Why this exists: the three role-plugins shipped with
    ``issuer_aids=[USURANCE_ADMIN_AID]``, a literal usurance AID in framework
    source. No ecosystem could override it, so the gate answered "was this
    issued by Usurance's operator?" rather than "was this issued by the
    authority MY ecosystem trusts for this role?". The EGF already carries both
    halves: a catalog entry's ``issuer_role``, and the ``authorities`` that
    resolve a role to AIDs within an accepted phase.
    """
    if not req.credential_id or egf_doc is None:
        return req
    try:
        entry = None
        for c in _catalog(egf_doc):
            if getattr(c, "id", None) == req.credential_id:
                entry = c
                break
        if entry is None:
            return req
        aids = [a.aid for a in egf_doc.authorities(
            entry.issuer_role, accept_phases=accept_phases) if a.aid]
        if not aids:
            return req      # a role nobody occupies must not widen the gate
        return replace(req,
                       schema_said=getattr(entry, "schema_said", "") or req.schema_said,
                       issuer_aids=aids)
    except Exception:       # noqa: BLE001 -- an unreadable EGF never opens a gate
        return req


def _catalog(egf_doc):
    """Every credential entry the document declares, however it exposes them."""
    for attr in ("all_credentials", "credentials"):
        got = getattr(egf_doc, attr, None)
        if callable(got):
            return got()
        if got is not None:
            return got
    return getattr(egf_doc, "_credentials", ()) or ()


def gate_satisfied(held_credentials: Any, req: RequiredCredential) -> bool:
    """True iff the holder has >=1 credential that is schema-matched, issued by a
    trusted issuer, in the required TEL state, and fully chain-verified
    (non-escrowed). Pure — no I/O.
    """
    for c in held_credentials:
        if (c.schema_said == req.schema_said
                and c.issuer_aid in req.issuer_aids
                and c.state == req.required_state
                and getattr(c, "chain_verified", False)):
            return True
    return False
