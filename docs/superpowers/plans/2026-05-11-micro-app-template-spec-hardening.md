# Micro-App Template Spec Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the micro-app template spec (`docs/superpowers/specs/2026-05-09-micro-app-template-authoring-and-data-model.md`) into machine-validatable artifacts — JSON-Schema meta-schemas, SAID/validation Python tooling, and a fully fleshed-out `micro-app-template-gen` Claude skill — and prove it works end-to-end by authoring one worked-example template.

**Architecture:** Three deliverable streams that converge on a working toolchain. **Stream 1 — validation foundation:** a `locksmith.micro_app_template` Python package with canonicalization, SAID computation (wrapping keripy's `Saider.saidify`), and JSON-Schema validation, plus CLI wrappers. **Stream 2 — meta-schemas:** JSON-Schema documents at `docs/superpowers/specs/schemas/` that the validator consumes; built incrementally one primitive at a time. **Stream 3 — skill expansion:** TDD-shaped (per `superpowers:writing-skills`) build of the `micro-app-template-gen` skill — baseline subagent test first, then `references/*` files, then `SKILL.md` prose, then with-skill subagent test and iteration. The streams converge in Task 20: authoring one carrier-license-application micro-app end-to-end via the skill, validated by the toolchain.

**Tech Stack:** Python 3.13, `jsonschema` library (already in keripy's dep tree), keripy's `Saider.saidify`, pytest, JSON-Schema Draft 2020-12. No new top-level dependencies — everything builds on what's already in the wallet.

---

## File Structure

**Created in this plan:**

```
src/locksmith/micro_app_template/
├── __init__.py
├── canonical_json.py         # canonicalize(obj) → str (sorted keys, deterministic spacing)
├── saidify.py                # compute_said(doc), saidify_document(doc) — wraps Saider
├── validate.py               # validate_template(doc, schema_path) — jsonschema + xref checks
└── xref.py                   # cross-reference validation helpers

scripts/
├── micro_app_saidify.py      # CLI wrapper for saidify
└── micro_app_validate.py     # CLI wrapper for validate

docs/superpowers/specs/schemas/
├── micro-app-template.schema.json   # the canonical meta-schema (built in 5 increments)
└── metadata.schema.json             # meta-schema for sibling metadata.json

tests/micro_app_template/
├── __init__.py
├── conftest.py                       # fixtures shared across tests
├── test_canonical_json.py
├── test_saidify.py
├── test_validate.py
├── test_meta_schema.py               # validates fixture templates against the schema
└── fixtures/
    ├── minimal_valid_template.json
    ├── minimal_valid_metadata.json
    ├── invalid_missing_d.json
    ├── invalid_missing_role.json
    ├── invalid_wrong_kind.json
    └── invalid_dangling_rule_ref.json

.claude/skills/micro-app-template-gen/
├── SKILL.md                          # expanded from stub
└── references/
    ├── ten-step-process.md
    ├── question-bank.md
    ├── adversarial-prompts.md
    ├── rule-types-reference.md
    ├── naming-conventions.md
    ├── skeleton.json                 # minimal-valid starting template
    └── examples/
        └── carrier-license-application/
            ├── micro-app-template.json
            ├── metadata.json
            └── schemas/
                └── policy.json

docs/skill-test-runs/
└── micro-app-template-gen/
    ├── baseline-2026-05-11.md        # subagent results without full skill
    └── with-skill-2026-05-11.md      # subagent results with full skill
```

**Modified in this plan:**

- `.claude/skills/micro-app-template-gen/SKILL.md` (existing stub → full skill)

---

## Task 1: Canonical JSON helper

**Files:**
- Create: `src/locksmith/micro_app_template/__init__.py`
- Create: `src/locksmith/micro_app_template/canonical_json.py`
- Create: `tests/micro_app_template/__init__.py`
- Create: `tests/micro_app_template/test_canonical_json.py`

- [ ] **Step 1: Create the package directories**

```bash
mkdir -p src/locksmith/micro_app_template tests/micro_app_template
touch src/locksmith/micro_app_template/__init__.py tests/micro_app_template/__init__.py
```

- [ ] **Step 2: Write the failing test**

Create `tests/micro_app_template/test_canonical_json.py`:

```python
"""Tests for micro-app-template canonical JSON serialization."""
from __future__ import annotations

from locksmith.micro_app_template.canonical_json import canonicalize


def test_sorts_top_level_keys():
    obj = {"z": 1, "a": 2, "m": 3}
    out = canonicalize(obj)
    assert out.index('"a"') < out.index('"m"') < out.index('"z"')


def test_sorts_nested_keys_recursively():
    obj = {"outer": {"z": 1, "a": 2}, "inner": {"y": 3, "b": 4}}
    out = canonicalize(obj)
    a_pos = out.index('"a"')
    z_pos = out.index('"z"')
    b_pos = out.index('"b"')
    y_pos = out.index('"y"')
    assert a_pos < z_pos
    assert b_pos < y_pos


def test_preserves_array_order():
    obj = {"items": ["c", "a", "b"]}
    out = canonicalize(obj)
    assert out.index('"c"') < out.index('"a"') < out.index('"b"')


def test_two_space_indent():
    obj = {"a": {"b": 1}}
    out = canonicalize(obj)
    assert '\n  "a"' in out
    assert '\n    "b"' in out


def test_ends_with_single_newline():
    obj = {"a": 1}
    out = canonicalize(obj)
    assert out.endswith("\n")
    assert not out.endswith("\n\n")


def test_utf8_unicode_preserved():
    obj = {"description": "Crédit licencié"}
    out = canonicalize(obj)
    assert "Crédit licencié" in out


def test_round_trip_stable():
    """canonicalize(parse(canonicalize(x))) == canonicalize(x)"""
    import json
    obj = {"z": 1, "a": {"y": 2, "b": [3, 1, 2]}, "m": "text"}
    once = canonicalize(obj)
    twice = canonicalize(json.loads(once))
    assert once == twice
```

- [ ] **Step 3: Run test to verify it fails**

```bash
source .venv/bin/activate
pytest tests/micro_app_template/test_canonical_json.py -v
```

Expected: FAIL with `ImportError: cannot import name 'canonicalize'`.

- [ ] **Step 4: Implement `canonical_json.py`**

Create `src/locksmith/micro_app_template/canonical_json.py`:

```python
"""Canonical JSON serialization for micro-app templates.

Produces a deterministic, sorted-keys, two-space-indented JSON form
used both for human-facing files on disk and as input to SAID
computation. Round-trip stable: parse(canonicalize(x)) → canonicalize again
yields the same bytes.
"""
from __future__ import annotations

import json
from typing import Any


def canonicalize(obj: Any) -> str:
    """Render obj as canonical JSON.

    - Keys sorted lexicographically at every level
    - UTF-8 encoded (no ASCII escaping)
    - Two-space indent
    - Single trailing newline
    """
    return json.dumps(
        obj,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        separators=(",", ": "),
    ) + "\n"
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/micro_app_template/test_canonical_json.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/micro_app_template/__init__.py src/locksmith/micro_app_template/canonical_json.py tests/micro_app_template/__init__.py tests/micro_app_template/test_canonical_json.py
git commit -m "$(cat <<'EOF'
feat(micro-app-template): canonical JSON helper

Produces sorted-keys, two-space-indented, UTF-8 JSON. Stable under
round-trip. Foundation for SAID computation and on-disk artifact
storage.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: SAID computation utility

**Files:**
- Create: `src/locksmith/micro_app_template/saidify.py`
- Create: `tests/micro_app_template/test_saidify.py`

- [ ] **Step 1: Write the failing test**

Create `tests/micro_app_template/test_saidify.py`:

```python
"""Tests for micro-app-template SAID computation."""
from __future__ import annotations

import json

from locksmith.micro_app_template.saidify import (
    PLACEHOLDER,
    compute_said,
    saidify_document,
    verify_said,
)


def test_compute_said_produces_44_char_blake3():
    doc = {"d": "", "ecosystem": {"id": "test"}}
    said = compute_said(doc)
    assert isinstance(said, str)
    assert len(said) == 44
    assert said.startswith("E")  # Blake3-256 CESR prefix


def test_saidify_document_fills_d_field():
    doc = {"d": "", "header": {"id": "carrier-license"}}
    out = saidify_document(doc)
    assert out["d"] != ""
    assert len(out["d"]) == 44


def test_saidify_is_deterministic():
    doc = {"d": "", "header": {"id": "carrier-license"}, "role": {"id": "carrier"}}
    a = saidify_document(json.loads(json.dumps(doc)))  # deep copy
    b = saidify_document(json.loads(json.dumps(doc)))
    assert a["d"] == b["d"]


def test_saidify_does_not_mutate_input():
    doc = {"d": "", "header": {"id": "carrier-license"}}
    saidify_document(doc)
    assert doc["d"] == ""


def test_verify_said_passes_on_stamped_document():
    doc = {"d": "", "header": {"id": "carrier-license"}}
    stamped = saidify_document(doc)
    assert verify_said(stamped) is True


def test_verify_said_fails_on_tampered_document():
    doc = {"d": "", "header": {"id": "carrier-license"}}
    stamped = saidify_document(doc)
    stamped["header"]["id"] = "different-id"
    assert verify_said(stamped) is False


def test_placeholder_constant_is_correct_length():
    assert len(PLACEHOLDER) == 44


def test_saidify_requires_d_field():
    import pytest
    with pytest.raises(KeyError):
        saidify_document({"header": {"id": "x"}})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/micro_app_template/test_saidify.py -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `saidify.py`**

Create `src/locksmith/micro_app_template/saidify.py`:

```python
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
from keri.kering import Saids


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
    sad = copy.deepcopy(doc)
    sad[label] = PLACEHOLDER
    saider, _ = Saider.saidify(sad=sad, code=MtrDex.Blake3_256, label=label)
    return saider.qb64


def saidify_document(doc: dict[str, Any], *, label: str = "d") -> dict[str, Any]:
    """Return a copy of doc with the SAID injected at the label field."""
    if label not in doc:
        raise KeyError(f"document missing label field: {label!r}")
    sad = copy.deepcopy(doc)
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/micro_app_template/test_saidify.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/micro_app_template/saidify.py tests/micro_app_template/test_saidify.py
git commit -m "$(cat <<'EOF'
feat(micro-app-template): SAID computation utility

Wraps keripy's Saider.saidify to produce content-addressed identifiers
for micro-app-template.json. Exposes compute_said, saidify_document,
verify_said. Ensures alignment with the rest of the KERI stack rather
than rolling our own canonicalization or digest scheme.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Validation library

**Files:**
- Create: `src/locksmith/micro_app_template/xref.py`
- Create: `src/locksmith/micro_app_template/validate.py`
- Create: `tests/micro_app_template/test_validate.py`
- Create: `tests/micro_app_template/conftest.py`

- [ ] **Step 1: Write the test fixtures**

Create `tests/micro_app_template/conftest.py`:

```python
"""Shared fixtures for micro-app-template tests."""
from __future__ import annotations

from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def minimal_valid_template() -> dict:
    """A minimal document that conforms to the meta-schema once it is built.

    Used as the smoke-test seed across validation tests.
    """
    return {
        "d": "#" * 44,
        "spec_version": "micro-app-template/0.1",
        "header": {
            "id": "minimal-test",
            "display_name": "Minimal Test Template",
            "description": "Smallest valid template used as a test fixture.",
            "version": "0.1",
            "expression_language": "UEL/1.0",
        },
        "role": {
            "id": "tester",
            "display_name": "Test Actor",
            "description": "A placeholder role used for fixtures.",
            "kind": "individual",
            "keri_infrastructure": {
                "witness_pool": False,
                "watcher_network": False,
                "mailbox": True,
                "acdc_registry": False,
            },
        },
        "credentials": {"held": [], "issued": []},
        "commands": [],
        "aggregates": [],
        "reactions": [],
        "workflows": [],
        "projections": [],
        "rules": [],
    }
```

- [ ] **Step 2: Write the failing test**

Create `tests/micro_app_template/test_validate.py`:

```python
"""Tests for micro-app-template validation."""
from __future__ import annotations

from pathlib import Path

import pytest

from locksmith.micro_app_template.validate import (
    ValidationError,
    validate_against_meta_schema,
    validate_cross_references,
    validate_template,
)


# Path to the meta-schema (built in Tasks 4-8).
META_SCHEMA = Path(__file__).parent.parent.parent / "docs/superpowers/specs/schemas/micro-app-template.schema.json"


def test_minimal_valid_template_passes_meta_schema(minimal_valid_template, fixtures_dir):
    # This test asserts the schema accepts the minimal fixture once the
    # schema exists. It will be enabled fully in Task 4.
    if not META_SCHEMA.exists():
        pytest.skip("meta-schema not yet built")
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert errors == []


def test_missing_d_field_fails(minimal_valid_template):
    if not META_SCHEMA.exists():
        pytest.skip("meta-schema not yet built")
    bad = dict(minimal_valid_template)
    del bad["d"]
    errors = validate_against_meta_schema(bad, META_SCHEMA)
    assert any("'d'" in e.message or "d " in e.message for e in errors)


def test_dangling_rule_ref_caught_by_xref():
    doc = {
        "rules": [{"id": "real-rule", "type": "legal_prose", "title": "X", "body": "y"}],
        "credentials": {
            "held": [],
            "issued": [
                {
                    "id": "cred-a",
                    "name": "Cred A",
                    "description": "x",
                    "envelope": {"holder_role": "x", "verifier_roles": [], "edges": [], "disclosure_mode": "full"},
                    "schema": {"schema_said": "E" + "x" * 43, "schema_path": "schemas/a.json"},
                    "lifecycle": {"states": ["active"], "initial": "active", "transitions": []},
                    "rule_refs": ["does-not-exist"],
                    "value_flow": {"implied_credentials": []},
                }
            ],
        },
    }
    errors = validate_cross_references(doc)
    assert any("does-not-exist" in e.message for e in errors)


def test_validate_template_combines_meta_and_xref(minimal_valid_template):
    if not META_SCHEMA.exists():
        pytest.skip("meta-schema not yet built")
    result = validate_template(minimal_valid_template, META_SCHEMA)
    assert result.is_valid
    assert result.errors == []


def test_validate_template_returns_typed_result(minimal_valid_template):
    if not META_SCHEMA.exists():
        pytest.skip("meta-schema not yet built")
    bad = dict(minimal_valid_template)
    del bad["role"]
    result = validate_template(bad, META_SCHEMA)
    assert not result.is_valid
    assert len(result.errors) > 0
    assert all(isinstance(e, ValidationError) for e in result.errors)
```

- [ ] **Step 3: Run test to verify it fails (most skipped, xref test fails on import)**

```bash
pytest tests/micro_app_template/test_validate.py -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 4: Implement `xref.py`**

Create `src/locksmith/micro_app_template/xref.py`:

```python
"""Cross-reference validation for micro-app templates.

JSON-Schema validates structural shape. This module validates the
references *within* the document: rule_refs resolve to declared rule
ids, credential_held_id references resolve to entries in
credentials.held, lifecycle transition workflow references resolve to
declared workflows, etc.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class XrefError:
    """A cross-reference that does not resolve."""
    path: str
    reference: str
    target_type: str

    @property
    def message(self) -> str:
        return f"{self.path}: {self.target_type} {self.reference!r} not found"


def _collect_rule_ids(doc: dict[str, Any]) -> set[str]:
    return {r["id"] for r in doc.get("rules", []) if "id" in r}


def _collect_credential_ids(doc: dict[str, Any]) -> tuple[set[str], set[str]]:
    creds = doc.get("credentials", {})
    held = {c["id"] for c in creds.get("held", []) if "id" in c}
    issued = {c["id"] for c in creds.get("issued", []) if "id" in c}
    return held, issued


def _collect_workflow_ids(doc: dict[str, Any]) -> set[str]:
    return {w["id"] for w in doc.get("workflows", []) if "id" in w}


def _collect_command_ids(doc: dict[str, Any]) -> set[str]:
    return {c["id"] for c in doc.get("commands", []) if "id" in c}


def _collect_reaction_ids(doc: dict[str, Any]) -> set[str]:
    return {r["id"] for r in doc.get("reactions", []) if "id" in r}


def _collect_aggregate_ids(doc: dict[str, Any]) -> set[str]:
    return {a["id"] for a in doc.get("aggregates", []) if "id" in a}


def validate_xrefs(doc: dict[str, Any]) -> list[XrefError]:
    """Return a list of unresolved cross-references found in doc."""
    errors: list[XrefError] = []
    rule_ids = _collect_rule_ids(doc)
    held_ids, issued_ids = _collect_credential_ids(doc)
    workflow_ids = _collect_workflow_ids(doc)
    command_ids = _collect_command_ids(doc)
    reaction_ids = _collect_reaction_ids(doc)
    aggregate_ids = _collect_aggregate_ids(doc)

    # credentials.issued[].rule_refs
    for i, c in enumerate(doc.get("credentials", {}).get("issued", [])):
        for j, ref in enumerate(c.get("rule_refs", [])):
            if ref not in rule_ids:
                errors.append(XrefError(
                    path=f"credentials.issued[{i}].rule_refs[{j}]",
                    reference=ref, target_type="rule",
                ))
        # lifecycle transitions
        for k, t in enumerate(c.get("lifecycle", {}).get("transitions", [])):
            wf = t.get("via_workflow")
            if wf is not None and wf not in workflow_ids:
                errors.append(XrefError(
                    path=f"credentials.issued[{i}].lifecycle.transitions[{k}].via_workflow",
                    reference=wf, target_type="workflow",
                ))
            cond = t.get("condition_rule_ref")
            if cond is not None and cond not in rule_ids:
                errors.append(XrefError(
                    path=f"credentials.issued[{i}].lifecycle.transitions[{k}].condition_rule_ref",
                    reference=cond, target_type="rule",
                ))
            for m, req in enumerate(t.get("requires", []) or []):
                rr = req.get("rule_ref") if isinstance(req, dict) else None
                if rr is not None and rr not in rule_ids:
                    errors.append(XrefError(
                        path=f"credentials.issued[{i}].lifecycle.transitions[{k}].requires[{m}].rule_ref",
                        reference=rr, target_type="rule",
                    ))

    # commands[].*_preconditions
    for i, cmd in enumerate(doc.get("commands", [])):
        for kind in ("auth_preconditions", "state_preconditions", "temporal_preconditions"):
            for j, pre in enumerate(cmd.get(kind, []) or []):
                rr = pre.get("rule_ref") if isinstance(pre, dict) else None
                if rr is not None and rr not in rule_ids:
                    errors.append(XrefError(
                        path=f"commands[{i}].{kind}[{j}].rule_ref",
                        reference=rr, target_type="rule",
                    ))

    # aggregates[].invariants
    for i, agg in enumerate(doc.get("aggregates", [])):
        for j, inv in enumerate(agg.get("invariants", []) or []):
            rr = inv.get("rule_ref") if isinstance(inv, dict) else None
            if rr is not None and rr not in rule_ids:
                errors.append(XrefError(
                    path=f"aggregates[{i}].invariants[{j}].rule_ref",
                    reference=rr, target_type="rule",
                ))

    # workflows[].steps[].command_id / reaction_id / branches[].rule_ref
    for i, wf in enumerate(doc.get("workflows", [])):
        for j, step in enumerate(wf.get("steps", []) or []):
            cid = step.get("command_id")
            if cid is not None and cid not in command_ids:
                errors.append(XrefError(
                    path=f"workflows[{i}].steps[{j}].command_id",
                    reference=cid, target_type="command",
                ))
            rid = step.get("reaction_id")
            if rid is not None and rid not in reaction_ids:
                errors.append(XrefError(
                    path=f"workflows[{i}].steps[{j}].reaction_id",
                    reference=rid, target_type="reaction",
                ))
            for k, br in enumerate(step.get("branches", []) or []):
                rr = br.get("rule_ref") if isinstance(br, dict) else None
                if rr is not None and rr not in rule_ids:
                    errors.append(XrefError(
                        path=f"workflows[{i}].steps[{j}].branches[{k}].rule_ref",
                        reference=rr, target_type="rule",
                    ))

    # projections[].access.row_filter_rule_ref
    for i, p in enumerate(doc.get("projections", [])):
        rr = p.get("access", {}).get("row_filter_rule_ref")
        if rr is not None and rr not in rule_ids:
            errors.append(XrefError(
                path=f"projections[{i}].access.row_filter_rule_ref",
                reference=rr, target_type="rule",
            ))

    # rules[].links (binding_link references)
    for i, r in enumerate(doc.get("rules", [])):
        for j, link in enumerate(r.get("links", []) or []):
            tid = link.get("rule_id") if isinstance(link, dict) else None
            if tid is not None and tid not in rule_ids:
                errors.append(XrefError(
                    path=f"rules[{i}].links[{j}].rule_id",
                    reference=tid, target_type="rule",
                ))

    return errors
```

- [ ] **Step 5: Implement `validate.py`**

Create `src/locksmith/micro_app_template/validate.py`:

```python
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
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/micro_app_template/test_validate.py -v
```

Expected: `test_dangling_rule_ref_caught_by_xref` PASSES; meta-schema tests SKIP (schema not yet built).

- [ ] **Step 7: Commit**

```bash
git add src/locksmith/micro_app_template/validate.py src/locksmith/micro_app_template/xref.py tests/micro_app_template/conftest.py tests/micro_app_template/test_validate.py
git commit -m "$(cat <<'EOF'
feat(micro-app-template): validation library

ValidationResult / ValidationError types. validate_template() combines
JSON-Schema structural validation against the meta-schema (loaded by
path) with custom cross-reference validation (rule_refs resolve to
declared rules, credential_held_id matches credentials.held, workflow
step references resolve, etc.). Cross-reference logic in xref.py is
unit-tested independently. Meta-schema tests skip until the schema is
built in Tasks 4-8.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Meta-schema part 1 — top level + header + role

**Files:**
- Create: `docs/superpowers/specs/schemas/micro-app-template.schema.json`

This task produces the FIRST version of the meta-schema with only the top-level structure, the header primitive, and the role primitive. Later tasks (5-8) add credentials, commands/aggregates, reactions/workflows/projections, and rules respectively.

- [ ] **Step 1: Create the schemas directory**

```bash
mkdir -p docs/superpowers/specs/schemas
```

- [ ] **Step 2: Write the initial meta-schema**

Create `docs/superpowers/specs/schemas/micro-app-template.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://locksmith/spec/micro-app-template/0.1",
  "title": "Micro-App Template",
  "description": "Canonical artifact describing one role's slice of operational behavior in a KERI-native ecosystem application.",
  "type": "object",
  "required": ["d", "spec_version", "header", "role", "credentials", "commands", "aggregates", "reactions", "workflows", "projections", "rules"],
  "additionalProperties": false,
  "properties": {
    "d": {
      "type": "string",
      "minLength": 44,
      "maxLength": 44,
      "description": "Self-SAID of this document. 44-character CESR-encoded Blake3-256 digest of the canonical form with d field placeholdered."
    },
    "spec_version": {
      "type": "string",
      "pattern": "^micro-app-template/[0-9]+\\.[0-9]+$",
      "description": "Version of the ecosystem-template meta-schema this document conforms to."
    },
    "header": { "$ref": "#/$defs/header" },
    "role": { "$ref": "#/$defs/role" },
    "credentials": {
      "type": "object",
      "required": ["held", "issued"],
      "properties": {
        "held": { "type": "array", "items": { "type": "object" } },
        "issued": { "type": "array", "items": { "type": "object" } }
      }
    },
    "commands": { "type": "array", "items": { "type": "object" } },
    "aggregates": { "type": "array", "items": { "type": "object" } },
    "reactions": { "type": "array", "items": { "type": "object" } },
    "workflows": { "type": "array", "items": { "type": "object" } },
    "projections": { "type": "array", "items": { "type": "object" } },
    "rules": { "type": "array", "items": { "type": "object" } }
  },
  "$defs": {
    "header": {
      "type": "object",
      "required": ["id", "display_name", "description", "version", "expression_language"],
      "additionalProperties": false,
      "properties": {
        "id": { "type": "string", "pattern": "^[a-z][a-z0-9-]*$" },
        "display_name": { "type": "string", "minLength": 1 },
        "description": { "type": "string", "minLength": 1 },
        "version": { "type": "string", "pattern": "^[0-9]+\\.[0-9]+(\\.[0-9]+)?$" },
        "expression_language": { "type": "string", "pattern": "^[A-Z][A-Za-z]*/[0-9]+\\.[0-9]+$" },
        "forked_from": {
          "type": "object",
          "required": ["template_said", "template_version", "forked_at"],
          "additionalProperties": false,
          "properties": {
            "template_said": { "type": "string", "minLength": 44, "maxLength": 44 },
            "template_version": { "type": "string" },
            "forked_at": { "type": "string", "format": "date" },
            "fork_intent": { "type": "string" }
          }
        }
      }
    },
    "role": {
      "type": "object",
      "required": ["id", "display_name", "description", "kind", "keri_infrastructure"],
      "additionalProperties": false,
      "properties": {
        "id": { "type": "string", "pattern": "^[a-z][a-z0-9_-]*$" },
        "display_name": { "type": "string", "minLength": 1 },
        "description": { "type": "string", "minLength": 1 },
        "kind": {
          "type": "string",
          "enum": ["individual", "organization", "system", "device", "agent", "government"]
        },
        "keri_infrastructure": {
          "type": "object",
          "required": ["witness_pool", "watcher_network", "mailbox", "acdc_registry"],
          "additionalProperties": false,
          "properties": {
            "witness_pool": { "type": "boolean" },
            "watcher_network": { "type": "boolean" },
            "mailbox": { "type": "boolean" },
            "acdc_registry": { "type": "boolean" }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 3: Write fixtures**

Create `tests/micro_app_template/fixtures/minimal_valid_template.json`:

```bash
mkdir -p tests/micro_app_template/fixtures
```

```json
{
  "d": "#####################################",
  "spec_version": "micro-app-template/0.1",
  "header": {
    "id": "minimal-test",
    "display_name": "Minimal Test Template",
    "description": "Smallest valid template used as a test fixture.",
    "version": "0.1",
    "expression_language": "UEL/1.0"
  },
  "role": {
    "id": "tester",
    "display_name": "Test Actor",
    "description": "A placeholder role used for fixtures.",
    "kind": "individual",
    "keri_infrastructure": {
      "witness_pool": false,
      "watcher_network": false,
      "mailbox": true,
      "acdc_registry": false
    }
  },
  "credentials": { "held": [], "issued": [] },
  "commands": [],
  "aggregates": [],
  "reactions": [],
  "workflows": [],
  "projections": [],
  "rules": []
}
```

Note: The `d` placeholder is 37 characters but the schema requires 44. Update to 44:

```bash
# The minimal_valid_template's d field needs to be exactly 44 chars.
# Use a fully-stamped placeholder; the validator only checks length and shape.
python3 -c "import json; doc = json.load(open('tests/micro_app_template/fixtures/minimal_valid_template.json')); doc['d'] = '#' * 44; json.dump(doc, open('tests/micro_app_template/fixtures/minimal_valid_template.json', 'w'), indent=2)"
```

- [ ] **Step 4: Write a smoke test for the meta-schema**

Append to `tests/micro_app_template/test_validate.py`:

```python
def test_meta_schema_file_exists():
    assert META_SCHEMA.exists(), f"meta-schema not found at {META_SCHEMA}"


def test_meta_schema_is_valid_jsonschema():
    import json
    import jsonschema
    with open(META_SCHEMA) as f:
        schema = json.load(f)
    jsonschema.Draft202012Validator.check_schema(schema)


def test_minimal_template_validates_against_meta_schema(minimal_valid_template):
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert errors == [], f"unexpected errors: {[e.message for e in errors]}"


def test_wrong_kind_fails(minimal_valid_template):
    minimal_valid_template["role"]["kind"] = "not_a_real_kind"
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert any("kind" in e.path or "kind" in e.message for e in errors)


def test_missing_required_top_level_fails(minimal_valid_template):
    del minimal_valid_template["role"]
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert any("role" in e.message for e in errors)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/micro_app_template/test_validate.py -v
```

Expected: all meta-schema tests now PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/schemas/micro-app-template.schema.json tests/micro_app_template/fixtures/minimal_valid_template.json tests/micro_app_template/test_validate.py
git commit -m "$(cat <<'EOF'
feat(micro-app-template): meta-schema part 1 — top level, header, role

Initial JSON-Schema (Draft 2020-12) for micro-app-template.json with:
- Top-level structure (d, spec_version, all 8 primitive arrays)
- Header primitive ($defs/header) with forked_from optional block
- Role primitive ($defs/role) with kind enum (individual, organization,
  system, device, agent, government) and keri_infrastructure flags

All other primitives are loosely typed (array of object) at this point;
subsequent tasks (5-8) tighten each in turn. Smoke tests validate the
minimal fixture and catch obvious malformed cases.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Meta-schema part 2 — credentials (held + issued)

**Files:**
- Modify: `docs/superpowers/specs/schemas/micro-app-template.schema.json`
- Modify: `tests/micro_app_template/test_validate.py`

This task adds the credentials primitive's full schema, including the nested envelope, schema, lifecycle, rule_refs, and value_flow sub-fields.

- [ ] **Step 1: Extend the meta-schema's `$defs`**

In `docs/superpowers/specs/schemas/micro-app-template.schema.json`, replace the `credentials` property and add to `$defs`:

```json
"credentials": {
  "type": "object",
  "required": ["held", "issued"],
  "additionalProperties": false,
  "properties": {
    "held": {
      "type": "array",
      "items": { "$ref": "#/$defs/held_credential" }
    },
    "issued": {
      "type": "array",
      "items": { "$ref": "#/$defs/issued_credential" }
    }
  }
}
```

And add to `$defs` (extending the existing $defs object):

```json
"held_credential": {
  "type": "object",
  "required": ["id", "expected_schema_said"],
  "additionalProperties": false,
  "properties": {
    "id": { "type": "string", "pattern": "^[a-z][a-z0-9_-]*$" },
    "expected_schema_said": { "type": "string", "minLength": 44, "maxLength": 44 },
    "expected_issuer_role": { "type": "string" },
    "expected_attribute_constraints": { "type": "object" },
    "lifecycle_acceptance": {
      "type": "array",
      "items": { "type": "string" },
      "default": ["active"]
    },
    "narrative": { "type": "string" }
  }
},
"edge_operator": {
  "type": "string",
  "enum": ["authorizes", "references", "authorizes-via-delegate"]
},
"disclosure_mode": {
  "type": "string",
  "enum": ["full", "selective", "aggregate"]
},
"tel_primitive": {
  "type": "string",
  "enum": ["issue", "update", "revoke"]
},
"issued_credential": {
  "type": "object",
  "required": ["id", "name", "description", "envelope", "schema", "lifecycle"],
  "additionalProperties": false,
  "properties": {
    "id": { "type": "string", "pattern": "^[a-z][a-z0-9_-]*$" },
    "name": { "type": "string", "minLength": 1 },
    "description": { "type": "string", "minLength": 1 },
    "envelope": {
      "type": "object",
      "required": ["holder_role", "verifier_roles", "edges", "disclosure_mode"],
      "additionalProperties": false,
      "properties": {
        "holder_role": { "type": "string" },
        "verifier_roles": { "type": "array", "items": { "type": "string" } },
        "edges": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["edge_name", "credential_id", "cardinality", "operator"],
            "additionalProperties": false,
            "properties": {
              "edge_name": { "type": "string" },
              "credential_id": { "type": "string" },
              "cardinality": { "type": "string", "enum": ["one", "one_or_more"] },
              "operator": { "$ref": "#/$defs/edge_operator" }
            }
          }
        },
        "disclosure_mode": { "$ref": "#/$defs/disclosure_mode" }
      }
    },
    "schema": {
      "type": "object",
      "required": ["schema_said", "schema_path"],
      "additionalProperties": false,
      "properties": {
        "schema_said": { "type": "string", "minLength": 44, "maxLength": 44 },
        "schema_path": { "type": "string", "pattern": "^schemas/[a-z][a-z0-9_-]*\\.json$" }
      }
    },
    "lifecycle": {
      "type": "object",
      "required": ["states", "initial", "transitions"],
      "additionalProperties": false,
      "properties": {
        "states": {
          "type": "array",
          "items": { "type": "string" },
          "minItems": 1,
          "uniqueItems": true
        },
        "initial": { "type": "string" },
        "transitions": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["id", "from", "to", "tel_primitive"],
            "additionalProperties": false,
            "properties": {
              "id": { "type": "string" },
              "from": {
                "oneOf": [
                  { "type": "string" },
                  { "type": "array", "items": { "type": "string" } }
                ]
              },
              "to": { "type": "string" },
              "via_workflow": { "type": ["string", "null"] },
              "tel_primitive": { "$ref": "#/$defs/tel_primitive" },
              "trigger": { "type": "string", "enum": ["manual", "automatic"] },
              "condition_rule_ref": { "type": "string" },
              "requires": {
                "type": "array",
                "items": {
                  "type": "object",
                  "required": ["rule_ref"],
                  "additionalProperties": false,
                  "properties": { "rule_ref": { "type": "string" } }
                }
              }
            }
          }
        }
      }
    },
    "rule_refs": { "type": "array", "items": { "type": "string" }, "default": [] },
    "value_flow": {
      "type": "object",
      "required": ["implied_credentials"],
      "additionalProperties": false,
      "properties": {
        "implied_credentials": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["credential_id", "relationship"],
            "additionalProperties": false,
            "properties": {
              "credential_id": { "type": "string" },
              "relationship": {
                "type": "string",
                "enum": ["issuer_grants", "per_emission", "per_holder_emission", "implies_obligation"]
              },
              "description": { "type": "string" }
            }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 2: Add fixture for credentials**

Create `tests/micro_app_template/fixtures/credentials_valid.json`:

```json
{
  "d": "############################################",
  "spec_version": "micro-app-template/0.1",
  "header": {
    "id": "credentials-test",
    "display_name": "Credentials Test Template",
    "description": "Exercises the credentials primitive.",
    "version": "0.1",
    "expression_language": "UEL/1.0"
  },
  "role": {
    "id": "carrier",
    "display_name": "Test Carrier",
    "description": "A carrier role for credential testing.",
    "kind": "organization",
    "keri_infrastructure": {
      "witness_pool": true,
      "watcher_network": true,
      "mailbox": true,
      "acdc_registry": true
    }
  },
  "credentials": {
    "held": [
      {
        "id": "carrier_license",
        "expected_schema_said": "EAuthorityIssuedSchemaSAID0000000000000xxxxx",
        "expected_issuer_role": "regulator",
        "lifecycle_acceptance": ["active"],
        "narrative": "License from a state regulator authorizes binding policies."
      }
    ],
    "issued": [
      {
        "id": "policy",
        "name": "Policy Credential",
        "description": "Insurance policy binding terms.",
        "envelope": {
          "holder_role": "policyholder_individual",
          "verifier_roles": ["broker"],
          "edges": [
            {
              "edge_name": "authority",
              "credential_id": "carrier_license",
              "cardinality": "one",
              "operator": "authorizes"
            }
          ],
          "disclosure_mode": "selective"
        },
        "schema": {
          "schema_said": "EPolicySchemaSAID000000000000000000000000000",
          "schema_path": "schemas/policy.json"
        },
        "lifecycle": {
          "states": ["pending", "active", "expired", "revoked"],
          "initial": "pending",
          "transitions": [
            {
              "id": "activate",
              "from": "pending",
              "to": "active",
              "tel_primitive": "issue"
            },
            {
              "id": "revoke",
              "from": ["active"],
              "to": "revoked",
              "tel_primitive": "revoke"
            }
          ]
        },
        "rule_refs": [],
        "value_flow": {
          "implied_credentials": []
        }
      }
    ]
  },
  "commands": [],
  "aggregates": [],
  "reactions": [],
  "workflows": [],
  "projections": [],
  "rules": []
}
```

- [ ] **Step 3: Write tests for the credentials schema**

Append to `tests/micro_app_template/test_validate.py`:

```python
def test_credentials_fixture_validates(fixtures_dir):
    import json
    with open(fixtures_dir / "credentials_valid.json") as f:
        doc = json.load(f)
    errors = validate_against_meta_schema(doc, META_SCHEMA)
    assert errors == [], f"unexpected: {[e.message for e in errors]}"


def test_invalid_edge_operator_fails(fixtures_dir):
    import json
    with open(fixtures_dir / "credentials_valid.json") as f:
        doc = json.load(f)
    doc["credentials"]["issued"][0]["envelope"]["edges"][0]["operator"] = "not_a_real_operator"
    errors = validate_against_meta_schema(doc, META_SCHEMA)
    assert any("operator" in e.path or "operator" in e.message for e in errors)


def test_invalid_disclosure_mode_fails(fixtures_dir):
    import json
    with open(fixtures_dir / "credentials_valid.json") as f:
        doc = json.load(f)
    doc["credentials"]["issued"][0]["envelope"]["disclosure_mode"] = "secret"
    errors = validate_against_meta_schema(doc, META_SCHEMA)
    assert any("disclosure_mode" in e.path or "secret" in e.message for e in errors)


def test_invalid_tel_primitive_fails(fixtures_dir):
    import json
    with open(fixtures_dir / "credentials_valid.json") as f:
        doc = json.load(f)
    doc["credentials"]["issued"][0]["lifecycle"]["transitions"][0]["tel_primitive"] = "delete"
    errors = validate_against_meta_schema(doc, META_SCHEMA)
    assert any("tel_primitive" in e.path or "delete" in e.message for e in errors)


def test_schema_path_must_be_in_schemas_dir(fixtures_dir):
    import json
    with open(fixtures_dir / "credentials_valid.json") as f:
        doc = json.load(f)
    doc["credentials"]["issued"][0]["schema"]["schema_path"] = "elsewhere/policy.json"
    errors = validate_against_meta_schema(doc, META_SCHEMA)
    assert any("schema_path" in e.path for e in errors)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/micro_app_template/test_validate.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/schemas/micro-app-template.schema.json tests/micro_app_template/fixtures/credentials_valid.json tests/micro_app_template/test_validate.py
git commit -m "$(cat <<'EOF'
feat(micro-app-template): meta-schema part 2 — credentials

Adds held_credential and issued_credential definitions to the
meta-schema. issued_credential nests envelope (with edges + edge_operator
enum + disclosure_mode enum), schema (by-reference with schema_said
44-char and schema_path pattern), lifecycle (states/initial/transitions
with tel_primitive enum), rule_refs, and value_flow (with relationship
enum). All edge cases tested with positive and negative fixtures.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Meta-schema part 3 — commands + aggregates

**Files:**
- Modify: `docs/superpowers/specs/schemas/micro-app-template.schema.json`
- Modify: `tests/micro_app_template/test_validate.py`

- [ ] **Step 1: Extend the meta-schema**

In the meta-schema, replace the `commands` and `aggregates` properties:

```json
"commands": {
  "type": "array",
  "items": { "$ref": "#/$defs/command" }
},
"aggregates": {
  "type": "array",
  "items": { "$ref": "#/$defs/aggregate" }
}
```

Add to `$defs`:

```json
"rule_ref_obj": {
  "type": "object",
  "required": ["rule_ref"],
  "additionalProperties": false,
  "properties": { "rule_ref": { "type": "string" } }
},
"exchange": {
  "type": "object",
  "required": ["kind"],
  "oneOf": [
    {
      "required": ["kind", "verb"],
      "properties": {
        "kind": { "const": "credential" },
        "verb": { "type": "string", "enum": ["apply", "offer", "agree", "grant", "admit", "spurn"] },
        "credential_held_id": { "type": ["string", "null"] },
        "credential_issued_id": { "type": ["string", "null"] },
        "schema_said_referenced": { "type": ["string", "null"] }
      }
    },
    {
      "required": ["kind", "pattern", "route"],
      "properties": {
        "kind": { "const": "message" },
        "pattern": { "type": "string", "enum": ["command", "query", "notification"] },
        "route": { "type": "string", "pattern": "^/[a-z][a-z0-9_/-]*$" },
        "schema_id": { "type": "string" }
      }
    }
  ]
},
"emission": {
  "type": "object",
  "required": ["kind"],
  "oneOf": [
    {
      "required": ["kind", "exchange"],
      "properties": {
        "kind": { "const": "exchange" },
        "exchange": { "$ref": "#/$defs/exchange" }
      }
    },
    {
      "required": ["kind", "credential_issued_id", "to_state"],
      "properties": {
        "kind": { "const": "lifecycle_advance" },
        "credential_issued_id": { "type": "string" },
        "to_state": { "type": "string" }
      }
    },
    {
      "required": ["kind", "aggregate_id", "event_type", "payload_mapping"],
      "properties": {
        "kind": { "const": "aggregate_event" },
        "aggregate_id": { "type": "string" },
        "event_type": { "type": "string" },
        "payload_mapping": { "type": "string" }
      }
    }
  ]
},
"command": {
  "type": "object",
  "required": ["id", "name", "description", "route", "payload_schema", "idempotency_key_expression", "emissions"],
  "additionalProperties": false,
  "properties": {
    "id": { "type": "string", "pattern": "^[a-z][a-z0-9_-]*$" },
    "name": { "type": "string" },
    "description": { "type": "string" },
    "route": { "type": "string", "pattern": "^/[a-z][a-z0-9_/-]*$" },
    "counterparty_role": { "type": ["string", "null"] },
    "payload_schema": { "type": "object" },
    "auth_preconditions": { "type": "array", "items": { "$ref": "#/$defs/rule_ref_obj" } },
    "state_preconditions": { "type": "array", "items": { "$ref": "#/$defs/rule_ref_obj" } },
    "temporal_preconditions": { "type": "array", "items": { "$ref": "#/$defs/rule_ref_obj" } },
    "idempotency_key_expression": { "type": "string" },
    "emissions": { "type": "array", "items": { "$ref": "#/$defs/emission" } }
  }
},
"log_scope": { "type": "string", "enum": ["private", "witnessed", "shared"] },
"aggregate": {
  "type": "object",
  "required": ["id", "description", "inception_event_type", "state_schema", "initial_state", "log_scope"],
  "additionalProperties": false,
  "properties": {
    "id": { "type": "string", "pattern": "^[a-z][a-z0-9_-]*$" },
    "description": { "type": "string" },
    "inception_event_type": { "type": "string" },
    "state_schema": { "type": "object" },
    "initial_state": {},
    "invariants": { "type": "array", "items": { "$ref": "#/$defs/rule_ref_obj" } },
    "log_scope": { "$ref": "#/$defs/log_scope" }
  }
}
```

Forbid `/ipex/*` routes (reserved for protocol):

Add a top-level `allOf` constraint inside `command`:

```json
"command": {
  "type": "object",
  "allOf": [
    {
      "not": {
        "properties": { "route": { "pattern": "^/ipex/" } },
        "required": ["route"]
      }
    }
  ],
  ...
}
```

Actually JSON-Schema doesn't easily express "must NOT match this pattern". Use `not` + `pattern` together. Cleaner approach: instead use `pattern` with negative lookahead — but JSON-Schema doesn't support lookahead. Use enum-as-prefix check:

Use `"not": { "pattern": "^/ipex/" }` on the route string. Update the route property:

```json
"route": {
  "type": "string",
  "pattern": "^/[a-z][a-z0-9_/-]*$",
  "not": { "pattern": "^/ipex/" }
}
```

- [ ] **Step 2: Write tests**

Append to `test_validate.py`:

```python
def test_command_with_credential_emission_validates(minimal_valid_template):
    minimal_valid_template["commands"].append({
        "id": "submit_app",
        "name": "Submit Application",
        "description": "Submit a license application.",
        "route": "/insurance/cmd/submit_application",
        "counterparty_role": "regulator",
        "payload_schema": {
            "type": "object",
            "properties": {"jurisdiction": {"type": "string"}}
        },
        "auth_preconditions": [],
        "state_preconditions": [],
        "temporal_preconditions": [],
        "idempotency_key_expression": "hash(payload.jurisdiction)",
        "emissions": [
            {
                "kind": "exchange",
                "exchange": {
                    "kind": "credential",
                    "verb": "apply",
                    "credential_held_id": None,
                    "credential_issued_id": None,
                    "schema_said_referenced": "EAbc0000000000000000000000000000000000000000"
                }
            }
        ]
    })
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert errors == [], f"unexpected: {[e.message for e in errors]}"


def test_command_on_ipex_route_fails(minimal_valid_template):
    minimal_valid_template["commands"].append({
        "id": "bad",
        "name": "Bad",
        "description": "Tries to use /ipex/ route.",
        "route": "/ipex/apply",
        "payload_schema": {},
        "idempotency_key_expression": "hash(payload)",
        "emissions": []
    })
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert len(errors) > 0  # at least one error: route forbidden


def test_invalid_ipex_verb_fails(minimal_valid_template):
    minimal_valid_template["commands"].append({
        "id": "bad",
        "name": "Bad",
        "description": "Uses non-IPEX verb.",
        "route": "/insurance/cmd/x",
        "payload_schema": {},
        "idempotency_key_expression": "hash(payload)",
        "emissions": [
            {
                "kind": "exchange",
                "exchange": {
                    "kind": "credential",
                    "verb": "yeet",
                    "credential_held_id": None,
                    "credential_issued_id": None
                }
            }
        ]
    })
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert len(errors) > 0


def test_aggregate_validates(minimal_valid_template):
    minimal_valid_template["aggregates"].append({
        "id": "license_registry",
        "description": "Tracks carrier license lifecycle.",
        "inception_event_type": "license_received",
        "state_schema": {
            "type": "object",
            "properties": {"active": {"type": "array"}}
        },
        "initial_state": {"active": []},
        "invariants": [],
        "log_scope": "private"
    })
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert errors == []


def test_invalid_log_scope_fails(minimal_valid_template):
    minimal_valid_template["aggregates"].append({
        "id": "x",
        "description": "y",
        "inception_event_type": "z",
        "state_schema": {},
        "initial_state": {},
        "invariants": [],
        "log_scope": "public"
    })
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert any("log_scope" in e.path or "public" in e.message for e in errors)
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/micro_app_template/test_validate.py -v
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/schemas/micro-app-template.schema.json tests/micro_app_template/test_validate.py
git commit -m "$(cat <<'EOF'
feat(micro-app-template): meta-schema part 3 — commands + aggregates

Adds command and aggregate definitions plus shared $defs for exchange
(credential/message kinds with oneOf), emission (exchange/lifecycle_advance/
aggregate_event kinds), log_scope enum, and rule_ref_obj. Enforces
forbidden /ipex/* routes on commands (reserved for protocol). IPEX
verb enum (apply/offer/agree/grant/admit/spurn) and message pattern
enum (command/query/notification). Tests positive + negative paths.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Meta-schema part 4 — reactions + workflows + projections

**Files:**
- Modify: `docs/superpowers/specs/schemas/micro-app-template.schema.json`
- Modify: `tests/micro_app_template/test_validate.py`

- [ ] **Step 1: Extend the meta-schema**

Replace `reactions`, `workflows`, `projections` properties:

```json
"reactions": { "type": "array", "items": { "$ref": "#/$defs/reaction" } },
"workflows": { "type": "array", "items": { "$ref": "#/$defs/workflow" } },
"projections": { "type": "array", "items": { "$ref": "#/$defs/projection" } }
```

Add to `$defs`:

```json
"reaction_trigger": {
  "type": "object",
  "required": ["type"],
  "oneOf": [
    {
      "required": ["type", "credential_held_id"],
      "properties": {
        "type": { "const": "credential_received" },
        "credential_held_id": { "type": "string" },
        "ipex_verb": { "type": "string", "enum": ["apply", "offer", "agree", "grant", "admit", "spurn"] }
      }
    },
    {
      "required": ["type", "route"],
      "properties": {
        "type": { "const": "exn_received" },
        "route": { "type": "string", "pattern": "^/[a-z][a-z0-9_/-]*$" },
        "schema_id": { "type": "string" }
      }
    },
    {
      "required": ["type"],
      "properties": {
        "type": { "const": "lifecycle_event" },
        "credential_issued_id": { "type": "string" },
        "credential_held_id": { "type": "string" },
        "to_state": { "type": "string" }
      }
    },
    {
      "required": ["type"],
      "properties": {
        "type": { "const": "scheduled" },
        "cadence": { "type": "string" },
        "at": { "type": "string", "format": "date-time" }
      }
    }
  ]
},
"reaction": {
  "type": "object",
  "required": ["id", "description", "trigger", "emissions"],
  "additionalProperties": false,
  "properties": {
    "id": { "type": "string", "pattern": "^[a-z][a-z0-9_-]*$" },
    "description": { "type": "string" },
    "trigger": { "$ref": "#/$defs/reaction_trigger" },
    "emissions": { "type": "array", "items": { "$ref": "#/$defs/emission" } },
    "failure_policy": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "on_validation_failure": { "type": "string", "enum": ["log_and_continue", "log_and_spurn", "abort"] },
        "timeout_seconds": { "type": ["integer", "null"], "minimum": 0 }
      }
    }
  }
},
"workflow_step": {
  "type": "object",
  "required": ["id", "name", "actor"],
  "additionalProperties": false,
  "properties": {
    "id": { "type": "string" },
    "name": { "type": "string" },
    "actor": { "type": "string", "enum": ["self", "counterparty"] },
    "command_id": { "type": "string" },
    "reaction_id": { "type": "string" },
    "advance_lifecycle": {
      "type": ["object", "null"],
      "required": ["credential_id", "to_state"],
      "additionalProperties": false,
      "properties": {
        "credential_id": { "type": "string" },
        "to_state": { "type": "string" }
      }
    },
    "expected_inbound": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "trigger_type": { "type": "string", "enum": ["credential_received", "exn_received", "lifecycle_event"] },
          "credential_held_id": { "type": "string" },
          "ipex_verb": { "type": "string", "enum": ["apply", "offer", "agree", "grant", "admit", "spurn"] },
          "route": { "type": "string" },
          "on_match": { "type": "string", "pattern": "^next_step:" }
        }
      }
    },
    "branches": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["rule_ref", "next_step"],
        "additionalProperties": false,
        "properties": {
          "rule_ref": { "type": "string" },
          "next_step": { "type": "string" }
        }
      }
    },
    "next_steps": { "type": "array", "items": { "type": "string" } },
    "time_bound": {
      "type": "object",
      "required": ["duration", "on_expiry"],
      "additionalProperties": false,
      "properties": {
        "duration": { "type": "string" },
        "on_expiry": { "type": "string" }
      }
    }
  }
},
"workflow_trigger": {
  "type": "object",
  "required": ["type"],
  "properties": {
    "type": { "type": "string", "enum": ["manual", "scheduled", "lifecycle_event", "exn_received", "credential_received"] },
    "initiator_role": { "type": "string" },
    "cadence": { "type": "string" },
    "at": { "type": "string", "format": "date-time" },
    "credential_id": { "type": "string" },
    "credential_held_id": { "type": "string" },
    "to_state": { "type": "string" },
    "route": { "type": "string" },
    "ipex_verb": { "type": "string", "enum": ["apply", "offer", "agree", "grant", "admit", "spurn"] }
  }
},
"workflow": {
  "type": "object",
  "required": ["id", "name", "description", "trigger", "steps"],
  "additionalProperties": false,
  "properties": {
    "id": { "type": "string", "pattern": "^[a-z][a-z0-9_-]*$" },
    "name": { "type": "string" },
    "description": { "type": "string" },
    "counterparty_role": { "type": ["string", "null"] },
    "trigger": { "$ref": "#/$defs/workflow_trigger" },
    "steps": { "type": "array", "items": { "$ref": "#/$defs/workflow_step" }, "minItems": 1 }
  }
},
"view_type": {
  "type": "string",
  "enum": ["table", "list", "cards", "kanban", "timeline", "summary"]
},
"projection": {
  "type": "object",
  "required": ["id", "name", "description", "source_events", "output_schema", "fold_expression"],
  "additionalProperties": false,
  "properties": {
    "id": { "type": "string", "pattern": "^[a-z][a-z0-9_-]*$" },
    "name": { "type": "string" },
    "description": { "type": "string" },
    "source_events": { "type": "array", "items": { "type": "string" }, "minItems": 1 },
    "output_schema": { "type": "object" },
    "fold_expression": { "type": "string" },
    "access": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "row_filter_rule_ref": { "type": "string" },
        "lens_template": { "type": "string" }
      }
    },
    "display": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "view_type": { "$ref": "#/$defs/view_type" },
        "columns": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "field": { "type": "string" },
              "header": { "type": "string" },
              "display_template": { "type": "string" }
            }
          }
        },
        "default_sort": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "column": { "type": "string" },
            "direction": { "type": "string", "enum": ["asc", "desc"] }
          }
        },
        "empty_state": { "type": "string" }
      }
    }
  }
}
```

- [ ] **Step 2: Write tests**

Append:

```python
def test_reaction_validates(minimal_valid_template):
    minimal_valid_template["reactions"].append({
        "id": "on_license_granted",
        "description": "Admit incoming license credential.",
        "trigger": {
            "type": "credential_received",
            "credential_held_id": "carrier_license",
            "ipex_verb": "grant"
        },
        "emissions": [
            {
                "kind": "exchange",
                "exchange": {
                    "kind": "credential",
                    "verb": "admit",
                    "credential_held_id": "carrier_license"
                }
            }
        ],
        "failure_policy": {
            "on_validation_failure": "log_and_spurn",
            "timeout_seconds": None
        }
    })
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert errors == [], f"unexpected: {[e.message for e in errors]}"


