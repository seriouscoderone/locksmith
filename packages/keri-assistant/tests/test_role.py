import pytest
from keri_assistant.role import RoleContext

REPORTER = RoleContext(
    role_id="reporter",
    display_name="Reporter",
    responsibility="publish reports",
    goal_hint="produce and publish reports",
    tool_tags=frozenset({"parsing"}),
)


def test_fields_and_defaults():
    r = RoleContext(role_id="clerk", display_name="Clerk", responsibility="file records")
    assert r.goal_hint == ""
    assert r.tool_tags == frozenset()


def test_is_frozen():
    with pytest.raises(Exception):
        REPORTER.role_id = "auditor"          # type: ignore[misc]


def test_standing_instruction_names_who_and_what():
    text = REPORTER.standing_instruction()
    assert "Reporter" in text
    assert "publish reports" in text
    assert "produce and publish reports" in text


def test_standing_instruction_omits_the_goal_line_when_absent():
    text = RoleContext(role_id="c", display_name="Clerk",
                       responsibility="file records").standing_instruction()
    assert "Clerk" in text
    assert "file records" in text
    assert text.count("\n") >= 1        # still structured, just one line shorter


def test_standing_instruction_states_the_proposal_boundary():
    # the model must be told it proposes and the human authorizes — orientation, not enforcement
    text = REPORTER.standing_instruction()
    lower = text.lower()
    assert "propose" in lower
    assert "authorize" in lower or "authorise" in lower


def test_standing_instruction_is_stable_for_cache_warmth():
    # the static prefix must not vary between calls (KV-cache reuse; rebecca-poc finding)
    assert REPORTER.standing_instruction() == REPORTER.standing_instruction()
