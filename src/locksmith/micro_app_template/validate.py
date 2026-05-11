"""Top-level validation for micro-app templates.

Combines JSON-Schema structural validation against the meta-schema with
cross-reference validation (rule_refs, credential ids, workflow ids,
etc.). Returns a unified result object.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema

from locksmith.micro_app_template.xref import XrefError, validate_xrefs


@dataclass
class ValidationError:
    """A single validation error."""
    path: str
    message: str
    severity: str = "error"  # error | warning


@dataclass
class ValidationResult:
    """Combined result of meta-schema + cross-reference validation."""
    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)


def _jsonschema_error_to_validation(e: jsonschema.ValidationError) -> ValidationError:
    return ValidationError(
        path="/".join(str(p) for p in e.absolute_path) or "<root>",
        message=e.message,
    )


def _xref_error_to_validation(e: XrefError) -> ValidationError:
    return ValidationError(path=e.path, message=e.message)


def validate_against_meta_schema(
    doc: dict[str, Any], schema_path: Path
) -> list[ValidationError]:
    """Run JSON-Schema validation; return list of errors (empty if valid)."""
    with open(schema_path) as f:
        schema = json.load(f)
    validator = jsonschema.Draft202012Validator(schema)
    return [_jsonschema_error_to_validation(e) for e in validator.iter_errors(doc)]


def validate_cross_references(doc: dict[str, Any]) -> list[ValidationError]:
    """Run cross-reference checks; return list of errors."""
    return [_xref_error_to_validation(e) for e in validate_xrefs(doc)]


def validate_template(doc: dict[str, Any], schema_path: Path) -> ValidationResult:
    """Full validation: meta-schema + cross-references."""
    errors: list[ValidationError] = []
    errors.extend(validate_against_meta_schema(doc, schema_path))
    errors.extend(validate_cross_references(doc))
    return ValidationResult(is_valid=(len(errors) == 0), errors=errors)
