# -*- encoding: utf-8 -*-
"""Tests for the issued-credentials list's "Revoke" row action.

The DOI stock wallet's issued-credentials list is the DOI-side trigger for
the live demo's revocation flow. `_on_row_action` previously only logged for
`action == "Revoke"`; this pins that it now resolves the credential + issuer
hab and schedules `make_revoke_doer`'s doer onto `vault.extend`.

`IssuedCredentialsListPage.__init__` requires a real parent widget with a
`.app` and constructs live Qt table widgets, so — mirroring the
`__new__`-bypass pattern used elsewhere in this repo (e.g.
tests/test_keri_v2_compat.py's `LoadSchemaDoer.__new__` construction) — the
page is built via `__new__` and only the attributes `_on_row_action` reads
(`self.app`, `self.parent`) are set directly.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from locksmith.ui.vault.credentials.issued.list import IssuedCredentialsListPage


def _page():
    page = IssuedCredentialsListPage.__new__(IssuedCredentialsListPage)  # bypass Qt init
    hab = MagicMock()
    hab.pre = "EISSUER"
    hab.__class__.__name__ = "Hab"
    hab.kever.wits = []
    creder = MagicMock()
    creder.issuer = "EISSUER"
    vault = SimpleNamespace(
        hby=SimpleNamespace(habs={"EISSUER": hab}),
        rgy=MagicMock(),
        extend=MagicMock(),
    )
    vault.rgy.reger.cloneCred.return_value = (creder, None, None, None)
    page.app = SimpleNamespace(vault=vault)
    page.parent = None
    return page, vault


def test_revoke_action_schedules_revoke_doer():
    page, vault = _page()
    sentinel = object()
    with patch(
        "locksmith.ui.vault.credentials.issued.list.make_revoke_doer",
        return_value=sentinel,
    ) as mk:
        page._on_row_action(
            {"SAID": "ELICENSE", "Schema": "carrier_license", "Issuer": "EISSUER"},
            "Revoke",
        )
    mk.assert_called_once()
    assert mk.call_args.kwargs["credential_said"] == "ELICENSE"
    vault.extend.assert_called_once_with([sentinel])


def test_revoke_action_logs_and_returns_when_credential_not_found():
    page, vault = _page()
    vault.rgy.reger.cloneCred.return_value = (None, None, None, None)
    with patch(
        "locksmith.ui.vault.credentials.issued.list.make_revoke_doer"
    ) as mk:
        page._on_row_action(
            {"SAID": "EMISSING", "Schema": "carrier_license", "Issuer": "EISSUER"},
            "Revoke",
        )
    mk.assert_not_called()
    vault.extend.assert_not_called()


def test_revoke_action_logs_and_returns_when_issuer_hab_not_open():
    page, vault = _page()
    vault.hby.habs.clear()  # issuer hab not open in this wallet
    with patch(
        "locksmith.ui.vault.credentials.issued.list.make_revoke_doer"
    ) as mk:
        page._on_row_action(
            {"SAID": "ELICENSE", "Schema": "carrier_license", "Issuer": "EISSUER"},
            "Revoke",
        )
    mk.assert_not_called()
    vault.extend.assert_not_called()


def test_revoke_action_warns_on_not_implemented_group_hab():
    page, vault = _page()
    with patch(
        "locksmith.ui.vault.credentials.issued.list.make_revoke_doer",
        side_effect=NotImplementedError("GroupHab/witnessed revoke not supported"),
    ) as mk:
        page._on_row_action(
            {"SAID": "ELICENSE", "Schema": "carrier_license", "Issuer": "EISSUER"},
            "Revoke",
        )
    mk.assert_called_once()
    vault.extend.assert_not_called()
