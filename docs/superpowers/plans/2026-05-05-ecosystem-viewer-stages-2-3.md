# Ecosystem Viewer — Stages 2 & 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the ecosystem-viewer plugin from stage-1 (schema/AID list) to stages 2 (per-schema detail page with edge drill-down) and 3 (plugin-owned LMDB store for user-construct ecosystems plus a UI for creating, viewing, editing, and annotating them).

**Architecture:** Stage 2 adds a SchemaDetailPage that renders the full inspector output and supports intra-plugin navigation between linked schemas. Stage 3 adds an `EcosystemBaser` (LMDB, per-vault, plugin-owned) modeled on `KFBaser`, plus pages for ecosystem CRUD and member management. Both stages are read-mostly UI work backed by the existing `locksmith.acdc.inspector` and the wallet's existing schema/contact stores.

**Tech Stack:** PySide6 (Qt for Python), keripy (`keri.db.dbing.LMDBer` + `keri.db.koming.Komer` for typed sub-DBs), pytest (introduced for the first time — pyproject.toml is already configured for it; we set up `tests/` here).

---

## Worktree assumption

All work in this plan happens in `.worktrees/ecosystem-viewer/` on branch `feat/acdc-ecosystem-viewer`. Commands assume `cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer && source .venv/bin/activate` is the active shell context.

## File map

Files created or modified across stages 2 + 3:

| Path | Stage | Disposition |
|---|---|---|
| `tests/__init__.py` | 2 | Create (empty package marker) |
| `tests/test_acdc_inspector.py` | 2 | Create — retroactive coverage for stage-1 inspector |
| `tests/test_ecosystem_baser.py` | 3 | Create — DB-layer tests |
| `src/locksmith/plugins/ecosystem_viewer/pages.py` | 2 + 3 | Modify — add SchemaDetailPage; later add EcosystemDetailPage; existing list rows become clickable |
| `src/locksmith/plugins/ecosystem_viewer/plugin.py` | 2 + 3 | Modify — register new pages, wire DB lifecycle |
| `src/locksmith/plugins/ecosystem_viewer/db.py` | 3 | Create — `EcosystemBaser` + dataclasses |
| `src/locksmith/plugins/ecosystem_viewer/dialogs.py` | 3 | Create — modals for "Create Ecosystem", "Add Annotation", member-add pickers |
| `src/locksmith/plugins/ecosystem_viewer/README.md` | 3 (notes) | Modify — bump roadmap markers |

---

## Verification approach

This codebase has no test suite yet — `pyproject.toml` has pytest configured but no `tests/` exists (per `CLAUDE.md`). This plan introduces `tests/` with the inspector's retroactive coverage as the first occupant.

- **For pure-Python logic** (inspector, EcosystemBaser CRUD): real pytest tests, TDD where adding new behavior.
- **For Qt UI** (pages, dialogs): no automated tests in this plan. Each UI task ends with an explicit "smoke test" step: launch the wallet from this worktree's venv, exercise the path manually, capture log output if anything looks off. UI test infrastructure is out of scope.

---

## Stage 2 — Per-schema detail page

### Task 2.1: Set up tests/ and add retroactive inspector tests

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_acdc_inspector.py`

- [ ] **Step 1: Create `tests/__init__.py`** (empty file)

```bash
touch tests/__init__.py
```

- [ ] **Step 2: Write `tests/test_acdc_inspector.py` covering inspector basics**

```python
# -*- encoding: utf-8 -*-
"""Tests for locksmith.acdc.inspector — pure-Python, no Qt or vault required."""
from __future__ import annotations

import pytest

from locksmith.acdc import inspect_acdc, inspect_acdc_schema


# ---------------------------------------------------------------------------
# Instance inspection
# ---------------------------------------------------------------------------


def _minimal_acdc(**overrides):
    base = {
        "v": "ACDC10JSON000050_",
        "d": "EAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "i": "EIssuerIssuerIssuerIssuerIssuerIssuerIssuer",
        "s": "ESchemaSchemaSchemaSchemaSchemaSchemaSchema",
    }
    base.update(overrides)
    return base


def test_minimal_acdc_classifies_as_metadata_public_untargeted():
    i = inspect_acdc(_minimal_acdc())
    assert i.is_private is False
    assert i.is_targeted is False
    assert i.issuee_aid is None
    assert i.disclosure_tier == "metadata"
    assert i.sections.attribute == "absent"
    assert i.sections.aggregate == "absent"
    assert i.sections.edges == "absent"
    assert i.sections.rules == "absent"


def test_acdc_with_u_field_is_private():
    i = inspect_acdc(_minimal_acdc(u="0AnonceXxxxxxxxxxxxxxxxxxx"))
    assert i.is_private is True
    assert i.nonce == "0AnonceXxxxxxxxxxxxxxxxxxx"


def test_acdc_with_attribute_block_having_i_is_targeted():
    a = {
        "d": "EAttribAttribAttribAttribAttribAttribAttrib",
        "i": "EIssueeIssueeIssueeIssueeIssueeIssueeIssuee",
        "name": "Alice",
    }
    i = inspect_acdc(_minimal_acdc(a=a))
    assert i.is_targeted is True
    assert i.issuee_aid == "EIssueeIssueeIssueeIssueeIssueeIssueeIssuee"
    assert i.sections.attribute == "full"


def test_acdc_with_compact_attribute_section_is_partial():
    i = inspect_acdc(_minimal_acdc(
        a="EAttribSAIDAttribSAIDAttribSAIDAttribSAIDAttribSAID",
        e={"d": "EEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdge",
           "x": {"n": "ETargetTargetTargetTargetTargetTargetTarget",
                 "s": "ETargetSchemaTargetSchemaTargetSchemaTarget"}},
    ))
    assert i.sections.attribute == "compact"
    assert i.sections.edges == "full"
    # Mixed forms => partial
    assert i.disclosure_tier == "partial"


def test_acdc_with_aggregate_section_is_selective():
    i = inspect_acdc(_minimal_acdc(A={"d": "EAggrAggrAggrAggrAggrAggrAggrAggrAggrAggr"}))
    assert i.sections.aggregate == "full"
    assert i.disclosure_tier == "selective"


def test_inspect_acdc_extracts_edges_with_operator():
    i = inspect_acdc(_minimal_acdc(e={
        "d": "EEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdge",
        "license": {
            "n": "ELicenseInstLicenseInstLicenseInstLicenseInst",
            "s": "ELicenseSchemaLicenseSchemaLicenseSchemaLic",
            "o": "I2I",
        },
    }))
    assert len(i.edges) == 1
    edge = i.edges[0]
    assert edge.is_edge is True
    assert edge.name == "license"
    assert edge.target_said == "ELicenseInstLicenseInstLicenseInstLicenseInst"
    assert edge.operator == "I2I"


def test_inspect_acdc_distinguishes_edge_groups_from_edges():
    # Edge-group: dict without `n`, contains nested edges
    i = inspect_acdc(_minimal_acdc(e={
        "d": "EEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdge",
        "any_of": {
            "o": "OR",
            "license_a": {"n": "ELicAaaa", "s": "ESchAaaa"},
            "license_b": {"n": "ELicBbbb", "s": "ESchBbbb"},
        },
    }))
    assert len(i.edges) == 1
    group = i.edges[0]
    assert group.is_edge is False
    assert group.group_operator == "OR"
    assert len(group.nested) == 2
    assert all(e.is_edge for e in group.nested)


def test_inspect_acdc_rules_flag_missing_legal_language():
    # Per spec: rule blocks REQUIRE l field. Inspector flags absence.
    i = inspect_acdc(_minimal_acdc(r={
        "d": "ERulesRulesRulesRulesRulesRulesRulesRulesRules",
        "good": {"l": "Compliant rule with legal language."},
        "bad": {"description": "missing l field"},
    }))
    by_name = {r.name: r for r in i.rules}
    assert by_name["good"].has_legal_language is True
    assert by_name["good"].legal_language == "Compliant rule with legal language."
    assert by_name["bad"].has_legal_language is False


def test_inspect_acdc_missing_required_field_raises():
    with pytest.raises(ValueError, match="missing required spec field"):
        inspect_acdc({"v": "x", "d": "y"})  # no i, no s


def test_inspect_acdc_accepts_legacy_ri_or_spec_rd():
    i_legacy = inspect_acdc(_minimal_acdc(ri="ERegistryLegacyRiRiRiRiRiRiRiRiRiRiRi"))
    i_spec = inspect_acdc(_minimal_acdc(rd="ERegistrySpecRdRdRdRdRdRdRdRdRdRdRdRd"))
    assert i_legacy.registry_said == "ERegistryLegacyRiRiRiRiRiRiRiRiRiRiRi"
    assert i_spec.registry_said == "ERegistrySpecRdRdRdRdRdRdRdRdRdRdRdRd"


# ---------------------------------------------------------------------------
# Schema inspection
# ---------------------------------------------------------------------------


def _schema(**overrides):
    base = {
        "$id": "ESchemaSaidSchemaSaidSchemaSaidSchemaSaidSchemaSaid",
        "title": "ExampleCredential",
        "description": "Test schema",
        "credentialType": "ExampleCredentialV1",
        "version": "1.0.0",
        "type": "object",
        "properties": {
            "v": {"type": "string"},
            "d": {"type": "string"},
            "i": {"type": "string"},
            "s": {"type": "string"},
        },
        "required": ["v", "d", "i", "s"],
    }
    base.update(overrides)
    return base


def test_schema_inspection_metadata():
    s = inspect_acdc_schema(_schema())
    assert s.title == "ExampleCredential"
    assert s.credential_type == "ExampleCredentialV1"
    assert s.schema_version == "1.0.0"


def test_schema_inspection_detects_targeted_requirement():
    s = inspect_acdc_schema(_schema(properties={
        "v": {"type": "string"},
        "d": {"type": "string"},
        "i": {"type": "string"},
        "s": {"type": "string"},
        "a": {
            "oneOf": [
                {"type": "string"},
                {
                    "type": "object",
                    "required": ["d", "i"],
                    "properties": {"d": {"type": "string"}, "i": {"type": "string"}},
                },
            ],
        },
    }, required=["v", "d", "i", "s", "a"]))
    assert s.requires_targeted is True
    assert s.declared_sections.declares_attribute is True
    assert s.declared_sections.attribute_required is True


def test_schema_inspection_extracts_edge_with_locked_target_schema():
    s = inspect_acdc_schema(_schema(properties={
        "v": {"type": "string"},
        "d": {"type": "string"},
        "i": {"type": "string"},
        "s": {"type": "string"},
        "e": {
            "oneOf": [
                {"type": "string"},
                {
                    "type": "object",
                    "required": ["d", "license"],
                    "properties": {
                        "d": {"type": "string"},
                        "license": {
                            "type": "object",
                            "required": ["n", "s"],
                            "properties": {
                                "n": {"type": "string"},
                                "s": {"type": "string", "const": "ELockedTargetSchemaLockedTargetSchemaLockedTar"},
                                "o": {"type": "string", "enum": ["I2I", "DI2I"]},
                            },
                        },
                    },
                },
            ],
        },
    }, required=["v", "d", "i", "s", "e"]))
    assert len(s.edge_requirements) == 1
    edge = s.edge_requirements[0]
    assert edge.name == "license"
    assert edge.target_schema_said == "ELockedTargetSchemaLockedTargetSchemaLockedTar"
    assert edge.operator_constraint == ("I2I", "DI2I")
