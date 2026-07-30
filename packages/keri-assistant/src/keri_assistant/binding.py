"""AssistantBinding — the backend-agnostic proposer seam.

It abstracts platform-neutral INTENTS, never backend mechanisms: a standing instruction, an
output-must-match-this-schema constraint, text that is DATA rather than instructions, and
"suppress chain-of-thought". Each concrete binding translates those into its backend's own
mechanism (llama.cpp `json_schema` + `/no_think`, a cloud `response_format`, …) and reports the
ENFORCEMENT STRENGTH it actually achieved, so the harness knows whether it is leaning on a
guarantee or a hope. See design spec 8.1.

Trap for later phases: `ProposalResult.enforcement` is typed `EnforcementStrength`, but a backend
that deserializes a JSON response (e.g. `{"enforcement": "hard"}`) will produce a plain `str` like
`"hard"` instead of the enum member. Such a caller must coerce with `EnforcementStrength(value)`
before passing it to `require_hard` — `require_hard` compares by identity, so a raw string raises
`AttributeError` rather than the declared `SoftEnforcementError`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .enforcement import EnforcementStrength


@dataclass(frozen=True)
class ProposalRequest:
    instruction: str
    utterance: str
    schema: dict
    data_context: tuple[str, ...] = ()
    suppress_reasoning: bool = True


@dataclass(frozen=True)
class ProposalResult:
    raw: dict
    enforcement: EnforcementStrength


@runtime_checkable
class AssistantBinding(Protocol):
    def enforcement(self) -> EnforcementStrength: ...

    def propose(self, request: ProposalRequest) -> ProposalResult: ...