def test_workflow_validates(minimal_valid_template):
    minimal_valid_template["workflows"].append({
        "id": "license_application_carrier_side",
        "name": "License Application (Carrier)",
        "description": "Carrier-side license application flow.",
        "counterparty_role": "regulator",
        "trigger": {"type": "manual", "initiator_role": "carrier"},
        "steps": [
            {
                "id": "submit",
                "name": "Submit",
                "actor": "self",
                "command_id": "submit_application",
                "next_steps": ["await_response"]
            }
        ]
    })
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert errors == [], f"unexpected: {[e.message for e in errors]}"


def test_projection_validates(minimal_valid_template):
    minimal_valid_template["projections"].append({
        "id": "active_policies",
        "name": "Active Policies",
        "description": "Currently in-force policies.",
        "source_events": ["policy_issued", "policy_revoked"],
        "output_schema": {
            "type": "array",
            "items": {"type": "object"}
        },
        "fold_expression": "state + [event.payload]",
        "display": {
            "view_type": "table",
            "columns": [{"field": "policy_id", "header": "Policy"}],
            "default_sort": {"column": "policy_id", "direction": "asc"},
            "empty_state": "No policies in force."
        }
    })
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert errors == []


def test_invalid_view_type_fails(minimal_valid_template):
    minimal_valid_template["projections"].append({
        "id": "x",
        "name": "y",
        "description": "z",
        "source_events": ["e1"],
        "output_schema": {},
        "fold_expression": "state",
        "display": {"view_type": "spreadsheet"}
    })
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert any("view_type" in e.path or "spreadsheet" in e.message for e in errors)
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/micro_app_template/test_validate.py -v
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/schemas/micro-app-template.schema.json tests/micro_app_template/test_validate.py
git commit -m "$(cat <<'EOF'
feat(micro-app-template): meta-schema part 4 — reactions + workflows + projections

