"""LoopState — the loop's state as an EXPLICIT, SERIALIZABLE value (design spec 9.13).

The owner requires that an approved plan survive closing and reopening the wallet ("in the name of
being HELPFUL"). That persistence lands in 2C, but it is only possible if the state is a plain value
here: nothing in a closure, nothing in a generator frame, nothing mutated in place. Keeping it a
value also means swapping the loop for a framework later is a substitution behind the seam rather
than a rewrite.

Note the split the spec draws: 2B's loop state need NOT persist (re-running reads is cheap and safe);
2C's signed plan MUST. And resume must re-verify the plan's SAID rather than trust restored state —
restoring an unverified plan is the divergence hole 2C exists to close.
"""
from __future__ import annotations

from dataclasses import dataclass

from .tools import ToolResult


def observation_for(result: ToolResult) -> str:
    """Render a tool result for the model as clearly-marked DATA (spec 4.2 injection posture).

    The `[tool:<id>]` prefix is the marker: this text is an observation, not an instruction. It is
    appended to `ProposalRequest.data_context` and MUST NEVER be concatenated into `instruction`.
    """
    if result.ok:
        return f"[tool:{result.tool_id}] {result.content}"
    return f"[tool:{result.tool_id}] FAILED: {result.detail}"


@dataclass(frozen=True)
class LoopState:
    utterance: str
    iteration: int = 0
    tool_calls: int = 0
    observations: tuple[str, ...] = ()

    def advanced(self, *, observation: str | None = None, tool_call: bool = False) -> LoopState:
        return LoopState(
            utterance=self.utterance,
            iteration=self.iteration + 1,
            tool_calls=self.tool_calls + (1 if tool_call else 0),
            observations=self.observations + ((observation,) if observation is not None else ()),
        )

    def to_dict(self) -> dict:
        return {
            "utterance": self.utterance,
            "iteration": self.iteration,
            "tool_calls": self.tool_calls,
            "observations": list(self.observations),
        }

    @classmethod
    def from_dict(cls, d: dict) -> LoopState:
        return cls(
            utterance=d["utterance"],
            iteration=int(d.get("iteration", 0)),
            tool_calls=int(d.get("tool_calls", 0)),
            observations=tuple(d.get("observations", ())),
        )
