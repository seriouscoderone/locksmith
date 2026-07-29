"""Never-verbs: routes that must be structurally absent from any assistant surface.

KEL establishment + secret display + (provisionally) IPEX admit. See design spec
Global Constraints and §9.5. This is a STRUCTURAL exclusion, not a runtime authz check.
"""
from __future__ import annotations

import re

NEVER_VERB_TOKENS: frozenset[str] = frozenset({
    "rotate", "rot",
    "delegate", "dip", "drt",
    "revoke", "rev",
    "recover",
    "seed", "passcode",
    "admit",  # spec §9.5 — human-only until reconciled with the KERI-protocol action space
})

_SPLIT = re.compile(r"[/_]+")


def is_never_verb(route: str) -> bool:
    tokens = {t for t in _SPLIT.split(route.lower()) if t}
    return bool(tokens & NEVER_VERB_TOKENS)