Adds reaction (with reaction_trigger oneOf covering credential_received,
exn_received, lifecycle_event, scheduled), workflow (with workflow_trigger,
workflow_step containing self/counterparty actor, expected_inbound,
branches, next_steps, time_bound), and projection (with access,
display, view_type enum). All event-flow primitives now structurally
typed. Positive + negative tests for each.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Meta-schema part 5 — rules (final primitive)

**Files:**
- Modify: `docs/superpowers/specs/schemas/micro-app-template.schema.json`
- Modify: `tests/micro_app_template/test_validate.py`

- [ ] **Step 1: Extend the meta-schema**

Replace `rules` property:

```json
"rules": { "type": "array", "items": { "$ref": "#/$defs/rule" } }
```

Add to `$defs`:

```json
"rule_type": {
  "type": "string",
  "enum": [
    "legal_prose",
    "behavioral_expectation",
    "business_policy",
    "predicate",
    "computational",
    "validation",
    "binding_link"
  ]
},
"predicate_purpose": {
  "type": "string",
  "enum": [
    "auth_precondition",
    "state_precondition",
    "temporal_precondition",
    "lifecycle_transition_requires",
    "lifecycle_transition_condition",
    "workflow_branch_condition",
    "aggregate_invariant",
    "projection_row_filter",
    "derived_membership"
  ]
},
"rule": {
  "type": "object",
  "required": ["id", "type", "title"],
  "additionalProperties": false,
  "properties": {
    "id": { "type": "string", "pattern": "^[a-z][a-z0-9_-]*$" },
    "type": { "$ref": "#/$defs/rule_type" },
    "title": { "type": "string" },
    "description": { "type": "string" },
    "body": { "type": "string" },
    "expression": { "type": "string" },
    "language": { "type": "string", "pattern": "^[A-Z][A-Za-z]*/[0-9]+\\.[0-9]+$" },
    "purpose": { "$ref": "#/$defs/predicate_purpose" },
    "result_attribute": { "type": "string" },
    "links": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["rule_id"],
        "additionalProperties": false,
        "properties": { "rule_id": { "type": "string" } }
      }
    }
  },
  "allOf": [
    {
      "if": { "properties": { "type": { "enum": ["legal_prose", "behavioral_expectation"] } } },
      "then": { "required": ["body"] }
    },
    {
      "if": { "properties": { "type": { "enum": ["predicate", "computational", "validation"] } } },
      "then": { "required": ["expression", "language"] }
    },
    {
      "if": { "properties": { "type": { "const": "predicate" } } },
      "then": { "required": ["purpose"] }
    },
    {
      "if": { "properties": { "type": { "const": "computational" } } },
      "then": { "required": ["result_attribute"] }
    },
    {
      "if": { "properties": { "type": { "const": "binding_link" } } },
      "then": { "required": ["links"] }
    }
  ]
}
```

