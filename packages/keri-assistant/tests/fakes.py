from keri_assistant.intent import ResolvedIntent
from keri_assistant.seams import Preview, DispatchResult, AuditEvent
from keri_assistant.binding import ProposalRequest, ProposalResult
from keri_assistant.enforcement import EnforcementStrength
from keri_assistant.tools import ToolResult


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


class FakeBinding:
    def __init__(self, raw: dict, strength: EnforcementStrength = EnforcementStrength.HARD):
        self._raw = raw
        self._strength = strength
        self.requests: list[ProposalRequest] = []

    def enforcement(self) -> EnforcementStrength:
        return self._strength

    def propose(self, request: ProposalRequest) -> ProposalResult:
        self.requests.append(request)
        return ProposalResult(raw=self._raw, enforcement=self._strength)


class RecordingToolExecutor:
    def __init__(self, results: dict[str, ToolResult] | None = None):
        self._results = dict(results or {})
        self.calls: list[tuple[str, dict]] = []

    def execute(self, tool_id: str, args: dict) -> ToolResult:
        self.calls.append((tool_id, dict(args)))
        if tool_id in self._results:
            return self._results[tool_id]
        return ToolResult(tool_id=tool_id, ok=False, content="",
                          detail=f"no fake result configured for {tool_id!r}")
