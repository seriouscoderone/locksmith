# ACDC Parties & Lifecycle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the v1 "Parties & lifecycle" placeholder into the full design from `2026-05-07-acdc-parties-lifecycle.md` — split into two cards, add role-decorated sigil glyphs, replace the side-panel text hint with a glyph cell, add a lifecycle glyph to schema graph nodes, and surface known-issuer chips on the schema-detail page.

**Architecture:** All new visuals are painted directly with `QPainter` (no SVG asset commissioning) — same pattern as the existing `DisclosureTierWidget` and `SectionFingerprintWidget`. Inspector gets two new derived `bool` flags; everything else is pure presentation work. Self-issued/self-attested visuals are *strictly instance-level* and stay in the inspector layer until the credential-detail page exists (out of scope here).

**Tech Stack:** PySide6 (Qt) painting via `paintEvent` / `QGraphicsItem.paint()`, pytest with the existing `qapp` fixture in `tests/conftest.py`, no new dependencies.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/locksmith/acdc/inspector.py` | Modify | Add `is_self_issued` + `is_self_attested` derived flags to `ACDCInspection` |
| `tests/test_acdc_inspector.py` | Modify | TDD tests for the two new derived flags (4 cases) |
| `src/locksmith/plugins/ecosystem_viewer/widgets.py` | Modify | New `LifecycleWidget` painted glyph (clockface vs open-arc) — same pattern as `DisclosureTierWidget` |
| `tests/test_lifecycle_widget.py` | Create | Smoke tests using the `qapp` fixture |
| `src/locksmith/plugins/ecosystem_viewer/overview_cards.py` | Modify | Extend `IssuerSigilCircle` with a `role` parameter (None / "from" / "to" / "both") that paints directional ribbons |
| `src/locksmith/plugins/ecosystem_viewer/pages.py` | Modify | Split `_build_parties_lifecycle_card` into `_build_parties_card` + `_build_lifecycle_card`; drop field-name parentheticals; add lifecycle glyph in hero header next to variant glyph; add §7.1 known-issuers chip row to Parties card |
| `src/locksmith/plugins/ecosystem_viewer/side_panel.py` | Modify | Replace text `lifecycle_lbl` with a `LifecycleWidget` cell next to the existing classification glyph row |
| `src/locksmith/plugins/ecosystem_viewer/graph_items.py` | Modify | Add a small painted lifecycle glyph in the bottom-left corner of `SchemaNode.paint()` |
| `src/locksmith/plugins/ecosystem_viewer/README.md` | Modify | Add a one-paragraph note in the spec-vs-convention discipline section calling out `is_self_issued`, `is_self_attested`, and the lifecycle/role names as convention overlays |

---

## Task 1: Inspector — `is_self_issued` and `is_self_attested` flags

**Files:**
- Modify: `src/locksmith/acdc/inspector.py:119-163` (dataclass) and `src/locksmith/acdc/inspector.py:320-336` (constructor call in `inspect_acdc`)
- Test: `tests/test_acdc_inspector.py` (append after the existing instance-test block, before the schema-test block)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_acdc_inspector.py` immediately after `test_inspect_acdc_accepts_legacy_ri_or_spec_rd`:

```python
def test_self_issued_when_targeted_and_issuer_equals_issuee():
    aid = "EAliceAliceAliceAliceAliceAliceAliceAliceAlice"
    a = {
        "d": "EAttribAttribAttribAttribAttribAttribAttrib",
        "i": aid,
        "name": "self",
    }
    i = inspect_acdc(_minimal_acdc(i=aid, a=a))
    assert i.is_self_issued is True
    assert i.is_self_attested is False  # mutually exclusive with self_issued for targeted


def test_targeted_with_distinct_issuer_and_issuee_is_neither():
    a = {
        "d": "EAttribAttribAttribAttribAttribAttribAttrib",
        "i": "EIssueeIssueeIssueeIssueeIssueeIssueeIssuee",
        "name": "Alice",
    }
    i = inspect_acdc(_minimal_acdc(a=a))
    assert i.is_self_issued is False
    assert i.is_self_attested is False


def test_untargeted_acdc_is_self_attested_not_self_issued():
    i = inspect_acdc(_minimal_acdc())
    assert i.is_self_issued is False
    assert i.is_self_attested is True


def test_untargeted_with_compact_attribute_is_still_self_attested():
    i = inspect_acdc(_minimal_acdc(
        a="EAttribSAIDAttribSAIDAttribSAIDAttribSAIDAttribSAID",
    ))
    assert i.is_targeted is False
    assert i.is_self_attested is True
    assert i.is_self_issued is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_acdc_inspector.py::test_self_issued_when_targeted_and_issuer_equals_issuee tests/test_acdc_inspector.py::test_targeted_with_distinct_issuer_and_issuee_is_neither tests/test_acdc_inspector.py::test_untargeted_acdc_is_self_attested_not_self_issued tests/test_acdc_inspector.py::test_untargeted_with_compact_attribute_is_still_self_attested -v`

Expected: all four FAIL with `AttributeError: 'ACDCInspection' object has no attribute 'is_self_issued'` (or similar) — the fields don't exist yet.

- [ ] **Step 3: Add the two fields to ACDCInspection**

In `src/locksmith/acdc/inspector.py`, locate the `ACDCInspection` dataclass (~line 144) and add the two flags immediately after `issuee_aid: str | None`:

```python
    is_targeted: bool
    """True if the attribute block declares an issuee AID (`a.i`)."""
    issuee_aid: str | None
    """Issuee AID if targeted; None otherwise."""

    # --- Self-attestation classification (convention overlay; spec defines
    # neither term as a primitive — both are derived from AID equality and
    # targeting). See docs/superpowers/designs/2026-05-07-acdc-parties-lifecycle.md
    # §2.3 for spec rationale.
    is_self_issued: bool
    """True iff `is_targeted` and `issuer_aid == issuee_aid`. Spec leaves
    this implicit; we name it because the trust posture differs from a
    credential bestowed by another AID."""
    is_self_attested: bool
    """True iff `not is_targeted` (every untargeted ACDC is by construction
    a self-attestation by its issuer — spec §"Untargeted Attribute Section"
    lines 332-334 calls this an undirected verifiable attestation by the
    Issuer). Mutually exclusive with `is_self_issued` for targeted ACDCs."""
```

- [ ] **Step 4: Populate the fields in `inspect_acdc`**

In `src/locksmith/acdc/inspector.py`, locate the `return ACDCInspection(...)` block (~line 320) and update it. Replace:

```python
    return ACDCInspection(
        version_string=version_string,
        said=said,
        issuer_aid=issuer_aid,
        schema_said=schema_said,
        message_type=message_type,
        nonce=nonce,
        registry_said=registry_said,
        is_private=is_private,
        is_targeted=sections.attribute != "absent" and issuee_aid is not None,
        issuee_aid=issuee_aid,
        sections=sections,
        disclosure_tier=disclosure_tier,
        edges=edges,
        rules=rules,
        raw=parsed,
    )
```