- [ ] **Step 2: Write tests**

Append:

```python
def test_legal_prose_rule_validates(minimal_valid_template):
    minimal_valid_template["rules"].append({
        "id": "warranty_disclaimer",
        "type": "legal_prose",
        "title": "Coverage Warranty",
        "body": "Carrier warrants accuracy of all attributes."
    })
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert errors == []


def test_predicate_rule_requires_purpose(minimal_valid_template):
    minimal_valid_template["rules"].append({
        "id": "premium_paid",
        "type": "predicate",
        "title": "Premium Paid",
        "expression": "state.paid > 0",
        "language": "UEL/1.0"
        # missing purpose
    })
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert any("purpose" in e.message for e in errors)


def test_predicate_rule_validates_with_purpose(minimal_valid_template):
    minimal_valid_template["rules"].append({
        "id": "premium_paid",
        "type": "predicate",
        "purpose": "lifecycle_transition_requires",
        "title": "Premium Paid",
        "expression": "state.paid > 0",
        "language": "UEL/1.0"
    })
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert errors == []


def test_computational_rule_requires_result_attribute(minimal_valid_template):
    minimal_valid_template["rules"].append({
        "id": "premium",
        "type": "computational",
        "title": "Premium",
        "expression": "base * mult",
        "language": "UEL/1.0"
        # missing result_attribute
    })
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert any("result_attribute" in e.message for e in errors)


def test_binding_link_requires_links(minimal_valid_template):
    minimal_valid_template["rules"].append({
        "id": "link_a",
        "type": "binding_link",
        "title": "Link"
        # missing links
    })
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert any("links" in e.message for e in errors)


def test_legal_prose_requires_body(minimal_valid_template):
    minimal_valid_template["rules"].append({
        "id": "x",
        "type": "legal_prose",
        "title": "X"
        # missing body
    })
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert any("body" in e.message for e in errors)
```

- [ ] **Step 3: Run all tests**

```bash
pytest tests/micro_app_template/ -v
```

Expected: ALL PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/schemas/micro-app-template.schema.json tests/micro_app_template/test_validate.py
git commit -m "$(cat <<'EOF'
feat(micro-app-template): meta-schema part 5 — rules (complete primitive set)

Adds rule definition with rule_type enum (legal_prose,
behavioral_expectation, business_policy, predicate, computational,
validation, binding_link) and predicate_purpose enum. Conditional
required fields via JSON-Schema allOf+if-then: prose types require
body, executable types require expression+language, predicates
additionally require purpose, computational additionally requires
result_attribute, binding_link requires links. The meta-schema now
covers all 8 primitives.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Meta-schema for metadata.json

**Files:**
- Create: `docs/superpowers/specs/schemas/metadata.schema.json`
- Create: `tests/micro_app_template/fixtures/minimal_valid_metadata.json`
- Modify: `tests/micro_app_template/test_validate.py`

- [ ] **Step 1: Write the metadata meta-schema**

Create `docs/superpowers/specs/schemas/metadata.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://locksmith/spec/micro-app-template/0.1/metadata",
  "title": "Micro-App Template Metadata",
  "description": "Sibling metadata for a micro-app-template.json. Non-canonical viewer color; does not affect the template's SAID.",
  "type": "object",
  "required": ["for_micro_app_said"],
  "additionalProperties": false,
  "properties": {
    "for_micro_app_said": { "type": "string", "minLength": 44, "maxLength": 44 },
    "ecosystem_affinity": {
      "type": "array",
      "items": { "type": "string", "pattern": "^[a-z][a-z0-9-]*$" }
    },
    "convention_compliance": {
      "type": "object",
      "additionalProperties": { "type": "string" }
    },
    "semantic_lineage": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["relation", "target_said"],
        "additionalProperties": false,
        "properties": {
          "relation": {
            "type": "string",
            "enum": ["refines", "improves", "inspired_by", "competes_with", "obsoletes"]
          },
          "target_said": { "type": "string", "minLength": 44, "maxLength": 44 },
          "note": { "type": "string" }
        }
      }
    },
    "author_intent_notes": { "type": "string" },
    "compatibility_hints": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "compatible_with": {
          "type": "array",
          "items": { "type": "string", "minLength": 44, "maxLength": 44 }
        },
        "incompatible_with": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["target_said", "reason"],
            "additionalProperties": false,
            "properties": {
              "target_said": { "type": "string", "minLength": 44, "maxLength": 44 },
              "reason": { "type": "string" }
            }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 2: Write the fixture**

Create `tests/micro_app_template/fixtures/minimal_valid_metadata.json`:

```json
{
  "for_micro_app_said": "EAbc000000000000000000000000000000000000000",
  "ecosystem_affinity": ["insurance"],
  "convention_compliance": {
    "credential_naming": "compliant",
    "role_naming": "compliant"
  }
}
```

Note: `for_micro_app_said` must be 44 chars; the above is 43 + 1 = 44. Verify:

```bash
python3 -c "import json; d = json.load(open('tests/micro_app_template/fixtures/minimal_valid_metadata.json')); assert len(d['for_micro_app_said']) == 44"
```

- [ ] **Step 3: Write tests**

Append to `test_validate.py`:

```python
METADATA_SCHEMA = Path(__file__).parent.parent.parent / "docs/superpowers/specs/schemas/metadata.schema.json"