```

- [ ] **Step 3: Run pytest to verify tests pass**

Run: `pytest tests/test_acdc_inspector.py -v`

Expected: all 13 tests PASS. If any fail, the inspector implementation needs the fix — the test is the authority. (Retroactive coverage; the inspector should already conform.)

- [ ] **Step 4: Commit**

```bash
git add tests/__init__.py tests/test_acdc_inspector.py
git commit -m "test(acdc): retroactive coverage for inspector

Establishes tests/ in this repo (was empty per CLAUDE.md) and locks
down the inspector's spec-grounded classifications: variant via u,
targeting via a.i, per-section forms, disclosure-tier derivation,
edges vs edge-groups, rules with missing l flagged, ri/rd legacy
fallback, missing-required raise.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2.2: Add SchemaDetailPage skeleton with navigation hookup

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/pages.py`
- Modify: `src/locksmith/plugins/ecosystem_viewer/plugin.py`

- [ ] **Step 1: Add page-key constants and a navigation Signal at the top of pages.py**

In `src/locksmith/plugins/ecosystem_viewer/pages.py`, add the import for `Signal` and an explicit page-keys constant just below the existing imports:

```python
from PySide6.QtCore import Qt, Signal
```

Then immediately above the `EcosystemViewerPage` class, add:

```python
# Page keys registered with VaultPage's content stack. Owned by this plugin.
PAGE_KEY_OVERVIEW = "ecosystem_viewer"
PAGE_KEY_SCHEMA_DETAIL = "ecosystem_viewer.schema_detail"
```

- [ ] **Step 2: Make schema rows in the overview emit a navigation signal**

Add a Signal to `EcosystemViewerPage` that the plugin will connect to:

```python
class EcosystemViewerPage(QWidget):
    """List view: every schema + every known AID + their inspector classifications."""

    show_schema_detail_requested = Signal(str)  # emits schema SAID
```

In `_build_schema_row`, wrap the existing row's content area in a clickable affordance. Replace the existing `def _build_schema_row(self, i: Any) -> QWidget:` body with:

```python
    def _build_schema_row(self, i: Any) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            "QFrame { background-color: white; border: 1px solid #E0E3EA; border-radius: 6px; }"
            "QFrame:hover { background-color: #F0F3FA; }"
        )
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        rl = QVBoxLayout(row)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.setSpacing(4)

        title = QLabel(
            f"<b>{i.title or '(untitled schema)'}</b>"
            + (f" v{i.schema_version}" if i.schema_version else "")
        )
        title.setStyleSheet("font-size: 14px;")
        rl.addWidget(title)

        if i.description:
            desc = QLabel(i.description)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
            rl.addWidget(desc)

        meta = QLabel(
            f"<span style='color:{colors.TEXT_SECONDARY}'>SAID:</span> "
            f"<code>{i.schema_said}</code>"
        )
        meta.setStyleSheet("font-size: 11px;")
        meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rl.addWidget(meta)

        chips: list[str] = []
        if i.requires_targeted:
            chips.append("targeted")
        if i.requires_nonce:
            chips.append("private (requires u)")
        if i.requires_registry:
            chips.append("requires registry")
        if i.declared_sections.declares_aggregate:
            chips.append("supports selective disclosure")
        if i.edge_requirements:
            chips.append(f"{len(i.edge_requirements)} edge requirement(s)")

        if chips:
            class_label = QLabel(" · ".join(f"<b>{c}</b>" for c in chips))
            class_label.setWordWrap(True)
            class_label.setStyleSheet(f"color: {colors.TEXT_DARK}; font-size: 12px;")
            rl.addWidget(class_label)

        for edge in i.edge_requirements:
            edge_text = f"&nbsp;&nbsp;↳ edge <b>{edge.name}</b>"
            if edge.target_schema_said:
                edge_text += f" → schema <code>{edge.target_schema_said[:20]}…</code>"
            if edge.operator_locked:
                edge_text += f" (op locked: {edge.operator_locked})"
            elif edge.operator_constraint:
                edge_text += f" (op ∈ {{{', '.join(edge.operator_constraint)}}})"
            edge_label = QLabel(edge_text)
            edge_label.setWordWrap(True)
            edge_label.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
            rl.addWidget(edge_label)

        # Click anywhere on the row navigates to the detail page
        said = i.schema_said
        row.mousePressEvent = lambda _event, s=said: self.show_schema_detail_requested.emit(s)

        return row
```

- [ ] **Step 3: Add a SchemaDetailPage class below EcosystemViewerPage**

Append to `src/locksmith/plugins/ecosystem_viewer/pages.py`:

```python
class SchemaDetailPage(QWidget):
    """Per-schema deep-inspect view. Renders inspector output + linked schemas."""

    back_requested = Signal()
    show_schema_detail_requested = Signal(str)  # for clicking edge target schemas

    def __init__(self, app: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self._current_said: str | None = None

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(colors.BACKGROUND_CONTENT))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top bar with back button
        bar = QHBoxLayout()
        bar.setContentsMargins(20, 12, 20, 0)
        back = QLabel('<a href="#back" style="color:#3a5fff;text-decoration:none;">‹ Back to overview</a>')
        back.setOpenExternalLinks(False)
        back.linkActivated.connect(lambda _: self.back_requested.emit())
        back.setStyleSheet("font-size: 13px;")
        bar.addWidget(back)
        bar.addStretch()
        outer.addLayout(bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT}; border: none;")
        scroll.viewport().setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")

        self._content = QWidget()
        self._content.setObjectName("schemaDetailContent")
        self._content.setStyleSheet(
            f"#schemaDetailContent {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
        )
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(20, 16, 20, 30)
        self._content_layout.setSpacing(16)
        self._content_layout.addStretch()
        scroll.setWidget(self._content)
        outer.addWidget(scroll)

    def show_schema(self, schema_said: str) -> None:
        """Load and render the schema with the given SAID. Called by the plugin."""
        self._current_said = schema_said
        self._refresh()

    def _refresh(self) -> None:
        # Clear all widgets except the trailing stretch
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()

        if self._current_said is None:
            self._content_layout.insertWidget(0, QLabel("(no schema selected)"))
            return

        vault = getattr(self.app, "vault", None)
        if vault is None or vault.hby is None:
            self._content_layout.insertWidget(0, QLabel("Vault not open."))
            return

        schemer = vault.hby.db.schema.get(keys=(self._current_said,))
        if schemer is None:
            msg = QLabel(
                f"Schema <code>{self._current_said}</code> not found in this wallet. "
                "It may have been deleted, or never resolved here. "
                "Add it via Credentials → Schemas → Add."
            )
            msg.setWordWrap(True)
            msg.setTextFormat(Qt.TextFormat.RichText)
            self._content_layout.insertWidget(0, msg)
            return

        from locksmith.acdc import inspect_acdc_schema
        inspection = inspect_acdc_schema(schemer.sed)
        # Render in the order: header, identity, requirements, sections, edges, raw JSON
        self._content_layout.insertWidget(0, self._build_header(inspection))
        self._content_layout.insertWidget(1, self._build_identity_section(inspection))
        self._content_layout.insertWidget(2, self._build_requirements_section(inspection))
        self._content_layout.insertWidget(3, self._build_sections_section(inspection))
        self._content_layout.insertWidget(4, self._build_edges_section(inspection, vault))
        self._content_layout.insertWidget(5, self._build_raw_json_section(inspection))

    def _build_header(self, i: Any) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        title = QLabel(
            f"{i.title or '(untitled schema)'}"
            + (f"  <span style='color:{colors.TEXT_SECONDARY};font-size:14px;'>v{i.schema_version}</span>"
               if i.schema_version else "")
        )
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(title)
        if i.credential_type:
            ct = QLabel(f"<span style='color:{colors.TEXT_SECONDARY};font-size:12px;'>credentialType: <code>{i.credential_type}</code></span>")
            layout.addWidget(ct)
        if i.description:
            desc = QLabel(i.description)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {colors.TEXT_DARK}; font-size: 13px; margin-top: 6px;")
            layout.addWidget(desc)
        return wrapper

    def _build_identity_section(self, i: Any) -> QWidget:
        frame = self._card("Identity")
        layout: QVBoxLayout = frame.layout()  # type: ignore[assignment]
        meta = QLabel(
            f"<span style='color:{colors.TEXT_SECONDARY}'>Schema SAID:</span> "
            f"<code>{i.schema_said}</code>"
        )
        meta.setStyleSheet("font-size: 12px;")
        meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(meta)
        return frame

    def _build_requirements_section(self, i: Any) -> QWidget:
        frame = self._card("Required ACDC variant")
        layout: QVBoxLayout = frame.layout()  # type: ignore[assignment]
        rows = [
            ("Targeted (a.i required)", i.requires_targeted),
            ("Private (u required)", i.requires_nonce),
            ("Has registry (rd/ri required)", i.requires_registry),
            ("Has message type (t required)", i.requires_message_type),
        ]
        for label, value in rows:
            txt = QLabel(f"<b>{'yes' if value else 'no':>4}</b> · {label}")
            txt.setStyleSheet("font-size: 12px;")
            layout.addWidget(txt)
        return frame

    def _build_sections_section(self, i: Any) -> QWidget:
        frame = self._card("Declared sections")
        layout: QVBoxLayout = frame.layout()  # type: ignore[assignment]
        sd = i.declared_sections
        rows = [
            ("a (attribute)", sd.declares_attribute, sd.attribute_required),
            ("A (aggregate, selective disclosure)", sd.declares_aggregate, sd.aggregate_required),
            ("e (edges)", sd.declares_edges, sd.edges_required),
            ("r (rules)", sd.declares_rules, sd.rules_required),
        ]
        for name, declared, required in rows:
            mark = "✓" if declared else "—"
            req = " (required)" if required else ""
            txt = QLabel(f"<code>{mark}</code> {name}{req}")
            txt.setStyleSheet("font-size: 12px;")
            layout.addWidget(txt)
        if i.rule_keys_declared:
            keys = QLabel(
                f"<span style='color:{colors.TEXT_SECONDARY}'>rule keys:</span> "
                + ", ".join(f"<code>{k}</code>" for k in i.rule_keys_declared)
            )
            keys.setStyleSheet("font-size: 12px; margin-top: 6px;")
            layout.addWidget(keys)
        return frame

    def _build_edges_section(self, i: Any, vault: Any) -> QWidget:
        frame = self._card("Edge requirements")
        layout: QVBoxLayout = frame.layout()  # type: ignore[assignment]
        if not i.edge_requirements:
            empty = QLabel("(no edges declared)")
            empty.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px; font-style: italic;")
            layout.addWidget(empty)
            return frame
        for edge in i.edge_requirements:
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(10, 8, 10, 8)
            row_layout.setSpacing(2)
            row.setStyleSheet("QWidget { background: #F8F9FF; border-radius: 4px; }")
            head = QLabel(f"<b>{edge.name}</b>")
            head.setStyleSheet("font-size: 13px;")
            row_layout.addWidget(head)
            if edge.description and edge.description != edge.name:
                desc = QLabel(edge.description)
                desc.setWordWrap(True)
                desc.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
                row_layout.addWidget(desc)
            if edge.target_schema_said:
                # Make the target schema link clickable if it's known to this wallet
                known = vault.hby.db.schema.get(keys=(edge.target_schema_said,)) is not None
                if known:
                    link = QLabel(
                        f"target schema: <a href=\"#nav\" style=\"color:#3a5fff;text-decoration:none;\">"
                        f"<code>{edge.target_schema_said}</code></a>"
                    )
                    link.setOpenExternalLinks(False)
                    link.linkActivated.connect(
                        lambda _l, said=edge.target_schema_said: self.show_schema_detail_requested.emit(said)
                    )
                else:
                    link = QLabel(
                        f"target schema: <code>{edge.target_schema_said}</code> "
                        f"<span style='color:{colors.TEXT_SECONDARY}'>(not in this wallet)</span>"
                    )
                link.setWordWrap(True)
                link.setStyleSheet("font-size: 12px;")
                link.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse)
                row_layout.addWidget(link)
            if edge.operator_locked:
                op = QLabel(f"operator locked: <b>{edge.operator_locked}</b>")
                op.setStyleSheet("font-size: 12px;")
                row_layout.addWidget(op)
            elif edge.operator_constraint:
                op = QLabel(f"operator ∈ {{{', '.join(edge.operator_constraint)}}}")
                op.setStyleSheet("font-size: 12px;")
                row_layout.addWidget(op)
            else:
                op = QLabel(
                    "operator: (none constrained — defaults to <b>I2I</b> for targeted ACDCs)"
                )
                op.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
                row_layout.addWidget(op)
            layout.addWidget(row)
        return frame

    def _build_raw_json_section(self, i: Any) -> QWidget:
        import json
        frame = self._card("Raw schema (JSON)")
        layout: QVBoxLayout = frame.layout()  # type: ignore[assignment]
        from PySide6.QtWidgets import QPlainTextEdit
        text = QPlainTextEdit()
        text.setPlainText(json.dumps(i.raw, indent=2))
        text.setReadOnly(True)
        text.setStyleSheet(
            "QPlainTextEdit { font-family: monospace; font-size: 11px; background: #FAFAFA; border: 1px solid #E0E3EA; }"
        )
        text.setMaximumHeight(300)
        layout.addWidget(text)
        return frame

    def _card(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title_label)
        return frame
