"""The product-designer page's readability, state visibility and mint ceremony.

Everything here was found by a three-lens UX panel measuring the built page, and
most of it is a defect rather than a preference: content destroyed with no
recovery path, a control whose state was not visible, and an irreversible mint
with less ceremony than a CRUD delete.
"""
import hashlib
import base64

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget

from locksmith.plugins.product_designer.page import (
    _IDENTIFIER_COLUMNS, _TABLE_HEADERS, ProductDesignerPage, short_said)
from locksmith.ui import colors


def said(seed: str) -> str:
    """A 44-char SAID-shaped value, HASHED not transformed.

    An earlier fixture built these by transforming the seed's characters, so
    "mandate-auto" and "mandate-prop" shared a head AND a tail and three distinct
    mandates all rendered identically in the shortened column. A real SAID is a
    content hash; a fixture that is not makes the screenshot lie.
    """
    digest = hashlib.blake2b(seed.encode(), digest_size=32).digest()
    return "E" + base64.urlsafe_b64encode(digest).decode()[:43]


def _rows():
    """Two programs under one mandate, one under another — the grouping the page
    exists to make visible."""
    spec = [("a-one", "m-auto", "1.0.0", "Publish"),
            ("a-two", "m-auto", "1.1.0", "Publish"),
            ("a-three", "m-prop", "2.0.0", "Sandbox")]
    return {said(a): {"attestation_said": said(a), "issuer": said("actuary"),
                      "mandate_said": said(m), "manifest_said": said(f"man-{a}"),
                      "version": v, "action": r}
            for a, m, v, r in spec}


@pytest.fixture
def page(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    p = ProductDesignerPage(app=None, parent=parent)
    p._received = _rows()
    p._refresh_received_table()
    yield p


def test_a_shortened_said_keeps_both_ends():
    """Head-8 carries the derivation code plus entropy; tail-4 is what lets a
    human eye-match against a value on their clipboard. Right-elision hid the
    tail, which is the half that distinguishes two SAIDs."""
    full = said("something")
    assert len(full) == 44
    short = short_said(full)
    assert short.startswith(full[:8]) and short.endswith(full[-4:])
    assert "…" in short and len(short) < len(full)
    assert short_said("1.0.0") == "1.0.0", "short values are left alone"


def test_two_different_saids_do_not_shorten_to_the_same_string():
    """The guard on the shortener, and on the fixture: distinct content must read
    as distinct."""
    shown = {short_said(r["mandate_said"]) for r in _rows().values()}
    assert len(shown) == 2, f"mandate groups collapsed into {shown}"


def test_every_cell_carries_its_full_value_in_a_tooltip(page):
    """The ONLY recovery path for a truncated value. Every tooltip on this table
    was the empty string, so an elided SAID was simply gone — and `short_said`
    now truncates deliberately, which makes this load-bearing rather than nice."""
    table = page._received_table
    for row in range(table.rowCount()):
        for col in range(table.columnCount()):
            item = table.item(row, col)
            full = page._received[page._row_saids[row]][
                ("attestation_said", "issuer", "mandate_said",
                 "manifest_said", "version", "action")[col]]
            assert item.toolTip() == f"{_TABLE_HEADERS[col]}\n{full}"
            if col in _IDENTIFIER_COLUMNS:
                assert full[:8] in item.toolTip()


def test_identifier_columns_are_monospaced_and_others_are_not(page):
    table = page._received_table
    mono = QFont(page._received_table.item(0, 0).font()).family()
    assert mono, "identifier cells carry no explicit family"
    assert table.item(0, 4).font().family() != mono, (
        "the version column is a short token, not an identifier")


def test_the_table_can_scroll_rather_than_destroying_content(page):
    """`Stretch` for every column fills the viewport exactly, which makes a
    horizontal scrollbar structurally impossible — so a SAID too wide for its
    column had no recovery at any window size."""
    table = page._received_table
    assert table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert table.horizontalHeader().stretchLastSection() is False
    assert table.textElideMode() == Qt.TextElideMode.ElideMiddle
    assert table.verticalHeader().isVisible() is False


def test_the_blocker_speaks_in_every_state(qtbot):
    """It used to early-return HIDDEN when nothing was selected, so the empty
    page showed a live-looking primary above no explanation at all."""
    parent = QWidget()
    qtbot.addWidget(parent)
    empty = ProductDesignerPage(app=None, parent=parent)
    assert empty._assemble_blocker.text(), "the empty page explains nothing"
    assert "actuary" in empty._assemble_blocker.text().lower(), (
        "the wait does not name who the designer is waiting on")

    empty._received = _rows()
    empty._refresh_received_table()
    empty._refresh_assemble_gate()
    assert "select" in empty._assemble_blocker.text().lower()


def test_the_primary_names_the_size_of_the_set(page):
    """Assembly acts on a mandate GROUP; the interface only ever indicated a row.
    Two of these three programs share a mandate."""
    page._on_row_clicked(0, 0)
    assert len(page._programs_for_selected()) == 2
    assert "2 programs" in page._assemble.text(), page._assemble.text()


def test_the_set_is_defined_once(page):
    """The label, the blocker and the mint all read `_programs_for_selected`, so
    they cannot disagree about what is about to be assembled."""
    page._on_row_clicked(0, 0)
    chosen = page._programs_for_selected()
    mandate = page._received[page._selected_said]["mandate_said"]
    assert chosen == sorted(s for s, r in page._received.items()
                            if r["mandate_said"] == mandate)


def test_the_bundle_said_can_leave_the_page(page):
    """The artifact this page exists to mint was not selectable — 44 base64
    characters could only leave the app by being retyped."""
    flags = page._bundle_said.textInteractionFlags()
    assert flags & Qt.TextInteractionFlag.TextSelectableByMouse
    assert page._bundle_copy is not None
    assert page._bundle_copy.isVisible() is False, "no SAID yet, no copy button"


def test_the_retention_column_is_not_called_action(page):
    """`Action` is the slot the suite reserves for row actions; this column
    carries the ACDC's retention value (Publish / Sandbox)."""
    assert "Retention" in _TABLE_HEADERS
    assert "Action" not in _TABLE_HEADERS


def test_the_selection_indicator_does_not_rely_on_fill_alone(page):
    """The token fill computes 1.25:1 on white — under the 3:1 a non-text
    indicator needs. The 3px bar is the compliance."""
    sheet = page._received_table.styleSheet()
    assert "item:selected" in sheet
    assert colors.BACKGROUND_TABLE_ROW_SELECTED.lower() in sheet.lower()
    assert "border-left: 3px solid" in sheet
    assert colors.PRIMARY_HOVER.lower() in sheet.lower()
