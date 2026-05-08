# Stage 13: Roles UI in the List Tab — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Surface the Stage 12 role primitives in the ecosystem detail page's **List** tab. Users can: create roles via a dialog, see existing roles with current resolved member counts, delete roles, set per-schema role-qualification rules, and see a "(via role: X)" indicator on schema rows. No graph-view changes (those land in Stage 14).

**Architecture:** Stage 12 added the data layer (`RoleRecord` + CRUD + resolver). This stage wires it through the `EcosystemDetailPage`'s List-tab body and the plugin's handlers. A new helper `vault_credential_finder(vault)` returns a `find_credentials_of_schema` callable that reads `vault.rgy.reger.creds` — that's the bridge between the resolver's mockable interface and real wallet state.

**Tech Stack:** PySide6 (Qt) — `QFrame` cards, `LocksmithDialog`, `QMenu` for context-menu deletion. Reuses existing chip-row patterns from `_build_permitted_issuers_row`.

**Design source:** `docs/superpowers/designs/2026-05-08-ecosystem-governance-roadmap.md` Stage 13 section.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/locksmith/plugins/ecosystem_viewer/plugin.py` | Modify | New `_credential_finder()` helper that walks `vault.rgy.reger.creds`. New plugin handlers: `_open_create_role_dialog`, `_on_create_role`, `_delete_role`, `_set_qualification_rule`, `_remove_qualification_rule` |
| `src/locksmith/plugins/ecosystem_viewer/dialogs.py` | Modify | New `CreateRoleDialog` class (name + qualification schema picker + issuer role picker + root AIDs picker) |
| `src/locksmith/plugins/ecosystem_viewer/pages.py` | Modify | New `_build_roles_section` method on `EcosystemDetailPage`; new role-card builder; new signals (`create_role_clicked`, `delete_role_clicked`, `set_qualification_rule_clicked`, `remove_qualification_rule_clicked`); update `_build_permitted_issuers_row` to show "(via role: X)" indicator |

No new tests files. The data-layer is fully tested in Stage 12; UI is visual-review-only per the existing convention in this codebase.

---

## Task 1: `vault_credential_finder` helper

Goal: a tiny helper that wraps `vault.rgy.reger.creds` into the `find_credentials_of_schema(schema_said) -> list` callable that the resolver expects. Takes a vault, returns a callable. Pure function; no UI.

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/plugin.py` — append a module-level helper

- [ ] **Step 1: Add the helper at module level**

In `src/locksmith/plugins/ecosystem_viewer/plugin.py`, near the top (after imports, before the `EcosystemViewerPlugin` class), add:

```python
from collections import namedtuple

# Resolver-compatible credential shape: matches what
# EcosystemBaser.resolve_role_members expects (.holder_aid, .issuer_aid,
# .schema_said). Used by vault_credential_finder.
_VaultCred = namedtuple("_VaultCred", ["holder_aid", "issuer_aid", "schema_said"])


def vault_credential_finder(vault: Any):
    """Return a find_credentials_of_schema(schema_said) callable backed
    by `vault.rgy.reger.creds`. The callable yields a tuple per matching
    credential with the three fields the resolver needs.

    Pure function over vault state; no caching. The resolver is invoked
    once per UI render that asks for role members, so for v1 we accept
    the linear scan cost. (Tens to low hundreds of credentials in
    realistic vaults; if this becomes hot, add a per-render cache.)
    """
    def find_credentials_of_schema(schema_said: str):
        if vault is None:
            return []
        try:
            creds_db = vault.rgy.reger.creds
        except AttributeError:
            return []
        out: list = []
        for _keys, serder in creds_db.getItemIter():
            sad = getattr(serder, "sad", None)
            if not isinstance(sad, dict):
                continue
            if sad.get("s") != schema_said:
                continue
            issuer = sad.get("i")
            attr = sad.get("a")
            holder = None
            if isinstance(attr, dict):
                holder = attr.get("i")
            # Untargeted ACDCs have no holder; they cannot qualify role
            # membership (which requires a specific AID to be the holder).
            if not holder or not issuer:
                continue
            out.append(_VaultCred(
                holder_aid=holder,
                issuer_aid=issuer,
                schema_said=schema_said,
            ))
        return out

    return find_credentials_of_schema
```

- [ ] **Step 2: Smoke-test imports**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
.venv/bin/python -c "from locksmith.plugins.ecosystem_viewer.plugin import vault_credential_finder; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Run existing test suite as regression**

```bash
.venv/bin/python -m pytest tests/test_ecosystem_baser.py tests/test_layout.py tests/test_acdc_inspector.py tests/test_lifecycle_widget.py -q
```

Expected: 89 passed.

- [ ] **Step 4: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
git add src/locksmith/plugins/ecosystem_viewer/plugin.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): vault_credential_finder helper (Stage 13)

