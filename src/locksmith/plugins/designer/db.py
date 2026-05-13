# -*- encoding: utf-8 -*-
"""DesignerBaser: per-vault LMDB index for the Designer plugin.

Stores fast-lookup metadata about templates the user has interacted with
in this vault. Source of truth for templates themselves is the on-disk
files under TemplateStore. This is purely an index + open-state cache.

Modeled on EcosystemBaser (ecosystem_viewer/db.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from keri.db import dbing, koming


@dataclass
class TemplateIndexRecord:
    """Cached metadata about one template the user has interacted with.

    `ref_key` is a unique key: "draft:<local-id>" or "registered:<SAID>".
    All other fields are display-cache derived from the on-disk file at
    plugin startup or save time.
    """
    ref_key: str = ""
    kind: str = "draft"  # "draft" | "registered"
    label: str = ""
    role_kind: str = ""  # "individual" | "organization" | "system" | ...
    validation_summary: str = "unknown"  # "valid" | "errors" | "warnings"
    modified_at: str = ""  # ISO-8601 UTC
    source: str = "manual"  # "manual" | "imported_file" | "imported_oobi"


@dataclass
class OpenStateRecord:
    """Last-opened template for resume-on-launch.

    Singleton: stored under the constant key ("_open_state",).
    """
    last_opened_ref_key: str = ""
    last_opened_at: str = ""


_OPEN_STATE_KEY = ("_open_state",)


class DesignerBaser(dbing.LMDBer):
    """LMDB database for the Designer plugin."""

    TailDirPath = "keri/dgnr"
    AltTailDirPath = ".keri/dgnr"
    TempPrefix = "dgnr"

    def __init__(
        self,
        name: str = "designer",
        headDirPath: str | None = None,
        reopen: bool = True,
        **kwa,
    ):
        self.index = None
        self.open_state = None
        super().__init__(name=name, headDirPath=headDirPath, reopen=reopen, **kwa)

    def reopen(self, **kwa):
        super().reopen(**kwa)
        self.index = koming.Komer(
            db=self, subkey='idx.', schema=TemplateIndexRecord,
        )
        self.open_state = koming.Komer(
            db=self, subkey='ops.', schema=OpenStateRecord,
        )
        return self.env

    def put_index(self, rec: TemplateIndexRecord) -> None:
        if not rec.ref_key:
            raise ValueError("TemplateIndexRecord.ref_key is required")
        if rec.kind not in ("draft", "registered"):
            raise ValueError(
                f"TemplateIndexRecord.kind must be 'draft' or 'registered'; "
                f"got {rec.kind!r}"
            )
        self.index.pin(keys=(rec.ref_key,), val=rec)

    def get_index(self, ref_key: str) -> TemplateIndexRecord | None:
        return self.index.get(keys=(ref_key,))

    def list_index(self) -> list[TemplateIndexRecord]:
        return [val for (_keys, val) in self.index.getItemIter()]

    def delete_index(self, ref_key: str) -> None:
        """Remove an index record. Idempotent — silently no-op if absent."""
        self.index.rem(keys=(ref_key,))

    def put_open_state(self, rec: OpenStateRecord) -> None:
        self.open_state.pin(keys=_OPEN_STATE_KEY, val=rec)

    def get_open_state(self) -> OpenStateRecord | None:
        return self.open_state.get(keys=_OPEN_STATE_KEY)
