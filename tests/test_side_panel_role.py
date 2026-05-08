# -*- encoding: utf-8 -*-
"""Visual + structural smoke test for SidePanel.show_role."""
from __future__ import annotations
from pathlib import Path
import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.ecosystem_viewer.db import RoleRecord
from locksmith.plugins.ecosystem_viewer.side_panel import SidePanel


SHOTS_DIR = Path(__file__).parent / "_screenshots"


def _grab(widget, name):
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOTS_DIR / f"{name}.png"
    pixmap = widget.grab()
    assert pixmap.save(str(path))
    return path


def test_side_panel_show_role_root_with_two_members(qapp):
    panel = SidePanel()
    panel.resize(360, 540)
    role = RoleRecord(
        ecosystem_name="Insurance",
        name="state-doi",
        description="State departments of insurance.",
        qualification_schema_said="ECmEfS_Producer",
        root_issuer_aids=[
            "EBOG_DOI_CA_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "EBOG_DOI_NY_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        ],
    )
    panel.show_role(
        role=role,
        members=[
            "EAID_member_1_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "EAID_member_2_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        ],
        qualification_schema_title="ProducerLicense",
        issuer_role_label=None,
    )
    panel.show()
    QTest.qWait(200)
    qapp.processEvents()

    shot = _grab(panel, "side_panel_role_state_doi_root")
    assert shot.exists()


def test_side_panel_show_role_chained_with_no_members(qapp):
    panel = SidePanel()
    panel.resize(360, 540)
    role = RoleRecord(
        ecosystem_name="Insurance",
        name="producer",
        description="Licensed producers.",
        qualification_schema_said="ECmEfS_License",
        issuer_role_name="state-doi",
        root_issuer_aids=[],
    )
    panel.show_role(
        role=role,
        members=[],
        qualification_schema_title="ProducerLicense",
        issuer_role_label="state-doi",
    )
    panel.show()
    QTest.qWait(200)
    qapp.processEvents()

    shot = _grab(panel, "side_panel_role_producer_chained")
    assert shot.exists()
