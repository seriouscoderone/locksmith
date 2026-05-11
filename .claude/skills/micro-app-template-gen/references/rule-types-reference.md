# Rule Types Reference

Detailed guidance for each rule type, with worked examples.

For UEL/1.0 expression syntax — bound contexts per `purpose`, available
operators, idiomatic patterns, format pipes, and gotchas — see
`uel-1.0-cheat-sheet.md`.

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

Each purpose has a different bound context (which variables are in scope).
See `uel-1.0-cheat-sheet.md` §1 for the table.

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