With:

```python
    is_targeted = sections.attribute != "absent" and issuee_aid is not None
    is_self_issued = is_targeted and issuee_aid == issuer_aid
    is_self_attested = not is_targeted

    return ACDCInspection(
        version_string=version_string,
        said=said,
        issuer_aid=issuer_aid,
        schema_said=schema_said,
        message_type=message_type,
        nonce=nonce,
        registry_said=registry_said,
        is_private=is_private,
        is_targeted=is_targeted,
        issuee_aid=issuee_aid,
        is_self_issued=is_self_issued,
        is_self_attested=is_self_attested,
        sections=sections,
        disclosure_tier=disclosure_tier,
        edges=edges,
        rules=rules,
        raw=parsed,
    )
```

- [ ] **Step 5: Run all inspector tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_acdc_inspector.py -v`

Expected: all tests pass (including the four new ones plus all pre-existing ones).

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/acdc/inspector.py tests/test_acdc_inspector.py
git commit -m "$(cat <<'EOF'
feat(acdc): inspector exposes is_self_issued + is_self_attested

Per design 2026-05-07-acdc-parties-lifecycle.md §2.3, §3.5, §7.5: two
derived flags on ACDCInspection so credential-detail rendering can
distinguish self-attestations and self-issued credentials without
re-deriving the AID-equality check at every call site. Both are
convention overlays (spec defines neither name as a primitive); flagged
as such in the dataclass docstrings.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: New `LifecycleWidget` painted glyph

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/widgets.py` (append at end)
- Test: `tests/test_lifecycle_widget.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lifecycle_widget.py`:

```python
# -*- encoding: utf-8 -*-
"""Smoke tests for LifecycleWidget — Qt-required, uses the offscreen
QApplication fixture from conftest.py."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QPainter

from locksmith.plugins.ecosystem_viewer.widgets import LifecycleWidget


def test_lifecycle_widget_constructs_in_revocable_state(qapp):
    w = LifecycleWidget(revocable=True)
    assert w.revocable is True
    assert w.sizeHint() == QSize(LifecycleWidget._SIZE, LifecycleWidget._SIZE)


def test_lifecycle_widget_constructs_in_oneshot_state(qapp):
    w = LifecycleWidget(revocable=False)
    assert w.revocable is False


def test_lifecycle_widget_paints_without_crashing(qapp):
    """Render to an offscreen QImage and verify no painter errors."""
    w = LifecycleWidget(revocable=True)
    w.resize(w.sizeHint())
    image = QImage(w.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    w.render(painter)
    painter.end()
    # If we reach here without exception, paint() succeeded.


def test_lifecycle_widget_revocable_setter_updates(qapp):
    w = LifecycleWidget(revocable=False)
    w.revocable = True
    assert w.revocable is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_lifecycle_widget.py -v`

Expected: FAIL with `ImportError: cannot import name 'LifecycleWidget' from 'locksmith.plugins.ecosystem_viewer.widgets'`.

- [ ] **Step 3: Implement `LifecycleWidget` in widgets.py**

Append to `src/locksmith/plugins/ecosystem_viewer/widgets.py`:

```python
# ---------------------------------------------------------------------------
# LifecycleWidget
# ---------------------------------------------------------------------------


class LifecycleWidget(QWidget):
    """Painted glyph for the registry-backed (revocable) vs registryless
    (one-shot) lifecycle axis (design 2026-05-07-acdc-parties-lifecycle §3.2).

    - revocable=True : clockface — circle with a single hand at 12 o'clock.
      Reads as "state can change after issuance." Color teal #0D9488 to
      match the aggregate-section dot from redesign §2.4.
    - revocable=False: open-bottom circle (270° arc) with a center dot.
      Reads as "anchored point, no clockwork." Color TEXT_SECONDARY.

    Painted (not SVG) for the same reason as DisclosureTierWidget — the
    state encodes inspector data and re-tinting at runtime is cleaner via
    QPainter than via QPixmap.SourceIn.
    """

    _SIZE = 18  # default pixel size; callers can resize

    _REVOCABLE_COLOR = "#0D9488"

    def __init__(self, revocable: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._revocable = revocable
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setToolTip(
            "Revocable via TEL" if revocable else "One-shot — no revocation"
        )

    @property
    def revocable(self) -> bool:
        return self._revocable

    @revocable.setter
    def revocable(self, value: bool) -> None:
        if self._revocable != value:
            self._revocable = value
            self.setToolTip(
                "Revocable via TEL" if value else "One-shot — no revocation"
            )
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._SIZE, self._SIZE)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        size = self._SIZE
        margin = 2
        rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)

        if self._revocable:
            color = QColor(self._REVOCABLE_COLOR)
            # Clockface ring
            painter.setPen(QPen(color, 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)
            # Single hand at 12 (vertical from center to top)
            cx = rect.center().x()
            cy = rect.center().y()
            painter.setPen(QPen(color, 1.5))
            painter.drawLine(QPointF(cx, cy), QPointF(cx, rect.top() + 2))
            # Center pivot dot
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(cx - 1, cy - 1, 2, 2))
        else:
            color = QColor(colors.TEXT_SECONDARY)
            # Open-bottom 270° arc — start at -45° (bottom-right) sweeping
            # 270° counter-clockwise to -45°+270° = 225° (bottom-left).
            # QPainter uses 1/16-degree units and CCW positive.
            painter.setPen(QPen(color, 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # Start angle -45° = -45*16, span 270° = 270*16
            painter.drawArc(rect, -45 * 16, 270 * 16)
            # Center anchor dot
            cx = rect.center().x()
            cy = rect.center().y()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(cx - 1.5, cy - 1.5, 3, 3))

        painter.end()
```

Required imports at the top of `widgets.py` are already there (`QRectF`, `QSize`, `Qt`, `QColor`, `QPainter`, `QPen`, `QWidget`) — verify they include `QPointF` from `PySide6.QtCore`. If not, add it to the existing `from PySide6.QtCore import` line.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_lifecycle_widget.py -v`

Expected: 4 passed.

- [ ] **Step 5: Run the full test suite as a regression check**

Run: `.venv/bin/python -m pytest -q`

Expected: all tests pass (no regressions).

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/widgets.py tests/test_lifecycle_widget.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): painted LifecycleWidget — revocable vs one-shot

Clockface (single hand at 12, teal #0D9488) for registry-backed
credentials; open-bottom 270° arc with anchor dot (neutral) for
one-shot. Same painted-from-inspector-state pattern as
DisclosureTierWidget and SectionFingerprintWidget. Per design
2026-05-07-acdc-parties-lifecycle §3.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Role-decorated sigil — extend `IssuerSigilCircle`

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/overview_cards.py` (locate `class IssuerSigilCircle` ~line 380)

