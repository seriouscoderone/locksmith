# -*- encoding: utf-8 -*-
"""TemplateModel: QObject wrapping the in-memory template dict.

Emits `changed(path)` on every mutation so editor surfaces and the
JSON source view can re-render reactively. Tracks the dirty flag for
save prompts.
"""
from __future__ import annotations

import copy
from typing import Any

from PySide6.QtCore import QObject, Signal


def _walk(doc: dict[str, Any], parts: list[str]) -> Any:
    cur: Any = doc
    for p in parts:
        if isinstance(cur, list):
            cur = cur[int(p)]
        else:
            cur = cur[p]
    return cur


def _set_at(doc: dict[str, Any], parts: list[str], value: Any) -> None:
    parent = _walk(doc, parts[:-1])
    last = parts[-1]
    if isinstance(parent, list):
        parent[int(last)] = value
    else:
        parent[last] = value


def _path_parts(path: str) -> list[str]:
    if not path or path == "/":
        return []
    return [p for p in path.lstrip("/").split("/") if p]


class TemplateModel(QObject):
    """In-memory template model with change signals and dirty tracking.

    Owns its own copy of the input dict — callers may discard their
    original reference after construction. Direct mutations via
    `model.doc[...] = ...` are NOT signal-emitting; use the named
    methods instead.

    Signals:
      changed(path):       emitted on every mutation; path is the
                           JSON pointer that changed, or "" when the
                           entire document was replaced (full reload).
      dirty_changed(bool): emitted only on actual dirty-flag transitions.
    """

    changed = Signal(str)         # path that changed
    dirty_changed = Signal(bool)

    def __init__(self, doc: dict[str, Any]):
        super().__init__()
        self._doc = copy.deepcopy(doc)
        self._dirty = False

    @property
    def doc(self) -> dict[str, Any]:
        return self._doc

    @property
    def dirty(self) -> bool:
        return self._dirty

    def _set_dirty(self, value: bool) -> None:
        if self._dirty != value:
            self._dirty = value
            self.dirty_changed.emit(value)

    def get_path(self, path: str) -> Any:
        return _walk(self._doc, _path_parts(path))

    def set_path(self, path: str, value: Any) -> None:
        parts = _path_parts(path)
        if not parts:
            raise ValueError("Cannot set the root document via set_path()")
        _set_at(self._doc, parts, value)
        self._set_dirty(True)
        self.changed.emit(path)

    def append_to(self, path: str, value: Any) -> int:
        target = _walk(self._doc, _path_parts(path))
        if not isinstance(target, list):
            raise TypeError(f"Cannot append to non-list at {path}")
        target.append(value)
        self._set_dirty(True)
        self.changed.emit(path)
        return len(target) - 1

    def remove_from(self, path: str, index: int) -> None:
        target = _walk(self._doc, _path_parts(path))
        if not isinstance(target, list):
            raise TypeError(f"Cannot remove from non-list at {path}")
        del target[index]
        self._set_dirty(True)
        self.changed.emit(path)

    def replace_doc(self, new_doc: dict[str, Any]) -> None:
        self._doc = copy.deepcopy(new_doc)
        self._set_dirty(False)
        self.changed.emit("")

    def mark_clean(self) -> None:
        self._set_dirty(False)
