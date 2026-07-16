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

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RequiredCredential:
    """Declares the credential gate a role-plugin requires.

    ``schema_said`` is the ACDC schema SAID the credential must match.
    ``issuer_aids`` is the set of trusted issuer AIDs (e.g. a DOI). The
    credential's TEL state must equal ``required_state`` (default
    "active").
    """

    schema_said: str
    issuer_aids: list[str] = field(default_factory=list)
    required_state: str = "active"


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
