"""The loop and the tool registry must work on the real corpus, not just fixtures."""
import json
import pathlib

from keri_assistant.audit_schema import unconstrained_entity_fields
from keri_assistant.decide import ANSWER, CALL_TOOL, build_decide_schema
from keri_assistant.grounding import Grounding
from keri_assistant.loop import AgentLoop
from keri_assistant.role import RoleContext
from keri_assistant.surface import build_micro_app_surface
from keri_assistant.tools import ToolResult, ToolSpec, build_tool_registry
from tests.fakes import RecordingToolExecutor, ScriptedBinding

REAL = pathlib.Path(__file__).parent / "fixtures" / "real"
CARRIER = json.loads((REAL / "regulator_grants_carrier_license.json").read_text())
ACTUARY_T = json.loads((REAL / "actuary_attests_product_rating.json").read_text())
DOI = "EDoi000000000000000000000000000000000000000"
G = Grounding(known_aids=frozenset({DOI}), allowed_schema_saids=frozenset())

PARSER = ToolSpec(id="doc-parse", kind="compute", description="parse a source document",
               input_schema={"type": "object", "additionalProperties": False,
                             "required": ["path"], "properties": {"path": {"type": "string"}}},
               tags=frozenset({"parsing"}))
ACTUARY_ROLE = RoleContext(role_id="actuary", display_name="Actuary",
                           responsibility="attest product rating",
                           goal_hint="produce and attest rate tables",
                           tool_tags=frozenset({"parsing"}))


def test_carrier_projections_become_read_tools():
    reg = build_tool_registry(build_micro_app_surface(CARRIER))
    assert set(reg.ids()) == {"pending_applications", "active_licenses_in_state"}


def test_no_carrier_command_becomes_a_tool():
    surf = build_micro_app_surface(CARRIER)
    exchange = {v.id for v in surf.verbs if v.kind == "exchange"}
    assert exchange and not (exchange & set(build_tool_registry(surf).ids()))


def test_actuary_registry_admits_the_ipd_workbench_tool_under_its_purpose():
    reg = build_tool_registry(build_micro_app_surface(ACTUARY_T), compute=(PARSER,), role=ACTUARY_ROLE)
    assert "doc-parse" in reg.ids()


def test_decide_schema_compiles_over_the_real_actuary_registry():
    reg = build_tool_registry(build_micro_app_surface(ACTUARY_T), compute=(PARSER,), role=ACTUARY_ROLE)
    schema = build_decide_schema(reg)
    tool_alt = schema["oneOf"][0]
    assert tool_alt["properties"]["action"]["const"] == CALL_TOOL
    assert set(tool_alt["properties"]["tool_id"]["enum"]) == set(reg.ids())


def test_a_full_loop_runs_a_workbench_tool_then_answers_on_the_real_actuary_template():
    surf = build_micro_app_surface(ACTUARY_T)
    reg = build_tool_registry(surf, compute=(PARSER,), role=ACTUARY_ROLE)
    ex = RecordingToolExecutor({"doc-parse": ToolResult(tool_id="doc-parse", ok=True,
                                                        content="parsed 3 shards")})
    b = ScriptedBinding([{"action": CALL_TOOL, "tool_id": "doc-parse"},
                         {"path": "/tmp/rates.xlsx"},
                         {"action": ANSWER, "text": "parsed 3 shards"}])
    out = AgentLoop(binding=b, surface=surf, grounding=G, registry=reg, executor=ex,
                    role=ACTUARY_ROLE).run("parse the rate workbook")
    assert out.status == "answer"
    assert ex.calls == [("doc-parse", {"path": "/tmp/rates.xlsx"})]
    assert out.state.observations[0].startswith("[tool:doc-parse]")


def test_the_application_id_gap_is_REPORTED_on_the_real_regulator_template():
    # the live defect from 2A's review: required, free string, documented as a SAID by the template
    found = unconstrained_entity_fields(build_micro_app_surface(CARRIER), G)
    assert ("grant_license", "application_id") in found


def test_the_report_is_non_empty_on_the_real_corpus_so_review_has_something_to_read():
    for tmpl in (CARRIER, ACTUARY_T):
        assert unconstrained_entity_fields(build_micro_app_surface(tmpl), G)