- [ ] **Step 1: Read the existing IssuerSigilCircle**

Skim `src/locksmith/plugins/ecosystem_viewer/overview_cards.py` and find `class IssuerSigilCircle(QWidget)` to see the current paint logic and constructor signature. The current class draws a 48px circle with the issuer-sigil pixmap centered.

- [ ] **Step 2: Extend the constructor with a `role` parameter**

In `overview_cards.py`, replace the existing `IssuerSigilCircle.__init__` and `paintEvent` with:

```python
class IssuerSigilCircle(QWidget):
    """Painted 48px circular avatar containing the §2.8 issuer sigil glyph.

    Optional `role` decoration paints small directional ribbons on the
    circle to indicate the AID's role in a specific credential context:
      - "from": ribbon on bottom-right pointing right (issuer / outflow)
      - "to":   ribbon on bottom-left pointing left (issuee / inflow)
      - "both": both ribbons (self-issued — single AID is both parties)
      - None:   no decoration (used in directories where role is undefined)
    Per design 2026-05-07-acdc-parties-lifecycle.md §3.1.
    """

    DIAMETER = ISSUER_AVATAR_DIAMETER

    def __init__(
        self,
        is_self: bool = False,
        role: str | None = None,  # None | "from" | "to" | "both"
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._is_self = is_self
        self._role = role
        # Slightly wider hit area when ribbons attach so they're not clipped.
        extra = 8 if role else 0
        self.setFixedSize(self.DIAMETER + extra, self.DIAMETER)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        sigil_color = colors.PRIMARY if is_self else colors.TEXT_DARK
        self._sigil_px = _load_tinted_pixmap(
            icons.ICON_ISSUER_SIGIL, self.DIAMETER - 16, sigil_color
        )

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Background ring
        ring_color = QColor(colors.PRIMARY) if self._is_self else QColor(colors.BORDER)
        p.setPen(QPen(ring_color, 1.5))
        p.setBrush(QColor(colors.BACKGROUND_CONTENT))
        # Center the circle when ribbons add horizontal padding.
        circle_x = (self.width() - self.DIAMETER) / 2
        p.drawEllipse(QRectF(circle_x + 1, 1, self.DIAMETER - 2, self.DIAMETER - 2))
        # Sigil centered in circle
        if not self._sigil_px.isNull():
            sx = circle_x + (self.DIAMETER - self._sigil_px.width()) / 2
            sy = (self.DIAMETER - self._sigil_px.height()) / 2
            p.drawPixmap(QPointF(sx, sy), self._sigil_px)

        # Role ribbons (small triangles attached to the bottom of the circle)
        if self._role in ("from", "both"):
            self._draw_ribbon(p, side="from", circle_x=circle_x, color=ring_color)
        if self._role in ("to", "both"):
            self._draw_ribbon(p, side="to", circle_x=circle_x, color=ring_color)

        p.end()

    def _draw_ribbon(self, p: QPainter, *, side: str, circle_x: float, color: QColor) -> None:
        """Paint a 6×8 directional triangle ribbon at the bottom of the circle.

        side="from" → right-pointing triangle on bottom-right (outflow).
        side="to"   → left-pointing triangle on bottom-left (inflow).
        """
        from PySide6.QtGui import QPolygonF
        d = self.DIAMETER
        # Anchor near the bottom of the circle.
        anchor_y = d - 6
        if side == "from":
            # Triangle just outside the right edge of the circle, pointing right.
            base_x = circle_x + d - 2
            points = [
                QPointF(base_x, anchor_y),         # base top
                QPointF(base_x, anchor_y + 8),     # base bottom
                QPointF(base_x + 6, anchor_y + 4), # tip pointing right
            ]
        else:  # "to"
            base_x = circle_x + 2
            points = [
                QPointF(base_x, anchor_y),         # base top
                QPointF(base_x, anchor_y + 8),     # base bottom
                QPointF(base_x - 6, anchor_y + 4), # tip pointing left
            ]
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPolygon(QPolygonF(points))
```

This requires `QPointF` in the imports at the top of `overview_cards.py` — verify the existing `from PySide6.QtCore import` line includes it; add if missing.

- [ ] **Step 3: Run the wallet to smoke-test rendering**

Run: `.venv/bin/python -m locksmith.main` (background)

Open the wallet → ecosystem viewer overview → existing issuer cards should still render correctly (role=None preserves prior behavior). Stop the wallet before the next step.

- [ ] **Step 4: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/overview_cards.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): IssuerSigilCircle role decoration ribbons

Adds optional role= parameter ("from" / "to" / "both" / None) to the
existing painted sigil circle. Ribbons paint as small directional
triangles attached to the bottom of the circle: right-pointing for
issuer (from), left-pointing for issuee (to), both for self-issued.
None preserves the prior decoration-free behavior used in the overview
issuer column. Per design 2026-05-07-acdc-parties-lifecycle §3.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Schema-detail page — split Parties from Lifecycle

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/pages.py` — replace `_build_parties_lifecycle_card` (and the existing call site) with two methods

- [ ] **Step 1: Locate the existing single card and call site**

In `src/locksmith/plugins/ecosystem_viewer/pages.py`, find:
- The line `self._content_layout.insertWidget(idx, self._build_parties_lifecycle_card(i)); idx += 1` (around line 626)
- The method `_build_parties_lifecycle_card(self, i: Any)` (around line 902) and its helper `_build_party_row` (around line 988)

- [ ] **Step 2: Replace the call site with two inserts**

Find and replace:

```python
        self._content_layout.insertWidget(idx, self._build_parties_lifecycle_card(i)); idx += 1
```

With:

```python
        self._content_layout.insertWidget(idx, self._build_parties_card(i)); idx += 1
        self._content_layout.insertWidget(idx, self._build_lifecycle_card(i)); idx += 1