```

- [ ] **Step 4: Wire detail page into the plugin**

Replace `src/locksmith/plugins/ecosystem_viewer/plugin.py` entirely with:

```python
# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.plugin module

EcosystemViewerPlugin — registers a sidebar entry that opens a viewer
into the wallet's known schemas, AIDs, and (planned) ecosystem groupings.
See README.md for design rationale and roadmap.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget
from keri import help

from locksmith.plugins.base import PluginBase
from locksmith.plugins.ecosystem_viewer.pages import (
    EcosystemViewerPage,
    SchemaDetailPage,
    PAGE_KEY_OVERVIEW,
    PAGE_KEY_SCHEMA_DETAIL,
)
from locksmith.ui.toolkit.widgets.buttons import BackButton
from locksmith.ui.vault.menu import MenuButton, MenuSpacer

logger = help.ogler.getLogger(__name__)


class EcosystemViewerPlugin(PluginBase):
    """Stages 1-2: domain-classified browsing of the wallet's known schemas + AIDs."""

    @property
    def plugin_id(self) -> str:
        return "ecosystem_viewer"

    def initialize(self, app: Any) -> None:
        self._app = app
        self._overview_page: EcosystemViewerPage | None = EcosystemViewerPage(app=app)
        self._schema_detail_page: SchemaDetailPage | None = SchemaDetailPage(app=app)
        self._nav_button: MenuButton | None = None

        # Wire intra-plugin navigation
        self._overview_page.show_schema_detail_requested.connect(self._show_schema_detail)
        self._schema_detail_page.back_requested.connect(self._show_overview)
        self._schema_detail_page.show_schema_detail_requested.connect(self._show_schema_detail)

        logger.info("EcosystemViewerPlugin initialized (stages 1-2)")

    def on_vault_opened(self, vault: Any) -> None:
        if self._overview_page is not None:
            self._overview_page.on_show()

    def on_vault_closed(self, vault: Any) -> None:
        pass

    def get_menu_entry(self) -> MenuButton:
        return MenuButton(
            icon=QIcon(":/assets/material-icons/schema.svg"),
            label="Ecosystem Viewer",
        )

    def get_menu_section(self) -> list[QWidget]:
        items: list[QWidget] = []
        items.append(BackButton(dark_mode=False))
        items.append(MenuSpacer(15))
        self._nav_button = MenuButton(
            icon=QIcon(":/assets/material-icons/schema.svg"),
            label="Overview",
        )
        self._nav_button.clicked.connect(self._show_overview)
        items.append(self._nav_button)
        return items

    def get_pages(self) -> dict[str, QWidget]:
        pages: dict[str, QWidget] = {}
        if self._overview_page is not None:
            pages[PAGE_KEY_OVERVIEW] = self._overview_page
        if self._schema_detail_page is not None:
            pages[PAGE_KEY_SCHEMA_DETAIL] = self._schema_detail_page
        return pages

    def _show_overview(self, *_args: Any) -> None:
        vault_page = getattr(self._app, "_vault_page", None)
        if vault_page is None:
            return
        vault_page._show_page(PAGE_KEY_OVERVIEW)
        if self._overview_page is not None:
            self._overview_page.on_show()

    def _show_schema_detail(self, schema_said: str) -> None:
        vault_page = getattr(self._app, "_vault_page", None)
        if vault_page is None:
            return
        vault_page._show_page(PAGE_KEY_SCHEMA_DETAIL)
        if self._schema_detail_page is not None:
            self._schema_detail_page.show_schema(schema_said)
```

- [ ] **Step 5: Smoke test the new pages**

Run:

```bash
pkill -f "python -m locksmith.main" 2>/dev/null; sleep 1
python -m locksmith.main &
```

Wait ~5 seconds for the wallet to start. Open vault `joe`, click Ecosystem Viewer in the sidebar, then click Overview. You should see the schema list as before. Click any schema row — it should navigate to the SchemaDetailPage showing identity, requirements, sections, edges, raw JSON. Click "‹ Back to overview" — should return. If a schema's edge target schema is also in the wallet, clicking that target's SAID should navigate to its detail page.

Expected log lines:
```
locksmith.plugins.ecosystem_viewer.plugin INFO  EcosystemViewerPlugin initialized (stages 1-2)
locksmith.plugins.manager INFO  Plugin 'ecosystem_viewer' loaded from entry point 'ecosystem_viewer'
```

If the wallet fails to start, run:

```bash
tail -50 /private/tmp/claude-501/-Users-seriouscoderone-code-locksmith/<session-id>/tasks/<bg-task>.output
```

to capture the traceback. Common failure: a missing import or a typo in a Qt selector — the traceback will point at the line.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/pages.py src/locksmith/plugins/ecosystem_viewer/plugin.py
git commit -m "feat(ecosystem-viewer): per-schema detail page (stage 2)

Schema rows in the overview are now clickable; navigating shows a
SchemaDetailPage rendering the full inspector output:

  - Header (title, version, credentialType, description)
  - Identity (SAID)
  - Required ACDC variant (targeted, private, registry, message-type)
  - Declared sections (a, A, e, r) with declared+required flags
  - Edge requirements (each with locked target schema SAID,
    operator constraint or default note, intra-plugin click-through
    to the target schema's detail when known to the wallet)
  - Raw schema JSON (collapsible-styled, monospace)

Plugin now owns two pages and handles navigation between them via
internal Signals. Stage 3 (EcosystemBaser + grouping UI) is next.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Stage 3 — EcosystemBaser + grouping UI

### Task 3.1: Define EcosystemBaser dataclasses and LMDB sub-DBs

**Files:**
- Create: `src/locksmith/plugins/ecosystem_viewer/db.py`
- Create: `tests/test_ecosystem_baser.py`

- [ ] **Step 1: Write the failing tests for EcosystemBaser CRUD**

Create `tests/test_ecosystem_baser.py`:

```python
# -*- encoding: utf-8 -*-
"""Tests for EcosystemBaser — temp LMDB, no Qt or vault required."""
from __future__ import annotations

import pytest

from locksmith.plugins.ecosystem_viewer.db import (
    AnnotationKind,
    AnnotationRecord,
    DiscoveryEvent,
    EcosystemBaser,
    EcosystemRecord,
)


@pytest.fixture
def baser():
    """Per-test EcosystemBaser backed by an LMDB temp directory."""
    db = EcosystemBaser(name="test_ecosys", temp=True, reopen=True)
    yield db
    db.close(clear=True)


def test_create_and_get_ecosystem(baser):
    rec = EcosystemRecord(
        name="insurance-ca",
        description="California insurance proxy ecosystem",
        schema_saids=["ESchemaA", "ESchemaB"],
        issuer_aids=["EIssuer1"],
        source_kind="manual",
    )
    baser.put_ecosystem(rec)
    fetched = baser.get_ecosystem("insurance-ca")
    assert fetched is not None
    assert fetched.name == "insurance-ca"
    assert fetched.description == "California insurance proxy ecosystem"
    assert fetched.schema_saids == ["ESchemaA", "ESchemaB"]
    assert fetched.issuer_aids == ["EIssuer1"]


def test_list_ecosystems_returns_all(baser):
    baser.put_ecosystem(EcosystemRecord(name="a", description="A"))
    baser.put_ecosystem(EcosystemRecord(name="b", description="B"))
    names = sorted(e.name for e in baser.list_ecosystems())
    assert names == ["a", "b"]


def test_delete_ecosystem(baser):
    baser.put_ecosystem(EcosystemRecord(name="doomed", description="x"))
    assert baser.get_ecosystem("doomed") is not None
    baser.delete_ecosystem("doomed")
    assert baser.get_ecosystem("doomed") is None


def test_add_remove_schema_member(baser):
    baser.put_ecosystem(EcosystemRecord(name="eco", description=""))
    baser.add_schema_to_ecosystem("eco", "ESchemaX")
    rec = baser.get_ecosystem("eco")
    assert rec is not None
    assert "ESchemaX" in rec.schema_saids
    # Idempotent
    baser.add_schema_to_ecosystem("eco", "ESchemaX")
    assert rec.schema_saids.count("ESchemaX") <= 1 or baser.get_ecosystem("eco").schema_saids.count("ESchemaX") == 1
    baser.remove_schema_from_ecosystem("eco", "ESchemaX")
    rec2 = baser.get_ecosystem("eco")
    assert rec2 is not None
    assert "ESchemaX" not in rec2.schema_saids


def test_add_remove_aid_member(baser):
    baser.put_ecosystem(EcosystemRecord(name="eco", description=""))
    baser.add_aid_to_ecosystem("eco", "EIssuerY")
    assert "EIssuerY" in (baser.get_ecosystem("eco") or EcosystemRecord("","")).issuer_aids
    baser.remove_aid_from_ecosystem("eco", "EIssuerY")
    rec = baser.get_ecosystem("eco")
    assert rec is not None
    assert "EIssuerY" not in rec.issuer_aids


def test_membership_lookup_by_schema(baser):
    baser.put_ecosystem(EcosystemRecord(name="alpha", description=""))
    baser.put_ecosystem(EcosystemRecord(name="beta", description=""))
    baser.add_schema_to_ecosystem("alpha", "ESharedSchema")
    baser.add_schema_to_ecosystem("beta", "ESharedSchema")
    names = sorted(baser.ecosystems_for_schema("ESharedSchema"))
    assert names == ["alpha", "beta"]


