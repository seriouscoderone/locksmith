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
