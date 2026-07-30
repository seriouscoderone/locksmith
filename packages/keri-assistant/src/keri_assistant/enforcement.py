"""Enforcement strength — whether a backend's output constraint is a guarantee or a hope.

HARD = the sampler could not emit an invalid token (grammar/logit masking): invalid output is
IMPOSSIBLE. SOFT = validate-and-retry: invalid output is possible and merely caught afterwards.
A wallet may not rest an authority-bearing proposal on SOFT. See design spec 8.1.
"""
from __future__ import annotations

from enum import Enum


class EnforcementStrength(str, Enum):
    HARD = "hard"
    SOFT = "soft"


class SoftEnforcementError(RuntimeError):
    """Raised when an authority-bearing proposal would rest on soft enforcement."""


def require_hard(strength: EnforcementStrength) -> None:
    if strength is not EnforcementStrength.HARD:
        raise SoftEnforcementError(
            f"authority-bearing proposals require hard (grammar-level) enforcement; "
            f"binding reported {strength.value!r}"
        )
