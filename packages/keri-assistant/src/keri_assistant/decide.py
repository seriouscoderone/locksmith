"""Pass 1 of the two-pass loop: DECIDE what to do next — never how to shape it (spec 4.2).

The reported "constraint tax" / tool-suppression effect (spec 9.8, unreproduced) is specifically
about a single grammar-constrained decode being asked to BOTH choose an action AND emit
perfectly-shaped arguments: output stays schema-compliant while the model quietly stops calling
tools at all. This schema therefore carries a choice and nothing else — no tool arguments, no command
parameters. Pass 2 shapes the chosen thing, and only pass 2 carries the
ungrounded-value-is-impossible guarantee.

`build_decide_schema` is one function on purpose: swapping in a different decide strategy (e.g. free
text plus parsing) is then a substitution behind a seam rather than a rewrite. 2D's eval gate decides
empirically, by tracking tool-call RATE and not merely accuracy.
"""
from __future__ import annotations

from dataclasses import dataclass

from .actionschema import MAX_TEXT
from .proposal import GrammarViolation
from .tools import ToolRegistry

CALL_TOOL = "call_tool"
PROPOSE = "propose"
ANSWER = "answer"


@dataclass(frozen=True)
class Decision:
    action: str
    tool_id: str | None = None
    text: str = ""


def _alt(action: str, extra: dict | None = None) -> dict:
    props: dict = {"action": {"const": action}}
    required = ["action"]
    for name, sub in (extra or {}).items():
        props[name] = sub
        required.append(name)
    return {"type": "object", "properties": props, "required": required,
            "additionalProperties": False}


def build_decide_schema(registry: ToolRegistry) -> dict:
    alternatives: list[dict] = []
    tool_ids = list(registry.ids())
    if tool_ids:
        # omit rather than emit an empty enum — an empty enum is unsatisfiable and may break
        # grammar compilation, exactly as in build_proposal_schema
        alternatives.append(_alt(CALL_TOOL, {"tool_id": {"enum": tool_ids}}))
    alternatives.append(_alt(PROPOSE))
    alternatives.append(_alt(ANSWER, {"text": {"type": "string", "minLength": 1,
                                               "maxLength": MAX_TEXT}}))
    return {"oneOf": alternatives}


def parse_decision(raw: dict, registry: ToolRegistry) -> Decision:
    action = raw.get("action")
    if action not in (CALL_TOOL, PROPOSE, ANSWER):
        raise GrammarViolation(f"decision names an unknown action: {action!r}")

    if action == CALL_TOOL:
        tool_id = raw.get("tool_id")
        if not isinstance(tool_id, str) or registry.by_id(tool_id) is None:
            raise GrammarViolation(f"decision names an unregistered tool: {tool_id!r}")
        return Decision(action=CALL_TOOL, tool_id=tool_id)

    if action == ANSWER:
        text = raw.get("text")
        if not isinstance(text, str) or not text:
            raise GrammarViolation("answer decision carries no text")
        return Decision(action=ANSWER, text=text)

    return Decision(action=PROPOSE)
