# -*- encoding: utf-8 -*-
"""Designer plugin dialog tests."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from locksmith.plugins.designer.dialogs import (
    CreateTemplateDialog, EditHeaderDialog, EditRoleDialog,
)


def test_create_dialog_emits_payload(qapp):
    dlg = CreateTemplateDialog()
    received: list[dict] = []
    dlg.create_requested.connect(lambda d: received.append(d))
    dlg._template_display_name.setText("New Template")
    dlg._template_id.setText("new-template")
    dlg._role_display_name.setText("Homeowner")
    dlg._role_id.setText("homeowner")
    dlg._role_kind.setCurrentText("individual")
    dlg._submit()
    assert received == [{
        "template_display_name": "New Template",
        "template_id": "new-template",
        "role_display_name": "Homeowner",
        "role_id": "homeowner",
        "role_kind": "individual",
    }]


def test_edit_header_dialog_seeds_and_emits(qapp):
    seed = {
        "display_name": "Existing",
        "description": "Desc",
        "version": "1.0",
        "expression_language": "UEL/1.0",
    }
    dlg = EditHeaderDialog(seed=seed)
    received: list[dict] = []
    dlg.save_requested.connect(lambda d: received.append(d))
    assert dlg._display_name.text() == "Existing"
    dlg._display_name.setText("Renamed")
    dlg._submit()
    assert received == [{
        "display_name": "Renamed",
        "description": "Desc",
        "version": "1.0",
        "expression_language": "UEL/1.0",
    }]


def test_edit_role_dialog_seeds_and_emits(qapp):
    seed = {
        "id": "r1",
        "display_name": "Tester",
        "description": "A role",
        "kind": "individual",
        "keri_infrastructure": {
            "witness_pool": False, "watcher_network": True,
            "mailbox": False, "acdc_registry": False,
        },
    }
    dlg = EditRoleDialog(seed=seed)
    received: list[dict] = []
    dlg.save_requested.connect(lambda d: received.append(d))
    dlg._display_name.setText("Regulator")
    dlg._kind.setCurrentText("government")
    dlg._infra_witness_pool.setChecked(True)
    dlg._submit()
    assert received == [{
        "id": "r1",
        "display_name": "Regulator",
        "description": "A role",
        "kind": "government",
        "keri_infrastructure": {
            "witness_pool": True, "watcher_network": True,
            "mailbox": False, "acdc_registry": False,
        },
    }]