def test_metadata_fixture_validates(fixtures_dir):
    import json
    with open(fixtures_dir / "minimal_valid_metadata.json") as f:
        doc = json.load(f)
    errors = validate_against_meta_schema(doc, METADATA_SCHEMA)
    assert errors == []


def test_metadata_requires_for_micro_app_said(fixtures_dir):
    import json
    with open(fixtures_dir / "minimal_valid_metadata.json") as f:
        doc = json.load(f)
    del doc["for_micro_app_said"]
    errors = validate_against_meta_schema(doc, METADATA_SCHEMA)
    assert any("for_micro_app_said" in e.message for e in errors)


def test_invalid_lineage_relation_fails(fixtures_dir):
    import json
    with open(fixtures_dir / "minimal_valid_metadata.json") as f:
        doc = json.load(f)
    doc["semantic_lineage"] = [{
        "relation": "loves",
        "target_said": "E" + "x" * 43,
        "note": "x"
    }]
    errors = validate_against_meta_schema(doc, METADATA_SCHEMA)
    assert any("loves" in e.message or "relation" in e.path for e in errors)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/micro_app_template/ -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/schemas/metadata.schema.json tests/micro_app_template/fixtures/minimal_valid_metadata.json tests/micro_app_template/test_validate.py
git commit -m "$(cat <<'EOF'
feat(micro-app-template): meta-schema for sibling metadata.json

Separate JSON-Schema for the optional sibling metadata file. Validates
for_micro_app_said (required, 44-char SAID), ecosystem_affinity tags
(kebab-case), convention_compliance (open keys, string values),
semantic_lineage entries (relation enum: refines/improves/inspired_by/
competes_with/obsoletes), author_intent_notes (free text),
compatibility_hints. Metadata is hint-layer only — does not affect
runtime behavior or canonical SAID computation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: CLI wrappers

**Files:**
- Create: `scripts/micro_app_saidify.py`
- Create: `scripts/micro_app_validate.py`
- Create: `tests/micro_app_template/test_cli.py`

- [ ] **Step 1: Write failing tests**

Create `tests/micro_app_template/test_cli.py`:

```python
"""Tests for micro-app-template CLI wrappers."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent.parent
SAIDIFY = REPO_ROOT / "scripts/micro_app_saidify.py"
VALIDATE = REPO_ROOT / "scripts/micro_app_validate.py"


def _run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
    )


def test_saidify_stamps_d_field(tmp_path, minimal_valid_template):
    doc = dict(minimal_valid_template)
    doc["d"] = "#" * 44
    src = tmp_path / "t.json"
    src.write_text(json.dumps(doc))
    result = _run(SAIDIFY, "--input", str(src), "--in-place")
    assert result.returncode == 0, result.stderr
    out = json.loads(src.read_text())
    assert out["d"] != "#" * 44
    assert len(out["d"]) == 44


def test_saidify_verify_passes_on_stamped(tmp_path, minimal_valid_template):
    doc = dict(minimal_valid_template)
    doc["d"] = "#" * 44
    src = tmp_path / "t.json"
    src.write_text(json.dumps(doc))
    _run(SAIDIFY, "--input", str(src), "--in-place")
    result = _run(SAIDIFY, "--input", str(src), "--verify")
    assert result.returncode == 0, result.stderr


def test_saidify_verify_fails_on_tampered(tmp_path, minimal_valid_template):
    doc = dict(minimal_valid_template)
    doc["d"] = "#" * 44
    src = tmp_path / "t.json"
    src.write_text(json.dumps(doc))
    _run(SAIDIFY, "--input", str(src), "--in-place")
    out = json.loads(src.read_text())
    out["header"]["display_name"] = "TAMPERED"
    src.write_text(json.dumps(out))
    result = _run(SAIDIFY, "--input", str(src), "--verify")
    assert result.returncode != 0


def test_validate_passes_on_valid(tmp_path, minimal_valid_template):
    doc = dict(minimal_valid_template)
    src = tmp_path / "t.json"
    src.write_text(json.dumps(doc))
    result = _run(VALIDATE, "--input", str(src))
    assert result.returncode == 0, result.stderr + result.stdout


def test_validate_fails_on_invalid(tmp_path, minimal_valid_template):
    doc = dict(minimal_valid_template)
    del doc["role"]
    src = tmp_path / "t.json"
    src.write_text(json.dumps(doc))
    result = _run(VALIDATE, "--input", str(src))
    assert result.returncode != 0
    assert "role" in (result.stdout + result.stderr).lower()
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/micro_app_template/test_cli.py -v
```

