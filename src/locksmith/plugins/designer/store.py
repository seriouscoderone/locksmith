# -*- encoding: utf-8 -*-
"""File-on-disk template store for the Designer plugin.

Layout under `root`:

    root/templates/registered/<SAID>/{micro-app-template.json, metadata.json}
    root/templates/drafts/<local-id>/{micro-app-template.json, metadata.json}

`root` is set by the plugin to the canonical tail dir (keri/dgnr) or a
test temporary directory. The store treats both subdirs as shared
across vaults; vault-specific concerns live in DesignerBaser.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

TEMPLATE_FILENAME = "micro-app-template.json"
METADATA_FILENAME = "metadata.json"


class TemplateNotFound(Exception):
    """Raised when a ref does not resolve to an on-disk directory."""


class TemplateAlreadyExists(Exception):
    """Raised when saving registered without overwrite and dir exists."""


@dataclass(frozen=True)
class TemplateRef:
    """Locator for a template on disk.

    Exactly one of (local_id, said) is set, matching `kind`.
    """
    kind: Literal["draft", "registered"]
    local_id: str | None
    said: str | None

    def __post_init__(self) -> None:
        if self.kind == "draft":
            if not self.local_id or self.said is not None:
                raise ValueError(
                    f"draft refs must have local_id set and said=None; got "
                    f"local_id={self.local_id!r}, said={self.said!r}"
                )
        elif self.kind == "registered":
            if not self.said or self.local_id is not None:
                raise ValueError(
                    f"registered refs must have said set and local_id=None; got "
                    f"local_id={self.local_id!r}, said={self.said!r}"
                )
        else:
            raise ValueError(f"unknown kind: {self.kind!r}")


class TemplateStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    @property
    def _templates_dir(self) -> Path:
        return self.root / "templates"

    @property
    def _registered_dir(self) -> Path:
        return self._templates_dir / "registered"

    @property
    def _drafts_dir(self) -> Path:
        return self._templates_dir / "drafts"

    def _write_pair_atomic(
        self, dir_path: Path, doc: dict[str, Any], metadata: dict[str, Any],
    ) -> None:
        """Write template + metadata atomically via .tmp + Path.replace().

        Both files are written to sibling .tmp paths first; only after both
        succeed are they each renamed into place. A crash before the final
        rename leaves no half-written final files (list_templates ignores
        .tmp files because it checks for the canonical filename).
        """
        dir_path.mkdir(parents=True, exist_ok=True)
        doc_tmp = dir_path / (TEMPLATE_FILENAME + ".tmp")
        meta_tmp = dir_path / (METADATA_FILENAME + ".tmp")
        doc_tmp.write_text(json.dumps(doc, indent=2, sort_keys=True))
        meta_tmp.write_text(json.dumps(metadata, indent=2, sort_keys=True))
        doc_tmp.replace(dir_path / TEMPLATE_FILENAME)
        meta_tmp.replace(dir_path / METADATA_FILENAME)

    def _ref_dir(self, ref: TemplateRef) -> Path:
        if ref.kind == "registered":
            assert ref.said is not None
            return self._registered_dir / ref.said
        assert ref.local_id is not None
        return self._drafts_dir / ref.local_id

    def list_templates(self) -> list[TemplateRef]:
        refs: list[TemplateRef] = []
        if self._registered_dir.exists():
            for child in sorted(self._registered_dir.iterdir()):
                if child.is_dir() and (child / TEMPLATE_FILENAME).exists():
                    refs.append(TemplateRef(
                        kind="registered", local_id=None, said=child.name,
                    ))
        if self._drafts_dir.exists():
            for child in sorted(self._drafts_dir.iterdir()):
                if child.is_dir() and (child / TEMPLATE_FILENAME).exists():
                    refs.append(TemplateRef(
                        kind="draft", local_id=child.name, said=None,
                    ))
        return refs

    def load(self, ref: TemplateRef) -> tuple[dict[str, Any], dict[str, Any]]:
        dir_path = self._ref_dir(ref)
        if not dir_path.exists():
            raise TemplateNotFound(f"No template at {dir_path}")
        doc_path = dir_path / TEMPLATE_FILENAME
        meta_path = dir_path / METADATA_FILENAME
        if not doc_path.exists():
            raise TemplateNotFound(f"No {TEMPLATE_FILENAME} at {dir_path}")
        doc = json.loads(doc_path.read_text())
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        return doc, meta

    def save_draft(
        self, *, local_id: str, doc: dict[str, Any], metadata: dict[str, Any],
    ) -> TemplateRef:
        ref = TemplateRef(kind="draft", local_id=local_id, said=None)
        dir_path = self._ref_dir(ref)
        self._write_pair_atomic(dir_path, doc, metadata)
        return ref

    def save_registered(
        self, *, said: str, doc: dict[str, Any], metadata: dict[str, Any],
        overwrite: bool = False,
    ) -> TemplateRef:
        ref = TemplateRef(kind="registered", local_id=None, said=said)
        dir_path = self._ref_dir(ref)
        if dir_path.exists() and not overwrite:
            raise TemplateAlreadyExists(f"Already at {dir_path}")
        self._write_pair_atomic(dir_path, doc, metadata)
        return ref

    def promote_to_registered(
        self, draft_ref: TemplateRef, *, said: str,
    ) -> TemplateRef:
        if draft_ref.kind != "draft":
            raise ValueError(f"Expected draft ref, got {draft_ref.kind}")
        doc, meta = self.load(draft_ref)
        doc = {**doc, "d": said}
        self.save_registered(said=said, doc=doc, metadata=meta, overwrite=True)
        shutil.rmtree(self._ref_dir(draft_ref))
        return TemplateRef(kind="registered", local_id=None, said=said)

    def delete(self, ref: TemplateRef) -> None:
        dir_path = self._ref_dir(ref)
        if not dir_path.exists():
            raise TemplateNotFound(f"No template at {dir_path}")
        shutil.rmtree(dir_path)
