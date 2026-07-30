"""Shared loop fixtures. Lives here (not in a test module) so Tasks 6 and 7 can import it
without coupling test files to each other — same pattern as fixtures/sample_template.py."""
from keri_assistant.grounding import Grounding
from keri_assistant.role import RoleContext
from keri_assistant.surface import build_micro_app_surface
from keri_assistant.tools import ToolSpec, build_tool_registry

COUNTERPARTY = "ECounterparty0000000000000000000000000000000"

TEMPLATE = {
    "commands": [{"id": "submit_report", "name": "submit report", "route": "/dom/cmd/submit_report",
                  "counterparty_role": "reviewer", "authz": {"method": "open"},
                  "payload_schema": {"type": "object", "additionalProperties": False,
                                     "required": ["amount"],
                                     "properties": {"amount": {"type": "number"}}}}],
    "projections": [{"id": "board", "name": "Board", "display": {"view_type": "table"}}],
}
SURF = build_micro_app_surface(TEMPLATE)
G = Grounding(known_aids=frozenset({COUNTERPARTY}), allowed_schema_saids=frozenset())

PARSER_TOOL = ToolSpec(
    id="doc-parse", kind="compute", description="parse a source document",
    input_schema={"type": "object", "additionalProperties": False,
                  "required": ["path"], "properties": {"path": {"type": "string"}}},
    tags=frozenset({"parsing"}),
)
REG = build_tool_registry(SURF, compute=(PARSER_TOOL,))
ROLE = RoleContext(role_id="reporter", display_name="Reporter",
                   responsibility="submit reports", tool_tags=frozenset({"parsing"}))
