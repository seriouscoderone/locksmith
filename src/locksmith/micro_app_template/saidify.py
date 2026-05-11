"""SAID computation for micro-app templates.

Wraps keripy's Saider.saidify to produce content-addressed identifiers
for micro-app-template.json documents. The SAID lives in the document's
top-level `d` field; the field is set to a placeholder, the canonical
form is hashed, and the placeholder is replaced with the resulting
44-character Blake3-256 CESR-encoded digest.
"""
from __future__ import annotations

import copy
from typing import Any

from keri.core.coring import MtrDex, Saider


def _sort_keys_recursive(obj):
    """Return obj with all nested dict keys sorted lexicographically.

    Matches the canonical form produced by canonicalize() — ensures SAID
    computation operates on the same byte-ordering as on-disk storage.
    """
    if isinstance(obj, dict):
        return {k: _sort_keys_recursive(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, list):
        return [_sort_keys_recursive(item) for item in obj]
    return obj


PLACEHOLDER = "#" * 44
"""44-character placeholder used while computing a Blake3-256 SAID."""


def compute_said(doc: dict[str, Any], *, label: str = "d") -> str:
    """Compute the SAID of doc without mutating it.

    The document must contain the label field (default 'd'); its value
    is set to a placeholder during computation, then the canonical form
    is hashed and the SAID is returned.
    """
    if label not in doc:
        raise KeyError(f"document missing label field: {label!r}")
    sad = _sort_keys_recursive(copy.deepcopy(doc))
    sad[label] = PLACEHOLDER
    saider, _ = Saider.saidify(sad=sad, code=MtrDex.Blake3_256, label=label)
    return saider.qb64


def saidify_document(doc: dict[str, Any], *, label: str = "d") -> dict[str, Any]:
    """Return a copy of doc with the SAID injected at the label field."""
    if label not in doc:
        raise KeyError(f"document missing label field: {label!r}")
    sad = _sort_keys_recursive(copy.deepcopy(doc))
    sad[label] = PLACEHOLDER
    _, stamped = Saider.saidify(sad=sad, code=MtrDex.Blake3_256, label=label)
    return stamped


def verify_said(doc: dict[str, Any], *, label: str = "d") -> bool:
    """Return True iff doc[label] is the SAID of the rest of the document.

    Returns False on tamper or absence of the field.
    """
    if label not in doc or not doc[label]:
        return False
    claimed = doc[label]
    recomputed = compute_said(doc, label=label)
    return claimed == recomputed