Module-level helper that wraps vault.rgy.reger.creds into the
find_credentials_of_schema(schema_said) callable that
EcosystemBaser.resolve_role_members expects. Linear scan over the
credentials Komer per call; acceptable at the few-tens-to-low-
hundreds scale of realistic vaults. Untargeted ACDCs (no a.i holder)
are filtered out — they can't qualify role membership.

Per design 2026-05-08-ecosystem-governance-roadmap §2.3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Roles section in the List tab — read-only display

Goal: surface the ecosystem's roles in the List tab. New "Roles" section between the existing Schemas and Issuer AIDs sections. Each role card shows: name, qualification schema (linked text), issuer role (or "(root)"), root AIDs count, current resolved member count. Empty state when no roles. Schema rows in the existing Schemas section gain a "(via role: X)" indicator next to the existing "Permitted issuers:" chip row when `issuer_qualification_rules` has a rule for that schema.

No add/edit/delete UI yet — that's Task 3. This task is purely visualization.

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/pages.py` — `EcosystemDetailPage`

- [ ] **Step 1: Add `_build_roles_section` method**

In `pages.py`, find `class EcosystemDetailPage`. After the existing `_build_aids_section` method (which builds the Issuer AIDs section), add the new roles-section builder:

```python
    def _build_roles_section(self, eco: Any) -> QWidget:
        section = QFrame()
        section.setObjectName("edRolesSection")
        section.setStyleSheet(
            "QFrame#edRolesSection { background-color: white;"
            " border: 1px solid #E0E3EA; border-radius: 8px; }"
            "QFrame#edRolesSection QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(section)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        # Header row.
        head = QHBoxLayout()
        title = QLabel(f"Roles ({len(eco.role_names)})")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        head.addWidget(title)
        head.addStretch()
        add_btn = LocksmithInvertedButton("Add role")
        add_btn.clicked.connect(lambda: self.create_role_clicked.emit(eco.name))
        head.addWidget(add_btn)
        head_w = QWidget()
        head_w.setLayout(head)
        layout.addWidget(head_w)

        # Brief explainer for first-time users.
        explainer = QLabel(
            "A role is a credential-qualified class of AID — anyone holding "
            "the qualification credential automatically qualifies. Roles "
            "replace AID-by-AID enumeration for permitted-issuer policies."
        )
        explainer.setWordWrap(True)
        explainer.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 12px;"
            " font-style: italic;"
        )
        layout.addWidget(explainer)

        if not eco.role_names:
            layout.addWidget(EmptyStateCard(
                "No roles defined yet. Click 'Add role' to define a "
                "credential-qualified class of AID."
            ))
            return section

        # Role cards. The DB stores roles individually; pull each by name.
        for role_name in eco.role_names:
            if self._db is None:
                continue
            role = self._db.get_role(eco.name, role_name)
            if role is None:
                continue
            layout.addWidget(self._build_role_card(eco, role))
        return section

    def _build_role_card(self, eco: Any, role: Any) -> QWidget:
        """One card per role: name, qualification schema (linked),
        issuer role (linked or "(root)"), root AIDs count, resolved
        member count."""
        card = QFrame()
        card.setObjectName("edRoleCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(
            "QFrame#edRoleCard {"
            f" background: {colors.BACKGROUND_SELECTION};"
            " border-radius: 6px; padding: 10px 12px;"
            "}"
            "QFrame#edRoleCard QLabel { background: transparent; }"
        )
        # Right-click context menu wired in Task 3.
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, n=eco.name, r=role.name: self._show_role_context_menu(n, r, pos, card)
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Top row: name + delete affordance (right-click also works)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        name_lbl = QLabel(f"<b>{html.escape(role.name)}</b>")
        name_lbl.setStyleSheet(f"font-size: 14px; color: {colors.TEXT_DARK};")
        head.addWidget(name_lbl)
        head.addStretch()
        head_w = QWidget()
        head_w.setLayout(head)
        layout.addWidget(head_w)

        if role.description:
            desc = QLabel(html.escape(role.description))
            desc.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_SECONDARY};")
            desc.setWordWrap(True)
            layout.addWidget(desc)

        # Detail rows.
        # Qualification schema (clickable to schema detail).
        if role.qualification_schema_said:
            qual_html = (
                f"<span style='color:{colors.TEXT_SECONDARY}'>"
                f"Qualification credential:</span> "
                f"<a href='#nav' style='color:{colors.BLUE_BORDER};"
                "text-decoration:none;'>"
                f"{html.escape(role.qualification_schema_said[:20])}…</a>"
            )
            qual = QLabel(qual_html)
            qual.setOpenExternalLinks(False)
            qual.setStyleSheet("font-size: 11px;")
            qual.linkActivated.connect(
                lambda _l, s=role.qualification_schema_said:
                    self.show_schema_detail_requested.emit(s)
            )
            layout.addWidget(qual)

        # Issuer role.
        if role.issuer_role_name:
            issuer = QLabel(
                f"<span style='color:{colors.TEXT_SECONDARY}'>"
                f"Issued by role:</span> <b>{html.escape(role.issuer_role_name)}</b>"
            )
        else:
            issuer = QLabel(
                f"<span style='color:{colors.TEXT_SECONDARY}'>"
                f"Trust root:</span> "
                f"<b>{len(role.root_issuer_aids)} AID(s)</b>"
            )
        issuer.setStyleSheet("font-size: 11px;")
        layout.addWidget(issuer)

        # Resolved member count (computes via resolver — vault-dependent).
        member_count = self._resolve_role_member_count(eco.name, role.name)
        if member_count is None:
            count_text = "Members: (vault unavailable)"
        else:
            count_text = f"<b>{member_count}</b> current member{'s' if member_count != 1 else ''}"
        count_lbl = QLabel(count_text)
        count_lbl.setStyleSheet(f"font-size: 11px; color: {colors.TEXT_SECONDARY};")
        layout.addWidget(count_lbl)

        return card

    def _resolve_role_member_count(self, eco_name: str, role_name: str) -> int | None:
        """Resolve current role membership and return the count. Returns
        None if vault is unavailable. Tolerates resolver errors (e.g.,
        cycle detection) by returning 0 with a logged warning."""
        if self._db is None:
            return None
        vault = getattr(self.app, "vault", None)
        if vault is None:
            return None
        try:
            from locksmith.plugins.ecosystem_viewer.plugin import vault_credential_finder
            finder = vault_credential_finder(vault)
            members = self._db.resolve_role_members(eco_name, role_name, finder)
            return len(members)
        except ValueError:
            # Cycle detected — show 0 rather than crashing the page render.
            logger.exception(
                f"Role-chain cycle in '{eco_name}/{role_name}'; rendering 0 members"
            )
            return 0
        except Exception:
            logger.exception("Unexpected resolver error")
            return 0

    def _show_role_context_menu(self, eco_name: str, role_name: str,
                                pos: Any, anchor: QWidget) -> None:
        """Stub — populated in Task 3 with Edit / Delete entries.
        Wired now so the right-click handler exists; Task 3 connects it
        to actual actions."""
        # Intentionally empty until Task 3.
        return