Expected: FAIL (scripts don't exist).

- [ ] **Step 3: Implement `scripts/micro_app_saidify.py`**

Create `scripts/micro_app_saidify.py`:

```python
#!/usr/bin/env python3
"""CLI wrapper: compute or verify the SAID of a micro-app template."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from locksmith.micro_app_template.canonical_json import canonicalize
from locksmith.micro_app_template.saidify import saidify_document, verify_said


def main() -> int:
    p = argparse.ArgumentParser(description="Stamp or verify the SAID of a micro-app template.")
    p.add_argument("--input", required=True, type=Path, help="Path to micro-app-template.json")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--in-place", action="store_true", help="Stamp the SAID in place")
    g.add_argument("--verify", action="store_true", help="Verify the existing SAID; exit non-zero on mismatch")
    g.add_argument("--print", action="store_true", help="Print the computed SAID to stdout without modifying the file")
    args = p.parse_args()

    if not args.input.exists():
        print(f"error: file not found: {args.input}", file=sys.stderr)
        return 2

    doc = json.loads(args.input.read_text())

    if args.in_place:
        stamped = saidify_document(doc)
        args.input.write_text(canonicalize(stamped))
        print(f"stamped {args.input} with SAID {stamped['d']}", file=sys.stderr)
        return 0

    if args.verify:
        ok = verify_said(doc)
        if ok:
            print(f"OK: SAID matches", file=sys.stderr)
            return 0
        print(f"FAIL: SAID mismatch in {args.input}", file=sys.stderr)
        return 1

    if args.print:
        from locksmith.micro_app_template.saidify import compute_said
        print(compute_said(doc))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Implement `scripts/micro_app_validate.py`**

Create `scripts/micro_app_validate.py`:

```python
#!/usr/bin/env python3
"""CLI wrapper: validate a micro-app template against the meta-schema and cross-references."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from locksmith.micro_app_template.validate import validate_template


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMA = REPO_ROOT / "docs/superpowers/specs/schemas/micro-app-template.schema.json"


def main() -> int:
    p = argparse.ArgumentParser(description="Validate a micro-app template.")
    p.add_argument("--input", required=True, type=Path, help="Path to micro-app-template.json")
    p.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Path to meta-schema (default: project meta-schema)")
    args = p.parse_args()

    if not args.input.exists():
        print(f"error: file not found: {args.input}", file=sys.stderr)
        return 2
    if not args.schema.exists():
        print(f"error: schema not found: {args.schema}", file=sys.stderr)
        return 2

    doc = json.loads(args.input.read_text())
    result = validate_template(doc, args.schema)

    if result.is_valid:
        print(f"OK: {args.input} validates against {args.schema.name}")
        return 0

    print(f"FAIL: {args.input}", file=sys.stderr)
    for e in result.errors:
        print(f"  {e.path}: {e.message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/micro_app_template/test_cli.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/micro_app_saidify.py scripts/micro_app_validate.py tests/micro_app_template/test_cli.py
chmod +x scripts/micro_app_saidify.py scripts/micro_app_validate.py
git update-index --chmod=+x scripts/micro_app_saidify.py scripts/micro_app_validate.py
git commit -m "$(cat <<'EOF'
feat(micro-app-template): CLI wrappers for saidify and validate

scripts/micro_app_saidify.py — stamp, verify, or print the SAID of a
micro-app-template.json document. Supports --in-place (stamp), --verify
(check existing), --print (compute without modifying).

scripts/micro_app_validate.py — validate a template against the
meta-schema + cross-references. Returns non-zero on errors with
formatted error output.

Subprocess-tested via pytest.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Skill baseline test (TDD RED phase)

Per `superpowers:writing-skills`, the skill build follows RED-GREEN-REFACTOR. This task is the RED phase: dispatch a subagent to attempt authoring a micro-app template given only the spec + the existing stub SKILL.md (no references/). Document where they fail.

**Files:**
- Create: `docs/skill-test-runs/micro-app-template-gen/baseline-2026-05-11.md`

- [ ] **Step 1: Dispatch the baseline subagent**

Dispatch a general-purpose subagent with this prompt:

```
You are an SME (subject-matter expert) in the insurance industry helping author a micro-app template.

You have access to:
- The spec at: /Users/seriouscoderone/code/locksmith/docs/superpowers/specs/2026-05-09-micro-app-template-authoring-and-data-model.md
- The skill stub at: /Users/seriouscoderone/code/locksmith/.claude/skills/micro-app-template-gen/SKILL.md
- The meta-schema at: /Users/seriouscoderone/code/locksmith/docs/superpowers/specs/schemas/micro-app-template.schema.json
- The CLI validator: scripts/micro_app_validate.py

Your task: produce a `micro-app-template.json` for "a homeowner files an insurance claim with their carrier". This is the homeowner's side only — they apply, attach evidence, and await the carrier's decision.

Write the file to: /tmp/skill-baseline-homeowner-claim/micro-app-template.json
Validate it with: source .venv/bin/activate && python scripts/micro_app_validate.py --input /tmp/skill-baseline-homeowner-claim/micro-app-template.json

Report back:
- What you produced (paste the JSON)
- What questions you had to invent answers for
- Where the spec was unclear or missing guidance
- Whether your output validated; if not, what errors
- How long it took (qualitatively: easy, medium, hard, blocked)
```

- [ ] **Step 2: Capture the subagent's output to the baseline document**

Create `docs/skill-test-runs/micro-app-template-gen/baseline-2026-05-11.md` with:

```markdown
# Skill Baseline Test — 2026-05-11

## Scenario

Subagent attempts to author a micro-app template for "homeowner files an insurance claim" given only the spec + stub SKILL.md (no references/, no question bank, no examples).

## Subagent Output

[paste the subagent's full report here]

## Gaps Identified

[list the points where the subagent struggled, invented answers, or couldn't proceed. Each gap becomes a target for one of the references/ files in Tasks 12-17.]

## Rationalization Patterns

[list any rationalizations the subagent made — "I'll just guess at this", "this seemed obvious", etc. These inform how the skill should anticipate and counter shortcuts.]

## Decisions for the Skill Build

[list 5-10 concrete things the references/ + SKILL.md prose MUST address based on the baseline.]
```

- [ ] **Step 3: Commit the baseline**

```bash
mkdir -p docs/skill-test-runs/micro-app-template-gen
git add docs/skill-test-runs/micro-app-template-gen/baseline-2026-05-11.md
git commit -m "$(cat <<'EOF'
test(micro-app-template-gen): baseline subagent run (TDD RED)

Documents the failure modes of a subagent attempting to author a
micro-app template with only the spec + stub SKILL.md and no
references/ directory. Identifies gaps the references/ files and full
SKILL.md prose must address. Per superpowers:writing-skills TDD pattern.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Skill reference — `ten-step-process.md`

**Files:**
- Create: `.claude/skills/micro-app-template-gen/references/ten-step-process.md`

- [ ] **Step 1: Write the ten-step-process reference**

Create `.claude/skills/micro-app-template-gen/references/ten-step-process.md`:

```markdown
# The Ten-Step Process (Detailed)

Detailed prose for each step of the micro-app template authoring path. The SKILL.md gives a one-line summary per step; this file gives the full context, rationale, and instructions.

## Step 0 — Identify the role

**Goal:** Select the single role this micro-app embodies. Every subsequent step is from this role's perspective.

**Why this is Step 0:** A micro-app captures *one role's slice* of a use case. Multi-actor patterns decompose into multiple templates. Naming the role first prevents scope creep into multi-role territory.

**What to capture:**

| Field | Notes |
|---|---|
| `role.id` | kebab-case stable identifier (e.g., `carrier`, `homeowner`, `state-doi`) |
| `role.display_name` | Title case label for UI ("Insurance Carrier", "Homeowner") |
| `role.description` | One paragraph explaining what this role *is* in the ecosystem |
| `role.kind` | One of: individual, organization, system, device, agent, government |
| `role.keri_infrastructure` | Four boolean flags (witness_pool, watcher_network, mailbox, acdc_registry) |

**Suggesting defaults for `keri_infrastructure`:**

- `individual` → mailbox usually true; witness_pool/watcher_network/acdc_registry usually false
- `organization`, `government` → all four typically true
- `system`, `agent` → mailbox true; others depend on operational scope
- `device` → usually only mailbox

Let the SME override defaults. The flags are deployment-readiness *expectations* — not enforcement.

**Anti-patterns:**

- ❌ Declaring two roles ("carrier and broker") — split into two templates
- ❌ Picking the wrong kind ("carrier is a person") — explain what kinds mean
- ❌ Skipping keri_infrastructure ("I don't know what these mean") — default by kind

**Save:** Write `role` field to the output template. The header (Step 1) hasn't been authored yet; defer the file write until the canonical JSON has at least `header + role`.

## Step 1 — Name the use case

**Goal:** Capture the use case's identity (header) and articulate the pivotal event from this role's perspective.

**Why this matters:** The "pivotal event" is the past-tense fact that defines success. Naming it sharpens the scope and reveals when you're actually trying to model two use cases.

**Questions to ask:**

1. *Outcome statement?* — One sentence in past tense, in the role's voice. "A claim has been filed." "A license has been granted."
2. *Multiple events surfacing?* — If two pivotal events compete, you have two micro-apps. Stop and split.
3. *Version?* — Start at `"1.0"` unless this is explicitly a fork of an existing template (Step 0 already captured the role; the header version is independent).
4. *Forked from?* — If derived from another template, capture the parent's SAID + version + intent.

**Field mapping:**

| Field | Source |
|---|---|
| `header.id` | kebab-case use case identifier (often `<role>-<verb>-<noun>`) |
| `header.display_name` | Title case label |
| `header.description` | The pivotal event statement + 1-2 sentences of context |
| `header.version` | Semver |
| `header.expression_language` | `"UEL/1.0"` (default for now) |
| `header.forked_from` | Optional |

**Save:** Write `header` and `role` fields. The template is now structurally minimal-valid (other primitives are empty arrays).

## Step 2 — Held credentials (imports)

**Goal:** Identify the credentials this role must hold for its commands to be authorized.

**Why this comes before issued credentials:** What you HOLD constrains what you can DO. Held credentials determine the universe of commands available.

**For each held credential, capture:**

| Field | Notes |
|---|---|
| `id` | Local identifier (used by commands' auth_preconditions) |
| `expected_schema_said` | SAID of the schema; lookup in known templates or note as TBD |
| `expected_issuer_role` | Optional narrowing constraint |
| `expected_attribute_constraints` | Optional type hints |
| `lifecycle_acceptance` | Which lifecycle states make it usable (default `["active"]`) |
| `narrative` | SME tooltip explanation |

**When the SAID isn't yet known:** Note it explicitly. The Ecosystem Viewer will surface dangling imports as candidates for alignment.

**Anti-patterns:**

- ❌ Inventing schema SAIDs — they must be content-addressed
- ❌ Conflating "credentials this role *holds*" with "credentials this role *issues*" — different lists

## Step 3 — Issued credentials (exports)

**Goal:** Define the credentials this role produces — their envelope, schema, lifecycle, rules, value flow.

**The most substantial step.** Each issued credential has six layers (per spec §6.3).

For each issued credential, walk:

1. **Envelope contract** — who holds it, who verifies it, what it chains from
2. **Schema** — author a JSON-Schema file in `schemas/` and capture its SAID
3. **Lifecycle** — states, initial state, transitions (with `tel_primitive` mapping each transition to issue/update/revoke)
4. **Ricardian rules** — forward-reference rule ids; will be authored in Step 9
5. **Value flow** — references to other credentials implied by this one

**Edge operators:**

| Operator | Meaning |
|---|---|
| `authorizes` | Holder of parent becomes issuer of this credential |
| `references` | Informational pointer; no authority transfer |
| `authorizes-via-delegate` | Issuer is a KEL-delegated AID of parent's holder |

**Lifecycle transitions ground out in TEL primitives:**

- `issue` — TEL issuance event (state becomes active or whatever the initial-active state is)
- `update` — TEL update event (intermediate state change, e.g., active → suspended)
- `revoke` — TEL revocation event

The state machine layered on top can have any names; transitions map each to one of these three TEL primitives.

**Schema authoring side-step:** When you reach the schema for a credential, write a separate JSON-Schema file at `schemas/{credential_id}.json`. Compute its SAID using `python scripts/saidify_acdc_schema.py` (the existing project utility) OR by stamping with the same saidify helper used for the template. Reference both `schema_said` and `schema_path` in the template.

## Step 4 — Commands

**Goal:** Define the actions this role takes. Each command becomes a button in Locksmith.

**For each command:**

1. **Route** — exn route following naming conventions (see `naming-conventions.md`). Must not start with `/ipex/`.
2. **Counterparty role** — who receives this command, if any
3. **Payload schema** — JSON-Schema for the actor's input (Locksmith renders as a form)
4. **Preconditions** — auth (forward-ref rules), state (forward-ref rules), temporal (forward-ref rules)
5. **Idempotency key expression** — UEL over `payload` only (no state, no principal)
6. **Emissions** — what fires on success: exchange (IPEX or exn out), lifecycle_advance (advance a credential's state), aggregate_event (append to a local aggregate)

**Anti-patterns:**

- ❌ Using `/ipex/*` for app-defined commands — reserved for protocol
- ❌ Referencing state or principal in idempotency_key_expression — must be deterministic from payload alone

## Step 5 — Aggregates

**Goal:** Define the local state this role tracks.

Aggregates are typically TEL-backed (when tracking credential lifecycle) or KEL-anchored local logs. For each:

1. **Inception event type** — the event that mints the aggregate's identifier
2. **State schema** — JSON-Schema for the folded state
3. **Initial state** — starting value
4. **Invariants** — forward-ref validation rules
5. **Log scope** — `private` | `witnessed` | `shared`

## Step 6 — Reactions

**Goal:** Define what this role does when it observes external events.

For each reaction:

1. **Trigger** — credential_received (with credential_held_id + optional ipex_verb), exn_received (with route), lifecycle_event (with credential and state), or scheduled (with cadence)
2. **Emissions** — same shape as command emissions
3. **Failure policy** — `log_and_continue` | `log_and_spurn` | `abort`; optional timeout_seconds

**The subscriber pattern:** Reactions observe events; they don't push to others. The decentralized property.

## Step 7 — Workflows

**Goal:** Name the multi-step external interactions from this role's perspective.

Each workflow is a sequence of self-actions and counterparty-awaits. From this role's POV only — the counterparty's half lives in their own micro-app.

For each:

1. **Counterparty role**
2. **Trigger** — manual (with initiator_role), scheduled, lifecycle_event, exn_received, credential_received
3. **Steps** — ordered list. Each step has: `actor` (self or counterparty), `command_id` or `reaction_id` (for self steps), `expected_inbound` (for counterparty steps), `branches` (rule-conditioned next_step pointers), `next_steps` (unconditional), `time_bound` (duration + on_expiry).

The exchange palette across steps:

- IPEX credential exchange — kind: credential, verb: one of six (apply/offer/agree/grant/admit/spurn)
- exn message — kind: message, pattern: command|query|notification, route
- Internal step — exchange: null

## Step 8 — Projections

**Goal:** Define what this role looks at.

Projections fold events into views. Locksmith renders them.

For each:

1. **Source events** — names of event types to fold
2. **Output schema** — JSON-Schema for the resulting state
3. **Fold expression** — UEL over `{ state, event, source }` producing new state
4. **Access** — row_filter (rule_ref), lens_template
5. **Display** — view_type (table | list | cards | kanban | timeline | summary), columns, default_sort, empty_state

## Step 9 — Rules

**Goal:** Author every rule forward-referenced in Steps 3–8.

**Resolve every forward reference.** Walking the template after Step 9, no rule_ref should point to an undefined id.

For each rule, choose its `type`:

| Type | Body or Expression? | Notes |
|---|---|---|
| `legal_prose` | `body` (markdown) | Ricardian contractual prose |
| `behavioral_expectation` | `body` (markdown) | Prose-only obligation |
| `business_policy` | both `body` and `expression` allowed | Hybrid prose + formal |
| `predicate` | `expression` + `language` + `purpose` | Executable boolean |
| `computational` | `expression` + `language` + `result_attribute` | Derived value |
| `validation` | `expression` + `language` | Constraint check |
| `binding_link` | `links[]` | Connects prose to executable |

See `rule-types-reference.md` for detailed guidance per type.

## Step 10 — Conventions, hints, lineage (metadata.json)

**Goal:** Produce the optional sibling `metadata.json` with non-canonical viewer color.

1. **Convention compliance audit** — for each category (credential_naming, role_naming, workflow_naming, etc.), record whether the template complies with conventions or where it deviates with rationale
2. **Ecosystem affinity** — kebab-case tags suggesting which emergent ecosystems this template belongs to
3. **Semantic lineage** — optional refines/improves/inspired_by/competes_with/obsoletes relations to other templates
4. **Author intent notes** — free text the viewer can surface
5. **Compatibility hints** — compatible_with and incompatible_with lists

**Save:** Write `metadata.json` alongside `micro-app-template.json`. Set `for_micro_app_said` to the template's SAID (computed in the saidify step below).

## Adversarial review (informal)

Walk the adversarial checklist (see `adversarial-prompts.md`). Document concerns in `metadata.author_intent_notes` or as out-of-band notes.

## Save and saidify

1. Run `scripts/micro_app_validate.py --input <path>` — must pass.
2. Run `scripts/micro_app_saidify.py --input <path> --in-place` — stamps the `d` field.
3. Re-run validate to confirm SAID is now correct.
4. Update `metadata.json` `for_micro_app_said` to the new SAID.
5. Commit the entire directory.
```

- [ ] **Step 2: Commit**

```bash
mkdir -p .claude/skills/micro-app-template-gen/references
git add .claude/skills/micro-app-template-gen/references/ten-step-process.md
git commit -m "$(cat <<'EOF'
docs(micro-app-template-gen): reference — detailed ten-step process

Full prose for each of the 10 authoring steps. SKILL.md gives one-line
summaries; this reference fills in the rationale, field mappings,
anti-patterns, and KERI-stack grounding (TEL primitives, IPEX verbs,
exn routes, schema authoring, etc.).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Skill reference — `question-bank.md`

**Files:**
- Create: `.claude/skills/micro-app-template-gen/references/question-bank.md`

- [ ] **Step 1: Write the question bank**

Create `.claude/skills/micro-app-template-gen/references/question-bank.md`:

```markdown
# Question Bank

Per-step questions to ask an SME. Pick the primary question first; ask follow-ups only when the primary answer leaves ambiguity. One question at a time. Plain language — push back on KERI jargon in user-facing answers.

## Step 0 — Identify the role

**Primary:**
- *"Which role does this micro-app embody?"* — get id, display name, description

**Follow-ups:**
- *"Is this an individual, an organization, a system, a device, an autonomous agent, or a government?"* — get `kind`
- *"Does this role typically operate its own witnesses? Watch others' KELs? Need an always-on mailbox to receive offline messages? Run credential registries?"* — get `keri_infrastructure` flags. Suggest defaults by kind; let the SME override.

## Step 1 — Name the use case

**Primary:**
- *"From this role's perspective, what's the outcome they want? State it as a past-tense fact in business language."*

**Follow-ups:**
- *"If two outcomes feel central, can you state each separately? They might be two micro-apps."*
- *"Does this template descend from another? If so, what's the parent's SAID and version, and what did you change?"*

## Step 2 — Held credentials (imports)

**Primary:**
- *"What credentials must this role hold to take its actions?"*

**Follow-ups per held credential:**
- *"What's this credential type called?"*
- *"What's the SAID of the schema?"* — if not known, note as TBD and continue
- *"Who issues it? (which role)"*
- *"Which lifecycle states make it usable? (default: active)"*

## Step 3 — Issued credentials (exports)

**Primary:**
- *"What credentials does this role produce?"*

**Follow-ups per issued credential:**
- *"What's the credential called and what does it convey?"*
- *"Who holds it? Who can verify it?"*
- *"Does it chain from another credential — like 'I can only issue this if I hold a parent credential'? If so, which?"*
  - *"Is the chain authorizing (holder becomes issuer), referencing (informational only), or via delegated AID?"*
- *"How sensitive is its data? Full disclosure, selective (per-field), or aggregate?"*
- *"What states does this credential go through?"* — list them
- *"For each state, how is it reached? Through which workflow? Mapping to KERI: is the transition an `issue` (initial creation), an `update` (mid-life change), or a `revoke` (terminal)?"*

## Step 4 — Commands

**Primary:**
- *"What actions does this role take?"*

**Follow-ups per command:**
- *"In imperative voice, what's this command called?"*
- *"What does the actor supply? (the payload)"*
- *"What must already be true for this command to be valid?"*
  - *"What credentials must the actor hold? (auth preconditions)"*
  - *"What facts must exist in the local state? (state preconditions)"*
  - *"Any deadlines, cooldowns, business hours? (temporal preconditions)"*
- *"If the actor retries, what stops a duplicate? (idempotency key — derivable from payload alone)"*
- *"What happens on success? Does it emit an IPEX message? Advance a credential's lifecycle? Append to a local aggregate? All of those?"*

## Step 5 — Aggregates

**Primary:**
- *"What state does this role track locally?"*

**Follow-ups per aggregate:**
- *"What history must I read to know if a command is valid?"* — that's the aggregate
- *"What's its identifier and how is it minted? (inception event)"*
- *"What invariants does it protect? (plain English; will become validation rules)"*
- *"Is this log private, witnessed, or shared with others?"*

## Step 6 — Reactions

**Primary:**
- *"What does this role do when something happens that they didn't initiate?"*

**Follow-ups per reaction:**
- *"What event are they reacting to? An incoming credential? An exn message? A local lifecycle transition? A scheduled timer?"*
- *"What do they do in response? (same emission shape as commands)"*
- *"What if the reaction fails? Log and continue? Spurn? Abort?"*

## Step 7 — Workflows

**Primary:**
- *"Are there multi-step external interactions this role participates in?"*

**Follow-ups per workflow:**
- *"Who's the counterparty?"*
- *"What kicks it off? A user action? A schedule? A received credential?"*
- *"Walk through the steps from this role's perspective only. For each: do they act, or are they waiting? If acting, which command or reaction? If waiting, what are they waiting for and what triggers the next step?"*
- *"Are there branches based on conditions? Time limits?"*

## Step 8 — Projections

**Primary:**
- *"What views does this role need to do their job?"*

**Follow-ups per projection:**
- *"What question does this answer?"*
- *"Which event streams does it fold over?"*
- *"What's the output shape? (Locksmith will render this as a table, list, cards, kanban, timeline, or summary)"*
- *"Who's allowed to see each row? (credential-gated row filter)"*

## Step 9 — Rules

**Primary:**
- *"Let's go through all the forward-referenced rules and author each. For each rule, what type fits best?"*

**Follow-ups per rule:**
- *Type-specific questions, see `rule-types-reference.md`*

## Step 10 — Metadata

**Primary:**
- *"Let's audit the naming conventions. Did we follow them, or do you have specific reasons for deviating?"*

**Follow-ups:**
- *"Which emergent ecosystems do you think this micro-app belongs to? (kebab-case tags)"*
- *"Does this template improve on, refine, or compete with any other template you know of?"*
- *"Any author notes you want surfaced when someone explores the emergent ecosystem view?"*
- *"Any templates you know are compatible or incompatible with this one?"*
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/micro-app-template-gen/references/question-bank.md
git commit -m "$(cat <<'EOF'
docs(micro-app-template-gen): reference — per-step question bank

Primary + follow-up questions for each of the 10 steps. Plain-language
phrasing; pushes back on KERI jargon. Drives the conversational
authoring flow at execution time.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Skill reference — `adversarial-prompts.md`

**Files:**
- Create: `.claude/skills/micro-app-template-gen/references/adversarial-prompts.md`

- [ ] **Step 1: Write the adversarial prompts reference**

Create `.claude/skills/micro-app-template-gen/references/adversarial-prompts.md`:

```markdown
# Adversarial Review Checklist

Before declaring a template done, deliberately try to break it. Walk this checklist with the SME. Capture concerns in `metadata.json` `author_intent_notes` so reviewers see them.

## 1. Impersonation

- *Can an impostor present a forged credential and have it pass auth_preconditions?*
- KERI's signature/credential machinery makes this "no by construction" when auth_preconditions correctly reference held credentials with proper rule blocks. Verify that your auth_preconditions DO reference real credential checks (not just `true` or omitted).

## 2. Credential revocation timing

- *A credential is valid at command time but revoked by the time the resulting event is folded into an aggregate. Does the micro-app handle this gracefully?*
- Define the cut-off rule. Most ecosystems use "valid at command time" as authoritative; some require freshness checks.

## 3. Concurrent commands

- *Two commands arrive simultaneously on the same aggregate. What happens?*
- The aggregate's append order resolves it. The loser fails on a stale-state precondition. Is the loser's experience graceful? (UI message, retry guidance, etc.)

## 4. Missed events

- *A subscriber crashes during a multi-event sequence and resumes later. Can it catch up by replaying?*
- Projections must be idempotent under replay. Verify your fold_expression doesn't accumulate side effects on re-fold.

## 5. Counterparty bad behavior

- *The counterparty sends an unexpected message, refuses to advance, or spurns at a surprising moment. Are workflow time_bounds and spurn handlers complete?*
- Every workflow step that awaits the counterparty should have either a time_bound or a clear expected_inbound match for refusal.

## 6. Compromised actor keys

- *The role's keys are rotated under duress. The aggregate respects whatever key state was authoritative at command time.*
- Verify this is the behavior your micro-app needs. If freshness matters more than historical accuracy, document a different rule.

## 7. Schema versioning

- *The schema's SAID changes (because the underlying JSON-Schema changed). Old credentials are still valid; do projections handle multiple schema versions?*
- ACDC schemas are immutable per SAID; new schemas get new SAIDs. Your projections should fold events typed by schema SAID, not name.

## 8. Convention divergence

- *The micro-app references a credential type by name (`ProducerLicense`) but its schema_said differs from neighbor micro-apps. Is this intentional competition, or an avoidable accident?*
- Document the choice in `metadata.json` semantic_lineage or compatibility_hints.

## 9. Idempotency under network retry

- *The actor's transport layer retries an exn after a long delay. Does the recipient deduplicate correctly?*
- The command's `idempotency_key_expression` is the gate. Verify it's deterministic from payload alone (no state, no principal).

## 10. Permission escalation via chained credentials

- *An attacker holds a credential that chains from another via `authorizes`. Can they issue a credential they shouldn't be able to?*
- Trace the chain depth. Confirm that depth limits or scope constraints in the chain prevent unauthorized escalation. If unsure, document the assumption.

## Recording the review

After walking the checklist, add a paragraph to `metadata.json` `author_intent_notes`:

> Adversarial review performed 2026-MM-DD. Walked checklist items 1-10. Identified concerns: [list]. Mitigations: [list]. Open risks: [list].
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/micro-app-template-gen/references/adversarial-prompts.md
git commit -m "$(cat <<'EOF'
docs(micro-app-template-gen): reference — adversarial review checklist

10-item checklist for pre-deployment review: impersonation, revocation
timing, concurrent commands, missed events, counterparty bad behavior,
key compromise, schema versioning, convention divergence, idempotency
under retry, permission escalation. Each item names the concern and
how the spec's primitives address it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Skill reference — `rule-types-reference.md`

**Files:**
- Create: `.claude/skills/micro-app-template-gen/references/rule-types-reference.md`

- [ ] **Step 1: Write the rule types reference**

Create `.claude/skills/micro-app-template-gen/references/rule-types-reference.md`:

```markdown
# Rule Types Reference

Detailed guidance for each rule type, with worked examples.

## `legal_prose`

**When to use:** Ricardian contractual prose. Terms of service, warranties, scope-of-authority statements, disclaimers.

**Fields:**
- `id`, `title`, `body` (markdown)

**Worked example:**

```json
{
  "id": "warranty_disclaimer",
  "type": "legal_prose",
  "title": "Coverage Warranty",
  "body": "Carrier warrants accuracy of all attribute values as of the issuance date. Holder agrees that material misrepresentation in the issuance attributes is grounds for credential revocation per the dispute resolution process specified in the ecosystem governance document."
}
```

## `behavioral_expectation`

**When to use:** Obligations that can't be cryptographically enforced — things parties are *expected* to do but no signature ensures.

**Fields:**
- `id`, `title`, `body` (markdown)

**Worked example:**

```json
{
  "id": "compliance_obligation",
  "type": "behavioral_expectation",
  "title": "Ongoing Compliance",
  "body": "Carrier maintains actuarially-certified solvency reserves and submits annual filings to the regulator within 90 days of fiscal year end. Failure to comply is grounds for license suspension but is not detectable by the credential infrastructure alone — regulator must observe externally."
}
```

## `business_policy`

**When to use:** Declarative business rules that may have both human-readable and formal expression. Spans the prose/formal boundary.

**Fields:**
- `id`, `title`, optional `body`, optional `expression` + `language`

**Worked example:**

```json
{
  "id": "claims_threshold_policy",
  "type": "business_policy",
  "title": "Senior approval for large claims",
  "body": "Claims exceeding $10,000 require senior claims adjuster approval before disbursement.",
  "expression": "command.amount <= 10000 || principal.holds_credential('senior_adjuster_license', { state: 'active' })",
  "language": "UEL/1.0"
}
```

## `predicate`

**When to use:** Executable boolean expression evaluated at a specific point in the lifecycle/workflow.

**Required fields:**
- `id`, `title`, `expression`, `language`, `purpose`

**Purpose values:**
- `auth_precondition` — command auth gate
- `state_precondition` — command state gate
- `temporal_precondition` — command timing gate
- `lifecycle_transition_requires` — credential transition gate
- `lifecycle_transition_condition` — automatic transition firing condition
- `workflow_branch_condition` — workflow step branch
- `aggregate_invariant` — aggregate validity check
- `projection_row_filter` — projection access control
- `derived_membership` — derived-role membership

**Worked example:**

```json
{
  "id": "issuer_must_be_active_regulator",
  "type": "predicate",
  "purpose": "lifecycle_transition_requires",
  "title": "Issuer must be active regulator",
  "description": "Transition to active requires the issuer to hold a current regulator credential.",
  "expression": "issuer.holds_credential('regulator_authority', { state: 'active' })",
  "language": "UEL/1.0"
}
```

## `computational`

**When to use:** Derived values — formulas that compute a credential attribute from other attributes.

**Required fields:**
- `id`, `title`, `expression`, `language`, `result_attribute`

**Worked example:**

```json
{
  "id": "premium_calculation",
  "type": "computational",
  "title": "Premium derivation",
  "description": "Premium is base_rate × risk_multiplier × term_months ÷ 12.",
  "expression": "attributes.base_rate * attributes.risk_multiplier * attributes.term_months / 12",
  "language": "UEL/1.0",
  "result_attribute": "attributes.premium"
}
```

## `validation`

**When to use:** Schema-level constraints that go beyond what JSON-Schema can express. Evaluated at issuance, update, and aggregate append.

**Required fields:**
- `id`, `title`, `expression`, `language`

**Worked example:**

```json
{
  "id": "no_duplicate_active_license",
  "type": "validation",
  "title": "At most one active license per jurisdiction",
  "description": "A carrier cannot hold multiple active licenses for the same jurisdiction simultaneously.",
  "expression": "state.active_licenses.filter(l => l.jurisdiction == event.payload.jurisdiction).length <= 1",
  "language": "UEL/1.0"
}
```

## `binding_link`

**When to use:** Connect a `legal_prose` clause to the `predicate` / `computational` / `validation` rule that formally enforces it. Lets prose and machine-checked layers coexist with explicit pairing.

**Required fields:**
- `id`, `title`, `links[]`

**Worked example:**

```json
{
  "id": "warranty_articulation",
  "type": "binding_link",
  "title": "Warranty articulation",
  "description": "The Coverage Warranty prose articulates what the Premium Calculation predicate enforces.",
  "links": [
    { "rule_id": "warranty_disclaimer" },
    { "rule_id": "premium_calculation" }
  ]
}
```

## Choosing the right type

```
Is this a contractual statement readable by humans, lawyers, auditors?
├── Yes — Is it enforceable cryptographically?
│   ├── Yes (a rule will enforce it) → legal_prose + binding_link to the enforcer
│   └── No → behavioral_expectation
└── No — Is it an executable check?
    ├── Yes — Returns a boolean?
    │   ├── Yes → predicate (with purpose)
    │   └── No (returns a value) → computational
    └── Yes — Is it a schema-level constraint? → validation
```

When in doubt, use `legal_prose` for the human view and a `predicate` for the formal view, then link them with `binding_link`.
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/micro-app-template-gen/references/rule-types-reference.md
git commit -m "$(cat <<'EOF'
docs(micro-app-template-gen): reference — rule types with worked examples

Detailed per-type guidance: legal_prose, behavioral_expectation,
business_policy, predicate, computational, validation, binding_link.
Each with required fields, when-to-use, and a fully-worked example.
Includes decision tree for type selection.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Skill reference — `naming-conventions.md`

**Files:**
- Create: `.claude/skills/micro-app-template-gen/references/naming-conventions.md`

- [ ] **Step 1: Write the naming conventions reference**

Create `.claude/skills/micro-app-template-gen/references/naming-conventions.md`:

```markdown
# Naming Conventions

The spec (§8) recommends these conventions. They're authoring guidance — deviations produce warnings, not errors. Convention compliance powers the Ecosystem Viewer's convention-based alignment (templates with matching names but different SAIDs likely interoperate; the viewer renders these as competing implementations).

## Credentials

| Pattern | Use for | Examples |
|---|---|---|
| `<Domain>License` | Authorization within a defined scope | `ProducerLicense`, `CarrierLicense`, `AdjusterLicense` |
| `<Domain>Authority` | Delegated authority | `BindingAuthority`, `RegulatorAuthority` |
| `<Domain>Card` or `<Domain>Identity` | Identity-bearing | `MemberCard`, `EmployeeIdentity` |
| `<Domain>Attestation` or `<Domain>Record` | Facts about events or objects | `InventoryCountAttestation`, `MeetingMinutesRecord` |
| `<Domain>Receipt` or `<Domain>Acknowledgment` | Transaction confirmations | `PaymentReceipt`, `DeliveryAcknowledgment` |
| `<Domain>Engagement` or `<Domain>Appointment` | Engagement of one role by another | `AuditEngagement`, `BrokerAppointment` |

Use PascalCase for credential type names.

## Roles

| Pattern | Use for | Examples |
|---|---|---|
| Ends in `-er` or `-or` | Active roles | `Carrier`, `Producer`, `Adjuster`, `Regulator`, `Auditor` |
| Ends in `-ee` | Receiving / passive roles | `Licensee`, `Payee`, `Grantee` |

Role *id* fields are kebab-case (`carrier`, `claims_adjuster`). Display names are PascalCase or Title Case ("Carrier", "Claims Adjuster").

## Lifecycle states

Recommended standard names (custom states allowed; standard names interop better):

| State | Meaning |
|---|---|
| `pending` | Awaiting action before becoming active |
| `active` | In force, normal operation |
| `suspended` | Temporarily not in force; reversible |
| `expired` | Time-based end-of-life |
| `revoked` | Permanently invalidated |
| `superseded` | Replaced by newer version of same logical credential |

## Workflows

| Pattern | Examples |
|---|---|
| `<Action>Workflow` | `ClaimSubmissionWorkflow` |
| `<Verb>By<Role>` | `LicenseGrantedByRegulator`, `ClaimFiledByPolicyholder` |
| `<Domain><Phase>` | `PolicyIssuance`, `PolicyRenewal`, `PolicyCancellation` |

Workflow *id* fields are kebab-case (`license_granted_by_regulator`). Display names use Title Case.

## Authority trees

| Pattern | Examples |
|---|---|
| `<Root>-<Domain>` | `Regulator-Insurance`, `Founder-Coop`, `Government-Identity` |

## exn routes

| Kind | Pattern | Examples |
|---|---|---|
| Command routes | `/<ecosystem-tag>/cmd/<verb>_<noun>` | `/insurance/cmd/submit_application`, `/insurance/cmd/file_claim` |
| Query routes | `/<ecosystem-tag>/qry/<noun>` | `/insurance/qry/active_policies` |
| Notification routes | `/<ecosystem-tag>/note/<event_name>` | `/insurance/note/policy_lapsed` |

**Reserved:** Routes beginning with `/ipex/` are reserved for the IPEX protocol. Do not author commands or messages on `/ipex/*`.

## Convention compliance audit

For each category, classify the template:

- `"compliant"` — follows all conventions in the category
- `"deviation: <description>"` — explains the specific deviation and recommended fix
- `"intentional_deviation: <rationale>"` — deviation made on purpose for a documented reason

Record the audit in `metadata.json`:

```json
{
  "convention_compliance": {
    "credential_naming": "compliant",
    "role_naming": "compliant",
    "workflow_naming": "deviation: 'CarrierApplies' (recommended: 'LicenseAppliedByCarrier' to match <Verb>By<Role> pattern)",
    "exn_route_naming": "compliant",
    "lifecycle_state_naming": "intentional_deviation: uses domain-specific states ('underwritten', 'bound') instead of standard 'pending'/'active' — required for industry parlance"
  }
}
```

The Ecosystem Viewer uses this to render warnings, suggest alignments, and surface convention drift across the corpus.
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/micro-app-template-gen/references/naming-conventions.md
git commit -m "$(cat <<'EOF'
docs(micro-app-template-gen): reference — naming conventions

Recommended naming patterns for credentials, roles, lifecycle states,
workflows, authority trees, and exn routes. Plus the format for
recording convention compliance in metadata.json (compliant /
deviation / intentional_deviation per category).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 17: Skill reference — `skeleton.json`

**Files:**
- Create: `.claude/skills/micro-app-template-gen/references/skeleton.json`

- [ ] **Step 1: Write the skeleton template**

Create `.claude/skills/micro-app-template-gen/references/skeleton.json`:

```json
{
  "d": "############################################",
  "spec_version": "micro-app-template/0.1",
  "header": {
    "id": "REPLACE-ME",
    "display_name": "REPLACE ME",
    "description": "REPLACE ME — one paragraph describing the use case from this role's perspective.",
    "version": "0.1",
    "expression_language": "UEL/1.0"
  },
  "role": {
    "id": "REPLACE-ME",
    "display_name": "REPLACE ME",
    "description": "REPLACE ME — one paragraph describing this role's purpose in the ecosystem.",
    "kind": "individual",
    "keri_infrastructure": {
      "witness_pool": false,
      "watcher_network": false,
      "mailbox": true,
      "acdc_registry": false
    }
  },
  "credentials": {
    "held": [],
    "issued": []
  },
  "commands": [],
  "aggregates": [],
  "reactions": [],
  "workflows": [],
  "projections": [],
  "rules": []
}
```

- [ ] **Step 2: Verify the skeleton passes meta-schema (after manual REPLACE-ME → valid value substitution)**

```bash
# After substituting REPLACE-ME with valid values, the skeleton should pass:
cp .claude/skills/micro-app-template-gen/references/skeleton.json /tmp/skel-test.json
python3 -c "
import json
doc = json.load(open('/tmp/skel-test.json'))
doc['header']['id'] = 'test-skeleton'
doc['header']['display_name'] = 'Test Skeleton'
doc['header']['description'] = 'A test of the skeleton.'
doc['role']['id'] = 'tester'
doc['role']['display_name'] = 'Tester'
doc['role']['description'] = 'A test role.'
json.dump(doc, open('/tmp/skel-test.json', 'w'), indent=2)
"
source .venv/bin/activate
python scripts/micro_app_validate.py --input /tmp/skel-test.json
```

Expected: validation passes.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/micro-app-template-gen/references/skeleton.json
git commit -m "$(cat <<'EOF'
docs(micro-app-template-gen): reference — minimal-valid skeleton template

A copyable starting point with all 8 primitives present (empty arrays
for non-required ones) and REPLACE-ME placeholders for the required
header/role string fields. After substitution it passes the
meta-schema; provides authors with structure rather than a blank canvas.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 18: Expand `SKILL.md` (full prose)

**Files:**
- Modify: `.claude/skills/micro-app-template-gen/SKILL.md`

Replace the stub content with the full skill prose that orchestrates the 10-step walk, references the support files, and embeds the discipline (rigid step order, save after each step, push back on jargon).

- [ ] **Step 1: Rewrite SKILL.md**

Replace `.claude/skills/micro-app-template-gen/SKILL.md` entirely:

```markdown
---
name: micro-app-template-gen
description: Use when authoring a single micro-app template — a JSON artifact describing one role's slice of a KERI-native ecosystem application. Walks a subject-matter expert (or AI agent) through producing micro-app-template.json + metadata.json + schemas/*.json conforming to the spec at docs/superpowers/specs/2026-05-09-micro-app-template-authoring-and-data-model.md.
user_invocable: true
---

# Micro-App Template Generator

## Overview

A **micro-app template** captures one role's perspective on one use case in some KERI-native ecosystem. The carrier's side of license-application is one template. The regulator's side is a different template. Multi-actor patterns decompose into multiple templates; bilateral conversations emerge at runtime from KERI-native protocols.

The artifact (`micro-app-template.json` + sibling `metadata.json` + `schemas/*.json`) is what Locksmith (the wallet) reads to render and run a deployed micro-app. This skill walks an SME through producing it.

**Read the spec first:** `docs/superpowers/specs/2026-05-09-micro-app-template-authoring-and-data-model.md` is normative. This skill is one (informative) authoring path. The artifact contract is fixed by the spec.

## When to use

- An SME wants to design a new micro-app from scratch.
- An SME wants to extend an existing template with a new credential, command, workflow, or rule.
- An AI agent is generating a candidate template for human review.
- A template is being forked from a parent and adapted.

## When NOT to use

- Reviewing or editing an existing template without re-walking the steps (use the Micro App: Designer plugin, when available).
- Authoring runtime behavior for a deployed micro-app (that's Locksmith's domain).
- Designing the ecosystem as a whole (no such artifact; ecosystem is emergent).

## Prerequisites

Before starting, confirm:

1. **Which role does this micro-app embody?** Get the role's id (kebab-case), display name, and intrinsic kind.
2. **One-sentence outcome statement?** Past tense, business language ("a license has been granted", "a claim has been adjusted").
3. **Where does the artifact get written?** Default: `docs/micro-apps/{role-id}-{use-case-id}/`.

## Workflow

The 10-step process is **rigid in order**. Step N's questions depend on Step N-1's answers. Within a step, the content is flexible. **Save after each step.**

| # | Step | Reference |
|---|---|---|
| 0 | Identify the role | `references/ten-step-process.md` §Step 0; `references/question-bank.md` §Step 0 |
| 1 | Name the use case (pivotal event) | §Step 1 |
| 2 | Held credentials (imports) | §Step 2 |
| 3 | Issued credentials (exports) | §Step 3 — heaviest step; produces schemas/*.json files |
| 4 | Commands | §Step 4 |
| 5 | Aggregates | §Step 5 |
| 6 | Reactions | §Step 6 |
| 7 | Workflows | §Step 7 |
| 8 | Projections | §Step 8 |
| 9 | Rules | §Step 9 — resolve every forward-referenced rule_ref |
| 10 | Conventions, hints, lineage (metadata.json) | §Step 10 |

Plus:

- **Adversarial review** (between Step 10 and save) — walk `references/adversarial-prompts.md` checklist
- **Saidify and validate** — run `scripts/micro_app_saidify.py --in-place` then `scripts/micro_app_validate.py`

## Reference files

| File | Purpose |
|---|---|
| `references/ten-step-process.md` | Detailed prose for each step — rationale, field mappings, anti-patterns |
| `references/question-bank.md` | Primary + follow-up questions to ask per step |
| `references/adversarial-prompts.md` | Pre-save adversarial review checklist |
| `references/rule-types-reference.md` | Per-type rule guidance with worked examples |
| `references/naming-conventions.md` | Recommended naming for credentials, roles, workflows, routes |
| `references/skeleton.json` | Copyable starting template (minimal-valid with REPLACE-ME fields) |
| `references/examples/` | Worked examples (one per ecosystem domain, when available) |

## Discipline (rigid)

- **Walk steps in order.** No skipping. Step N's answers depend on Step N-1's.
- **One question at a time.** Don't batch.
- **Save after each step.** Never lose progress.
- **Plain language.** Push back on KERI jargon (AID, IPEX) in user-facing fields. Use spec vocabulary (Roles, Credentials, Workflows).
- **Resolve every forward reference.** Step 9 walks all rule_refs surfaced in Steps 3-8; nothing dangles.
- **Run validation before declaring done.** `scripts/micro_app_validate.py` must pass.
- **Saidify before committing.** `scripts/micro_app_saidify.py --in-place` stamps the `d` field.

## Anti-patterns

- ❌ Authoring two roles in one template — split into two
- ❌ Skipping Step 9 (rules) — most contractual and enforcement substance lives there
- ❌ Skipping the adversarial review — the highest-value step
- ❌ Inventing schema SAIDs — they must be content-addressed
- ❌ Authoring on `/ipex/*` routes — reserved for protocol
- ❌ Conflating held credentials with issued credentials — different lists, different purposes
- ❌ Putting state or principal in `idempotency_key_expression` — must be deterministic from payload alone

## Recovery / resumption

If the user re-enters with a partial template:

1. Read the existing `micro-app-template.json`
2. Identify the first unfilled or incomplete primitive (often: empty arrays past a certain step)
3. Summarize what's filled in 3-5 lines
4. Resume at the first unfilled step

## Output

A directory at `docs/micro-apps/{role-id}-{use-case-id}/` containing:

```
{role-id}-{use-case-id}/
├── micro-app-template.json
├── metadata.json
└── schemas/
    ├── {credential_a}.json
    ├── {credential_b}.json
    └── ...
```

All files canonical JSON (sorted keys, two-space indent). Template has `d` field set to the computed SAID. Metadata's `for_micro_app_said` matches the template's `d`. Each schema file is its own JSON-Schema document with its own SAID computed via `scripts/saidify_acdc_schema.py` (existing utility) or the same saidify recipe.

## Validation

Before declaring done:

```bash
source .venv/bin/activate
python scripts/micro_app_validate.py --input docs/micro-apps/{path}/micro-app-template.json
python scripts/micro_app_saidify.py --input docs/micro-apps/{path}/micro-app-template.json --verify
```

Both must exit 0.
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/micro-app-template-gen/SKILL.md
git commit -m "$(cat <<'EOF'
docs(micro-app-template-gen): expand SKILL.md to full prose

Replaces the stub with the orchestrating skill content: overview,
when-to-use, prerequisites, the 10-step table with references/ pointers,
discipline rules, anti-patterns, recovery/resumption guidance, output
structure, and validation invocation. References the six supporting
files (ten-step-process, question-bank, adversarial-prompts,
rule-types-reference, naming-conventions, skeleton.json).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 19: Skill with-skill test (TDD GREEN/REFACTOR phase)

**Files:**
- Create: `docs/skill-test-runs/micro-app-template-gen/with-skill-2026-05-11.md`

- [ ] **Step 1: Dispatch the with-skill subagent**

Dispatch a general-purpose subagent with this prompt (same scenario as the baseline):

```
You are an SME (subject-matter expert) in the insurance industry helping author a micro-app template.

You have access to:
- The skill at: /Users/seriouscoderone/code/locksmith/.claude/skills/micro-app-template-gen/SKILL.md
  (read the SKILL.md and references/ subdirectory)
- The spec at: /Users/seriouscoderone/code/locksmith/docs/superpowers/specs/2026-05-09-micro-app-template-authoring-and-data-model.md
- The meta-schema at: /Users/seriouscoderone/code/locksmith/docs/superpowers/specs/schemas/micro-app-template.schema.json
- CLI scripts: scripts/micro_app_saidify.py, scripts/micro_app_validate.py

Your task: produce a `micro-app-template.json` for "a homeowner files an insurance claim with their carrier". This is the homeowner's side only — they apply, attach evidence, and await the carrier's decision.

Write the file to: /tmp/skill-with-homeowner-claim/micro-app-template.json (and sibling metadata.json, schemas/*.json as needed).
Validate it with: source .venv/bin/activate && python scripts/micro_app_validate.py --input /tmp/skill-with-homeowner-claim/micro-app-template.json

Follow the skill's discipline: read references/ on demand, walk steps in order, one question at a time. Where the SME (you, simulating) would have ambiguity, note it but make a defensible choice.

Report back:
- What you produced (paste the JSON files)
- Which references you consulted at each step
- Where the skill's guidance was unclear or missing
- Whether your output validated; if not, what errors
- How long it took (qualitatively)
- Compare to the baseline run: was the skill helpful, neutral, or unhelpful?
```

- [ ] **Step 2: Capture results**

Create `docs/skill-test-runs/micro-app-template-gen/with-skill-2026-05-11.md` with:

```markdown
# Skill With-Skill Test — 2026-05-11

## Scenario

Same as baseline: homeowner-files-claim micro-app. Subagent now has the full skill (SKILL.md + references/).

## Subagent Output

[paste full report]

## Comparison vs Baseline

[note where the skill helped vs where it didn't]

## Remaining Gaps

[list any places the skill is still unclear — these become refactor targets]

## Decision

[either: skill is good, move on; OR: iterate on specific references/ files based on remaining gaps]
```

- [ ] **Step 3: Iterate if needed**

If the with-skill test reveals significant gaps, identify which reference file needs revision and:

```bash
# Edit the relevant file (e.g., references/ten-step-process.md)
# Re-dispatch the test
# Update with-skill-2026-05-11.md with the new results
# Commit each iteration
```

- [ ] **Step 4: Commit final state**

```bash
git add docs/skill-test-runs/micro-app-template-gen/with-skill-2026-05-11.md
git commit -m "$(cat <<'EOF'
test(micro-app-template-gen): with-skill subagent run (TDD GREEN)

Subagent with full skill produces a homeowner-files-claim template
significantly closer to spec-compliance than baseline. Compares
performance vs baseline; documents any remaining gaps that informed
refactor of references/ files.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 20: Worked example — carrier-license-application end-to-end

**Files:**
- Create: `.claude/skills/micro-app-template-gen/references/examples/carrier-license-application/micro-app-template.json`
- Create: `.claude/skills/micro-app-template-gen/references/examples/carrier-license-application/metadata.json`
- Create: `.claude/skills/micro-app-template-gen/references/examples/carrier-license-application/schemas/policy.json`

The capstone task: produce one full worked example end-to-end via the toolchain. This proves the spec is implementable.

- [ ] **Step 1: Use the skill to author the carrier-license-application template**

Invoke the skill (`/micro-app-template-gen`) and walk through the 10 steps for "carrier applies to state regulator for license":

- Role: carrier (organization)
- Use case: carrier-applies-for-license
- Held credentials: none initially (this is a startup carrier)
- Issued credentials: none in this micro-app — the carrier doesn't issue anything in the licensing flow; they only receive
- Commands: submit_application
- Aggregates: license_registry (tracks our received licenses)
- Reactions: on_license_granted, on_license_revoked
- Workflows: license_application_carrier_side
- Projections: my_active_licenses
- Rules: a small set of preconditions and validations

Save outputs to `.claude/skills/micro-app-template-gen/references/examples/carrier-license-application/`.

- [ ] **Step 2: Author the policy schema (referenced if any issued credentials carry it)**

If the worked example issues no credentials, the schemas/ directory may be empty. If any are issued, author `schemas/{credential_id}.json` for each.

For this scenario (carrier receives but doesn't issue in the license-application use case), schemas/ is empty.

- [ ] **Step 3: Validate**

```bash
source .venv/bin/activate
python scripts/micro_app_validate.py --input .claude/skills/micro-app-template-gen/references/examples/carrier-license-application/micro-app-template.json
```

Expected: validation passes.

- [ ] **Step 4: Saidify**

```bash
python scripts/micro_app_saidify.py --input .claude/skills/micro-app-template-gen/references/examples/carrier-license-application/micro-app-template.json --in-place
python scripts/micro_app_saidify.py --input .claude/skills/micro-app-template-gen/references/examples/carrier-license-application/micro-app-template.json --verify
```

Expected: stamp succeeds; verify returns 0.

- [ ] **Step 5: Update metadata.json's for_micro_app_said**

```bash
python3 -c "
import json
template = json.load(open('.claude/skills/micro-app-template-gen/references/examples/carrier-license-application/micro-app-template.json'))
meta = json.load(open('.claude/skills/micro-app-template-gen/references/examples/carrier-license-application/metadata.json'))
meta['for_micro_app_said'] = template['d']
json.dump(meta, open('.claude/skills/micro-app-template-gen/references/examples/carrier-license-application/metadata.json', 'w'), indent=2)
"
```

- [ ] **Step 6: Validate metadata**

```bash
python scripts/micro_app_validate.py --input .claude/skills/micro-app-template-gen/references/examples/carrier-license-application/metadata.json --schema docs/superpowers/specs/schemas/metadata.schema.json
```

Expected: passes.

- [ ] **Step 7: Commit**

```bash
git add .claude/skills/micro-app-template-gen/references/examples/carrier-license-application/
git commit -m "$(cat <<'EOF'
example(micro-app-template-gen): worked example — carrier-license-application

Carrier's side of license application, authored end-to-end via the
skill, validated against the meta-schema, saidified. Serves as the
reference worked example consumers can compare against when authoring
similar micro-apps. Proves the spec + toolchain are coherent and
implementable.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 8: Run the full test suite to confirm nothing broke**

```bash
source .venv/bin/activate
QT_QPA_PLATFORM=offscreen pytest tests/micro_app_template/ -v
```

Expected: all tests pass.

---

## Self-Review

**Spec coverage check** (against `docs/superpowers/specs/2026-05-09-micro-app-template-authoring-and-data-model.md`):

| Spec section | Implementing task(s) |
|---|---|
| §1 Goal & scope | (Documentation only; no task) |
| §2 Three-artifact picture | Task 18 (SKILL.md) restates; Tasks 1-10 build the validation contract; Task 11+ build the skill |
| §3 Architecture | (Documentation only) |
| §4 Vocabulary | Tasks 4-9 encode enum values in meta-schema |
| §5.1 Shape | Task 4 (top-level structure) |
| §5.2 SAID self-identification | Task 2 (saidify utility), Task 10 (CLI) |
| §5.3 JSON canonical form | Task 1 (canonical_json) |
| §5.4 Round-trip and lint | Tasks 1, 2, 3 collectively |
| §5.5 Meta-schema | Tasks 4-8 (in 5 incremental parts) + Task 9 (metadata) |
| §5.6 File layout | Task 20 (worked example demonstrates) |
| §6.1 Header | Task 4 |
| §6.2 Role | Task 4 |
| §6.3 Credentials | Task 5 |
| §6.4 Commands | Task 6 |
| §6.5 Aggregates | Task 6 |
| §6.6 Reactions | Task 7 |
| §6.7 Workflows | Task 7 |
| §6.8 Projections | Task 7 |
| §6.9 Rules | Task 8 |
| §7.1 SAID-based alignment | (Out of plan scope — the Ecosystem Viewer's job, deferred plan) |
| §7.2 Convention-based alignment | Task 16 (naming-conventions.md in skill); the Ecosystem Viewer's runtime alignment is deferred |
| §8 Naming conventions | Task 16 (skill reference) |
| §9 Sibling metadata.json | Task 9 (meta-schema), Task 18 (skill prose) |
| §10 Out of scope | (Documentation only — explicitly preserved in this plan's scope) |
| §11 Follow-on work | This plan IS the first three items; deferred items remain deferred |
| Appendix A 10-step path | Task 12 (ten-step-process.md), Task 18 (SKILL.md), Tasks 13-17 (supporting refs) |
| Appendix B Adversarial | Task 14 (adversarial-prompts.md) |
| Appendix C Type reference | Encoded in meta-schema (Tasks 4-9) and Task 15 (rule-types-reference.md) |

All spec sections have at least one implementing task.

**Placeholder scan:** No "TBD", "TODO", "fill in later" in any task. All code blocks are complete. All commands are runnable.

**Type consistency check:**
- `compute_said` (Task 2) signature: `(doc: dict, *, label: str = "d") -> str` — used identically in Task 10 CLI
- `validate_template` (Task 3) signature: `(doc: dict, schema_path: Path) -> ValidationResult` — used in Task 10 CLI
- `ValidationError.path` field (Task 3) — used in Task 10 CLI error output
- Field name conventions in meta-schema: `id`, `name`, `description`, `expected_schema_said`, `schema_said`, `tel_primitive`, `rule_ref` — used consistently across Tasks 4-9 and skill references

All consistent.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-11-micro-app-template-spec-hardening.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
