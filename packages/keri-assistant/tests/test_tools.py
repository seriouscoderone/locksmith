import pytest
from keri_assistant.role import RoleContext
from keri_assistant.surface import build_micro_app_surface
from keri_assistant.tools import (
    ToolExecutor, ToolResult, ToolSpec, build_tool_registry, read_tools_from_surface,
)
from tests.fakes import RecordingToolExecutor

TEMPLATE = {
    "commands": [
        {"id": "publish_report", "name": "attest report", "route": "/dom/cmd/publish_report",
         "payload_schema": {"type": "object", "additionalProperties": False, "properties": {}},
         "authz": {"method": "open"}},
    ],
    "projections": [
        {"id": "open_items", "name": "Open items", "display": {"view_type": "table"}},
        {"id": "closed_items", "name": "Closed items", "display": {"view_type": "table"}},
    ],
}
SURF = build_micro_app_surface(TEMPLATE)

PARSER = ToolSpec(id="doc-parse", kind="compute", description="parse a source document",
               input_schema={"type": "object", "additionalProperties": False,
                             "required": ["path"], "properties": {"path": {"type": "string"}}},
               tags=frozenset({"parsing"}))
UNRELATED = ToolSpec(id="other-tool", kind="compute", description="an unrelated capability",
                     input_schema={"type": "object", "additionalProperties": False, "properties": {}},
                     tags=frozenset({"unrelated"}))
PARSING_ROLE = RoleContext(role_id="reporter", display_name="Reporter",
                           responsibility="submit reports", tool_tags=frozenset({"parsing"}))


def test_read_tools_come_from_projections_only():
    specs = read_tools_from_surface(SURF)
    assert {s.id for s in specs} == {"open_items", "closed_items"}
    assert all(s.kind == "read" for s in specs)


def test_exchange_verbs_are_NOT_tools():
    # authority-bearing work is never an autonomous tool — it becomes a proposal
    assert "publish_report" not in {s.id for s in read_tools_from_surface(SURF)}


def test_read_tool_input_schema_is_closed_and_empty():
    # a projection takes no arguments in 2B; an open schema would let the model invent parameters
    spec = read_tools_from_surface(SURF)[0]
    assert spec.input_schema["additionalProperties"] is False
    assert spec.input_schema.get("properties") == {}


def test_registry_unifies_reads_and_computes():
    reg = build_tool_registry(SURF, compute=(PARSER,))
    assert set(reg.ids()) == {"open_items", "closed_items", "doc-parse"}
    assert reg.by_id("doc-parse").kind == "compute"
    assert reg.by_id("open_items").kind == "read"


def test_ids_are_sorted_for_deterministic_grammars():
    reg = build_tool_registry(SURF, compute=(PARSER,))
    assert list(reg.ids()) == sorted(reg.ids())


def test_unknown_tool_id_is_none():
    assert build_tool_registry(SURF).by_id("nope") is None


def test_purpose_filters_compute_tools_by_tag():
    reg = build_tool_registry(SURF, compute=(PARSER, UNRELATED), role=PARSING_ROLE)
    assert "doc-parse" in reg.ids()
    assert "other-tool" not in reg.ids()


def test_purpose_never_filters_out_read_tools():
    # reads are framework state for the role's own surface; purpose narrows workbench tools only
    reg = build_tool_registry(SURF, compute=(PARSER, UNRELATED), role=PARSING_ROLE)
    assert {"open_items", "closed_items"} <= set(reg.ids())


def test_untagged_compute_tool_survives_filtering():
    # an untagged tool is general-purpose, not mis-tagged — do not silently drop it
    plain = ToolSpec(id="validate-schema", kind="compute", description="validate",
                     input_schema={"type": "object", "additionalProperties": False, "properties": {}})
    reg = build_tool_registry(SURF, compute=(plain,), role=PARSING_ROLE)
    assert "validate-schema" in reg.ids()


def test_no_role_means_no_filtering():
    reg = build_tool_registry(SURF, compute=(PARSER, UNRELATED))
    assert {"doc-parse", "other-tool"} <= set(reg.ids())


def test_duplicate_tool_ids_raise():
    dupe = ToolSpec(id="doc-parse", kind="compute", description="other",
                    input_schema={"type": "object", "additionalProperties": False, "properties": {}})
    with pytest.raises(ValueError, match="duplicate tool id"):
        build_tool_registry(SURF, compute=(PARSER, dupe))


def test_a_compute_tool_may_not_shadow_a_read_tool():
    clash = ToolSpec(id="open_items", kind="compute", description="shadow",
                     input_schema={"type": "object", "additionalProperties": False, "properties": {}})
    with pytest.raises(ValueError, match="duplicate tool id"):
        build_tool_registry(SURF, compute=(clash,))


def test_recording_executor_satisfies_the_protocol_and_records():
    ex = RecordingToolExecutor({"doc-parse": ToolResult(tool_id="doc-parse", ok=True, content="42 rows")})
    assert isinstance(ex, ToolExecutor)
    res = ex.execute("doc-parse", {"path": "/tmp/x.xlsx"})
    assert res.ok and res.content == "42 rows"
    assert ex.calls == [("doc-parse", {"path": "/tmp/x.xlsx"})]


def test_recording_executor_defaults_to_a_failure_for_unknown_tools():
    ex = RecordingToolExecutor()
    res = ex.execute("mystery", {})
    assert res.ok is False
    assert "mystery" in res.detail