```

Add the four new signals to `class EcosystemDetailPage`'s signal block (next to existing `add_permitted_issuer_clicked` etc.):

```python
    create_role_clicked = Signal(str)                 # ecosystem name
    delete_role_clicked = Signal(str, str)            # (eco_name, role_name)
    set_qualification_rule_clicked = Signal(str, str, str)     # (eco, schema, role)
    remove_qualification_rule_clicked = Signal(str, str)       # (eco, schema)
```

- [ ] **Step 2: Insert the roles section into `_refresh`**

Find `EcosystemDetailPage._refresh` (or wherever the List tab body is built — there should be calls like `self._content_layout.insertWidget(0, self._build_schemas_section(eco))` and `self._content_layout.insertWidget(1, self._build_aids_section(eco))`). Insert the roles section between schemas and AIDs:

Before:
```python
        self._content_layout.insertWidget(0, self._build_schemas_section(eco))
        self._content_layout.insertWidget(1, self._build_aids_section(eco))
        self._content_layout.insertWidget(2, self._build_actions_section(eco))
```

After:
```python
        self._content_layout.insertWidget(0, self._build_schemas_section(eco))
        self._content_layout.insertWidget(1, self._build_roles_section(eco))
        self._content_layout.insertWidget(2, self._build_aids_section(eco))
        self._content_layout.insertWidget(3, self._build_actions_section(eco))
```

(Note: if the existing indices in this code differ, preserve their relative order — schemas first, then roles, then aids, then actions.)

- [ ] **Step 3: Add "(via role: X)" indicator to `_build_permitted_issuers_row`**

Find `_build_permitted_issuers_row` in `pages.py` (it's used for the per-schema "Permitted issuers:" chip row — look for the prefix `QLabel("Permitted issuers:")`).

The method currently iterates `eco.permitted_issuers.get(said, [])` and renders chip widgets. Insert a new label BEFORE the chips when `issuer_qualification_rules` contains an entry for this schema. Find the section where the prefix label is added:

```python
        prefix = QLabel("Permitted issuers:")
        prefix.setStyleSheet(
            f"font-size: 11px; color: {colors.TEXT_SECONDARY};"
            " font-weight: 600; letter-spacing: 0.02em;"
        )
        row.addWidget(prefix)
```

Right after the prefix label, add the role indicator:

```python
        prefix = QLabel("Permitted issuers:")
        prefix.setStyleSheet(
            f"font-size: 11px; color: {colors.TEXT_SECONDARY};"
            " font-weight: 600; letter-spacing: 0.02em;"
        )
        row.addWidget(prefix)

        # "(via role: X)" indicator if a qualification rule is set.
        rule_role = eco.issuer_qualification_rules.get(said)
        if rule_role:
            role_lbl = QLabel(f"(via role: <b>{html.escape(rule_role)}</b>)")
            role_lbl.setStyleSheet(
                f"font-size: 11px; color: {colors.TEXT_DARK};"
            )
            row.addWidget(role_lbl)
