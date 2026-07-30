"""Grounding constraint-set (Phase-1 direct-lookup form).

The assistant may only address AIDs and reference schema SAIDs that the grounding
actually exposes (from the active template + vault state). It NEVER invents them,
and it NEVER decides authority — that is the recipient's KERI verification. See §5.
"""
from __future__ import annotations

from dataclasses import dataclass

from .intent import ResolvedIntent


@dataclass(frozen=True)
class Grounding:
    known_aids: frozenset[str]
    allowed_schema_saids: frozenset[str]
    known_credential_saids: frozenset[str] = frozenset()


def check_grounded(intent: ResolvedIntent, grounding: Grounding) -> str | None:
    if intent.receiver_aid is not None and intent.receiver_aid not in grounding.known_aids:
        return f"receiver AID {intent.receiver_aid!r} is not a known counterparty"
    if intent.schema_said is not None and intent.schema_said not in grounding.allowed_schema_saids:
        return f"schema SAID {intent.schema_said!r} is not grounded"
    return None
