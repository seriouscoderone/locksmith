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
from locksmith.plugins.ecosystem_viewer.db import (
    EcosystemBaser,
    EcosystemRecord,
    AnnotationKind,
    AnnotationRecord,
    RoleRecord,
)
from locksmith.plugins.ecosystem_viewer.dialogs import (
    AddMemberDialog,
    ConfirmDeleteEcosystemDialog,
    CreateEcosystemDialog,
    CreateRoleDialog,
    EditAnnotationDialog,
)
from locksmith.plugins.ecosystem_viewer.pages import (
    EcosystemViewerPage,
    SchemaDetailPage,
    EcosystemDetailPage,
    PAGE_KEY_OVERVIEW,
    PAGE_KEY_SCHEMA_DETAIL,
    PAGE_KEY_ECOSYSTEM_DETAIL,
)
from locksmith.ui.toolkit.widgets.buttons import BackButton
from locksmith.ui.vault.menu import MenuButton, MenuSpacer

logger = help.ogler.getLogger(__name__)


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


class EcosystemViewerPlugin(PluginBase):
    """Stages 1-2: domain-classified browsing of the wallet's known schemas + AIDs."""

    @property
    def plugin_id(self) -> str:
        return "ecosystem_viewer"

    def initialize(self, app: Any) -> None:
        self._app = app
        self._db: EcosystemBaser | None = None
        self._overview_page: EcosystemViewerPage | None = EcosystemViewerPage(app=app)
        self._schema_detail_page: SchemaDetailPage | None = SchemaDetailPage(app=app)
        self._ecosystem_detail_page: EcosystemDetailPage | None = EcosystemDetailPage(app=app)
        self._nav_button: MenuButton | None = None

        # Wire intra-plugin navigation
        self._overview_page.show_schema_detail_requested.connect(self._show_schema_detail)
        self._overview_page.create_ecosystem_clicked.connect(self._open_create_ecosystem_dialog)
        self._overview_page.show_issuer_requested.connect(self._show_issuer)
        self._schema_detail_page.back_requested.connect(self._show_overview)
        self._schema_detail_page.show_schema_detail_requested.connect(self._show_schema_detail)
        self._schema_detail_page.edit_annotation_clicked.connect(self._open_edit_annotation_dialog)
        self._schema_detail_page.show_issuer_requested.connect(self._show_issuer)

        # Ecosystem detail page wiring
        self._overview_page.show_ecosystem_detail_requested.connect(self._show_ecosystem_detail)
        self._ecosystem_detail_page.back_requested.connect(self._show_overview)
        self._ecosystem_detail_page.show_schema_detail_requested.connect(self._show_schema_detail)
        self._ecosystem_detail_page.add_schema_clicked.connect(self._open_add_schema_dialog)
        self._ecosystem_detail_page.add_aid_clicked.connect(self._open_add_aid_dialog)
        self._ecosystem_detail_page.remove_schema_clicked.connect(self._remove_schema_member)
        self._ecosystem_detail_page.remove_aid_clicked.connect(self._remove_aid_member)
        self._ecosystem_detail_page.delete_ecosystem_clicked.connect(self._delete_ecosystem)
        self._ecosystem_detail_page.show_issuer_requested.connect(self._show_issuer)
        self._ecosystem_detail_page.add_permitted_issuer_clicked.connect(
            self._add_permitted_issuer
        )
        self._ecosystem_detail_page.remove_permitted_issuer_clicked.connect(
            self._remove_permitted_issuer
        )
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

        logger.info("EcosystemViewerPlugin initialized (stages 1-3)")

    def on_vault_opened(self, vault: Any) -> None:
        # Open per-vault EcosystemBaser. Same pattern as KFBaser.
        self._db = EcosystemBaser(name=f"ecosystem_{vault.hby.name}", reopen=True)
        # Hand the DB reference to pages that need it
        if self._overview_page is not None:
            self._overview_page.set_db(self._db)
            self._overview_page.on_show()
        if self._schema_detail_page is not None:
            self._schema_detail_page.set_db(self._db)
        if self._ecosystem_detail_page is not None:
            self._ecosystem_detail_page.set_db(self._db)

    def on_vault_closed(self, vault: Any) -> None:
        # Close per-vault DB on vault close
        if self._db is not None:
            self._db.close()
            self._db = None
        if self._overview_page is not None:
            self._overview_page.set_db(None)
        if self._schema_detail_page is not None:
            self._schema_detail_page.set_db(None)
        if self._ecosystem_detail_page is not None:
            self._ecosystem_detail_page.set_db(None)

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
        if self._ecosystem_detail_page is not None:
            pages[PAGE_KEY_ECOSYSTEM_DETAIL] = self._ecosystem_detail_page
        return pages

    def _show_overview(self, *_args: Any) -> None:
        vault_page = getattr(self._app, "_vault_page", None)
        if vault_page is None:
            logger.warning("EcosystemViewerPlugin: vault_page not available; skipping overview navigation")
            return
        vault_page._show_page(PAGE_KEY_OVERVIEW)
        if self._overview_page is not None:
            self._overview_page.on_show()

    def _show_schema_detail(self, schema_said: str) -> None:
        vault_page = getattr(self._app, "_vault_page", None)
        if vault_page is None:
            logger.warning(f"EcosystemViewerPlugin: vault_page not available; cannot show schema {schema_said}")
            return
        vault_page._show_page(PAGE_KEY_SCHEMA_DETAIL)
        if self._schema_detail_page is not None:
            self._schema_detail_page.show_schema(schema_said)

    def _show_issuer(self, aid: str, is_self: bool) -> None:
        """Navigate to the wallet's contacts list (for remote AIDs) or the
        identifiers list (for self-AIDs). The list pages don't yet support
        deep-linking to a specific row, so for now we just land the user on
        the right surface; future work can scroll/highlight the AID."""
        vault_page = getattr(self._app, "_vault_page", None)
        if vault_page is None:
            logger.warning(f"EcosystemViewerPlugin: vault_page not available; cannot show issuer {aid}")
            return
        vault_page.nav_menu.pop_to_vault_menu()
        target = "identifiers" if is_self else "remotes"
        vault_page._show_page(target)

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

    def _show_ecosystem_detail(self, name: str) -> None:
        vault_page = getattr(self._app, "_vault_page", None)
        if vault_page is None:
            logger.warning(f"EcosystemViewerPlugin: vault_page not available; cannot show ecosystem {name}")
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

        if not candidates:
            logger.info(
                f"No eligible schemas to add to ecosystem '{ecosystem_name}' "
                f"(every wallet schema is already a member, or the wallet has none yet)"
            )
            self._show_no_candidates_notice(
                title="No schemas to add",
                body=(
                    "Every schema in your wallet is already a member of "
                    "this ecosystem, or your wallet has none yet. Resolve a "
                    "new schema via Credentials → Schemas → Add to bring "
                    "more in."
                ),
            )
            return

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
        seen: set[str] = set(eco.issuer_aids)
        # Remote contacts.
        try:
            for c in vault.org.list():
                aid = c.get("id", "")
                if not aid or aid in seen:
                    continue
                seen.add(aid)
                alias = c.get("alias") or "(no alias)"
                candidates.append((f"{alias}  —  {aid}", aid))
        except Exception:
            logger.exception("Failed to enumerate contacts for member-add")
        # Self-AIDs (the user's own habs) — they may want to add their own
        # AID as an issuer of this ecosystem (e.g., acting as a proxy DOI).
        try:
            for hab in vault.hby.habs.values():
                aid = hab.pre
                if not aid or aid in seen:
                    continue
                seen.add(aid)
                alias = hab.name or "(unnamed)"
                candidates.append((f"{alias} (mine)  —  {aid}", aid))
        except Exception:
            logger.exception("Failed to enumerate self-AIDs for member-add")

        if not candidates:
            logger.info(
                f"No eligible AIDs to add to ecosystem '{ecosystem_name}' "
                f"(every contact + own AID is already a member, or there are none)"
            )
            self._show_no_candidates_notice(
                title="No AIDs to add",
                body=(
                    "Every AID in your wallet (contacts and your own "
                    "identifiers) is already a member of this ecosystem, "
                    "or your wallet has none yet. Add a contact via "
                    "Contacts → Add or create your own identifier first."
                ),
            )
            return

        dialog = AddMemberDialog(
            kind="aid",
            candidates=candidates,
            parent=self._ecosystem_detail_page,
        )
        dialog.member_picked.connect(
            lambda aid, n=ecosystem_name: self._add_aid_member(n, aid)
        )
        dialog.open()

    def _show_no_candidates_notice(self, title: str, body: str) -> None:
        """Tiny modal shown when the user clicks Add Schema / Add AID but
        there's nothing left to add. Without this, the click silently
        does nothing (real bug observed)."""
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
        from locksmith.ui import colors as _colors
        from locksmith.ui.toolkit.widgets import (
            LocksmithButton,
            LocksmithDialog,
        )
        content = QWidget()
        content.setObjectName("ecoNoCandContent")
        content.setStyleSheet(
            f"#ecoNoCandContent {{ background-color: {_colors.BACKGROUND_CONTENT}; }}"
            "#ecoNoCandContent QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(8)
        body_lbl = QLabel(body)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(f"font-size: 13px; color: {_colors.TEXT_DARK};")
        layout.addWidget(body_lbl)
        button_row = QHBoxLayout()
        ok_btn = LocksmithButton("OK")
        button_row.addStretch()
        button_row.addWidget(ok_btn)
        dialog = LocksmithDialog(
            parent=self._ecosystem_detail_page,
            title=title,
            content=content,
            buttons=button_row,
            show_close_button=True,
        )
        ok_btn.clicked.connect(dialog.close)
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

    def _add_permitted_issuer(
        self, ecosystem_name: str, schema_said: str, aid: str,
    ) -> None:
        if self._db is None:
            return
        try:
            self._db.add_permitted_issuer(ecosystem_name, schema_said, aid)
        except Exception:
            logger.exception("Failed to add permitted issuer")
            return
        self._refresh_ecosystem_detail()

    def _remove_permitted_issuer(
        self, ecosystem_name: str, schema_said: str, aid: str,
    ) -> None:
        if self._db is None:
            return
        try:
            self._db.remove_permitted_issuer(ecosystem_name, schema_said, aid)
        except Exception:
            logger.exception("Failed to remove permitted issuer")
            return
        self._refresh_ecosystem_detail()

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
                seen: set[str] = set()
                for c in vault.org.list():
                    aid = c.get("id", "")
                    if aid in eco.issuer_aids and aid not in seen:
                        seen.add(aid)
                        alias = c.get("alias") or "(no alias)"
                        aids.append((f"{alias}  —  {aid[:14]}…", aid))
                # Self-AIDs that are members of the ecosystem.
                self_aids = {hab.pre for hab in vault.hby.habs.values()}
                for aid in eco.issuer_aids:
                    if aid in self_aids and aid not in seen:
                        seen.add(aid)
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

    def _delete_ecosystem(self, ecosystem_name: str) -> None:
        if self._db is None:
            return
        # Look up member counts to populate the confirmation message.
        try:
            rec = self._db.get_ecosystem(ecosystem_name)
        except Exception:
            logger.exception("Failed to load ecosystem for delete confirm")
            return
        if rec is None:
            return
        dialog = ConfirmDeleteEcosystemDialog(
            ecosystem_name=ecosystem_name,
            n_schemas=len(rec.schema_saids),
            n_aids=len(rec.issuer_aids),
            parent=self._ecosystem_detail_page,
        )
        dialog.confirmed.connect(
            lambda n=ecosystem_name: self._delete_ecosystem_confirmed(n)
        )
        dialog.open()

    def _delete_ecosystem_confirmed(self, ecosystem_name: str) -> None:
        if self._db is None:
            return
        try:
            self._db.delete_ecosystem(ecosystem_name)
        except Exception:
            logger.exception("Failed to delete ecosystem")
            return
        self._show_overview()

    def _refresh_ecosystem_detail(self) -> None:
        if self._ecosystem_detail_page is not None and self._ecosystem_detail_page.current_name:
            self._ecosystem_detail_page.show_ecosystem(self._ecosystem_detail_page.current_name)

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
        if self._schema_detail_page is not None and self._schema_detail_page.current_said == target:
            self._schema_detail_page.show_schema(target)

    def _delete_annotation(self, kind: str, target: str) -> None:
        if self._db is None:
            return
        try:
            self._db.delete_annotation(AnnotationKind(kind), target)
        except Exception:
            logger.exception("Failed to delete annotation")
            return
        if self._schema_detail_page is not None and self._schema_detail_page.current_said == target:
            self._schema_detail_page.show_schema(target)
