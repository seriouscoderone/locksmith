from keri_assistant.intent import ResolvedIntent
from keri_assistant.seams import Preview, DispatchResult, AuditEvent


class FakeConfirmer:
    def __init__(self, answer: bool):
        self.answer = answer
        self.previews: list[Preview] = []

    def confirm(self, preview: Preview) -> bool:
        self.previews.append(preview)
        return self.answer


class RecordingDispatcher:
    def __init__(self, ok: bool = True):
        self._ok = ok
        self.dispatched: list[ResolvedIntent] = []

    def dispatch(self, intent: ResolvedIntent) -> DispatchResult:
        self.dispatched.append(intent)
        return DispatchResult(ok=self._ok)


class RecordingAudit:
    def __init__(self):
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)
