# -*- encoding: utf-8 -*-
"""Validation adapter for the Designer plugin.

Wraps locksmith.micro_app_template.validate to produce ValidationReport
records the Designer's UI consumes — with normalized JSON-pointer paths
and a `surface` field routing each issue to the editor that displays
it. The underlying validation logic (meta-schema + xref) is reused
unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from locksmith.micro_app_template.validate import (
    ValidationError as _RawError,
    validate_template as _validate_template,
)


@dataclass(frozen=True)
class ValidationIssue:
    severity: Literal["error", "warning"]
    code: str
    message: str
    path: str             # JSON-pointer ("" = root, "/commands/2/inputs")
    surface: str          # "commands" | "exports" | "imports" | … | "overview"


@dataclass(frozen=True)
class ValidationReport:
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def all_issues(self) -> tuple[ValidationIssue, ...]:
        return self.errors + self.warnings


_TOPLEVEL_TO_SURFACE: dict[str, str] = {
    "commands": "commands",
    "aggregates": "aggregates",
    "reactions": "reactions",
    "workflows": "workflows",
    "projections": "projections",
    "rules": "rules",
    "credentials": "credentials",  # refined below to imports/exports
    "header": "overview",
    "role": "overview",
    "d": "overview",
    "spec_version": "overview",
}


def surface_from_path(path: str) -> str:
    """Derive editor surface from a JSON-pointer path."""
    if not path or path == "/":
        return "overview"
    parts = path.lstrip("/").split("/")
    top = parts[0] if parts else ""
    if top == "credentials" and len(parts) >= 2:
        if parts[1] == "imports":
            return "imports"
        if parts[1] == "exports":
            return "exports"
    return _TOPLEVEL_TO_SURFACE.get(top, "overview")


def _normalize_path(raw: str) -> str:
    """Convert validator's path notation to JSON-pointer.

    Inputs we see:
      "credentials/exports/0/rule_refs/0"      (jsonschema-style)
      "credentials.exports[0].rule_refs[0]"    (xref-style)
      "<root>"                                  (jsonschema-style for root)
      ""                                        (already root)
    """
    if not raw or raw == "<root>":
        return ""
    # Replace bracket-index notation: foo[3] -> foo/3
    out = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == ".":
            out.append("/")
        elif ch == "[":
            close = raw.find("]", i)
            if close == -1:
                out.append(ch)
                i += 1
                continue
            out.append("/")
            out.append(raw[i + 1 : close])
            i = close + 1
            continue
        else:
            out.append(ch)
        i += 1
    normalized = "".join(out)
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return normalized


def _issue_code(message: str) -> str:
    """Best-effort stable code from a validator's message.

    Real codes will be added when the validators emit them. For v1, use
    a heuristic prefix derived from message content.
    """
    msg = message.lower()
    if "required" in msg:
        return "missing-required"
    if "not found" in msg:
        return "unresolved-reference"
    if "additional" in msg and "not allowed" in msg:
        return "unexpected-property"
    if "match" in msg and "pattern" in msg:
        return "pattern-mismatch"
    return "schema-violation"


def _wrap(raw: _RawError) -> ValidationIssue:
    path = _normalize_path(raw.path)
    return ValidationIssue(
        severity="error" if raw.severity == "error" else "warning",
        code=_issue_code(raw.message),
        message=raw.message,
        path=path,
        surface=surface_from_path(path),
    )


class ValidationEngine:
    def __init__(self, meta_schema_path: Path):
        self.meta_schema_path = Path(meta_schema_path)

    def validate(self, doc: dict[str, Any]) -> ValidationReport:
        raw = _validate_template(doc, schema_path=self.meta_schema_path)
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        for r in raw.errors:
            wrapped = _wrap(r)
            (errors if wrapped.severity == "error" else warnings).append(wrapped)
        return ValidationReport(
            errors=tuple(errors), warnings=tuple(warnings),
        )