def test_membership_lookup_by_aid(baser):
    baser.put_ecosystem(EcosystemRecord(name="alpha", description=""))
    baser.put_ecosystem(EcosystemRecord(name="beta", description=""))
    baser.add_aid_to_ecosystem("alpha", "EIssuerShared")
    baser.add_aid_to_ecosystem("beta", "EIssuerShared")
    names = sorted(baser.ecosystems_for_aid("EIssuerShared"))
    assert names == ["alpha", "beta"]


def test_put_get_annotation(baser):
    ann = AnnotationRecord(
        kind=AnnotationKind.SCHEMA,
        target="ESchemaSaid",
        note="This is the canonical NFL trainer cert.",
        tags=["nfl", "trainer"],
    )
    baser.put_annotation(ann)
    got = baser.get_annotation(AnnotationKind.SCHEMA, "ESchemaSaid")
    assert got is not None
    assert got.note == "This is the canonical NFL trainer cert."
    assert got.tags == ["nfl", "trainer"]


def test_history_append_and_iter(baser):
    baser.append_history(DiscoveryEvent(kind="oobi_resolved", payload={"oobi": "x"}))
    baser.append_history(DiscoveryEvent(kind="ecosystem_added", payload={"name": "y"}))
    events = list(baser.iter_history())
    assert len(events) == 2
    kinds = sorted(e.kind for e in events)
    assert kinds == ["ecosystem_added", "oobi_resolved"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ecosystem_baser.py -v`

Expected: ALL fail with `ModuleNotFoundError: No module named 'locksmith.plugins.ecosystem_viewer.db'`

- [ ] **Step 3: Implement `db.py`**

Create `src/locksmith/plugins/ecosystem_viewer/db.py`:

```python
# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.db module

Plugin-owned LMDB store for ecosystem-level concepts that the wallet's
core stores don't track natively: named ecosystem groupings, user
annotations, and discovery history. One database per vault, namespaced
to keep plugin state isolated from KERI/ACDC core.

Modeled on KFBaser (kerifoundation/db/basing.py): subclass of
keri.db.dbing.LMDBer with koming.Komer sub-DBs for typed records.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable

from keri.db import dbing, koming


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass
class EcosystemRecord:
    """A user-defined grouping of schemas and issuer AIDs.

    `name` is the unique key. `source_kind` is informational
    ('manual', 'imported_oobi', 'imported_file'); `source_url` is
    populated when the ecosystem was sourced from an OOBI or file.
    """
    name: str = ""
    description: str = ""
    schema_saids: list[str] = field(default_factory=list)
    issuer_aids: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    source_kind: str = "manual"
    source_url: str = ""


class AnnotationKind(str, Enum):
    SCHEMA = "schema"
    AID = "aid"
    CREDENTIAL = "credential"
    ECOSYSTEM = "ecosystem"


@dataclass
class AnnotationRecord:
    """A user note attached to a schema, AID, credential, or ecosystem.

    Composite key: (kind.value, target). `target` is the SAID or AID
    or ecosystem name being annotated.
    """
    kind: AnnotationKind = AnnotationKind.SCHEMA
    target: str = ""
    note: str = ""
    tags: list[str] = field(default_factory=list)
    updated_at: str = ""


@dataclass
class DiscoveryEvent:
    """A timestamped event in the user's discovery history.

    `kind` is a free-form label ('oobi_resolved', 'ecosystem_added',
    'annotation_added'). Storage is keyed by ISO8601 timestamp so iteration
    yields chronological order naturally.
    """
    kind: str = ""
    payload: dict = field(default_factory=dict)
    timestamp: str = ""


@dataclass
class _MembershipRecord:
    """Reverse-lookup record: AID/SAID -> set of ecosystem names.

    Stored as a list because LMDB Komer doesn't deal in sets natively;
    we deduplicate on read/write.
    """
    ecosystem_names: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# EcosystemBaser
# ---------------------------------------------------------------------------


class EcosystemBaser(dbing.LMDBer):
    """LMDB database for the ecosystem-viewer plugin."""

    TailDirPath = "keri/ecosys"
    AltTailDirPath = ".keri/ecosys"
    TempPrefix = "ecosys"

    def __init__(self, name: str = "ecosystem", headDirPath: str | None = None, reopen: bool = True, **kwa):
        self.ecosystems = None
        self.annotations = None
        self.history = None
        self.schema_membership = None
        self.aid_membership = None
        super(EcosystemBaser, self).__init__(name=name, headDirPath=headDirPath, reopen=reopen, **kwa)

    def reopen(self, **kwa):
        super(EcosystemBaser, self).reopen(**kwa)

        self.ecosystems = koming.Komer(db=self, subkey='eco.', schema=EcosystemRecord)
        self.annotations = koming.Komer(db=self, subkey='ann.', schema=AnnotationRecord)
        self.history = koming.Komer(db=self, subkey='his.', schema=DiscoveryEvent)
        self.schema_membership = koming.Komer(db=self, subkey='smbr.', schema=_MembershipRecord)
        self.aid_membership = koming.Komer(db=self, subkey='ambr.', schema=_MembershipRecord)

        return self.env

    # --------------------------- Ecosystems ---------------------------

    def put_ecosystem(self, rec: EcosystemRecord) -> None:
        if not rec.name:
            raise ValueError("EcosystemRecord.name is required")
        now = datetime.now(timezone.utc).isoformat()
        if not rec.created_at:
            rec.created_at = now
        rec.updated_at = now
        # Dedupe member lists on save
        rec.schema_saids = sorted(set(rec.schema_saids))
        rec.issuer_aids = sorted(set(rec.issuer_aids))
        self.ecosystems.pin(keys=(rec.name,), val=rec)
        # Refresh reverse-membership indexes from this record's lists
        for said in rec.schema_saids:
            self._add_membership(self.schema_membership, said, rec.name)
        for aid in rec.issuer_aids:
            self._add_membership(self.aid_membership, aid, rec.name)

    def get_ecosystem(self, name: str) -> EcosystemRecord | None:
        return self.ecosystems.get(keys=(name,))

    def list_ecosystems(self) -> list[EcosystemRecord]:
        return [val for (_keys, val) in self.ecosystems.getItemIter()]

    def delete_ecosystem(self, name: str) -> None:
        rec = self.get_ecosystem(name)
        if rec is None:
            return
        for said in rec.schema_saids:
            self._remove_membership(self.schema_membership, said, name)
        for aid in rec.issuer_aids:
            self._remove_membership(self.aid_membership, aid, name)
        self.ecosystems.rem(keys=(name,))

    def add_schema_to_ecosystem(self, ecosystem_name: str, schema_said: str) -> None:
        rec = self.get_ecosystem(ecosystem_name)
        if rec is None:
            raise KeyError(f"unknown ecosystem '{ecosystem_name}'")
        if schema_said not in rec.schema_saids:
            rec.schema_saids = sorted(set(rec.schema_saids) | {schema_said})
            self.put_ecosystem(rec)

    def remove_schema_from_ecosystem(self, ecosystem_name: str, schema_said: str) -> None:
        rec = self.get_ecosystem(ecosystem_name)
        if rec is None:
            return
        if schema_said in rec.schema_saids:
            rec.schema_saids = [s for s in rec.schema_saids if s != schema_said]
            # put_ecosystem also updates membership; for the removal we need
            # to clear the reverse index ourselves first
            self._remove_membership(self.schema_membership, schema_said, ecosystem_name)
            self.ecosystems.pin(keys=(ecosystem_name,), val=rec)

    def add_aid_to_ecosystem(self, ecosystem_name: str, aid: str) -> None:
        rec = self.get_ecosystem(ecosystem_name)
        if rec is None:
            raise KeyError(f"unknown ecosystem '{ecosystem_name}'")
        if aid not in rec.issuer_aids:
            rec.issuer_aids = sorted(set(rec.issuer_aids) | {aid})
            self.put_ecosystem(rec)

    def remove_aid_from_ecosystem(self, ecosystem_name: str, aid: str) -> None:
        rec = self.get_ecosystem(ecosystem_name)
        if rec is None:
            return
        if aid in rec.issuer_aids:
            rec.issuer_aids = [a for a in rec.issuer_aids if a != aid]
            self._remove_membership(self.aid_membership, aid, ecosystem_name)
            self.ecosystems.pin(keys=(ecosystem_name,), val=rec)

    def ecosystems_for_schema(self, schema_said: str) -> list[str]:
        rec = self.schema_membership.get(keys=(schema_said,))
        return list(rec.ecosystem_names) if rec else []

    def ecosystems_for_aid(self, aid: str) -> list[str]:
        rec = self.aid_membership.get(keys=(aid,))
        return list(rec.ecosystem_names) if rec else []

    # --------------------------- Annotations ---------------------------

    def put_annotation(self, ann: AnnotationRecord) -> None:
        if not ann.target:
            raise ValueError("AnnotationRecord.target is required")
        ann.updated_at = datetime.now(timezone.utc).isoformat()
        kind_value = ann.kind.value if isinstance(ann.kind, AnnotationKind) else ann.kind
        self.annotations.pin(keys=(kind_value, ann.target), val=ann)

    def get_annotation(self, kind: AnnotationKind | str, target: str) -> AnnotationRecord | None:
        kind_value = kind.value if isinstance(kind, AnnotationKind) else kind
        return self.annotations.get(keys=(kind_value, target))

    def delete_annotation(self, kind: AnnotationKind | str, target: str) -> None:
        kind_value = kind.value if isinstance(kind, AnnotationKind) else kind
        self.annotations.rem(keys=(kind_value, target))

    # --------------------------- History ---------------------------

    def append_history(self, event: DiscoveryEvent) -> None:
        if not event.timestamp:
            event.timestamp = datetime.now(timezone.utc).isoformat()
        self.history.pin(keys=(event.timestamp,), val=event)

    def iter_history(self) -> Iterable[DiscoveryEvent]:
        for _keys, val in self.history.getItemIter():
            yield val

    # --------------------------- Internal ---------------------------

    def _add_membership(self, komer, key: str, ecosystem_name: str) -> None:
        rec = komer.get(keys=(key,))
        if rec is None:
            komer.pin(keys=(key,), val=_MembershipRecord(ecosystem_names=[ecosystem_name]))
            return
        if ecosystem_name not in rec.ecosystem_names:
            rec.ecosystem_names = sorted(set(rec.ecosystem_names) | {ecosystem_name})
            komer.pin(keys=(key,), val=rec)

    def _remove_membership(self, komer, key: str, ecosystem_name: str) -> None:
        rec = komer.get(keys=(key,))
        if rec is None:
            return
        if ecosystem_name in rec.ecosystem_names:
            rec.ecosystem_names = [n for n in rec.ecosystem_names if n != ecosystem_name]
            if not rec.ecosystem_names:
                komer.rem(keys=(key,))
            else:
                komer.pin(keys=(key,), val=rec)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ecosystem_baser.py -v`

Expected: all 9 tests PASS. If any fail, debug from the test name — the test is the spec.

- [ ] **Step 5: Commit**

```bash
git add tests/test_ecosystem_baser.py src/locksmith/plugins/ecosystem_viewer/db.py
git commit -m "feat(ecosystem-viewer): EcosystemBaser LMDB store (stage 3a)

Plugin-owned LMDB modeled on KFBaser. Five sub-DBs:

  - eco.   EcosystemRecord (name -> grouping)
  - ann.   AnnotationRecord ((kind, target) -> note)
  - his.   DiscoveryEvent (timestamp -> event)
  - smbr.  _MembershipRecord (schema_said -> ecosystem names)
  - ambr.  _MembershipRecord (aid -> ecosystem names)

Reverse-membership indexes are maintained automatically when ecosystem
records are added/removed.

Tested via pytest with temp LMDB fixtures (no Qt or vault required).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.2: Wire EcosystemBaser into plugin lifecycle

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/plugin.py`

- [ ] **Step 1: Add EcosystemBaser open/close to plugin lifecycle**

In `src/locksmith/plugins/ecosystem_viewer/plugin.py`, add the import at the top:

```python
from locksmith.plugins.ecosystem_viewer.db import EcosystemBaser
```

Add `_db` initialization in `initialize`:

```python
    def initialize(self, app: Any) -> None:
        self._app = app
        self._db: EcosystemBaser | None = None
        self._overview_page: EcosystemViewerPage | None = EcosystemViewerPage(app=app)
        self._schema_detail_page: SchemaDetailPage | None = SchemaDetailPage(app=app)
        self._nav_button: MenuButton | None = None

        # Wire intra-plugin navigation
        self._overview_page.show_schema_detail_requested.connect(self._show_schema_detail)
        self._schema_detail_page.back_requested.connect(self._show_overview)
        self._schema_detail_page.show_schema_detail_requested.connect(self._show_schema_detail)

        logger.info("EcosystemViewerPlugin initialized (stages 1-3)")
```

Modify `on_vault_opened` and `on_vault_closed` to manage `_db`:

```python
    def on_vault_opened(self, vault: Any) -> None:
        # Open per-vault EcosystemBaser. Same pattern as KFBaser.
        self._db = EcosystemBaser(name=f"ecosystem_{vault.hby.name}", reopen=True)
        # Hand the DB reference to pages that need it
        if self._overview_page is not None:
            self._overview_page.set_db(self._db)
            self._overview_page.on_show()
        if self._schema_detail_page is not None:
            self._schema_detail_page.set_db(self._db)

    def on_vault_closed(self, vault: Any) -> None:
        # Close per-vault DB on vault close
        if self._db is not None:
            self._db.close()
            self._db = None
        if self._overview_page is not None:
            self._overview_page.set_db(None)
        if self._schema_detail_page is not None:
            self._schema_detail_page.set_db(None)
```

- [ ] **Step 2: Add `set_db` placeholder to both pages so the wiring compiles**

In `pages.py`, add to the `EcosystemViewerPage` class (after `__init__`):

```python
    def set_db(self, db: Any) -> None:
        """Receive (or release) the plugin's EcosystemBaser. Called by plugin lifecycle."""
        self._db = db
```

And add to `__init__` (in EcosystemViewerPage):

```python
        self._db: Any = None
```

Same for `SchemaDetailPage` — add to `__init__`:

```python
        self._db: Any = None
```

And the `set_db` method:

```python
    def set_db(self, db: Any) -> None:
        self._db = db
```

(Pages don't use the DB yet — wiring it now means later tasks just consume `self._db` without re-plumbing.)

- [ ] **Step 3: Smoke test that opening/closing vaults doesn't crash**

```bash
pkill -f "python -m locksmith.main" 2>/dev/null; sleep 1
python -m locksmith.main &
```

Open vault `joe`. Watch the log:

Expected log lines:
```
locksmith.plugins.ecosystem_viewer.plugin INFO  EcosystemViewerPlugin initialized (stages 1-3)
locksmith.plugins.manager INFO  Plugin 'ecosystem_viewer' loaded from entry point 'ecosystem_viewer'
```

Verify the LMDB directory was created at `~/.keri/ecosys/` (or `keri/ecosys/`):

```bash
ls -la ~/.keri/ecosys/ 2>/dev/null || ls -la ~/keri/ecosys/ 2>/dev/null
```

Expected: a directory named `ecosystem_joe` (or whatever the vault name is) exists.

- [ ] **Step 4: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/plugin.py src/locksmith/plugins/ecosystem_viewer/pages.py
git commit -m "feat(ecosystem-viewer): wire EcosystemBaser into plugin lifecycle (stage 3b)

Plugin opens a per-vault EcosystemBaser at on_vault_opened, closes it
at on_vault_closed. Pages receive the DB reference via set_db() so
later UI tasks can consume it without re-plumbing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.3: Create-Ecosystem dialog

**Files:**
- Create: `src/locksmith/plugins/ecosystem_viewer/dialogs.py`

- [ ] **Step 1: Write the dialog module**

Create `src/locksmith/plugins/ecosystem_viewer/dialogs.py`:

```python
# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.dialogs module

Modal dialogs used by the ecosystem viewer pages.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import (
    FloatingLabelLineEdit,
    LocksmithButton,
    LocksmithDialog,
    LocksmithInvertedButton,
)


class CreateEcosystemDialog(LocksmithDialog):
    """Modal for creating a new ecosystem grouping."""

    ecosystem_create_requested = Signal(str, str)  # (name, description)

    def __init__(self, app: Any, parent: QWidget | None = None):
        self.app = app

        content = QWidget()
        content.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addSpacing(12)

        intro = QLabel(
            "An ecosystem is a user-defined grouping of schemas and issuer "
            "AIDs that work together. Pick a short, recognizable name."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(intro)

        layout.addSpacing(12)

        self._name_field = FloatingLabelLineEdit("Ecosystem name")
        self._name_field.setFixedWidth(360)
        layout.addWidget(self._name_field)

        layout.addSpacing(12)

        self._desc_field = FloatingLabelLineEdit("Description (optional)")
        self._desc_field.setFixedWidth(360)
        layout.addWidget(self._desc_field)

        layout.addSpacing(12)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self._cancel_button = LocksmithInvertedButton("Cancel")
        self._cancel_button.clicked.connect(self.close)
        self._create_button = LocksmithButton("Create")
        self._create_button.clicked.connect(self._on_create)
        button_row.addStretch()
        button_row.addWidget(self._cancel_button)
        button_row.addWidget(self._create_button)

        super().__init__(
            parent=parent,
            title="Create ecosystem",
            content=content,
            buttons=button_row,
            show_close_button=True,
        )

    def _on_create(self) -> None:
        name = self._name_field.text().strip()
        if not name:
            self.show_error("Ecosystem name is required.")
            return
        desc = self._desc_field.text().strip()
        self.ecosystem_create_requested.emit(name, desc)
        self.close()
```

- [ ] **Step 2: Smoke test imports**

```bash
python -c "from locksmith.plugins.ecosystem_viewer.dialogs import CreateEcosystemDialog; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit (dialog standalone, before wiring)**

```bash
git add src/locksmith/plugins/ecosystem_viewer/dialogs.py
git commit -m "feat(ecosystem-viewer): CreateEcosystemDialog (stage 3c)

Modal for creating a new ecosystem grouping. Used by the next task
which wires it into the overview page.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.4: Add ecosystems section to overview + wire create dialog

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/pages.py`

- [ ] **Step 1: Add an `ecosystem_create_requested` signal and an ecosystems-section to EcosystemViewerPage**

In `pages.py`, add to `EcosystemViewerPage`:

```python
class EcosystemViewerPage(QWidget):

    show_schema_detail_requested = Signal(str)
    show_ecosystem_detail_requested = Signal(str)  # NEW: emits ecosystem name
    create_ecosystem_clicked = Signal()             # NEW: from "Create" button
```

Bump `_sections_anchor_index` logic — instead of just two sections, we now have three (ecosystems, schemas, contacts). Modify `_refresh` to insert the new section first:

```python
    def _refresh(self) -> None:
        # Drop any previously rendered sections (everything after the header,
        # before the trailing stretch).
        while self._content_layout.count() > self._sections_anchor_index + 1:
            item = self._content_layout.takeAt(self._sections_anchor_index)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()

        vault = getattr(self.app, "vault", None)
        if vault is None or vault.hby is None:
            empty = self._build_status_message("No vault open. Unlock a vault to begin exploring.")
            self._content_layout.insertWidget(self._sections_anchor_index, empty)
            return

        ecosystems_section = self._build_ecosystems_section()
        self._content_layout.insertWidget(self._sections_anchor_index, ecosystems_section)

        schema_section = self._build_schema_section(vault)
        self._content_layout.insertWidget(self._sections_anchor_index + 1, schema_section)

        contacts_section = self._build_contacts_section(vault)
        self._content_layout.insertWidget(self._sections_anchor_index + 2, contacts_section)
```

- [ ] **Step 2: Implement `_build_ecosystems_section`**

Add to `EcosystemViewerPage`:

```python
    def _build_ecosystems_section(self) -> QWidget:
        section = self._build_card(title="My ecosystems")
        layout: QVBoxLayout = section.layout()  # type: ignore[assignment]

        # Top row: count + Create button
        header_row = QWidget()
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)

        if self._db is None:
            ecosystems = []
        else:
            try:
                ecosystems = self._db.list_ecosystems()
            except Exception:
                logger.exception("Failed to list ecosystems")
                ecosystems = []

        count_label = QLabel(f"{len(ecosystems)} ecosystem(s) defined")
        count_label.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
        header_layout.addWidget(count_label)
        header_layout.addStretch()

        from locksmith.ui.toolkit.widgets import LocksmithButton
        create_btn = LocksmithButton("Create ecosystem")
        create_btn.clicked.connect(self.create_ecosystem_clicked.emit)
        header_layout.addWidget(create_btn)

        layout.addWidget(header_row)

        if not ecosystems:
            layout.addWidget(self._build_status_message(
                "No ecosystems yet. Click 'Create ecosystem' to define a grouping of "
                "schemas and issuer AIDs that work together."
            ))
            return section

        for eco in sorted(ecosystems, key=lambda e: e.name):
            layout.addWidget(self._build_ecosystem_row(eco))
        return section

    def _build_ecosystem_row(self, eco: Any) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            "QFrame { background-color: white; border: 1px solid #E0E3EA; border-radius: 6px; }"
            "QFrame:hover { background-color: #F0F3FA; }"
        )
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        rl = QVBoxLayout(row)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.setSpacing(4)

        title = QLabel(f"<b>{eco.name}</b>")
        title.setStyleSheet("font-size: 14px;")
        rl.addWidget(title)

        if eco.description:
            desc = QLabel(eco.description)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
            rl.addWidget(desc)

        counts = QLabel(
            f"<span style='color:{colors.TEXT_SECONDARY}'>"
            f"{len(eco.schema_saids)} schema(s) · {len(eco.issuer_aids)} AID(s)</span>"
        )
        counts.setStyleSheet("font-size: 11px;")
        rl.addWidget(counts)

        name = eco.name
        row.mousePressEvent = lambda _e, n=name: self.show_ecosystem_detail_requested.emit(n)
        return row
```

- [ ] **Step 3: Wire the dialog into the plugin**

In `plugin.py`, add the import:

```python
from locksmith.plugins.ecosystem_viewer.db import EcosystemBaser, EcosystemRecord
from locksmith.plugins.ecosystem_viewer.dialogs import CreateEcosystemDialog
```

In `initialize`, after the existing signal wiring:

```python
        self._overview_page.create_ecosystem_clicked.connect(self._open_create_ecosystem_dialog)
```

Add a method on the plugin:

```python
    def _open_create_ecosystem_dialog(self) -> None:
        dialog = CreateEcosystemDialog(app=self._app, parent=self._overview_page)
        dialog.ecosystem_create_requested.connect(self._on_create_ecosystem)
        dialog.open()

    def _on_create_ecosystem(self, name: str, description: str) -> None:
        if self._db is None:
            logger.warning("EcosystemViewerPlugin: no DB open; cannot create ecosystem")
            return
        try:
            self._db.put_ecosystem(EcosystemRecord(name=name, description=description))
            logger.info(f"Ecosystem '{name}' created")
        except Exception:
            logger.exception("Failed to create ecosystem")
            return
        if self._overview_page is not None:
            self._overview_page.on_show()
```

- [ ] **Step 4: Smoke test create flow**

```bash
pkill -f "python -m locksmith.main" 2>/dev/null; sleep 1
python -m locksmith.main &
```

Open vault `joe`, click Ecosystem Viewer → Overview. The "My ecosystems" section should appear at the top with "0 ecosystem(s) defined" and a Create button. Click Create. In the dialog, enter `test-ecosystem` and a description. Submit. The dialog closes; the ecosystem appears in the list with `0 schema(s) · 0 AID(s)`.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/pages.py src/locksmith/plugins/ecosystem_viewer/plugin.py
git commit -m "feat(ecosystem-viewer): create + list ecosystems on overview (stage 3d)

Adds 'My ecosystems' section to the overview page (above schemas/contacts).
The Create button opens CreateEcosystemDialog; submitted records are
persisted to EcosystemBaser and the list refreshes.

Each ecosystem row is clickable; a Signal is plumbed through but the
detail page itself is the next task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.5: Ecosystem detail page with member-add and remove

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/pages.py`
- Modify: `src/locksmith/plugins/ecosystem_viewer/plugin.py`
- Modify: `src/locksmith/plugins/ecosystem_viewer/dialogs.py`

- [ ] **Step 1: Add a member-picker dialog (schema or AID)**

Append to `src/locksmith/plugins/ecosystem_viewer/dialogs.py`:

```python
from PySide6.QtWidgets import QListWidget, QListWidgetItem


class AddMemberDialog(LocksmithDialog):
    """Pick a schema (or AID) from the wallet and add it to the ecosystem.

    `kind` is 'schema' or 'aid'. `candidates` is a list of (label, key)
    tuples — label is shown to the user, key is what gets emitted.
    """

    member_picked = Signal(str)  # emits the selected key (SAID or AID)

    def __init__(self, kind: str, candidates: list[tuple[str, str]],
                 parent: QWidget | None = None):
        self.kind = kind
        self._candidates = candidates

        content = QWidget()
        content.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addSpacing(12)

        intro = QLabel(
            f"Pick a {kind} from this wallet to add to the ecosystem. "
            f"Only items already in the wallet are eligible — resolve OOBIs / "
            f"add schemas via the regular wallet flow first."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(intro)

        layout.addSpacing(8)

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background: white; border: 1px solid #E0E3EA; border-radius: 4px; font-size: 12px; }"
        )
        for label, key in candidates:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._list.addItem(item)
        self._list.setMinimumHeight(200)
        layout.addWidget(self._list)

        layout.addSpacing(12)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        cancel = LocksmithInvertedButton("Cancel")
        cancel.clicked.connect(self.close)
        add = LocksmithButton("Add")
        add.clicked.connect(self._on_add)
        button_row.addStretch()
        button_row.addWidget(cancel)
        button_row.addWidget(add)

        super().__init__(
            parent=parent,
            title=f"Add {kind} to ecosystem",
            content=content,
            buttons=button_row,
            show_close_button=True,
        )

    def _on_add(self) -> None:
        item = self._list.currentItem()
        if item is None:
            self.show_error(f"Select a {self.kind} first.")
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        self.member_picked.emit(key)
        self.close()
```

- [ ] **Step 2: Add EcosystemDetailPage to pages.py**

Append to `src/locksmith/plugins/ecosystem_viewer/pages.py`:

```python
PAGE_KEY_ECOSYSTEM_DETAIL = "ecosystem_viewer.ecosystem_detail"


class EcosystemDetailPage(QWidget):
    """View + edit a single ecosystem: members, annotations."""

    back_requested = Signal()
    add_schema_clicked = Signal(str)        # emits ecosystem name
    add_aid_clicked = Signal(str)
    remove_schema_clicked = Signal(str, str)  # (ecosystem name, schema_said)
    remove_aid_clicked = Signal(str, str)
    delete_ecosystem_clicked = Signal(str)
    show_schema_detail_requested = Signal(str)

    def __init__(self, app: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self._db: Any = None
        self._current_name: str | None = None

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(colors.BACKGROUND_CONTENT))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        bar = QHBoxLayout()
        bar.setContentsMargins(20, 12, 20, 0)
        back = QLabel('<a href="#back" style="color:#3a5fff;text-decoration:none;">‹ Back to overview</a>')
        back.setOpenExternalLinks(False)
        back.linkActivated.connect(lambda _: self.back_requested.emit())
        back.setStyleSheet("font-size: 13px;")
        bar.addWidget(back)
        bar.addStretch()
        outer.addLayout(bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT}; border: none;")
        scroll.viewport().setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")

        self._content = QWidget()
        self._content.setObjectName("ecosystemDetailContent")
        self._content.setStyleSheet(
            f"#ecosystemDetailContent {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
        )
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(20, 16, 20, 30)
        self._content_layout.setSpacing(16)
        self._content_layout.addStretch()
        scroll.setWidget(self._content)
        outer.addWidget(scroll)

    def set_db(self, db: Any) -> None:
        self._db = db

    def show_ecosystem(self, name: str) -> None:
        self._current_name = name
        self._refresh()

    def _refresh(self) -> None:
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.deleteLater()

        if self._db is None or self._current_name is None:
            self._content_layout.insertWidget(0, QLabel("(no ecosystem loaded)"))
            return

        eco = self._db.get_ecosystem(self._current_name)
        if eco is None:
            self._content_layout.insertWidget(0, QLabel(
                f"Ecosystem '{self._current_name}' not found."
            ))
            return

        self._content_layout.insertWidget(0, self._build_header(eco))
        self._content_layout.insertWidget(1, self._build_schemas_section(eco))
        self._content_layout.insertWidget(2, self._build_aids_section(eco))
        self._content_layout.insertWidget(3, self._build_actions_section(eco))

    def _build_header(self, eco: Any) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        title = QLabel(f"<b>{eco.name}</b>")
        title.setStyleSheet("font-size: 22px;")
        layout.addWidget(title)
        if eco.description:
            desc = QLabel(eco.description)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {colors.TEXT_DARK}; font-size: 13px;")
            layout.addWidget(desc)
        meta = QLabel(
            f"<span style='color:{colors.TEXT_SECONDARY};font-size:11px;'>"
            f"created {eco.created_at} · updated {eco.updated_at} · source {eco.source_kind}</span>"
        )
        layout.addWidget(meta)
        return wrapper

    def _build_schemas_section(self, eco: Any) -> QWidget:
        section = QFrame()
        section.setStyleSheet(
            "QFrame { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
        )
        layout = QVBoxLayout(section)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel(f"Schemas ({len(eco.schema_saids)})")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        head.addWidget(title)
        head.addStretch()
        from locksmith.ui.toolkit.widgets import LocksmithInvertedButton
        add_btn = LocksmithInvertedButton("Add schema")
        add_btn.clicked.connect(lambda: self.add_schema_clicked.emit(eco.name))
        head.addWidget(add_btn)
        head_w = QWidget()
        head_w.setLayout(head)
        layout.addWidget(head_w)

        if not eco.schema_saids:
            empty = QLabel("(no schemas yet)")
            empty.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px; font-style: italic;")
            layout.addWidget(empty)
            return section

        for said in eco.schema_saids:
            row = QFrame()
            row.setStyleSheet("QFrame { background: #F8F9FF; border-radius: 4px; }")
            r = QHBoxLayout(row)
            r.setContentsMargins(10, 6, 10, 6)
            link = QLabel(
                f'<a href="#nav" style="color:#3a5fff;text-decoration:none;">'
                f'<code>{said}</code></a>'
            )
            link.setOpenExternalLinks(False)
            link.linkActivated.connect(lambda _l, s=said: self.show_schema_detail_requested.emit(s))
            link.setStyleSheet("font-size: 12px;")
            link.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse | Qt.TextInteractionFlag.TextSelectableByMouse)
            r.addWidget(link, 1)
            from locksmith.ui.toolkit.widgets.buttons import LocksmithIconButton
            remove_btn = LocksmithIconButton(":/assets/material-icons/close.svg", tooltip="Remove from ecosystem", icon_size=16)
            remove_btn.clicked.connect(lambda _c=False, n=eco.name, s=said: self.remove_schema_clicked.emit(n, s))
            r.addWidget(remove_btn)
            layout.addWidget(row)
        return section

    def _build_aids_section(self, eco: Any) -> QWidget:
        section = QFrame()
        section.setStyleSheet(
            "QFrame { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
        )
        layout = QVBoxLayout(section)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel(f"Issuer AIDs ({len(eco.issuer_aids)})")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        head.addWidget(title)
        head.addStretch()
        from locksmith.ui.toolkit.widgets import LocksmithInvertedButton
        add_btn = LocksmithInvertedButton("Add AID")
        add_btn.clicked.connect(lambda: self.add_aid_clicked.emit(eco.name))
        head.addWidget(add_btn)
        head_w = QWidget()
        head_w.setLayout(head)
        layout.addWidget(head_w)

        if not eco.issuer_aids:
            empty = QLabel("(no issuer AIDs yet)")
            empty.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px; font-style: italic;")
            layout.addWidget(empty)
            return section

        for aid in eco.issuer_aids:
            row = QFrame()
            row.setStyleSheet("QFrame { background: #F8F9FF; border-radius: 4px; }")
            r = QHBoxLayout(row)
            r.setContentsMargins(10, 6, 10, 6)
            label = QLabel(f"<code>{aid}</code>")
            label.setStyleSheet("font-size: 12px;")
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            r.addWidget(label, 1)
            from locksmith.ui.toolkit.widgets.buttons import LocksmithIconButton
            remove_btn = LocksmithIconButton(":/assets/material-icons/close.svg", tooltip="Remove from ecosystem", icon_size=16)
            remove_btn.clicked.connect(lambda _c=False, n=eco.name, a=aid: self.remove_aid_clicked.emit(n, a))
            r.addWidget(remove_btn)
            layout.addWidget(row)
        return section

    def _build_actions_section(self, eco: Any) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()
        from locksmith.ui.toolkit.widgets import LocksmithInvertedButton
        delete_btn = LocksmithInvertedButton("Delete ecosystem")
        delete_btn.clicked.connect(lambda: self.delete_ecosystem_clicked.emit(eco.name))
        layout.addWidget(delete_btn)
        return wrapper
```

- [ ] **Step 3: Register the ecosystem-detail page and wire navigation in plugin.py**

In `src/locksmith/plugins/ecosystem_viewer/plugin.py`, update the imports:

```python
from locksmith.plugins.ecosystem_viewer.pages import (
    EcosystemViewerPage,
    SchemaDetailPage,
    EcosystemDetailPage,
    PAGE_KEY_OVERVIEW,
    PAGE_KEY_SCHEMA_DETAIL,
    PAGE_KEY_ECOSYSTEM_DETAIL,
)
from locksmith.plugins.ecosystem_viewer.dialogs import (
    CreateEcosystemDialog,
    AddMemberDialog,
)
```

In `initialize`, add the new page and wire its signals:

```python
        self._ecosystem_detail_page: EcosystemDetailPage | None = EcosystemDetailPage(app=app)

        # ... existing wiring ...
        self._overview_page.show_ecosystem_detail_requested.connect(self._show_ecosystem_detail)
        self._ecosystem_detail_page.back_requested.connect(self._show_overview)
        self._ecosystem_detail_page.show_schema_detail_requested.connect(self._show_schema_detail)
        self._ecosystem_detail_page.add_schema_clicked.connect(self._open_add_schema_dialog)
        self._ecosystem_detail_page.add_aid_clicked.connect(self._open_add_aid_dialog)
        self._ecosystem_detail_page.remove_schema_clicked.connect(self._remove_schema_member)
        self._ecosystem_detail_page.remove_aid_clicked.connect(self._remove_aid_member)
        self._ecosystem_detail_page.delete_ecosystem_clicked.connect(self._delete_ecosystem)
```

In `on_vault_opened`, also call set_db on the new page:

```python
        if self._ecosystem_detail_page is not None:
            self._ecosystem_detail_page.set_db(self._db)
```

In `on_vault_closed`, also clear:

```python
        if self._ecosystem_detail_page is not None:
            self._ecosystem_detail_page.set_db(None)
```

Update `get_pages`:

```python
    def get_pages(self) -> dict[str, QWidget]:
        pages: dict[str, QWidget] = {}
        if self._overview_page is not None:
            pages[PAGE_KEY_OVERVIEW] = self._overview_page
        if self._schema_detail_page is not None:
            pages[PAGE_KEY_SCHEMA_DETAIL] = self._schema_detail_page
        if self._ecosystem_detail_page is not None:
            pages[PAGE_KEY_ECOSYSTEM_DETAIL] = self._ecosystem_detail_page
        return pages
```

Add the navigation + member-management methods:

```python
    def _show_ecosystem_detail(self, name: str) -> None:
        vault_page = getattr(self._app, "_vault_page", None)
        if vault_page is None:
            return
        vault_page._show_page(PAGE_KEY_ECOSYSTEM_DETAIL)
        if self._ecosystem_detail_page is not None:
            self._ecosystem_detail_page.show_ecosystem(name)

    def _open_add_schema_dialog(self, ecosystem_name: str) -> None:
        if self._db is None:
            return
        vault = getattr(self._app, "vault", None)
        if vault is None:
            return
        eco = self._db.get_ecosystem(ecosystem_name)
        if eco is None:
            return
        # Candidate schemas: every schema in the wallet not already in this ecosystem
        candidates: list[tuple[str, str]] = []
        try:
            for (said,), schemer in vault.hby.db.schema.getItemIter():
                if said in eco.schema_saids:
                    continue
                title = schemer.sed.get("title", "(untitled)")
                candidates.append((f"{title}  —  {said}", said))
        except Exception:
            logger.exception("Failed to enumerate schemas for member-add")

        dialog = AddMemberDialog(
            kind="schema",
            candidates=candidates,
            parent=self._ecosystem_detail_page,
        )
        dialog.member_picked.connect(
            lambda said, n=ecosystem_name: self._add_schema_member(n, said)
        )
        dialog.open()

    def _open_add_aid_dialog(self, ecosystem_name: str) -> None:
        if self._db is None:
            return
        vault = getattr(self._app, "vault", None)
        if vault is None:
            return
        eco = self._db.get_ecosystem(ecosystem_name)
        if eco is None:
            return
        candidates: list[tuple[str, str]] = []
        try:
            for c in vault.org.list():
                aid = c.get("id", "")
                if not aid or aid in eco.issuer_aids:
                    continue
                alias = c.get("alias") or "(no alias)"
                candidates.append((f"{alias}  —  {aid}", aid))
        except Exception:
            logger.exception("Failed to enumerate contacts for member-add")

        dialog = AddMemberDialog(
            kind="aid",
            candidates=candidates,
            parent=self._ecosystem_detail_page,
        )
        dialog.member_picked.connect(
            lambda aid, n=ecosystem_name: self._add_aid_member(n, aid)
        )
        dialog.open()

    def _add_schema_member(self, ecosystem_name: str, schema_said: str) -> None:
        if self._db is None:
            return
        try:
            self._db.add_schema_to_ecosystem(ecosystem_name, schema_said)
        except Exception:
            logger.exception("Failed to add schema to ecosystem")
            return
        self._refresh_ecosystem_detail()

    def _add_aid_member(self, ecosystem_name: str, aid: str) -> None:
        if self._db is None:
            return
        try:
            self._db.add_aid_to_ecosystem(ecosystem_name, aid)
        except Exception:
            logger.exception("Failed to add AID to ecosystem")
            return
        self._refresh_ecosystem_detail()

    def _remove_schema_member(self, ecosystem_name: str, schema_said: str) -> None:
        if self._db is None:
            return
        try:
            self._db.remove_schema_from_ecosystem(ecosystem_name, schema_said)
        except Exception:
            logger.exception("Failed to remove schema from ecosystem")
            return
        self._refresh_ecosystem_detail()

    def _remove_aid_member(self, ecosystem_name: str, aid: str) -> None:
        if self._db is None:
            return
        try:
            self._db.remove_aid_from_ecosystem(ecosystem_name, aid)
        except Exception:
            logger.exception("Failed to remove AID from ecosystem")
            return
        self._refresh_ecosystem_detail()

    def _delete_ecosystem(self, ecosystem_name: str) -> None:
        if self._db is None:
            return
        try:
            self._db.delete_ecosystem(ecosystem_name)
        except Exception:
            logger.exception("Failed to delete ecosystem")
            return
        self._show_overview()

    def _refresh_ecosystem_detail(self) -> None:
        if self._ecosystem_detail_page is not None and self._ecosystem_detail_page._current_name:
            self._ecosystem_detail_page.show_ecosystem(self._ecosystem_detail_page._current_name)
```

- [ ] **Step 4: Smoke test the full flow**

```bash
pkill -f "python -m locksmith.main" 2>/dev/null; sleep 1
python -m locksmith.main &
```

Open vault `joe`, navigate to Ecosystem Viewer → Overview. Use Create ecosystem to make `test-eco`. Click into `test-eco`. Verify:

- Detail page shows the name, description, created/updated timestamps, source
- Schemas section is empty with "Add schema" button
- AIDs section is empty with "Add AID" button
- "Delete ecosystem" button at the bottom
- "‹ Back to overview" returns to the overview

Click Add schema. The dialog should list every schema in the wallet (none should be marked already-included since the ecosystem is empty). Pick one, click Add. The detail page refreshes; the schema appears with a click-through link to the schema-detail page and an X to remove. Add an AID similarly.

Use the X icons to remove members one at a time — list updates each time. Use Delete ecosystem to remove the whole grouping; should land back on the overview with the test-eco gone.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/dialogs.py src/locksmith/plugins/ecosystem_viewer/pages.py src/locksmith/plugins/ecosystem_viewer/plugin.py
git commit -m "feat(ecosystem-viewer): EcosystemDetailPage + member CRUD (stage 3e)

- EcosystemDetailPage shows the ecosystem's metadata, schemas, AIDs,
  with Add/Remove buttons and a Delete-ecosystem action.
- AddMemberDialog presents wallet-known schemas/AIDs as picker candidates
  (excluding items already in the ecosystem).
- Schema rows in the detail page link through to SchemaDetailPage.
- All membership changes go through EcosystemBaser; reverse-membership
  indexes are kept consistent automatically (per stage-3a put_ecosystem
  semantics).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.6: Annotation UI (notes on schemas + AIDs)

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/dialogs.py`
- Modify: `src/locksmith/plugins/ecosystem_viewer/pages.py`
- Modify: `src/locksmith/plugins/ecosystem_viewer/plugin.py`

- [ ] **Step 1: Add an EditAnnotationDialog**

Append to `src/locksmith/plugins/ecosystem_viewer/dialogs.py`:

```python
from PySide6.QtWidgets import QPlainTextEdit


class EditAnnotationDialog(LocksmithDialog):
    """Edit a single annotation note. Tags input is comma-separated."""

    annotation_saved = Signal(str, list)  # (note_text, tags)
    annotation_deleted = Signal()

    def __init__(self, target_label: str, current_note: str, current_tags: list[str],
                 parent: QWidget | None = None):
        content = QWidget()
        content.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addSpacing(12)

        target = QLabel(f"<b>Annotating:</b> {target_label}")
        target.setWordWrap(True)
        target.setStyleSheet(f"color: {colors.TEXT_DARK}; font-size: 12px;")
        layout.addWidget(target)

        layout.addSpacing(8)

        note_label = QLabel("Note")
        note_label.setStyleSheet(f"color: {colors.TEXT_DARK}; font-size: 12px;")
        layout.addWidget(note_label)

        self._note_field = QPlainTextEdit()
        self._note_field.setPlainText(current_note)
        self._note_field.setStyleSheet(
            "QPlainTextEdit { background: white; border: 1px solid #E0E3EA; border-radius: 4px; font-size: 12px; padding: 6px; }"
        )
        self._note_field.setFixedHeight(120)
        layout.addWidget(self._note_field)

        layout.addSpacing(8)

        self._tags_field = FloatingLabelLineEdit("Tags (comma-separated)")
        self._tags_field.setText(", ".join(current_tags))
        self._tags_field.setFixedWidth(360)
        layout.addWidget(self._tags_field)

        layout.addSpacing(12)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        delete_btn = LocksmithInvertedButton("Delete annotation")
        delete_btn.clicked.connect(self._on_delete)
        cancel_btn = LocksmithInvertedButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        save_btn = LocksmithButton("Save")
        save_btn.clicked.connect(self._on_save)
        button_row.addWidget(delete_btn)
        button_row.addStretch()
        button_row.addWidget(cancel_btn)
        button_row.addWidget(save_btn)

        super().__init__(
            parent=parent,
            title="Edit annotation",
            content=content,
            buttons=button_row,
            show_close_button=True,
        )

    def _on_save(self) -> None:
        note = self._note_field.toPlainText().strip()
        tags = [t.strip() for t in self._tags_field.text().split(",") if t.strip()]
        self.annotation_saved.emit(note, tags)
        self.close()

    def _on_delete(self) -> None:
        self.annotation_deleted.emit()
        self.close()
```

- [ ] **Step 2: Add annotation rendering + edit button on SchemaDetailPage**

In `pages.py`, add to the `SchemaDetailPage` class:

```python
    edit_annotation_clicked = Signal(str, str, str)  # (kind, target, target_label)
```

Update `__init__` of `SchemaDetailPage` to initialize `self._db: Any = None` (already added in Task 3.2 step 2).

Add an annotations card to the rendering — modify `_refresh` to insert one more section:

In `_refresh()`, just before the `_build_raw_json_section` call, add:

```python
        self._content_layout.insertWidget(5, self._build_annotation_section(inspection))
```

And renumber the raw JSON insertion to index 6:

```python
        self._content_layout.insertWidget(6, self._build_raw_json_section(inspection))
```

Add the new method:

```python
    def _build_annotation_section(self, i: Any) -> QWidget:
        from locksmith.plugins.ecosystem_viewer.db import AnnotationKind
        frame = self._card("Annotation")
        layout: QVBoxLayout = frame.layout()  # type: ignore[assignment]

        ann = None
        if self._db is not None:
            try:
                ann = self._db.get_annotation(AnnotationKind.SCHEMA, i.schema_said)
            except Exception:
                logger.exception("Failed to load annotation")

        if ann is None or not ann.note:
            empty = QLabel("(no note yet)")
            empty.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px; font-style: italic;")
            layout.addWidget(empty)
        else:
            note = QLabel(ann.note)
            note.setWordWrap(True)
            note.setStyleSheet("font-size: 13px;")
            note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(note)
            if ann.tags:
                tags_label = QLabel(
                    "Tags: " + " ".join(f"<code style='background:#EEF;padding:1px 4px;border-radius:3px;'>{t}</code>" for t in ann.tags)
                )
                tags_label.setStyleSheet("font-size: 12px; margin-top: 4px;")
                layout.addWidget(tags_label)

        from locksmith.ui.toolkit.widgets import LocksmithInvertedButton
        edit_btn = LocksmithInvertedButton("Edit annotation")
        target_label = i.title or i.schema_said[:24]
        edit_btn.clicked.connect(
            lambda: self.edit_annotation_clicked.emit("schema", i.schema_said, target_label)
        )
        layout.addWidget(edit_btn)
        return frame
```

- [ ] **Step 3: Wire annotation editing in plugin.py**

In `src/locksmith/plugins/ecosystem_viewer/plugin.py`, update imports:

```python
from locksmith.plugins.ecosystem_viewer.db import (
    EcosystemBaser,
    EcosystemRecord,
    AnnotationKind,
    AnnotationRecord,
)
from locksmith.plugins.ecosystem_viewer.dialogs import (
    CreateEcosystemDialog,
    AddMemberDialog,
    EditAnnotationDialog,
)
```

In `initialize`, wire the new signal:

```python
        self._schema_detail_page.edit_annotation_clicked.connect(self._open_edit_annotation_dialog)
```

Add the methods:

```python
    def _open_edit_annotation_dialog(self, kind: str, target: str, target_label: str) -> None:
        if self._db is None:
            return
        try:
            current = self._db.get_annotation(AnnotationKind(kind), target)
        except Exception:
            logger.exception("Failed to load annotation for edit")
            current = None
        note = current.note if current else ""
        tags = list(current.tags) if current else []

        dialog = EditAnnotationDialog(
            target_label=target_label,
            current_note=note,
            current_tags=tags,
            parent=self._schema_detail_page,
        )
        dialog.annotation_saved.connect(
            lambda new_note, new_tags, k=kind, t=target: self._save_annotation(k, t, new_note, new_tags)
        )
        dialog.annotation_deleted.connect(
            lambda k=kind, t=target: self._delete_annotation(k, t)
        )
        dialog.open()

    def _save_annotation(self, kind: str, target: str, note: str, tags: list[str]) -> None:
        if self._db is None:
            return
        try:
            self._db.put_annotation(AnnotationRecord(
                kind=AnnotationKind(kind),
                target=target,
                note=note,
                tags=tags,
            ))
        except Exception:
            logger.exception("Failed to save annotation")
            return
        # Refresh whichever page is showing this target
        if self._schema_detail_page is not None and self._schema_detail_page._current_said == target:
            self._schema_detail_page.show_schema(target)

    def _delete_annotation(self, kind: str, target: str) -> None:
        if self._db is None:
            return
        try:
            self._db.delete_annotation(AnnotationKind(kind), target)
        except Exception:
            logger.exception("Failed to delete annotation")
            return
        if self._schema_detail_page is not None and self._schema_detail_page._current_said == target:
            self._schema_detail_page.show_schema(target)
```

- [ ] **Step 4: Smoke test annotation editing**

```bash
pkill -f "python -m locksmith.main" 2>/dev/null; sleep 1
python -m locksmith.main &
```

Open vault `joe`, navigate to Ecosystem Viewer → Overview → click any schema. The detail page should show an "Annotation" card with "(no note yet)" and an "Edit annotation" button. Click Edit. Enter a note and a comma-separated list of tags. Save. The card refreshes showing the note and tag chips. Click Edit again, change the note, Save — refreshes. Click Edit, click Delete annotation — card returns to "(no note yet)".

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/dialogs.py src/locksmith/plugins/ecosystem_viewer/pages.py src/locksmith/plugins/ecosystem_viewer/plugin.py
git commit -m "feat(ecosystem-viewer): per-schema annotations (stage 3f)

SchemaDetailPage gains an Annotation card (rendered before the raw JSON).
EditAnnotationDialog supports save + delete with tags input.

Per-AID and per-credential annotations follow the same EcosystemBaser
API but their UI surfaces are out of scope for this stage and follow
in subsequent commits.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.7: Bump README to mark stages 1-3 done

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/README.md`

- [ ] **Step 1: Update the roadmap table to mark stages 2 and 3 complete**

In `src/locksmith/plugins/ecosystem_viewer/README.md`, find the "What's in this initial commit" section and update its body:

Replace the "What's in this initial commit" block and the "What's deliberately deferred" block with:

```markdown
## What's in this codebase as of stage 3

- `locksmith.acdc.inspector` — full domain classification for ACDC
  instances and schemas, spec-grounded (citations in module docstring).
  Tested via `tests/test_acdc_inspector.py`.
- The plugin's overview page enumerates every schema and contact in
  the wallet with their inspector classifications.
- The schema detail page renders the full inspection result and
  supports intra-plugin navigation between linked schemas via edges
  whose target is also in the wallet.
- `EcosystemBaser` (LMDB, per-vault, plugin-owned) stores user
  ecosystem groupings, annotations, and discovery history. Tested
  via `tests/test_ecosystem_baser.py`.
- The overview adds a "My ecosystems" section with create + browse.
- EcosystemDetailPage supports adding/removing schemas and AIDs as
  members and deleting ecosystems entirely.
- SchemaDetailPage supports per-schema annotations.
- This README documents the design.

## Stages remaining

- **Stage 4: Ecosystem graph view** — directed graph of edge
  relationships between schemas (and optionally between issuer AIDs).
  See the appendix in `docs/superpowers/plans/2026-05-05-ecosystem-viewer-stages-2-3.md`
  for the outline approach.
- **Stage 5: Cross-issuer view** — "everyone who issues schema X."
- **Stage 6: First-person view** — given my held credentials, what
  can I do in this ecosystem.
- **Stage 7: ACDC builder** — `locksmith.acdc.builder` for authoring
  credentials in domain language.
- **Stage 8: Ecosystem export/import** — share ecosystem definitions
  across wallets.
```

- [ ] **Step 2: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/README.md
git commit -m "docs(ecosystem-viewer): mark stages 2-3 complete in README

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.8: Push all stage 2 + 3 commits to origin

- [ ] **Step 1: Push the branch**

```bash
git push origin feat/acdc-ecosystem-viewer
```

Expected: GitHub prints the commit count pushed and confirms branch tracking.

---

## Stage 4 — Ecosystem graph view (outline only)

Goal: visualize the directed graph of edge relationships across schemas (and optionally across issuer AIDs grouped by ecosystem). Click a node to drill into its detail page; click an edge to see the operator and target schema.

Approach to investigate (the right call depends on what's loadable in PySide6):

- **QGraphicsView + QGraphicsScene** — built into Qt, no external deps. Roll our own node/edge renderer with manual layout (e.g. Sugiyama / hierarchical) for small graphs. Best fit for ecosystems with ≤30 nodes.
- **pyqtgraph** — third-party, charting/network plotting library. Some graph layouts available but lower polish than Qt-native.
- **Embed a JS graph library via QWebEngineView** — load a static HTML page with vis-network, cytoscape.js, or d3-force. Highest visual polish; introduces a webengine dep and a JSON serialization layer between Python and JS.

Blockers to resolve before file-level planning:

- Confirm PySide6 includes QtWebEngine in the wallet's bundled dependencies (it's a separate optional install in some PySide6 distributions).
- Decide on layout strategy: hierarchical (good for chain-of-authority), force-directed (good for general relatedness), or both with a toggle.
- Decide whether the graph view operates over (a) all schemas in the wallet, (b) one ecosystem at a time, or (c) selectable.

When stages 4-onward come into view, re-plan with `superpowers:writing-plans` against the answered questions.

---

## Stages 5-8 — Roadmap notes (re-plan when next)

| Stage | Notes |
|---|---|
| 5: Cross-issuer view | "Everyone who issues schema X" — query over the wallet's Reger by schema_said, group by issuer AID. Likely a new page, but the same EcosystemBaser membership indexes can power "ecosystems in which schema X appears." |
| 6: First-person view | Given my held credentials (in vault.rgy.reger), what commands could I authorize across known ecosystems' schemas? Requires a notion of "this schema's authorization pattern" which we haven't formalized yet — likely needs the builder layer to land first. |
| 7: ACDC builder | Domain-language API for composing ACDCs. Companion to the inspector. Authored via TDD in `locksmith.acdc.builder`. |
| 8: Export/import | Serialize an EcosystemRecord (plus the schemas + AIDs it references, optionally) to a portable artifact and re-ingest into another wallet. Format and signing approach TBD. |

---

## Self-review

**Spec coverage check:**

| Stage 2 requirement | Task |
|---|---|
| Detail page renders inspector output | Task 2.2 (sections, edges, raw JSON) |
| Schemas in list become clickable | Task 2.2 (mousePressEvent → Signal) |
| Edge target schemas link through if known | Task 2.2 (`_build_edges_section` with conditional link) |

| Stage 3 requirement | Task |
|---|---|
| Plugin-owned LMDB store | Task 3.1 (EcosystemBaser) |
| Per-vault DB lifecycle | Task 3.2 (on_vault_opened/closed) |
| Create ecosystem | Task 3.3 + 3.4 |
| List ecosystems | Task 3.4 (overview section) |
| Ecosystem detail with members | Task 3.5 (EcosystemDetailPage) |
| Add/remove members | Task 3.5 (AddMemberDialog + remove buttons) |
| Per-schema annotations | Task 3.6 (EditAnnotationDialog + render card) |
| Tests for DB layer | Task 3.1 |
| README updated | Task 3.7 |

**Placeholder scan:** No "TBD," "implement later," "etc." in code blocks. All steps include the actual code. UI smoke tests have explicit verification steps (open vault, click X, expect Y).

**Type consistency:** `EcosystemRecord`, `AnnotationRecord`, `DiscoveryEvent`, `AnnotationKind` are defined in 3.1 and used consistently in 3.4–3.6. `PAGE_KEY_OVERVIEW`, `PAGE_KEY_SCHEMA_DETAIL`, `PAGE_KEY_ECOSYSTEM_DETAIL` defined in `pages.py` and referenced in `plugin.py` consistently. Signal signatures (`show_schema_detail_requested(str)`, `show_ecosystem_detail_requested(str)`, `add_schema_clicked(str)`, etc.) are emitted with matching argument types and connected with matching slot signatures.

**Test infrastructure note:** This plan introduces `tests/` to a codebase that previously had none. Pytest is already configured in `pyproject.toml`'s `[tool.pytest.ini_options]` (`pythonpath = ["src", "."]`), so tests will discover from the project root with no further setup. Future commits should keep adding pure-Python tests as new modules are added.
