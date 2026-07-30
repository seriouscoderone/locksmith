"""RoleContext — the PURPOSE layer (design spec 4.0.1).

Role confers two separable things. Authority bounding is NOT one of them here: this assistant never
holds authority to scope, so the compiled surface bounds *capability* and the signature confers
*authority*. What role does confer is ORIENTATION — who am I, what am I responsible for, and which
workbench tools serve that responsibility.

Purpose is deliberately SOFT and must never be described or relied on as a defence: a prompt
injection can redirect it. It earns its place for three other reasons: it decides which tools load at
all, it makes divergence legible at the ceremony (a proposal unrelated to the role's stated
responsibility is visibly wrong to the human reviewing it), and being directed rather than aimless is
a stated product requirement.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RoleContext:
    role_id: str
    display_name: str
    responsibility: str
    goal_hint: str = ""
    tool_tags: frozenset[str] = field(default_factory=frozenset)

    def standing_instruction(self) -> str:
        """The stable instruction prefix. Deterministic — callers rely on byte-identical output
        across calls so a backend can reuse its KV cache for the prefix (rebecca-poc finding)."""
        lines = [
            f"You are the assistant for the {self.display_name} role.",
            f"Your responsibility is: {self.responsibility}.",
        ]
        if self.goal_hint:
            lines.append(f"Everything you are asked to do serves this goal: {self.goal_hint}.")
        lines.append(
            "You may read and compute freely. You do not act with authority: you PROPOSE, "
            "and the human authorizes with a signature."
        )
        return "\n".join(lines)