```

- [ ] **Step 4: Smoke-test the wallet**

```bash
pgrep -f "locksmith.main" | xargs -r kill -9 2>/dev/null
sleep 1
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
.venv/bin/python -m locksmith.main &
WALLET_PID=$!
sleep 6
LOG=$(ls -t /private/tmp/claude-501/*/tasks/*.output 2>/dev/null | head -1)
[ -n "$LOG" ] && tail -10 "$LOG"
kill -9 $WALLET_PID 2>/dev/null
```

Confirm clean startup (no NEW tracebacks beyond the pre-existing `_panel_width` warning). Open an ecosystem detail → List tab. You should see a new "Roles (0)" section between Schemas and Issuer AIDs with the empty-state card and an "Add role" button (button does nothing yet — that's Task 3).

- [ ] **Step 5: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
git add src/locksmith/plugins/ecosystem_viewer/pages.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): Roles section in the List tab (Stage 13)

EcosystemDetailPage's List tab now has a Roles section between the
Schemas and Issuer AIDs sections. Each role card shows name,
qualification schema (clickable), issuer role (or root-AID count),
and current resolved member count via the Stage 12 resolver. Empty
state when no roles defined.

Schema member rows in the Schemas section now show a "(via role: X)"
indicator on the Permitted issuers sub-line when issuer_qualification
_rules has an entry for that schema.

Four new signals on EcosystemDetailPage (create_role_clicked,
delete_role_clicked, set_qualification_rule_clicked,
remove_qualification_rule_clicked) — wired to handlers in a follow-up
task. The right-click context menu on role cards is stubbed; populated
in Task 3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: CreateRoleDialog + delete + plugin handlers

Goal: dialog for creating a role + right-click delete. Plugin handlers wire the new signals through to `put_role` / `delete_role`.

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/dialogs.py` — new `CreateRoleDialog` class
- Modify: `src/locksmith/plugins/ecosystem_viewer/plugin.py` — new handlers + signal connections
- Modify: `src/locksmith/plugins/ecosystem_viewer/pages.py` — populate the role-card context menu

- [ ] **Step 1: Add `CreateRoleDialog` to `dialogs.py`**

In `src/locksmith/plugins/ecosystem_viewer/dialogs.py`, append at the end (after the existing `ConfirmDeleteEcosystemDialog`):

```python
class CreateRoleDialog(LocksmithDialog):
    """Modal for defining a new role in an ecosystem.

    A role is a credential-qualified class of AID. The user picks:
    - A name for the role (free text)
    - The qualification schema (a member schema of the ecosystem whose
      holders qualify for this role)
    - Either an issuer role (chained role — qualification must come from
      a member of that role) OR a list of root issuer AIDs (root role —
      enumerated trust roots)
    """

    role_create_requested = Signal(str, str, str, str, list)
    """(ecosystem_name, role_name, description, qualification_schema_said,
    issuer_role_name, root_issuer_aids). issuer_role_name is "" when the
    role is a root role."""

    def __init__(
        self,
        ecosystem_name: str,
        schemas: list[tuple[str, str]],   # list of (label, schema_said) for picker
        existing_roles: list[str],         # role names in the ecosystem
        issuer_aids: list[tuple[str, str]],  # list of (label, aid) for picker
        parent: QWidget | None = None,
    ):
        from PySide6.QtWidgets import QComboBox, QListWidget, QListWidgetItem
        self.ecosystem_name = ecosystem_name
        self._schema_options = schemas
        self._issuer_aids = issuer_aids

        content = QWidget()
        content.setObjectName("createRoleContent")
        content.setStyleSheet(
            f"#createRoleContent {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
            "#createRoleContent QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addSpacing(8)
        intro = QLabel(
            "A role is a credential-qualified class of AID. Pick a "
            "qualification credential and define how role members are "
            "issued credentials of that schema (root: enumerated AIDs, "
            "or chained: from members of another role)."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(intro)

        layout.addSpacing(8)

        # Name
        self._name_field = FloatingLabelLineEdit("Role name (e.g., 'state-doi')")
        self._name_field.setFixedWidth(420)
        layout.addWidget(self._name_field)

        layout.addSpacing(8)

        self._desc_field = FloatingLabelLineEdit("Description (optional)")
        self._desc_field.setFixedWidth(420)
        layout.addWidget(self._desc_field)

        layout.addSpacing(12)

        # Qualification schema picker
        layout.addWidget(QLabel("Qualification credential schema:"))
        self._schema_combo = QComboBox()
        self._schema_combo.setFixedWidth(420)
        if not schemas:
            self._schema_combo.addItem("(no schemas in this ecosystem)", "")
            self._schema_combo.setEnabled(False)
        else:
            for label, said in schemas:
                self._schema_combo.addItem(label, said)
        layout.addWidget(self._schema_combo)

        layout.addSpacing(12)

        # Issuer role picker (or "(root)" + AIDs)
        layout.addWidget(QLabel("Issuer role:"))
        self._issuer_role_combo = QComboBox()
        self._issuer_role_combo.setFixedWidth(420)
        self._issuer_role_combo.addItem("(root role — pick AIDs below)", "")
        for r in existing_roles:
            self._issuer_role_combo.addItem(r, r)
        layout.addWidget(self._issuer_role_combo)

        layout.addSpacing(8)

        # Root issuer AIDs picker (only relevant for root role)
        self._root_aids_label = QLabel("Trust-root AIDs (only for root role):")
        layout.addWidget(self._root_aids_label)
        self._root_aids_list = QListWidget()
        self._root_aids_list.setFixedWidth(420)
        self._root_aids_list.setFixedHeight(100)
        self._root_aids_list.setSelectionMode(
            QListWidget.SelectionMode.MultiSelection
        )
        for label, aid in issuer_aids:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, aid)
            self._root_aids_list.addItem(item)
        layout.addWidget(self._root_aids_list)

        # Toggle the AIDs list enabled-state based on issuer role choice.
        def _on_issuer_role_changed(idx: int) -> None:
            is_root = self._issuer_role_combo.itemData(idx) == ""
            self._root_aids_label.setVisible(is_root)
            self._root_aids_list.setVisible(is_root)
        self._issuer_role_combo.currentIndexChanged.connect(_on_issuer_role_changed)
        _on_issuer_role_changed(0)

        layout.addSpacing(8)

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
            title=f"Add role to '{ecosystem_name}'",
            content=content,
            buttons=button_row,
            show_close_button=True,
        )

    def _on_create(self) -> None:
        name = self._name_field.text().strip()
        if not name:
            self.show_error("Role name is required.")
            return
        desc = self._desc_field.text().strip()
        schema_said = self._schema_combo.currentData() or ""
        if not schema_said:
            self.show_error("A qualification schema is required.")
            return
        issuer_role = self._issuer_role_combo.currentData() or ""
        root_aids: list[str] = []
        if not issuer_role:
            for item in self._root_aids_list.selectedItems():
                root_aids.append(item.data(Qt.ItemDataRole.UserRole))
            if not root_aids:
                self.show_error(
                    "Root roles require at least one trust-root AID."
                )
                return
        self.role_create_requested.emit(
            self.ecosystem_name, name, desc, schema_said, issuer_role, root_aids,
        )
        self.close()
```

The `Signal(str, str, str, str, list)` declaration in the docstring is WRONG (it's 5 args but the docstring lists 6). Fix the actual `Signal(...)` call: it should be `Signal(str, str, str, str, str, list)` — six args: ecosystem_name, role_name, description, qualification_schema_said, issuer_role_name, root_issuer_aids:

```python
    role_create_requested = Signal(str, str, str, str, str, list)
```

(Replace the line in the class above accordingly.)

- [ ] **Step 2: Add plugin handlers**

In `src/locksmith/plugins/ecosystem_viewer/plugin.py`:

First, import the new dialog at the top:

```python
from locksmith.plugins.ecosystem_viewer.dialogs import (
    AddMemberDialog,
    ConfirmDeleteEcosystemDialog,
    CreateEcosystemDialog,
    CreateRoleDialog,
    EditAnnotationDialog,
)
```

Then in `EcosystemViewerPlugin.initialize`, find the `EcosystemDetailPage` signal connections (the block with `add_permitted_issuer_clicked.connect`, etc.). Append these four new connections:

```python
        self._ecosystem_detail_page.create_role_clicked.connect(
            self._open_create_role_dialog
        )
        self._ecosystem_detail_page.delete_role_clicked.connect(
            self._delete_role
        )
        self._ecosystem_detail_page.set_qualification_rule_clicked.connect(
            self._set_qualification_rule
        )
        self._ecosystem_detail_page.remove_qualification_rule_clicked.connect(
            self._remove_qualification_rule
        )
```

Then add the four handler methods anywhere in the class (e.g., after the existing `_remove_permitted_issuer`):

```python
    def _open_create_role_dialog(self, ecosystem_name: str) -> None:
        if self._db is None:
            return
        eco = self._db.get_ecosystem(ecosystem_name)
        if eco is None:
            return
        vault = getattr(self._app, "vault", None)

        # Build the schema picker options: (label, said) tuples for each
        # schema in the ecosystem.
        schemas: list[tuple[str, str]] = []
        if vault is not None:
            try:
                for said in eco.schema_saids:
                    schemer = vault.hby.db.schema.get(keys=(said,))
                    title = (schemer.sed.get("title") if schemer else None) or "(untitled)"
                    schemas.append((f"{title}  —  {said[:14]}…", said))
            except Exception:
                logger.exception("Failed to enumerate ecosystem schemas")

        # Build the issuer-AID picker options (for the root-AIDs multi-select).
        aids: list[tuple[str, str]] = []
        if vault is not None:
            try:
                for c in vault.org.list():
                    aid = c.get("id", "")
                    if aid in eco.issuer_aids:
                        alias = c.get("alias") or "(no alias)"
                        aids.append((f"{alias}  —  {aid[:14]}…", aid))
                # Self-AIDs that are members of the ecosystem.
                self_aids = {hab.pre for hab in vault.hby.habs.values()}
                for aid in eco.issuer_aids:
                    if aid in self_aids and not any(a == aid for _, a in aids):
                        hab = vault.hby.habByPre(aid)
                        alias = hab.name if hab else "(self)"
                        aids.append((f"{alias} (mine)  —  {aid[:14]}…", aid))
            except Exception:
                logger.exception("Failed to enumerate ecosystem AIDs")

        dialog = CreateRoleDialog(
            ecosystem_name=ecosystem_name,
            schemas=schemas,
            existing_roles=list(eco.role_names),
            issuer_aids=aids,
            parent=self._ecosystem_detail_page,
        )
        dialog.role_create_requested.connect(self._on_create_role)
        dialog.open()

    def _on_create_role(
        self,
        ecosystem_name: str,
        role_name: str,
        description: str,
        qualification_schema_said: str,
        issuer_role_name: str,
        root_issuer_aids: list,
    ) -> None:
        if self._db is None:
            return
        try:
            self._db.put_role(EcosystemRecord and __import__(
                "locksmith.plugins.ecosystem_viewer.db", fromlist=["RoleRecord"]
            ).RoleRecord(
                ecosystem_name=ecosystem_name,
                name=role_name,
                description=description,
                qualification_schema_said=qualification_schema_said,
                issuer_role_name=issuer_role_name,
                root_issuer_aids=list(root_issuer_aids),
            ))
        except Exception:
            logger.exception(f"Failed to create role '{role_name}'")
            return
        self._refresh_ecosystem_detail()

    def _delete_role(self, ecosystem_name: str, role_name: str) -> None:
        if self._db is None:
            return
        try:
            self._db.delete_role(ecosystem_name, role_name)
        except Exception:
            logger.exception(f"Failed to delete role '{role_name}'")
            return
        self._refresh_ecosystem_detail()

    def _set_qualification_rule(
        self, ecosystem_name: str, schema_said: str, role_name: str,
    ) -> None:
        if self._db is None:
            return
        try:
            eco = self._db.get_ecosystem(ecosystem_name)
            if eco is None:
                return
            eco.issuer_qualification_rules = dict(eco.issuer_qualification_rules)
            eco.issuer_qualification_rules[schema_said] = role_name
            self._db.put_ecosystem(eco)
        except Exception:
            logger.exception("Failed to set qualification rule")
            return
        self._refresh_ecosystem_detail()

    def _remove_qualification_rule(
        self, ecosystem_name: str, schema_said: str,
    ) -> None:
        if self._db is None:
            return
        try:
            eco = self._db.get_ecosystem(ecosystem_name)
            if eco is None:
                return
            eco.issuer_qualification_rules = dict(eco.issuer_qualification_rules)
            eco.issuer_qualification_rules.pop(schema_said, None)
            self._db.put_ecosystem(eco)
        except Exception:
            logger.exception("Failed to remove qualification rule")
            return
        self._refresh_ecosystem_detail()
```

Notice the `_on_create_role` method uses an awkward import-then-construct pattern. Replace it with a cleaner version using a top-level import. At the top of `plugin.py`, find:

```python
from locksmith.plugins.ecosystem_viewer.db import (
    EcosystemBaser,
    EcosystemRecord,
    AnnotationKind,
    AnnotationRecord,
)
```

Add `RoleRecord` to that import:

```python
from locksmith.plugins.ecosystem_viewer.db import (
    EcosystemBaser,
    EcosystemRecord,
    AnnotationKind,
    AnnotationRecord,
    RoleRecord,
)
```

Then simplify `_on_create_role`:

```python
    def _on_create_role(
        self,
        ecosystem_name: str,
        role_name: str,
        description: str,
        qualification_schema_said: str,
        issuer_role_name: str,
        root_issuer_aids: list,
    ) -> None:
        if self._db is None:
            return
        try:
            self._db.put_role(RoleRecord(
                ecosystem_name=ecosystem_name,
                name=role_name,
                description=description,
                qualification_schema_said=qualification_schema_said,
                issuer_role_name=issuer_role_name,
                root_issuer_aids=list(root_issuer_aids),
            ))
        except Exception:
            logger.exception(f"Failed to create role '{role_name}'")
            return
        self._refresh_ecosystem_detail()
```

- [ ] **Step 3: Populate the role-card context menu in `pages.py`**

Find the stub `_show_role_context_menu` from Task 2:

```python
    def _show_role_context_menu(self, eco_name: str, role_name: str,
                                pos: Any, anchor: QWidget) -> None:
        # Intentionally empty until Task 3.
        return
```

Replace with:

```python
    def _show_role_context_menu(self, eco_name: str, role_name: str,
                                pos: Any, anchor: QWidget) -> None:
        menu = QMenu(self)
        delete_action = menu.addAction(f"Delete role '{role_name}'")
        chosen = menu.exec(anchor.mapToGlobal(pos))
        if chosen is delete_action:
            self.delete_role_clicked.emit(eco_name, role_name)
```

- [ ] **Step 4: Smoke-test the wallet**

```bash
pgrep -f "locksmith.main" | xargs -r kill -9 2>/dev/null
sleep 1
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
.venv/bin/python -m locksmith.main &
WALLET_PID=$!
sleep 6
LOG=$(ls -t /private/tmp/claude-501/*/tasks/*.output 2>/dev/null | head -1)
[ -n "$LOG" ] && tail -10 "$LOG"
kill -9 $WALLET_PID 2>/dev/null
```

Confirm clean startup. Open an ecosystem detail page → List tab → click "Add role". The dialog should open with: a name field, description field, schema picker (populated from ecosystem schemas), issuer-role picker (with "(root role — pick AIDs below)" + any existing roles), and a root-AIDs multi-select that toggles visible based on the issuer-role choice. After submitting, the new role should appear as a card in the Roles section. Right-click the card → "Delete role 'X'" should remove it.

- [ ] **Step 5: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
git add src/locksmith/plugins/ecosystem_viewer/dialogs.py src/locksmith/plugins/ecosystem_viewer/plugin.py src/locksmith/plugins/ecosystem_viewer/pages.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): CreateRoleDialog + delete role + plugin handlers (Stage 13)

CreateRoleDialog modal with name + description + qualification schema
picker + issuer role picker + (when root role) trust-root AIDs
multi-select. Toggle hides AIDs picker when a non-root issuer role is
chosen. Validation: name required, qualification schema required,
root-role requires at least one trust-root AID.

Plugin handlers wire the four new EcosystemDetailPage signals through
to EcosystemBaser CRUD: create_role → put_role; delete_role →
delete_role; set/remove qualification rule → put_ecosystem with
mutated issuer_qualification_rules.

Right-click on a role card now shows a "Delete role" context menu
entry. Edit deferred to a follow-up — for now, delete + recreate.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Per-schema qualification-rule UI

Goal: add the user-facing UI to set and remove `issuer_qualification_rules` entries on individual schema rows in the List tab. The "(via role: X)" indicator from Task 2 currently shows the rule but has no way to add or remove. This task adds: a "+ Set role" affordance after the indicator chip when no rule is set; an "×" to remove the rule when set.

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/pages.py` — extend `_build_permitted_issuers_row`

- [ ] **Step 1: Replace the indicator from Task 2 with an interactive control**

Find the block added in Task 2 step 3:

```python
        # "(via role: X)" indicator if a qualification rule is set.
        rule_role = eco.issuer_qualification_rules.get(said)
        if rule_role:
            role_lbl = QLabel(f"(via role: <b>{html.escape(rule_role)}</b>)")
            role_lbl.setStyleSheet(
                f"font-size: 11px; color: {colors.TEXT_DARK};"
            )
            row.addWidget(role_lbl)
```

Replace with:

```python
        # Qualification rule chip — interactive: shows current rule with
        # remove-×, or a "+ Set role" affordance when no rule is set.
        rule_role = eco.issuer_qualification_rules.get(said)
        if rule_role:
            role_chip = QFrame()
            role_chip.setObjectName("edQualRuleChip")
            role_chip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            role_chip.setStyleSheet(
                "QFrame#edQualRuleChip {"
                f" background: {colors.BACKGROUND_SELECTION};"
                " border-radius: 9px; padding: 1px 4px 1px 8px; min-height: 18px;"
                "}"
                "QFrame#edQualRuleChip QLabel { background: transparent; }"
            )
            chip_l = QHBoxLayout(role_chip)
            chip_l.setContentsMargins(0, 0, 0, 0)
            chip_l.setSpacing(2)
            chip_l.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            label = QLabel(f"via role: <b>{html.escape(rule_role)}</b>")
            label.setStyleSheet(f"font-size: 11px; color: {colors.TEXT_DARK};")
            chip_l.addWidget(label)
            rm = QToolButton()
            rm.setText("×")
            rm.setCursor(Qt.CursorShape.PointingHandCursor)
            rm.setToolTip("Remove role qualification rule for this schema")
            rm.setStyleSheet(
                "QToolButton { background: transparent; border: none;"
                f" padding: 0 4px; font-size: 13px; color: {colors.TEXT_SECONDARY}; }}"
                f"QToolButton:hover {{ color: {colors.DANGER}; }}"
            )
            rm.clicked.connect(
                lambda _c=False, n=eco.name, s=said:
                    self.remove_qualification_rule_clicked.emit(n, s)
            )
            chip_l.addWidget(rm)
            row.addWidget(role_chip)
        else:
            # "+ Set role" affordance — only enabled when the ecosystem
            # has at least one role defined.
            set_btn = QToolButton()
            set_btn.setText("+ Set role")
            set_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if not eco.role_names:
                set_btn.setEnabled(False)
                set_btn.setToolTip(
                    "Define a role first via the Roles section above"
                )
            else:
                set_btn.setToolTip(
                    "Set a role-based permitted-issuer rule for this schema"
                )
            set_btn.setStyleSheet(
                "QToolButton {"
                f" background: white; border: 1px dashed {colors.BORDER};"
                " border-radius: 9px; padding: 0 6px; min-height: 18px;"
                f" font-size: 11px; color: {colors.TEXT_SECONDARY};"
                "}"
                f"QToolButton:hover {{ border-color: {colors.PRIMARY};"
                f" color: {colors.PRIMARY}; }}"
                f"QToolButton:disabled {{ color: {colors.TEXT_MUTED};"
                f" border-color: {colors.BORDER}; }}"
            )
            set_btn.clicked.connect(
                lambda _c=False, e=eco, s=said:
                    self._show_set_qualification_rule_menu(e, s)
            )
            row.addWidget(set_btn)
```

- [ ] **Step 2: Add the menu helper**

Anywhere inside `class EcosystemDetailPage`, add:

```python
    def _show_set_qualification_rule_menu(self, eco: Any, schema_said: str) -> None:
        """Pop a menu of available roles in this ecosystem; on selection
        emit set_qualification_rule_clicked."""
        if not eco.role_names:
            return
        menu = QMenu(self)
        for role_name in eco.role_names:
            action = menu.addAction(role_name)
            action.triggered.connect(
                lambda _c=False, n=eco.name, s=schema_said, r=role_name:
                    self.set_qualification_rule_clicked.emit(n, s, r)
            )
        menu.exec(QCursor.pos())
```

- [ ] **Step 3: Smoke-test**

```bash
pgrep -f "locksmith.main" | xargs -r kill -9 2>/dev/null
sleep 1
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
.venv/bin/python -m locksmith.main &
WALLET_PID=$!
sleep 6
LOG=$(ls -t /private/tmp/claude-501/*/tasks/*.output 2>/dev/null | head -1)
[ -n "$LOG" ] && tail -10 "$LOG"
kill -9 $WALLET_PID 2>/dev/null
```

Confirm clean startup. Test scenario: ecosystem with roles defined → on a schema row's "Permitted issuers:" line, click "+ Set role" → menu of role names appears → pick one → "(via role: X)" chip appears with × button → click × to remove.

- [ ] **Step 4: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
git add src/locksmith/plugins/ecosystem_viewer/pages.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): per-schema qualification-rule UI (Stage 13)

The "(via role: X)" indicator on each schema row's Permitted issuers
sub-line is now interactive: clickable chip with × to remove an
existing rule, or a "+ Set role" affordance to add one when no rule
exists. The "+ Set role" pops a menu of the ecosystem's defined roles;
disabled with a helpful tooltip when no roles exist yet.

Wires through the existing set_qualification_rule_clicked /
remove_qualification_rule_clicked signals to the plugin handlers from
Task 3, which mutate eco.issuer_qualification_rules and re-render.

Per design 2026-05-08-ecosystem-governance-roadmap §2.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-review checklist results

**Spec coverage:**
- §2 Roles section in List tab → Task 2 ✓
- §3 Qualification rule indicator on schema rows → Tasks 2 + 4 ✓
- §3 CreateRoleDialog → Task 3 ✓
- §3 Right-click delete on role card → Task 3 ✓
- §3 vault-backed credential finder → Task 1 ✓
- Edit role: explicitly deferred (delete + recreate is acceptable for v1)

**Type consistency:**
- `RoleRecord` constructed in plugin.py (Task 3) using same field names as the dataclass in db.py (added in Stage 12 T2) ✓
- `vault_credential_finder(vault) -> callable` matches the resolver's `find_credentials_of_schema` signature ✓
- The four new `EcosystemDetailPage` signals (Task 2) all have plugin handlers connected (Task 3) ✓

**Placeholder scan:** every step shows actual code; no "TBD"; the Task 2 stub `_show_role_context_menu` is documented as a stub with the actual implementation in Task 3.

**No code in this stage modifies the data layer** — Stage 12 already locked it in. This stage is purely UI + plugin glue.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-05-08-stage-13-roles-list-tab-ui.md`. Subagent-driven execution continues per the prior pattern.
