# -*- encoding: utf-8 -*-
"""Visual + structural smoke test for CreateRoleDialog.

Renders the dialog with seed data, asserts the structural state we care
about, and saves a screenshot to tests/_screenshots/ so a vision pass
(human or AI) can verify the actual pixels.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from locksmith.plugins.ecosystem_viewer.dialogs import CreateRoleDialog


SHOTS_DIR = Path(__file__).parent / "_screenshots"


def _grab(widget, name: str) -> Path:
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOTS_DIR / f"{name}.png"
    pixmap = widget.grab()
    assert not pixmap.isNull(), "grab() returned a null pixmap"
    assert pixmap.save(str(path)), f"failed to save pixmap to {path}"
    return path


def _stage(qapp, dlg, width: int = 520, height: int = 820) -> None:
    """Show + size the dialog and let label animations settle.

    The toolkit's FloatingLabelComboBox animates its label up over 200ms
    when an item is selected programmatically; without waiting we'd grab
    the dialog mid-animation with the label sitting on top of the
    selected text.
    """
    dlg.show()
    dlg.resize(width, height)
    qapp.processEvents()
    QTest.qWait(300)  # Let the floating-label animation finish.
    qapp.processEvents()


@pytest.fixture
def seed_data():
    schemas = [
        ("ProducerLicense — ECmEfS_FcGeVLd...", "ECmEfS_FcGeVLdAAA"),
        ("CarrierAppointment — EBOG_LhExAmple...", "EBOG_LhExAmpleBBB"),
    ]
    existing_roles: list[str] = []
    issuer_aids = [
        ("doi-producer-licensing (mine) — EBOGLGeth4OuoE...", "EBOGLGeth4OuoEAAA"),
        ("state-carrier-regulator — ENNN_Ah_FcQoFF...", "ENNN_Ah_FcQoFFBBB"),
        ("third-trust-root — ETHIRD_Trust_Root...", "ETHIRD_TrustRootCCC"),
    ]
    return schemas, existing_roles, issuer_aids


def test_create_role_dialog_renders_readable_form(qapp, seed_data):
    schemas, existing_roles, issuer_aids = seed_data
    dlg = CreateRoleDialog(
        ecosystem_name="Insurance",
        schemas=schemas,
        existing_roles=existing_roles,
        issuer_aids=issuer_aids,
    )
    _stage(qapp, dlg)

    # Structural assertions — what the user complained was "missing".
    assert dlg._schema_combo.combo_box.count() == 2
    assert dlg._schema_combo.currentData() == "ECmEfS_FcGeVLdAAA"
    assert dlg._issuer_role_combo.combo_box.count() == 1  # only the "(root role)" sentinel
    assert dlg._root_aids_list.count() == 3
    assert dlg._root_aids_list.isVisible()
    assert dlg._root_aids_label.isVisible()
    assert dlg._root_aids_list.minimumHeight() >= 160

    # Submit-without-AIDs path: should fail with the trust-root error.
    captured = {}
    dlg.role_create_requested.connect(
        lambda *args: captured.setdefault("emitted", args)
    )
    dlg._name_field.setText("Producer")
    QTest.qWait(250)  # let the line-edit floating label settle
    dlg._on_create()
    assert "emitted" not in captured  # no emit, error banner shown
    QTest.qWait(500)  # let the error-banner expand animation finish
    qapp.processEvents()

    shot = _grab(dlg, "create_role_dialog_root_no_aids_selected")
    assert shot.exists() and shot.stat().st_size > 0
    print(f"[visual] {shot}")


def test_create_role_dialog_with_aids_selected_succeeds(qapp, seed_data):
    schemas, existing_roles, issuer_aids = seed_data
    dlg = CreateRoleDialog(
        ecosystem_name="Insurance",
        schemas=schemas,
        existing_roles=existing_roles,
        issuer_aids=issuer_aids,
    )
    _stage(qapp, dlg)

    dlg._name_field.setText("Producer")
    # Programmatically select the first two AIDs.
    dlg._root_aids_list.item(0).setSelected(True)
    dlg._root_aids_list.item(1).setSelected(True)
    QTest.qWait(250)  # let the line-edit floating label settle
    qapp.processEvents()

    shot = _grab(dlg, "create_role_dialog_two_aids_selected")
    assert shot.exists()
    print(f"[visual] {shot}")

    captured = {}
    dlg.role_create_requested.connect(
        lambda *args: captured.setdefault("emitted", args)
    )
    dlg._on_create()
    assert "emitted" in captured
    eco, name, desc, said, issuer_role, aids = captured["emitted"]
    assert eco == "Insurance"
    assert name == "Producer"
    assert said == "ECmEfS_FcGeVLdAAA"
    assert issuer_role == ""
    assert set(aids) == {"EBOGLGeth4OuoEAAA", "ENNN_Ah_FcQoFFBBB"}


def test_create_role_dialog_chained_role_hides_aids_list(qapp):
    schemas = [("ProducerLicense — ECmEfS...", "ECmEfS_FcGeVLdAAA")]
    existing_roles = ["state-doi"]
    issuer_aids = [("ignored — EIGNORED...", "EIGNORED_AID")]
    dlg = CreateRoleDialog(
        ecosystem_name="Insurance",
        schemas=schemas,
        existing_roles=existing_roles,
        issuer_aids=issuer_aids,
    )
    _stage(qapp, dlg)

    # Pick the chained issuer role (index 1 -> "state-doi")
    dlg._issuer_role_combo.setCurrentIndex(1)
    qapp.processEvents()

    assert not dlg._root_aids_list.isVisible(), \
        "AIDs list should hide when a chained issuer role is chosen"
    assert not dlg._root_aids_label.isVisible()

    shot = _grab(dlg, "create_role_dialog_chained_state_doi")
    assert shot.exists()
    print(f"[visual] {shot}")
