"""Regression test: Remote Identifiers list must render rows even when
some Organizer records are missing ``alias``.

The previous bug — ``rm_id["alias"]`` inside an outer try/except —
would crash on the first aliasless record AND poison every row after
it, since the whole loop was inside one except handler. The user
would see "NO REMOTE IDENTIFIERS" even when the org table held
entries. This is what hid the freshly-added witness during the
witness-rotation walkthrough on 2026-06-01.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def list_page_with_mixed_org_data():
    """Stand up enough of RemoteIdentifierListPage's collaborators to exercise
    _load_remote_identifier_data without instantiating the QWidget.
    """
    from locksmith.ui.vault.remotes import list as remotes_list

    # Three Organizer records — one missing alias (the bug trigger),
    # one with alias and oobi, one with neither.
    org_records = [
        {"id": "BWIT_GOOD", "alias": "kerihost-witness-v2",
         "oobi": "https://witness.keri.host/oobi/BWIT_GOOD/controller"},
        {"id": "BWIT_NOALIAS",
         "oobi": "https://witness.keri.host/oobi/BWIT_NOALIAS/controller"},
        {"id": "EAID_BARE"},
    ]

    kevers = {}
    for r in org_records:
        kev = MagicMock()
        kev.sner = True
        kev.sn = 0
        kev.transferable = False
        kevers[r["id"]] = kev

    hby = SimpleNamespace(
        kevers=kevers,
        db=SimpleNamespace(ends=SimpleNamespace(getTopItemIter=lambda: iter([]))),
    )
    vault = SimpleNamespace(hby=hby, org=SimpleNamespace(list=lambda: org_records))
    app = SimpleNamespace(vault=vault, hby=hby)  # both shapes exist in the wild

    page = remotes_list.RemoteIdentifierListPage.__new__(remotes_list.RemoteIdentifierListPage)
    page.app = app
    page.parent = None
    page.current_identifier_filter = "both"

    captured: list[list[dict]] = []
    page.table = SimpleNamespace(
        set_static_data=lambda data: captured.append(list(data)),
    )
    return page, captured, org_records


def test_aliasless_record_renders_with_safe_fallback(list_page_with_mixed_org_data):
    page, captured, _ = list_page_with_mixed_org_data
    page._load_remote_identifier_data()

    assert captured, "set_static_data must be called"
    rows = captured[-1]
    aliases = {r["Alias"] for r in rows}
    # The aliased one must render with its alias intact.
    assert "kerihost-witness-v2" in aliases
    # The two without aliases must still render — fallback must not crash
    # and must not collapse into a single duplicate row.
    assert len(rows) == 3, (
        f"All 3 org records must surface as rows; got {len(rows)}: {aliases}"
    )


def test_one_bad_row_does_not_blank_the_whole_table(list_page_with_mixed_org_data):
    """The original bug was that ONE missing-alias record poisoned the
    whole loop (outer try/except → empty fallback). Pin the new behavior
    where bad rows fail in isolation."""
    page, captured, _ = list_page_with_mixed_org_data

    # Break one record's kever lookup to simulate a partial-resolve race
    # (KEL was queued for resolution but kevers entry hasn't landed yet).
    del page.app.vault.hby.kevers["BWIT_NOALIAS"]

    page._load_remote_identifier_data()
    rows = captured[-1]
    # The two healthy records still render; the broken one is skipped.
    aliases_or_prefixes = {(r.get("Alias"), r.get("Prefix")) for r in rows}
    pres = {p for _, p in aliases_or_prefixes}
    assert "BWIT_GOOD" in pres
    assert "EAID_BARE" in pres
    # 2 healthy + 1 broken-skipped, NOT 0
    assert len(rows) == 2


def test_uses_bracket_access_so_statedict_disk_fallback_works():
    """Regression for the keripy statedict gotcha that hid the same
    bug twice in a row:

      hby.kevers is a statedict subclass that overrides __getitem__ with
      a read-through cache from db.states — but does NOT override get().
      Bracket access kevers[k] loads from disk on miss; kevers.get(k)
      returns the default without touching disk.

      The original code was bracket access (worked at runtime, but raised
      KeyError on miss which the outer try/except swallowed and blanked
      the table). The first fix used .get() (defensive looking, but
      broke the disk fallback). Final fix: bracket + per-row KeyError.

    This test pins that the loader uses bracket access — if someone
    "tidies" it back to .get(), remote KELs that aren't in-memory will
    silently disappear from the UI after every wallet restart.
    """
    import inspect
    from locksmith.ui.vault.remotes.list import RemoteIdentifierListPage

    src = inspect.getsource(RemoteIdentifierListPage._load_remote_identifier_data)
    assert "kevers[pre]" in src or "kevers[rm_id" in src, (
        "Must use bracket access on hby.kevers to trigger the statedict "
        "read-through cache from db.states. .get() bypasses the cache."
    )
    # And we still want the per-row KeyError isolation.
    assert "except KeyError" in src
