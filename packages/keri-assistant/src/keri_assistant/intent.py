"""ResolvedIntent — the inert, grammar-constrained action object the harness emits.

It is NOT CESR, NOT a signed event, NOT a key operation. A trusted host Dispatcher
executes it only after a human confirms. See the design spec, §4.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_KINDS = frozenset({"exchange", "query"})


@dataclass(frozen=True)
class ResolvedIntent:
    route: str
    verb_id: str
    kind: str
    payload: dict = field(default_factory=dict)
    receiver_aid: str | None = None
    schema_said: str | None = None

    def __post_init__(self) -> None:
        if not self.route:
            raise ValueError("route must be a non-empty string")
        if self.kind not in _KINDS:
            raise ValueError(f"kind must be one of {sorted(_KINDS)}, got {self.kind!r}")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")
