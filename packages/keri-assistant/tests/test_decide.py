import pytest
from keri_assistant.decide import (
    ANSWER, CALL_TOOL, PROPOSE, Decision, build_decide_schema, parse_decision,
)
from keri_assistant.proposal import GrammarViolation
from keri_assistant.surface import build_micro_app_surface
from keri_assistant.tools import ToolSpec, build_tool_registry

TEMPLATE = {
    "commands": [{"id": "attest", "name": "attest", "route": "/ins/cmd/attest",
                  "payload_schema": {"type": "object", "additionalProperties": False, "properties": {}},
                  "authz": {"method": "open"}}],
    "projections": [{"id": "board", "name": "Board", "display": {"view_type": "table"}}],
}
SURF = build_micro_app_surface(TEMPLATE)
PARSER = ToolSpec(id="doc-parse", kind="compute", description="parse",
               input_schema={"type": "object", "additionalProperties": False, "properties": {}})
REG = build_tool_registry(SURF, compute=(PARSER,))
EMPTY = build_tool_registry(build_micro_app_surface({"commands": [], "projections": []}))


def _actions(schema):
    return [a["properties"]["action"]["const"] for a in schema["oneOf"]]


def test_three_alternatives_when_tools_exist():
    assert _actions(build_decide_schema(REG)) == [CALL_TOOL, PROPOSE, ANSWER]


def test_tool_id_is_enum_restricted_to_the_registry():
    alt = build_decide_schema(REG)["oneOf"][0]
    assert alt["properties"]["tool_id"] == {"enum": ["board", "doc-parse"]}
    assert alt["required"] == ["action", "tool_id"]


def test_call_tool_alternative_is_OMITTED_when_no_tools_exist():
    # never an empty enum: the alternative must be absent, not unsatisfiable
    assert _actions(build_decide_schema(EMPTY)) == [PROPOSE, ANSWER]


def test_decide_carries_NO_tool_arguments_or_command_parameters():
    # the whole point of the two-pass split: pass 1 chooses, pass 2 shapes
    for alt in build_decide_schema(REG)["oneOf"]:
        assert set(alt["properties"]) <= {"action", "tool_id", "text"}
        assert "payload" not in alt["properties"]
        assert "args" not in alt["properties"]


def test_every_alternative_forbids_extra_properties():
    for alt in build_decide_schema(REG)["oneOf"]:
        assert alt["additionalProperties"] is False


def test_answer_text_is_length_bounded_and_non_empty():
    alt = build_decide_schema(REG)["oneOf"][2]
    assert alt["properties"]["text"]["maxLength"] == 200
    assert alt["properties"]["text"]["minLength"] == 1


def test_parse_call_tool():
    d = parse_decision({"action": CALL_TOOL, "tool_id": "doc-parse"}, REG)
    assert d == Decision(action=CALL_TOOL, tool_id="doc-parse")


def test_parse_propose():
    assert parse_decision({"action": PROPOSE}, REG) == Decision(action=PROPOSE)


def test_parse_answer():
    d = parse_decision({"action": ANSWER, "text": "42 rows"}, REG)
    assert d == Decision(action=ANSWER, text="42 rows")


def test_unknown_action_is_a_grammar_violation():
    with pytest.raises(GrammarViolation):
        parse_decision({"action": "exfiltrate"}, REG)


def test_missing_action_is_a_grammar_violation():
    with pytest.raises(GrammarViolation):
        parse_decision({}, REG)


def test_call_tool_naming_an_unregistered_tool_is_a_grammar_violation():
    with pytest.raises(GrammarViolation) as exc:
        parse_decision({"action": CALL_TOOL, "tool_id": "rm-rf"}, REG)
    assert "rm-rf" in str(exc.value)


def test_call_tool_without_a_tool_id_is_a_grammar_violation():
    with pytest.raises(GrammarViolation):
        parse_decision({"action": CALL_TOOL}, REG)


def test_empty_answer_text_is_a_grammar_violation():
    # an empty answer is not an answer; matches the escape-hatch minLength rule in actionschema
    with pytest.raises(GrammarViolation):
        parse_decision({"action": ANSWER, "text": ""}, REG)
