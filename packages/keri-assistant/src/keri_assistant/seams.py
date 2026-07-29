"""Host seams — the thin interfaces a display (Locksmith, concierge) implements.

The library owns the harness; the host owns rendering the confirm ceremony, performing
the KERI protocol action (wrapping keripy), and recording the audit trail. See spec §2.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .intent import ResolvedIntent


@dataclass(frozen=True)
class Preview:
    route: str
    verb_id: str
    kind: str
    receiver_aid: str | None
    schema_said: str | None
    payload: dict
    summary: str


@dataclass(frozen=True)
class DispatchResult:
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class AuditEvent:
    proposed_by: str
    authorized_by: str | None
    intent: ResolvedIntent | None
    outcome: str  # "dispatched" | "dispatch_failed" | "rejected" | "refused_ungrounded" | "no_match"


@runtime_checkable
class Confirmer(Protocol):
    def confirm(self, preview: Preview) -> bool: ...


@runtime_checkable
class Dispatcher(Protocol):
    def dispatch(self, intent: ResolvedIntent) -> DispatchResult: ...


@runtime_checkable
class AuditSink(Protocol):
    def record(self, event: AuditEvent) -> None: ...
