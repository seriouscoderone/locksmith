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

    `permitted_issuers` maps schema_said -> list of AIDs that are
    considered permitted issuers of that schema *within this
    ecosystem*. The ACDC spec doesn't define this — it's a wallet-level
    convention overlay (the spec's EGF concept made first-class), so
    the README's spec-vs-convention block calls it out as such.

    An empty mapping (no entry, or empty list) means "any issuer in
    `issuer_aids` is acceptable" — preserves prior behavior for
    legacy records that predate this field.
    """
    name: str = ""
    description: str = ""
    schema_saids: list[str] = field(default_factory=list)
    issuer_aids: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    source_kind: str = "manual"
    source_url: str = ""
    permitted_issuers: dict = field(default_factory=dict)
    """schema_said -> list[AID]. See class docstring."""


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

        # Diff against the previously stored record (if any) so reverse-membership
        # indexes drop entries for members that were removed in this update.
        # Without this, overwriting a record with a reduced member list silently
        # corrupts the smbr./ambr. indexes.
        old = self.ecosystems.get(keys=(rec.name,))
        old_saids = set(old.schema_saids) if old is not None else set()
        old_aids = set(old.issuer_aids) if old is not None else set()
        new_saids = set(rec.schema_saids)
        new_aids = set(rec.issuer_aids)

        for said in old_saids - new_saids:
            self._remove_membership(self.schema_membership, said, rec.name)
        for aid in old_aids - new_aids:
            self._remove_membership(self.aid_membership, aid, rec.name)

        # Cascade permitted_issuers cleanup so it can never reference
        # schemas or AIDs that aren't members of the ecosystem.
        rec.permitted_issuers = self._cleanup_permitted_issuers(
            rec.permitted_issuers, schema_set=new_saids, aid_set=new_aids,
        )

        self.ecosystems.pin(keys=(rec.name,), val=rec)

        for said in new_saids:
            self._add_membership(self.schema_membership, said, rec.name)
        for aid in new_aids:
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
            # put_ecosystem now diffs old vs new and updates the reverse index
            # correctly, so we can delegate (which also refreshes updated_at).
            self.put_ecosystem(rec)

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
            self.put_ecosystem(rec)

    # --------------------------- Permitted issuers ---------------------------

    def permitted_issuers_for(
        self, ecosystem_name: str, schema_said: str
    ) -> list[str]:
        """Return the AIDs marked as permitted issuers of `schema_said`
        in `ecosystem_name`. Empty list if none are configured (which by
        convention means 'any ecosystem issuer is acceptable')."""
        rec = self.get_ecosystem(ecosystem_name)
        if rec is None:
            return []
        return list(rec.permitted_issuers.get(schema_said, []))

    def set_permitted_issuers(
        self, ecosystem_name: str, schema_said: str, aids: list[str],
    ) -> None:
        """Replace the permitted-issuer list for `schema_said`. The
        schema and each AID must already be members of the ecosystem."""
        rec = self.get_ecosystem(ecosystem_name)
        if rec is None:
            raise KeyError(f"unknown ecosystem '{ecosystem_name}'")
        if schema_said not in rec.schema_saids:
            raise ValueError(
                f"schema '{schema_said}' is not a member of '{ecosystem_name}'"
            )
        members = set(rec.issuer_aids)
        unknown = [a for a in aids if a not in members]
        if unknown:
            raise ValueError(
                f"AID(s) not members of '{ecosystem_name}': {', '.join(unknown)}"
            )
        deduped = sorted(set(aids))
        if deduped:
            rec.permitted_issuers[schema_said] = deduped
        else:
            rec.permitted_issuers.pop(schema_said, None)
        self.put_ecosystem(rec)

    def add_permitted_issuer(
        self, ecosystem_name: str, schema_said: str, aid: str,
    ) -> None:
        cur = self.permitted_issuers_for(ecosystem_name, schema_said)
        if aid in cur:
            return
        self.set_permitted_issuers(ecosystem_name, schema_said, cur + [aid])

    def remove_permitted_issuer(
        self, ecosystem_name: str, schema_said: str, aid: str,
    ) -> None:
        cur = self.permitted_issuers_for(ecosystem_name, schema_said)
        if aid not in cur:
            return
        self.set_permitted_issuers(
            ecosystem_name, schema_said, [a for a in cur if a != aid]
        )

    @staticmethod
    def _cleanup_permitted_issuers(
        mapping: dict, *, schema_set: set, aid_set: set,
    ) -> dict:
        """Drop entries for schemas not in `schema_set` and AIDs not in
        `aid_set`. Empty AID lists are removed entirely."""
        out: dict = {}
        for said, aids in (mapping or {}).items():
            if said not in schema_set:
                continue
            filtered = sorted({a for a in aids if a in aid_set})
            if filtered:
                out[said] = filtered
        return out

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
