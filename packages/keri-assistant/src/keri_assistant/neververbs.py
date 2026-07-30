"""Never-verbs: routes that must be structurally absent from any assistant surface.

KEL establishment + secret display. See design spec Global Constraints and §9.5. This
is a STRUCTURAL exclusion, not a runtime authz check.
"""
from __future__ import annotations

import re

NEVER_VERB_TOKENS: frozenset[str] = frozenset({
    # The framework floor: operations on the USER'S OWN key material and secrets. No template may
    # opt in — these must be the human's own hands on the primitive. Deliberately NARROW: a domain
    # verb whose NAME merely resembles a KERI operation (a `<verb>_<domain-object>` command, or one
    # whose route carries an IPEX route segment) is legitimate and proposable behind the ceremony.
    # Widening this set by token name silently deletes such commands from the surface, with no
    # error — that regression is what forced the floor to be narrowed. See design spec §9.5.
    "rotate", "rot",
    "delegate", "dip", "drt",
    "recover",
    "seed", "passcode",
})

_SPLIT = re.compile(r"[^a-z0-9]+")


def is_never_verb(route: str, tokens: frozenset[str] = NEVER_VERB_TOKENS) -> bool:
    """True if `route` names a floor operation.

    `tokens` is ADDITIVE: an application/user tier may add restrictions, but cannot remove the
    framework floor — passing a set that omits a floor token does not re-enable that token.
    """
    found = {t for t in _SPLIT.split(route.lower()) if t}
    return bool(found & (NEVER_VERB_TOKENS | tokens))
