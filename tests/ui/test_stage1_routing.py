# -*- encoding: utf-8 -*-
"""
tests/ui/test_stage1_routing.py

Routing matrix for the serviceaid bridge factories (`make_issue_doer` /
`make_grant_doer`) that stage-1 wallet UI call sites (the credential issue
dialog, the send-grant action) now route through. Complements
`tests/core/test_serviceaid_bridge.py`'s B7 smoke tests (eligible-issue,
GroupHab-issue, eligible-grant, witnessed-grant) with the two combinations
that suite didn't cover: witnessed-issue and GroupHab-grant -- together the
two files exercise all {GroupHab, witnessed} x {issue, grant} legacy-routing
combinations plus the eligible-routes-to-bridge case for each factory.
"""
from unittest.mock import MagicMock

from locksmith.core.serviceaid_bridge import make_grant_doer, make_issue_doer


def _hab(group=False, wits=()):
    h = MagicMock()
    h.__class__.__name__ = "GroupHab" if group else "Hab"
    h.kever.wits = list(wits)
    return h


def test_eligible_routes_to_bridge():
    d = make_issue_doer(MagicMock(), _hab(), schema_said="Es", recipient="Er",
                        attributes={}, registry_name="Es")
    assert type(d).__name__ == "ServiceaidIssueDoer"


def test_witnessed_routes_to_legacy():
    # NOTE: attributes={"a": 1}, not {} as in the task brief's literal
    # snippet -- legacy IssueCredentialDoer.__init__ raises ValueError on a
    # falsy `attributes` dict before it can construct/return, which fails
    # this test for a reason unrelated to routing. tests/core/
    # test_serviceaid_bridge.py's own B7 smoke test for this exact scenario
    # (ineligible hab -> legacy issue doer) uses the same non-empty
    # attributes dict for the same reason.
    d = make_issue_doer(MagicMock(), _hab(wits=["BW" + "X" * 42]), schema_said="Es",
                        recipient="Er", attributes={"a": 1}, registry_name="Es")
    assert type(d).__name__ == "IssueCredentialDoer"


def test_group_grant_routes_to_legacy():
    d = make_grant_doer(MagicMock(), _hab(group=True), credential_said="Ec", recipient="Er")
    assert type(d).__name__ == "SendGrantDoer"
