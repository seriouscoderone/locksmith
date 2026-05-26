from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QWidget

from locksmith.ui.vault.identifiers import create as create_module
from locksmith.ui.vault.identifiers.create import CreateIdentifierDialog


VALID_NON_TRANSFERABLE = "B" + "A" * 43  # 44-char base64url
VALID_TRANSFERABLE = "E" + "A" * 43
UNRESOLVED_AID = "B" + "B" * 43
INVALID_AID = "not-an-aid"


def _kever(transferable):
    return SimpleNamespace(transferable=transferable)


@pytest.fixture
def dialog(qapp):
    parent = QWidget()
    parent.resize(1024, 768)

    kevers = {
        VALID_NON_TRANSFERABLE: _kever(False),
        VALID_TRANSFERABLE: _kever(True),
    }

    # Omit `signals` entirely; the dialog gates on hasattr and will skip the
    # signal-bridge connect path when absent.
    app = SimpleNamespace(
        vault=SimpleNamespace(
            hby=SimpleNamespace(kevers=kevers),
        ),
    )

    dlg = CreateIdentifierDialog(
        icon_path=":/assets/material-icons/add.svg",
        app=app,
        parent=parent,
        config=SimpleNamespace(),
    )
    dlg.name_field.setText("alias-1")
    yield dlg
    dlg.close()
    parent.close()


def _set_witnesses(dialog, items):
    """Drive the underlying list widget via its public get_items contract."""
    # The widget's public surface includes get_items; the simplest reliable way
    # to seed it from a test is to monkey-patch get_items for the duration.
    dialog.witnesses_list.get_items = lambda: list(items)


def test_invalid_aid_format_rejected(dialog):
    _set_witnesses(dialog, [INVALID_AID])
    with patch.object(create_module, "habbing") as habbing, \
         patch.object(dialog, "show_error") as show_error:
        dialog.create_identifier()
    habbing.create_identifier.assert_not_called()
    assert show_error.called
    assert "not a valid 44-char AID prefix" in show_error.call_args.args[0]


def test_unresolved_aid_rejected(dialog):
    _set_witnesses(dialog, [UNRESOLVED_AID])
    with patch.object(create_module, "habbing") as habbing, \
         patch.object(dialog, "show_error") as show_error:
        dialog.create_identifier()
    habbing.create_identifier.assert_not_called()
    assert "KEL not resolved" in show_error.call_args.args[0]


def test_transferable_aid_rejected(dialog):
    _set_witnesses(dialog, [VALID_TRANSFERABLE])
    with patch.object(create_module, "habbing") as habbing, \
         patch.object(dialog, "show_error") as show_error:
        dialog.create_identifier()
    habbing.create_identifier.assert_not_called()
    assert "transferable" in show_error.call_args.args[0]


def test_valid_non_transferable_aid_threads_into_params(dialog):
    _set_witnesses(dialog, [VALID_NON_TRANSFERABLE])
    dialog.toad_field.setText("1")
    with patch.object(create_module, "habbing") as habbing:
        habbing.create_identifier.return_value = {"success": True, "message": "ok"}
        dialog.create_identifier()
    habbing.create_identifier.assert_called_once()
    kwargs = habbing.create_identifier.call_args.kwargs
    assert kwargs["wits"] == [VALID_NON_TRANSFERABLE]
    assert kwargs["toad"] == "1"


def test_toad_non_integer_rejected(dialog):
    _set_witnesses(dialog, [VALID_NON_TRANSFERABLE])
    dialog.toad_field.setText("abc")
    with patch.object(create_module, "habbing") as habbing, \
         patch.object(dialog, "show_error") as show_error:
        dialog.create_identifier()
    habbing.create_identifier.assert_not_called()
    assert "integer" in show_error.call_args.args[0]


def test_toad_exceeds_witness_count_rejected(dialog):
    _set_witnesses(dialog, [VALID_NON_TRANSFERABLE])
    dialog.toad_field.setText("2")
    with patch.object(create_module, "habbing") as habbing, \
         patch.object(dialog, "show_error") as show_error:
        dialog.create_identifier()
    habbing.create_identifier.assert_not_called()
    msg = show_error.call_args.args[0]
    assert "cannot exceed the number of witnesses" in msg


def test_toad_negative_rejected(dialog):
    _set_witnesses(dialog, [VALID_NON_TRANSFERABLE])
    dialog.toad_field.setText("-1")
    with patch.object(create_module, "habbing") as habbing, \
         patch.object(dialog, "show_error") as show_error:
        dialog.create_identifier()
    habbing.create_identifier.assert_not_called()
    assert "≥ 0" in show_error.call_args.args[0]
