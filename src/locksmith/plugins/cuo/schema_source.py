# -*- encoding: utf-8 -*-
"""The `declare_product_mandate` command's payload schema, read from the EGF.

Every control the form builds and every rule it enforces comes from here. Nothing
about the mandate's shape is written in Python -- not the line-of-business enum,
not the jurisdiction pattern, not the date format. `tests/plugins/cuo/
test_no_schema_literals.py` enforces that.

The resolution path uses no hardcoded SAID:

    egf-doc  ->  micro_apps[role_id == "cuo"].said
             ->  <said>.json  ->  commands[id == "declare_product_mandate"]
             ->  payload_schema

Fails LOUD at every step. A form that silently falls back to "no constraints" is
worse than a form that refuses to open: it would accept anything and let the
issuer reject it, which is the behaviour this plan replaces.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CUO_ROLE_ID = "cuo"
DECLARE_COMMAND_ID = "declare_product_mandate"

_EGF_SPEC_VERSION = "egf-doc/0.1"


class SchemaSourceError(RuntimeError):
    """The EGF could not yield the mandate payload schema."""


@dataclass(frozen=True)
class FieldConstraints:
    name: str
    type: str
    required: bool
    enum: tuple[str, ...] | None
    pattern: str | None
    fmt: str | None
    min_length: int | None
    item_pattern: str | None
    min_items: int | None
    unique_items: bool
    description: str


@dataclass(frozen=True)
class MandateSchema:
    """The parsed `declare_product_mandate` payload schema.

    `order` is a best-effort reading of the schema's own key order (see
    `load_mandate_schema`) -- a canary, not an authority. It is NOT the
    presentation order the form should render fields in, nor the order
    validation should report errors in. `required` is a JSON-Schema *set*:
    nothing in the format distinguishes "the author's intended order" from
    "incidentally alphabetical", and this bundle's `properties` block IS
    alphabetized (see `load_mandate_schema`'s docstring) -- so `required`
    merely happens to agree with intent today, it is not provably safer. The
    single authority for field sequence is `mandate_copy.FIELD_ORDER`
    (Task 3), used for both form layout and the order validation reports
    errors in.
    """
    fields: dict[str, FieldConstraints]
    order: tuple[str, ...]


def _egf_doc(egf_dir: Path) -> dict[str, Any]:
    for path in sorted(egf_dir.glob("E*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (isinstance(doc, dict)
                and doc.get("spec_version") == _EGF_SPEC_VERSION
                and "micro_apps" in doc):
            return doc
    raise SchemaSourceError(f"no egf-doc/0.1 with micro_apps in {egf_dir}")


def _cuo_template(egf_dir: Path, doc: dict[str, Any]) -> dict[str, Any]:
    said = next((m.get("said") for m in doc.get("micro_apps", [])
                 if m.get("role_id") == CUO_ROLE_ID), None)
    if not said:
        raise SchemaSourceError(
            f"the EGF declares no micro-app for role {CUO_ROLE_ID!r}")
    path = egf_dir / f"{said}.json"
    if not path.is_file():
        raise SchemaSourceError(
            f"the EGF references micro-app {said} but {path} is not published")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SchemaSourceError(f"{path} is not valid JSON: {exc}") from exc


def _payload_schema(template: dict[str, Any]) -> dict[str, Any]:
    for command in template.get("commands", []):
        if command.get("id") == DECLARE_COMMAND_ID:
            schema = command.get("payload_schema")
            if not isinstance(schema, dict) or "properties" not in schema:
                raise SchemaSourceError(
                    f"command {DECLARE_COMMAND_ID} has no usable payload_schema")
            return schema
    raise SchemaSourceError(
        f"the CUO micro-app declares no command {DECLARE_COMMAND_ID!r}")


def _constraints(name: str, sub: dict[str, Any], required: bool) -> FieldConstraints:
    items = sub.get("items") or {}
    return FieldConstraints(
        name=name,
        type=str(sub.get("type") or ""),
        required=required,
        enum=tuple(str(v) for v in sub["enum"]) if sub.get("enum") else None,
        pattern=sub.get("pattern"),
        fmt=sub.get("format"),
        min_length=sub.get("minLength"),
        item_pattern=items.get("pattern") if isinstance(items, dict) else None,
        min_items=sub.get("minItems"),
        unique_items=bool(sub.get("uniqueItems")),
        description=str(sub.get("description") or ""),
    )


def load_mandate_schema(egf_dir: Path) -> MandateSchema:
    """Parse the mandate payload schema out of the bundled EGF at `egf_dir`.

    `order` is read from the schema's `required` list rather than from
    iterating `properties`. Measured against the real bundled template:
    `properties` is alphabetized (`coverages, jurisdiction, line_of_business,
    ...` -- an artifact of whatever serialized the template), while `required`
    happens to carry the field order a CUO would naturally fill the form in
    (`line_of_business, jurisdiction, coverages, ...`). Reading `properties`
    order would have silently handed the page an alphabetized control layout.

    This only relocates the fragility, though -- it does not remove it.
    `required` is a JSON-Schema *set*; nothing in the format distinguishes
    "authored order" from "incidentally alphabetical", and this same file
    already alphabetized one field once. Treat `MandateSchema.order` as a
    canary (see its docstring), never as the presentation order -- that
    authority is `mandate_copy.FIELD_ORDER` (Task 3).

    Any property the schema leaves out of `required` (declared optional, no
    position implied by this reading) is appended afterward in `properties`
    order, so it still appears exactly once in `order`.
    """
    schema = _payload_schema(_cuo_template(egf_dir, _egf_doc(egf_dir)))
    required = list(schema.get("required") or ())
    required_set = set(required)
    properties = schema.get("properties") or {}
    fields = {}
    for name, sub in properties.items():
        if not isinstance(sub, dict):
            continue
        fields[name] = _constraints(name, sub, name in required_set)
    if not fields:
        raise SchemaSourceError("payload_schema declares no properties")
    order = [name for name in required if name in fields]
    order += [name for name in fields if name not in required_set]
    return MandateSchema(fields=fields, order=tuple(order))
