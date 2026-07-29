"""Assistant — the Phase-1 harness. Matches an utterance to a grounded verb, builds an
inert ResolvedIntent, shows the confirm ceremony, and dispatches ONLY on a human yes.
The model/matcher proposes; the human authorizes; the trusted Dispatcher executes. §4, §7.
"""
from __future__ import annotations

from dataclasses import dataclass

from .grounding import Grounding, check_grounded
from .intent import ResolvedIntent
from .matcher import match
from .neververbs import is_never_verb
from .seams import AuditEvent, AuditSink, Confirmer, Dispatcher, Preview
from .surface import CommandSurface, Verb


@dataclass(frozen=True)
class Outcome:
    status: str  # dispatched | dispatch_failed | rejected | no_match | disambiguation | refused_ungrounded
    intent: ResolvedIntent | None = None
    candidates: tuple[Verb, ...] = ()
    reason: str = ""


def _summary(verb: Verb, receiver_aid: str | None) -> str:
    who = f" to {receiver_aid}" if receiver_aid else ""
    return f"{verb.id} ({verb.route}){who}"


class Assistant:
    def __init__(self, *, surface: CommandSurface, grounding: Grounding,
                 confirmer: Confirmer, dispatcher: Dispatcher, audit: AuditSink,
                 proposed_by: str):
        self._surface = surface
        self._grounding = grounding
        self._confirmer = confirmer
        self._dispatcher = dispatcher
        self._audit = audit
        self._proposed_by = proposed_by

    def _emit(self, outcome: str, intent: ResolvedIntent | None, authorized_by: str | None) -> None:
        self._audit.record(AuditEvent(proposed_by=self._proposed_by, authorized_by=authorized_by,
                                      intent=intent, outcome=outcome))

    def handle(self, utterance: str, *, payload: dict | None = None,
               receiver_aid: str | None = None) -> Outcome:
        m = match(utterance, self._surface)
        if m.verb is None:
            if m.candidates:
                return Outcome(status="disambiguation", candidates=m.candidates)
            self._emit("no_match", None, None)
            return Outcome(status="no_match")

        verb = m.verb
        intent = ResolvedIntent(
            route=verb.route, verb_id=verb.id, kind=verb.kind,
            payload=dict(payload or {}), receiver_aid=receiver_aid, schema_said=verb.schema_said,
        )

        # Defensive invariant — the surface already excluded never-verbs; this must never fire.
        assert not is_never_verb(intent.route), f"never-verb route reached harness: {intent.route}"

        reason = check_grounded(intent, self._grounding)
        if reason is not None:
            self._emit("refused_ungrounded", intent, None)
            return Outcome(status="refused_ungrounded", intent=intent, reason=reason)

        preview = Preview(route=intent.route, verb_id=intent.verb_id, kind=intent.kind,
                          receiver_aid=intent.receiver_aid, schema_said=intent.schema_said,
                          payload=intent.payload, summary=_summary(verb, receiver_aid))

        if self._confirmer.confirm(preview):
            result = self._dispatcher.dispatch(intent)
            if result.ok:
                self._emit("dispatched", intent, "human")
                return Outcome(status="dispatched", intent=intent)
            # Human authorized; execution failed. authorized_by stays "human" —
            # the failure is the dispatcher's, not a lack of authorization.
            self._emit("dispatch_failed", intent, "human")
            return Outcome(status="dispatch_failed", intent=intent, reason=result.detail)

        self._emit("rejected", intent, None)
        return Outcome(status="rejected", intent=intent)
