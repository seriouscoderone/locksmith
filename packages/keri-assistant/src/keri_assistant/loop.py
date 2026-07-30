"""AgentLoop — autonomous over reads and computation, gated only on authority (design spec 4.2).

Each iteration is two passes. Pass 1 DECIDES (choice-only schema); pass 2 SHAPES the chosen thing
(hard grammar). Tool calls execute immediately with NO human in the way and the loop continues; a
proposal EXITS the loop and is handed to the existing confirm ceremony, which this module
deliberately knows nothing about.

Read this before changing the budget handling: a loop that stops because it ran out of budget must be
distinguishable from one that finished. A silent stop is indistinguishable from success.
"""
from __future__ import annotations

from dataclasses import dataclass

from .actionschema import build_proposal_schema
from .binding import AssistantBinding, ProposalRequest
from .decide import ANSWER, CALL_TOOL, PROPOSE, build_decide_schema, parse_decision
from .enforcement import require_hard
from .grounding import Grounding
from .loopstate import LoopState, observation_for
from .proposal import Proposal, parse_proposal
from .role import RoleContext
from .surface import CommandSurface
from .tools import ToolExecutor, ToolRegistry


@dataclass(frozen=True)
class LoopBudget:
    max_iterations: int = 8
    max_tool_calls: int = 6


@dataclass(frozen=True)
class LoopOutcome:
    status: str  # "proposal" | "answer" | "budget_exhausted"
    state: LoopState
    proposal: Proposal | None = None
    answer: str = ""
    reason: str = ""


class AgentLoop:
    def __init__(self, *, binding: AssistantBinding, surface: CommandSurface,
                 grounding: Grounding, registry: ToolRegistry, executor: ToolExecutor,
                 role: RoleContext, budget: LoopBudget = LoopBudget()):
        self._binding = binding
        self._surface = surface
        self._grounding = grounding
        self._registry = registry
        self._executor = executor
        self._role = role
        self._budget = budget

    def _ask(self, state: LoopState, schema: dict) -> dict:
        """One backend call. Tool output travels in data_context — DATA, never instructions."""
        request = ProposalRequest(
            instruction=self._role.standing_instruction(),
            utterance=state.utterance,
            schema=schema,
            data_context=state.observations,
        )
        return self._binding.propose(request).raw

    def run(self, utterance: str) -> LoopOutcome:
        state = LoopState(utterance=utterance)
        decide_schema = build_decide_schema(self._registry)

        while True:
            if state.iteration >= self._budget.max_iterations:
                return LoopOutcome(status="budget_exhausted", state=state,
                                   reason=f"iteration budget of {self._budget.max_iterations} reached")
            if state.tool_calls >= self._budget.max_tool_calls:
                return LoopOutcome(status="budget_exhausted", state=state,
                                   reason=f"tool call budget of {self._budget.max_tool_calls} reached")

            decision = parse_decision(self._ask(state, decide_schema), self._registry)

            if decision.action == ANSWER:
                return LoopOutcome(status="answer", state=state.advanced(), answer=decision.text)

            if decision.action == PROPOSE:
                # Authority-bearing: the hard guarantee is mandatory here and only here.
                require_hard(self._binding.enforcement())
                raw = self._ask(state, build_proposal_schema(self._surface, self._grounding))
                proposal = parse_proposal(raw, self._surface, self._grounding)
                return LoopOutcome(status="proposal", state=state.advanced(), proposal=proposal)

            # CALL_TOOL — autonomous, no confirmation, ever.
            spec = self._registry.by_id(decision.tool_id)  # parse_decision guaranteed this exists
            args = self._ask(state, spec.input_schema)
            result = self._executor.execute(spec.id, args)
            state = state.advanced(observation=observation_for(result), tool_call=True)