```

- [ ] **Step 3: Replace the old card builder with two focused ones**

Find the `_build_parties_lifecycle_card` method (it begins with the docstring `"""Render the issuer (always present) / issuee (a.i)`). Replace the entire method (and keep `_build_party_row` immediately after — it's still used by `_build_lifecycle_card` for the registry row) with:

```python
    def _build_parties_card(self, i: Any) -> QWidget:
        """Schema-level Parties card: the people axis.

        Issuer is always present; issuee depends on whether the schema
        requires targeting (a.i). Per design 2026-05-07-acdc-parties-lifecycle
        §4.2. Sigils render as role placeholders (no specific AID), since
        a schema describes potential credentials, not actual ones."""
        frame = QFrame()
        frame.setObjectName("sdPartiesCard")
        frame.setStyleSheet(
            "QFrame#sdPartiesCard { background-color: white;"
            " border: 1px solid #E0E3EA; border-radius: 8px; }"
            "QFrame#sdPartiesCard QLabel { background: transparent; }"
        )
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        title = QLabel("Parties")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        outer.addWidget(title)

        # Two-column layout: [issuer] | [issuee]
        cols = QHBoxLayout()
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(20)
        cols.setAlignment(Qt.AlignmentFlag.AlignTop)

        cols.addWidget(self._build_party_column(
            role="from",
            heading="Issuer",
            body=(
                "Always present. Every credential of this schema names an "
                "issuer AID. The schema cannot constrain who that is — "
                "that's an ecosystem-governance concern (see "
                "permitted issuers)."
            ),
        ), 1)

        if i.requires_targeted:
            cols.addWidget(self._build_party_column(
                role="to",
                heading="Issuee",
                body=(
                    "Required by this schema — credentials commit to a "
                    "holder AID inside their attribute block. Untargeted "
                    "credentials cannot conform to this schema."
                ),
            ), 1)
        else:
            cols.addWidget(self._build_party_column(
                role=None,  # absent role
                heading="No issuee",
                body=(
                    "This schema declares no issuee — credentials are "
                    "untargeted attestations from the issuer. Any verifier "
                    "can read them by SAID; no specific holder is bound. "
                    "Also called self-attestations."
                ),
                placeholder=True,
            ), 1)

        cols_w = QWidget()
        cols_w.setLayout(cols)
        outer.addWidget(cols_w)

        if i.requires_targeted:
            note = QLabel(
                "ⓘ When the issuer's AID equals the issuee's AID, the "
                "credential is <b>self-issued</b> — a self-attestation by "
                "that AID about itself. (Visible only on actual credentials.)"
            )
            note.setWordWrap(True)
            note.setTextFormat(Qt.TextFormat.RichText)
            note.setStyleSheet(
                f"font-size: 11px; color: {colors.TEXT_SECONDARY}; padding-top: 6px;"
            )
            outer.addWidget(note)

        return frame

    def _build_party_column(
        self,
        role: str | None,
        heading: str,
        body: str,
        placeholder: bool = False,
    ) -> QWidget:
        """One column of the Parties card: sigil placeholder + role label
        + body copy. `placeholder=True` renders a dashed-outline circle
        instead of the sigil, used for the 'No issuee' (untargeted) case."""
        from locksmith.plugins.ecosystem_viewer.overview_cards import (
            IssuerSigilCircle,
        )
        col = QFrame()
        col.setObjectName("sdPartyColumn")
        col.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        col.setStyleSheet(
            "QFrame#sdPartyColumn { background: transparent; }"
            "QFrame#sdPartyColumn QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(col)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Header row: sigil + heading
        head_row = QHBoxLayout()
        head_row.setContentsMargins(0, 0, 0, 0)
        head_row.setSpacing(10)
        head_row.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        if placeholder:
            head_row.addWidget(_DashedCircle(diameter=40))
        else:
            sigil = IssuerSigilCircle(is_self=False, role=role)
            head_row.addWidget(sigil)

        heading_lbl = QLabel(heading)
        heading_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {colors.TEXT_DARK};"
        )
        head_row.addWidget(heading_lbl)
        head_row.addStretch()

        head_w = QWidget()
        head_w.setLayout(head_row)
        layout.addWidget(head_w)

        body_lbl = QLabel(body)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_SECONDARY};")
        layout.addWidget(body_lbl)

        return col

    def _build_lifecycle_card(self, i: Any) -> QWidget:
        """Schema-level Lifecycle card: the time axis. Single fact —
        does this schema require registry anchoring? Per design
        2026-05-07-acdc-parties-lifecycle §4.2."""
        from locksmith.plugins.ecosystem_viewer.widgets import LifecycleWidget
        frame = QFrame()
        frame.setObjectName("sdLifecycleCard")
        frame.setStyleSheet(
            "QFrame#sdLifecycleCard { background-color: white;"
            " border: 1px solid #E0E3EA; border-radius: 8px; }"
            "QFrame#sdLifecycleCard QLabel { background: transparent; }"
        )
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        title = QLabel("Lifecycle")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        outer.addWidget(title)

        # Single row: glyph + heading + body
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        row.setAlignment(Qt.AlignmentFlag.AlignTop)

        glyph = LifecycleWidget(revocable=i.requires_registry)
        # Larger size for hero-card use; resize from default 18px to 32px.
        glyph.setFixedSize(32, 32)
        row.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)

        text_block = QVBoxLayout()
        text_block.setContentsMargins(0, 0, 0, 0)
        text_block.setSpacing(4)

        if i.requires_registry:
            heading_text = "Revocable"
            body_text = (
                "This schema requires registry anchoring. Issued credentials "
                "live in a TEL — the issuer can append a revocation event to "
                "mark a specific credential revoked. Verifiers should consult "
                "the TEL state, not just the SAID."
            )
        else:
            heading_text = "One-shot"
            body_text = (
                "No registry. Issued credentials are anchored once and "
                "cannot be revoked. The issuer's signature commits to the "
                "credential as-issued; verifiers trust it on its face. "
                "Appropriate for non-revocable attestations (a measurement, "
                "a transcript) but not for entitlements that must support "
                "withdrawal."
            )

        heading_lbl = QLabel(heading_text)
        heading_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {colors.TEXT_DARK};"
        )
        text_block.addWidget(heading_lbl)

        body_lbl = QLabel(body_text)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_SECONDARY};")
        text_block.addWidget(body_lbl)

        row.addLayout(text_block, 1)
        row_w = QWidget()
        row_w.setLayout(row)
        outer.addWidget(row_w)

        return frame
```

- [ ] **Step 4: Add the `_DashedCircle` helper class**

Append a small helper at the END of `pages.py` (after the last class/function in the module) — it's used by `_build_party_column` for the untargeted "No issuee" placeholder:

```python
class _DashedCircle(QWidget):
    """Painted dashed-outline circle used as the 'absent role'
    placeholder in the Parties card when a schema is untargeted."""

    def __init__(self, diameter: int = 40, parent: QWidget | None = None):
        super().__init__(parent)
        self._diameter = diameter
        self.setFixedSize(diameter, diameter)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(colors.TEXT_SECONDARY), 1.5)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        d = self._diameter
        p.drawEllipse(2, 2, d - 4, d - 4)
        p.end()
```

- [ ] **Step 5: Delete the now-orphaned `_build_party_row`**

In `pages.py`, find and delete the `_build_party_row` method entirely. It was only called by the old `_build_parties_lifecycle_card`. Verify no other callers via:

Run: `grep -n "_build_party_row" src/locksmith/plugins/ecosystem_viewer/pages.py`

Expected output: empty.

- [ ] **Step 6: Smoke-test the wallet**

Run: `pgrep -f "locksmith.main" | xargs -r kill -9 2>/dev/null; sleep 1; .venv/bin/python -m locksmith.main` (background)

Open a schema-detail page → there should now be TWO cards: "Parties" with two columns, and "Lifecycle" below it. Stop the wallet before next step.

- [ ] **Step 7: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/pages.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): split Parties + Lifecycle into two cards

Per design 2026-05-07-acdc-parties-lifecycle §4.2: the v1 placeholder
bundled people-axis facts (issuer/issuee) with time-axis facts
(registry-backed) into one card titled "Parties & lifecycle." The user
had to mentally split the card to read it. This separates:

- Parties card: two-column layout (issuer | issuee), each column
  headed by a role-decorated IssuerSigilCircle placeholder. Untargeted
  schemas show a dashed-circle placeholder under "No issuee".
- Lifecycle card: single-fact card with a 32px LifecycleWidget glyph
  (clockface for revocable, open-arc for one-shot) plus a one-line
  decision-relevant explanation.

Field-name leaks ("Issuer (i)", "Issuee (a.i)", "Registry (rd/ri)")
are removed from headings; field names move to Developer details only
(addressed in a follow-up task).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Schema-detail hero — add lifecycle glyph next to variant glyph

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/pages.py` — locate `_build_hero_card` (~line 634)

- [ ] **Step 1: Find the current hero glyph**

In `pages.py`, locate `_build_hero_card`. The current code paints a 72px variant glyph (open vs hatched circle) at the top-left of the hero. Just below the variant pixmap setup (after the `outer_layout.addWidget(glyph_label, 0, Qt.AlignmentFlag.AlignTop)` line), we'll add a 32px lifecycle glyph stacked under it.

- [ ] **Step 2: Stack a LifecycleWidget under the variant glyph**

In `_build_hero_card`, find the section:

```python
        outer_layout.addWidget(glyph_label, 0, Qt.AlignmentFlag.AlignTop)
```

Replace with a small VBox that holds variant glyph + lifecycle glyph:

```python
        from locksmith.plugins.ecosystem_viewer.widgets import LifecycleWidget

        glyph_stack = QVBoxLayout()
        glyph_stack.setContentsMargins(0, 0, 0, 0)
        glyph_stack.setSpacing(8)
        glyph_stack.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        glyph_stack.addWidget(glyph_label, 0, Qt.AlignmentFlag.AlignHCenter)

        lifecycle_glyph = LifecycleWidget(revocable=i.requires_registry)
        lifecycle_glyph.setFixedSize(32, 32)
        # Tooltip carries the prose; glyph alone reads at hero scale.
        lifecycle_glyph.setToolTip(
            "Revocable via TEL — registry-backed lifecycle"
            if i.requires_registry
            else "One-shot — no revocation surface"
        )
        glyph_stack.addWidget(lifecycle_glyph, 0, Qt.AlignmentFlag.AlignHCenter)

        glyph_stack_w = QWidget()
        glyph_stack_w.setLayout(glyph_stack)
        outer_layout.addWidget(glyph_stack_w, 0, Qt.AlignmentFlag.AlignTop)
```

- [ ] **Step 3: Smoke-test**

Run: `pgrep -f "locksmith.main" | xargs -r kill -9 2>/dev/null; sleep 1; .venv/bin/python -m locksmith.main` (background)

Open a schema-detail page → the hero card now shows the variant circle stacked above the lifecycle glyph. Stop the wallet.

- [ ] **Step 4: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/pages.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): lifecycle glyph in schema-detail hero

Variant glyph + lifecycle glyph are the headline classification axes;
the hero card now stacks them. 32px lifecycle glyph under the 72px
variant circle, tooltip carries the prose. Per design
2026-05-07-acdc-parties-lifecycle §4.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Schema-detail Parties card — known-issuers chip row (§7.1)

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/pages.py` — extend `_build_parties_card` (built in Task 4)

- [ ] **Step 1: Find the EcosystemBaser membership lookup**

Confirm the API: `EcosystemBaser.ecosystems_for_schema(schema_said) -> list[str]` returns the list of ecosystem names that contain this schema, and `EcosystemBaser.get_ecosystem(name)` returns the record. Both already exist in `db.py`.

- [ ] **Step 2: Find SchemaDetailPage's vault and db references**

In `pages.py`, locate `class SchemaDetailPage` — the constructor stores `self.app` and there's a `set_db(db)` method. Inside `_refresh` (~line 615), the code calls `vault = getattr(self.app, "vault", None)`. The same vault and `self._db` are available inside `_build_parties_card` if we pass them through.

- [ ] **Step 3: Update `_build_parties_card` signature to accept vault**

Edit the method signature in `pages.py`:

```python
    def _build_parties_card(self, i: Any) -> QWidget:
```

To:

```python
    def _build_parties_card(self, i: Any, vault: Any) -> QWidget:
```

And update the call site in `_refresh` (the line you added in Task 4):

```python
        self._content_layout.insertWidget(idx, self._build_parties_card(i)); idx += 1
```

To:

```python
        self._content_layout.insertWidget(idx, self._build_parties_card(i, vault)); idx += 1
```

- [ ] **Step 4: Append the known-issuers chip row inside `_build_parties_card`**

In `_build_parties_card`, *just before* the existing `return frame` line, insert:

```python
        # Known-issuers chip row (design §7.1) — bridges schema-detail to
        # the ecosystem-graph "who issues" question without requiring a
        # separate page navigation.
        known_aids = self._collect_known_issuer_aids_for_schema(i.schema_said, vault)
        outer.addWidget(self._build_known_issuers_row(known_aids, vault))
```

- [ ] **Step 5: Add the two helper methods**

Inside `class SchemaDetailPage`, add immediately after `_build_parties_card`:

```python
    def _collect_known_issuer_aids_for_schema(
        self, schema_said: str, vault: Any,
    ) -> list[str]:
        """Return the union of AIDs marked as permitted issuers of
        `schema_said` across every ecosystem that contains this schema.
        Returns at most a handful of AIDs in practice (one schema is
        typically a member of one or two ecosystems)."""
        if self._db is None:
            return []
        try:
            eco_names = self._db.ecosystems_for_schema(schema_said)
        except Exception:
            return []
        aids: list[str] = []
        seen: set[str] = set()
        for name in eco_names:
            try:
                rec = self._db.get_ecosystem(name)
            except Exception:
                continue
            if rec is None:
                continue
            for aid in rec.permitted_issuers.get(schema_said, []):
                if aid not in seen:
                    seen.add(aid)
                    aids.append(aid)
        return aids

    def _build_known_issuers_row(
        self, aids: list[str], vault: Any,
    ) -> QWidget:
        from locksmith.plugins.ecosystem_viewer.overview_cards import (
            IssuerSigilCircle,
        )
        wrap = QFrame()
        wrap.setObjectName("sdKnownIssuersRow")
        wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        wrap.setStyleSheet(
            "QFrame#sdKnownIssuersRow { background: transparent;"
            f" border-top: 1px solid {colors.BORDER}; padding-top: 8px; }}"
            "QFrame#sdKnownIssuersRow QLabel { background: transparent; }"
        )
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        prefix = QLabel("Known issuers in your wallet:")
        prefix.setStyleSheet(
            f"font-size: 11px; color: {colors.TEXT_SECONDARY};"
            " font-weight: 600; letter-spacing: 0.04em;"
        )
        layout.addWidget(prefix)

        if not aids:
            empty = QLabel("none yet")
            empty.setStyleSheet(
                f"font-size: 11px; color: {colors.TEXT_SECONDARY}; font-style: italic;"
            )
            layout.addWidget(empty)
            layout.addStretch()
            return wrap

        # Build a small chip per AID — sigil-circle + alias.
        try:
            self_aids = {hab.pre for hab in vault.hby.habs.values()} if vault else set()
        except Exception:
            self_aids = set()

        for aid in aids:
            chip = QFrame()
            chip.setObjectName("sdKnownIssuerChip")
            chip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(
                "QFrame#sdKnownIssuerChip {"
                f" background: {colors.BACKGROUND_SELECTION};"
                " border-radius: 12px; padding: 2px 8px 2px 4px;"
                "}"
                "QFrame#sdKnownIssuerChip QLabel { background: transparent; }"
            )
            chip_l = QHBoxLayout(chip)
            chip_l.setContentsMargins(0, 0, 0, 0)
            chip_l.setSpacing(4)
            chip_l.setAlignment(Qt.AlignmentFlag.AlignVCenter)

            is_self = aid in self_aids
            sigil = IssuerSigilCircle(is_self=is_self, role="from")
            # Shrink to chip scale.
            sigil.setFixedSize(20, 20)
            chip_l.addWidget(sigil)

            alias = self._alias_for_aid(aid, vault)
            label = QLabel(alias + (" ★" if is_self else ""))
            label.setStyleSheet(
                f"font-size: 11px; color: {colors.TEXT_DARK};"
                + (f" font-weight: 600;" if is_self else "")
            )
            label.setToolTip(aid)
            chip_l.addWidget(label)

            chip.mousePressEvent = (
                lambda _ev, a=aid, s=is_self:
                    self.show_issuer_requested.emit(a, s)
            )
            layout.addWidget(chip)

        layout.addStretch()
        return wrap

    def _alias_for_aid(self, aid: str, vault: Any) -> str:
        if vault is None or not aid:
            return aid[:14] + "…" if len(aid) > 16 else aid
        try:
            for c in vault.org.list():
                if c.get("id") == aid:
                    a = c.get("alias")
                    if a:
                        return a
        except Exception:
            pass
        try:
            hab = vault.hby.habByPre(aid)
            if hab is not None and hab.name:
                return hab.name
        except Exception:
            pass
        return aid[:14] + "…" if len(aid) > 16 else aid
```

- [ ] **Step 6: Add the `show_issuer_requested` signal to SchemaDetailPage**

Find the signal block at the top of `class SchemaDetailPage` (search for `back_requested = Signal()` etc.) and add:

```python
    show_issuer_requested = Signal(str, bool)  # (aid, is_self)
```

- [ ] **Step 7: Wire the signal in plugin.py**

In `src/locksmith/plugins/ecosystem_viewer/plugin.py`, find the schema-detail wiring block (search for `self._schema_detail_page.back_requested.connect`) and add a connection to the existing `_show_issuer` handler:

```python
        self._schema_detail_page.show_issuer_requested.connect(self._show_issuer)
```

- [ ] **Step 8: Smoke-test**

Run: `pgrep -f "locksmith.main" | xargs -r kill -9 2>/dev/null; sleep 1; .venv/bin/python -m locksmith.main` (background)

Open a schema-detail page → the Parties card now ends with a "Known issuers in your wallet:" chip row. If the schema has no permitted issuers configured, it reads "none yet". Clicking a chip should navigate to Contacts/Identifiers. Stop the wallet.

- [ ] **Step 9: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/pages.py src/locksmith/plugins/ecosystem_viewer/plugin.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): known-issuers chip row on schema-detail Parties

Per design §7.1 — bridges the schema-detail page to the graph view's
permitted-issuers section. The Parties card now ends with a small
chip row listing every AID marked as an permitted issuer of this
schema across any ecosystem the schema is a member of. Clicking a chip
opens Contacts (remote) or Identifiers (self) — same plumbing as the
overview's IssuerCard. Empty state reads "none yet"; mine-AIDs get the
★ + bold treatment.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Side panel — replace text lifecycle hint with glyph cell

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/side_panel.py` (locate the existing text `lifecycle_lbl` block, around lines 223-236)

- [ ] **Step 1: Locate the existing text-heavy lifecycle hint**

In `side_panel.py`, find the block:

```python
        # Lifecycle one-liner (Stage 10) — registry-backed = revocable; absent = one-shot.
        if getattr(inspection, "requires_registry", False):
            lifecycle_text = "Lifecycle: registry-backed (revocable via TEL)"
            lifecycle_color = "#0D9488"  # teal — matches aggregate dot
        else:
            lifecycle_text = "Lifecycle: one-shot (no revocation surface)"
            lifecycle_color = colors.TEXT_SECONDARY
        lifecycle_lbl = QLabel(lifecycle_text)
        lifecycle_lbl.setStyleSheet(
            f"font-size: 11px; color: {lifecycle_color}; font-weight: 600;"
        )
        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1, lifecycle_lbl,
        )
```

- [ ] **Step 2: Replace with a glyph + label cell**

Replace the entire block above with:

```python
        # Lifecycle glyph cell — registry-backed (revocable) vs one-shot.
        # Same visual register as the classification glyph row; tooltip
        # carries the prose. Per design §3.2 / §4.3.
        from locksmith.plugins.ecosystem_viewer.widgets import LifecycleWidget
        revocable = bool(getattr(inspection, "requires_registry", False))
        lifecycle_row = QHBoxLayout()
        lifecycle_row.setContentsMargins(0, 4, 0, 0)
        lifecycle_row.setSpacing(8)
        lifecycle_row.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        glyph = LifecycleWidget(revocable=revocable)
        # Use the default 18px size for chip-scale.
        lifecycle_row.addWidget(glyph)

        lifecycle_text_lbl = QLabel("Revocable" if revocable else "One-shot")
        lifecycle_text_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: "
            f"{'#0D9488' if revocable else colors.TEXT_SECONDARY};"
        )
        lifecycle_row.addWidget(lifecycle_text_lbl)
        lifecycle_row.addStretch()

        lifecycle_w = QWidget()
        lifecycle_w.setLayout(lifecycle_row)
        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1, lifecycle_w,
        )
```

- [ ] **Step 3: Smoke-test**

Run: `pgrep -f "locksmith.main" | xargs -r kill -9 2>/dev/null; sleep 1; .venv/bin/python -m locksmith.main` (background)

Open an ecosystem detail page → click a schema node → side panel now shows a glyph + "Revocable" or "One-shot" instead of the long text line. Stop the wallet.

- [ ] **Step 4: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/side_panel.py
git commit -m "$(cat <<'EOF'
refactor(ecosystem-viewer): lifecycle glyph cell in side panel

Replaces the text-heavy "Lifecycle: registry-backed (revocable via
TEL)" line with a LifecycleWidget glyph + short label, matching the
visual register of the existing classification glyph row above it.
Tooltip on the glyph carries the long prose and the field name. Per
design 2026-05-07-acdc-parties-lifecycle §4.3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: SchemaNode (graph) — lifecycle glyph in bottom-left corner

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/graph_items.py` — `SchemaNode.paint()` and `SchemaNode.__init__`

- [ ] **Step 1: Add `requires_registry` to SchemaNode constructor**

In `graph_items.py`, find `class SchemaNode` and add `requires_registry: bool = False` to the constructor signature (placed between the other booleans). Then store it on self:

Locate this section:

```python
    def __init__(
        self,
        *,
        said: str,
        title: str,
        version: str | None = None,
        is_targeted: bool = True,
        is_private: bool = False,
        disclosure_tier: Literal["metadata", "partial", "selective", "full"] = "metadata",
        has_attribute: bool = False,
        has_aggregate: bool = False,
        has_edges: bool = False,
        has_rules: bool = False,
        ghost: bool = False,
        parent: QGraphicsItem | None = None,
    ):
```

Insert `requires_registry: bool = False,` immediately after `has_rules: bool = False,`:

```python
    def __init__(
        self,
        *,
        said: str,
        title: str,
        version: str | None = None,
        is_targeted: bool = True,
        is_private: bool = False,
        disclosure_tier: Literal["metadata", "partial", "selective", "full"] = "metadata",
        has_attribute: bool = False,
        has_aggregate: bool = False,
        has_edges: bool = False,
        has_rules: bool = False,
        requires_registry: bool = False,
        ghost: bool = False,
        parent: QGraphicsItem | None = None,
    ):
```

In the body of `__init__`, find:

```python
        self.has_rules = has_rules
        self.ghost = ghost
```

And add the assignment between them:

```python
        self.has_rules = has_rules
        self.requires_registry = requires_registry
        self.ghost = ghost
```

- [ ] **Step 2: Paint the lifecycle glyph in the bottom-left corner**

In `graph_items.py`, locate `SchemaNode.paint()`. After the section-fingerprint dots are drawn (look for the four-dot painting block — the dots use `self.has_attribute`, `self.has_aggregate`, etc.), and before the `painter.end()` (or `return`) at the end of `paint()`, append:

```python
        # Lifecycle glyph (design 2026-05-07 §4.3) — bottom-left corner,
        # 12px. Skipped in ghost mode (which already returned early above).
        lifecycle_size = 12
        lx = 8
        ly = NODE_HEIGHT - lifecycle_size - 8
        lifecycle_rect = QRectF(lx, ly, lifecycle_size, lifecycle_size)
        if self.requires_registry:
            color = QColor("#0D9488")
            painter.setPen(QPen(color, 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(lifecycle_rect)
            # Single hand at 12 o'clock.
            cx = lifecycle_rect.center().x()
            cy = lifecycle_rect.center().y()
            painter.setPen(QPen(color, 1.2))
            painter.drawLine(QPointF(cx, cy), QPointF(cx, lifecycle_rect.top() + 1.5))
        else:
            color = QColor(colors.TEXT_SECONDARY)
            painter.setPen(QPen(color, 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(lifecycle_rect, -45 * 16, 270 * 16)
            cx = lifecycle_rect.center().x()
            cy = lifecycle_rect.center().y()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(cx - 1, cy - 1, 2, 2))
```

If `QPointF` is not already imported at the top of `graph_items.py`, add it to the existing `from PySide6.QtCore import` line.

- [ ] **Step 3: Pass requires_registry from `_build_scene` in graph_view.py**

In `src/locksmith/plugins/ecosystem_viewer/graph_view.py`, find the `SchemaNode(...)` constructor call inside `_build_scene` (the one that builds resolved schema nodes — there are two SchemaNode constructions, one for resolved + one for ghost; modify only the resolved-schema one). It looks like:

```python
            node = SchemaNode(
                said=said,
                title=insp.title or "(unnamed)",
                version=insp.schema_version,
                is_targeted=insp.requires_targeted,
                is_private=insp.requires_nonce,
                disclosure_tier=tier,
                has_attribute=sd.declares_attribute,
                has_aggregate=sd.declares_aggregate,
                has_edges=sd.declares_edges,
                has_rules=sd.declares_rules,
                ghost=False,
            )
```

Add the `requires_registry=insp.requires_registry,` line:

```python
            node = SchemaNode(
                said=said,
                title=insp.title or "(unnamed)",
                version=insp.schema_version,
                is_targeted=insp.requires_targeted,
                is_private=insp.requires_nonce,
                disclosure_tier=tier,
                has_attribute=sd.declares_attribute,
                has_aggregate=sd.declares_aggregate,
                has_edges=sd.declares_edges,
                has_rules=sd.declares_rules,
                requires_registry=insp.requires_registry,
                ghost=False,
            )
```

Leave the ghost-node `SchemaNode(...)` constructor call as-is (ghosts don't need a lifecycle glyph — they have no inspection data).

- [ ] **Step 4: Smoke-test**

Run: `pgrep -f "locksmith.main" | xargs -r kill -9 2>/dev/null; sleep 1; .venv/bin/python -m locksmith.main` (background)

Open an ecosystem detail page graph view → schema nodes now have a tiny clockface (revocable) or open-arc (one-shot) glyph in the bottom-left corner. Stop the wallet.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/graph_items.py src/locksmith/plugins/ecosystem_viewer/graph_view.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): lifecycle glyph on schema graph nodes

Per design 2026-05-07-acdc-parties-lifecycle §4.3: the schema graph
node now reads in four corners: variant (top-left), SAID + disclosure
(top-right), section fingerprint (bottom-right), lifecycle (bottom-
left, NEW). 12px clockface for revocable, 12px open-arc for one-shot.
SchemaNode constructor gains a requires_registry parameter; graph_view
populates it from inspection data.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Drop field-name parentheticals from default UI; document in Developer details

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/pages.py`

- [ ] **Step 1: Audit field-name leaks**

Run: `grep -n "(i)\|(a\.i)\|(rd/ri)\|(u required)\|(t required)\|requires u\|requires registry\|requires message type" src/locksmith/plugins/ecosystem_viewer/pages.py`

Most leaks were already removed in Task 4 (the new Parties + Lifecycle cards use no parentheticals). The one remaining surface is `_build_requirements_section` (developer details), which is the *correct* place for field names. Verify no other surface leaks by running the grep above and visually inspecting any matches.

Expected: matches only inside `_build_requirements_section` and the strings inside developer-details rows. If you see matches in other surfaces, replace those occurrences with field-name-free domain language.

- [ ] **Step 2: Update developer-details row labels to be more explicit**

In `_build_requirements_section`, the existing rows already use field names. Improve the language so the developer-details surface explicitly bridges domain ↔ spec terms. Replace:

```python
        rows = [
            ("Targeted (a.i required)", i.requires_targeted),
            ("Private (u required)", i.requires_nonce),
            ("Has registry (rd/ri required)", i.requires_registry),
            ("Has message type (t required)", i.requires_message_type),
        ]
```

With:

```python
        rows = [
            ("Targeted — requires a.i (issuee AID)", i.requires_targeted),
            ("Private — requires u (nonce)", i.requires_nonce),
            ("Registry-backed — requires rd (or legacy ri)", i.requires_registry),
            ("Has message type — requires t", i.requires_message_type),
        ]
```

This keeps field names exactly where they belong (developer details) and disambiguates each one ("rd or legacy ri" is clearer than "rd/ri").

- [ ] **Step 3: Smoke-test**

Run: `pgrep -f "locksmith.main" | xargs -r kill -9 2>/dev/null; sleep 1; .venv/bin/python -m locksmith.main` (background)

Open a schema-detail page → toggle developer details (the gear icon at top right of the page) → the requirements section should show the new explicit labels. Stop the wallet.

- [ ] **Step 4: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/pages.py
git commit -m "$(cat <<'EOF'
refactor(ecosystem-viewer): clearer developer-details requirement labels

Per design 2026-05-07-acdc-parties-lifecycle §4.2: field names belong
in developer details. Improves the labels to spell out the domain
concept first ("Targeted — requires a.i (issuee AID)") rather than
leading with the field name. Default-view surfaces have already had
their parentheticals removed in the Parties + Lifecycle card split.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: README — note the new convention overlays

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/README.md`

- [ ] **Step 1: Find the spec-vs-convention discipline section**

In `src/locksmith/plugins/ecosystem_viewer/README.md`, find the section titled `## Spec-vs-convention discipline` (around line 215).

- [ ] **Step 2: Append the new convention overlays**

In that section, find the bulleted list under "Convention overlay (called out as such)". Add `is_self_issued`, `is_self_attested`, and the lifecycle/role names to the existing list. Replace:

```markdown
- **Convention overlay** (called out as such): the names "ecosystem,"
  "is_private," "disclosure_tier" as a single label, and the user
  constructs in `EcosystemBaser`.
```

With:

```markdown
- **Convention overlay** (called out as such): the names "ecosystem,"
  "is_private," "disclosure_tier" as a single label, the user
  constructs in `EcosystemBaser`, and the parties + lifecycle vocabulary
  introduced in `2026-05-07-acdc-parties-lifecycle.md` —
  `is_self_issued` / `is_self_attested` flags on `ACDCInspection`, the
  "revocable" / "one-shot" lifecycle naming, and the "from" / "to"
  role labels on `IssuerSigilCircle`. None of these are spec-defined
  variants; they are this wallet's framing of derived facts.
```

- [ ] **Step 3: Update the roadmap to mark Stage 10 complete**

In the same README, find the roadmap table (around line 200). The current table has rows up to stage 8. Add a stage-10 row (stage 9 was added by Stage 9's commits already if present; otherwise keep moving). If stage 9 isn't in the README yet, add both:

Find:

```markdown
| 8 | Ecosystem export/import — share ecosystem definitions across wallets |
```

If only 1-8 are listed, append:

```markdown
| 9 | Per-schema permitted issuers (EGF overlay) |
| 10 | Parties + lifecycle vocabulary (issuer/issuee/registry-backed) |
```

If stage 9 is already there, just append the stage 10 row.

- [ ] **Step 4: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/README.md
git commit -m "$(cat <<'EOF'
docs(ecosystem-viewer): mark stage 10 + parties/lifecycle conventions

Adds is_self_issued / is_self_attested / lifecycle / role labels to
the spec-vs-convention discipline list so future maintainers can tell
spec primitives from this wallet's framing at a glance. Marks stage
10 (Parties + lifecycle vocabulary) as complete in the roadmap.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-review checklist results

**Spec coverage** — every recommendation in `2026-05-07-acdc-parties-lifecycle.md` §8 ("Summary of recommended deltas") has a task:
- §8.1 inspector additions → Task 1 ✓
- §8.2 icons module additions → **deferred** (see note below)
- §8.3 SVG asset commissioning → **deferred** (we paint instead)
- §8.4 split parties+lifecycle card, drop field-name parentheticals, role-decorated sigils, known-issuers chip row, hero lifecycle glyph → Tasks 4, 5, 6, 9 ✓
- §8.5 side panel glyph cell → Task 7 ✓
- §8.6 schema graph node lifecycle glyph → Task 8 ✓
- §8.7 developer details field-name notes → Task 9 ✓
- §8.8 forward to credential-detail (stage 7+) → out of scope here ✓

**Why we paint instead of commissioning SVGs:** the design itself notes (§3.5) that the role ribbons "could be drawn directly in `paint()` (no asset)" and the Lifecycle pair is small enough that a painted version preserves equivalence. The existing `DisclosureTierWidget` and `SectionFingerprintWidget` are already painted (no SVG) for the same reason. Skipping commissioning unblocks the work; SVGs can be swapped in later if a designer commissions them.

**Self-issued loop badge** (design §3.3, asset 7.27/7.28) is **out of scope** here: the design explicitly says it appears "only in credential-instance renderings (stage-7-plus surface), never on schema cards." Inspector flags from Task 1 are the prerequisite when credential rendering lands.

**Type consistency:** `is_self_issued` / `is_self_attested` field names are stable across Task 1 (definition), Task 4 (used in body copy reference only), and the §5 forward-pointing recommendation. `LifecycleWidget(revocable: bool)` is the consistent constructor signature across Tasks 2, 4, 5, 7. `IssuerSigilCircle(is_self, role)` signature is consistent across Tasks 3, 4, 6.

**Placeholder scan:** no "TBD", no "implement appropriate", no bare "write tests for the above" — every test step shows the actual test code, every code step shows the actual code.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-07-acdc-parties-lifecycle-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
