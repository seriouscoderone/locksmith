# UEL/1.0 Cheat-Sheet

UEL is the executable expression language for predicate, computational, and
validation rules, plus `fold_expression`, `payload_mapping`, `idempotency_key_expression`,
`lens_template`, and `row_filter` predicates.

**Two-phase model.** Every UEL expression is parsed, type-checked against a
*bound context* (which variables and types are in scope), and then evaluated.
A `state.foo` reference fails to compile if `foo` isn't in the aggregate's
state schema. The bindings below are what the loader provides — references to
anything else are unbound-name errors.

## 1. Bound contexts by position

The compiler matches each expression's position in the template to one of these
bound contexts. Use only the variables listed; nothing else is in scope.

| Where it appears | Bindings |
|---|---|
| `command.auth_preconditions[].rule.expression` (a `predicate` rule) | `{ principal, command }` |
| `command.state_preconditions[].rule.expression` | `{ state, command, principal }` |
| `command.temporal_preconditions[].rule.expression` | `{ command, now() }` |
| `command.idempotency_key_expression` | `{ payload }` only — **no state, no principal** |
| `command.emissions[].payload_mapping` (kind `aggregate_event`) | `{ state, command, principal, payload }` |
| `reaction.emissions[].payload_mapping` (`credential_received`) | `{ event, state }` — `event.credential.*` available |
| `reaction.emissions[].payload_mapping` (`exn_received`) | `{ event, state }` — `event.payload.*` available |
| `reaction.emissions[].payload_mapping` (`lifecycle_event`) | `{ event, state }` — `event.from_state`, `event.to_state` |
| `aggregate.events[].fold_expression` | `{ state, event }` (state BEFORE event applied) |
| `aggregate.invariants[].rule.expression` | `{ state, event }` (rule purpose `aggregate_invariant`) |
| `projection.fold_expression` | `{ state, event, source }` (source = event_type string) |
| `projection.access.row_filter_rule_ref` (rule with purpose `projection_row_filter`) | `{ row, principal }` |
| `projection.access.lens_template` | `{ principal, state }` (template form — see §5) |
| `workflow.steps[].branches[].condition` (purpose `workflow_branch_condition`) | `{ state, command, workflow, principal }` |
| `credential.lifecycle.transitions[].requires` (purpose `lifecycle_transition_requires`) | `{ credential, issuer, holder, workflow }` |
| `credential.lifecycle.transitions[].auto_when` (purpose `lifecycle_transition_condition`) | `{ credential, now() }` |
| `rule.expression` with purpose `derived_membership` | `{ principal, ecosystem }` |
| `rule.expression` with type `computational` | `{ attributes }` — produces value for `result_attribute` |
| `rule.expression` with type `validation` | `{ event, state }` — evaluated at issuance/update/aggregate append |

**Shapes:**

- `principal` — `{ aid: aid, credentials: list<{ type, holder, issuer, said, revoked }> }`
- `command` — fields of the command's `payload_schema`
- `payload` — alias for `command` payload (use whichever the position binds)
- `state` — fields of the aggregate's `state_schema`
- `event` — `{ payload, actorAID: aid, timestamp: datetime, aggregateId: string, priorEvent: said? }`
- `event.credential` (reactions on `credential_received` only) — `{ said, type, issuer, holder, attributes, validity, revoked }`
- `row` — fields of the projection's `output_schema` row
- `attributes` — fields of the credential's `attributes` block

## 2. Operators and methods

JavaScript-like syntax.

**Comparison:** `==`, `!=`, `<`, `<=`, `>`, `>=` (numbers, strings, datetimes; `==`/`!=` work on any pair)

**Logical:** `&&`, `||`, `!`

**Arithmetic:** `+`, `-`, `*`, `/`, `%` (numbers); `+` also for strings (concat) and lists (concat); `datetime + duration → datetime`; `datetime - datetime → duration`

**Nullish coalescing:** `optional ?? fallback`

**Conditional:** `cond ? then : else` (both branches must unify)

**Array methods** (only on `list<T>`):

| Method | Returns | Notes |
|---|---|---|
| `.filter(x => bool)` | `list<T>` | Keep matching |
| `.find(x => bool)` | `T?` | First match, optional |
| `.exists(x => bool)` | `bool` | Any match |
| `.every(x => bool)` | `bool` | All match |
| `.count` / `.count(x => bool)` | `number` | Cardinality |
| `.map(x => U)` | `list<U>` | Transform |
| `.groupBy(x => K)` | `list<{ key, items }>` | Bucket |
| `.distinct` | `list<T>` | Unique (property, no parens) |
| `.first` / `.last` | `T?` | (no parens) |
| `.length` | `number` | (property, no parens) |

**Strings:** `.length` (property)

**Record:** `obj.field`, `obj.nested.field`; build with `{ a: x, b: y }`; spread with `{ ...base, b: y }`

**Lists:** `[a, b, c]`; concat with `xs + ys`

## 3. Idiomatic patterns

**Does the principal currently hold a credential of type X?**

```
principal.credentials.exists(c => c.type == "CarrierLicense" && !c.revoked)
```

The Locksmith template-loader also exposes the shorthand:

```
principal.holds_credential("CarrierLicense", { state: "active" })
```

Use the shorthand when the spec or example shows it; use `.exists(...)` when you
need to inspect non-state fields (specific issuer, specific holder, etc.).

**Is the credential's holder me?**

```
event.credential.holder == principal.aid
```

**Compute a derived attribute** (`computational` rule, returns the value assigned
to `result_attribute`):

```
attributes.base_rate * attributes.risk_multiplier * attributes.term_months / 12
```

**No duplicate active credential per jurisdiction** (`validation` rule):

```
state.active_licenses.filter(l => l.jurisdiction == event.payload.jurisdiction).length == 0
```

**Aggregate invariant: at most one active license per jurisdiction:**

```
state.active_licenses.every(l =>
  state.active_licenses.filter(o => o.jurisdiction == l.jurisdiction).length == 1
)
```

**Append on one event, remove on another** (projection `fold_expression`):

```
source == "license_granted"
  ? state + [{
      license_said: event.payload.said,
      jurisdiction: event.payload.jurisdiction,
      granted_at:   event.payload.granted_at
    }]
  : source == "license_revoked"
    ? state.filter(l => l.license_said != event.payload.license_said)
    : state
```

**Idempotency key — payload only, deterministic:**

```
hash(payload.jurisdiction + ":" + payload.lines_of_business.sort().join(","))
```

**Self-or-licensed row filter** (projection `row_filter`, purpose
`projection_row_filter`):

```
row.holder_aid == principal.aid
|| principal.holds_credential("carrier_license", { state: "active" })
```

**Workflow branch on aggregate state** (purpose `workflow_branch_condition`):

```
state.applications.exists(a => a.id == workflow.context.application_id && a.status == "submitted")
```

## 4. Reserved functions

| Function | Signature | Notes |
|---|---|---|
| `now()` | `=> datetime` | Available in `temporal_precondition` and `lifecycle_transition_condition`. Do **not** use elsewhere — folds and idempotency keys must be deterministic. |
| `hash(...)` | `(...any) => said` | Variadic content hash. Use in `idempotency_key_expression` and in derived SAIDs inside `payload_mapping`. |
| `length(x)` | `(list \| string) => number` | Equivalent to `.length` property. |
| `min(a, b)` / `max(a, b)` | `(T, T) => T` | Same-type pair. |
| `notNull(x)` | `(T?) => bool` | Optional-presence check. |
| `unwrap(x)` | `(T?) => T` | Asserts non-null; type-checks but throws at runtime if null. |
| `isAID(x)` / `isSAID(x)` | `(string-like) => bool` | Format checks. |

## 5. Format pipes (templates, not predicates)

Used inside string templates: `summaryTemplate`, `lens_template`,
`display.columns[].display_template`, `row_summary_template`. The template
itself is a string with `{ expr|pipe }` interpolations.

| Pipe | Input type | Output | Notes |
|---|---|---|---|
| `\|date` | datetime | string | `YYYY-MM-DD` |
| `\|datetime` | datetime | string | full timestamp |
| `\|duration` | duration | string | human-readable |
| `\|durationFrom:<expr>` | datetime | string | duration from the argument |
| `\|aid8` / `\|aid12` | aid \| string | string | truncated AID |
| `\|said8` | said \| string | string | truncated SAID |
| `\|schemaName` | said \| string | string | resolves SAID to display name |
| `\|enum` | string | string | enum display value |
| `\|number:<digits>` | number | string | fixed-precision number |

Pipes are for templates. Inside predicate / fold / computational expressions,
write the conversion directly (e.g. `c.said` not `c.said|said8`).

## 6. Gotchas (real bugs)

- **`idempotency_key_expression` MUST be payload-only.** Referencing `state` or
  `principal` makes it non-deterministic across replays. The loader rejects this
  by giving the position a bindings-of-`{ payload }` only.

- **No `.contains()`.** Arrays don't have a `.contains` method. Use
  `xs.exists(x => x == y)` for membership.

- **`principal.credentials` element does not expose `.attributes`.** To gate on
  a credential's attribute (a specific role attribute, a specific endorsed line
  of business), use a `pattern_*` credential-pattern rule under
  `auth_preconditions` (Stage-14 work), **not** a UEL predicate. UEL only sees
  `{ type, holder, issuer, said, revoked }` on each credential in
  `principal.credentials`.

- **Arithmetic on `event.payload.<n>` in projection folds is rejected.**
  `event.payload` is typed `any` in projection folds (different sources have
  different payloads), and `number + any` is a type error. If you need a running
  total, compute it in the source aggregate's state (typed) and project it.

- **Lists must be element-type-uniform.** `[1, "x"]` is rejected; record-literal
  list `[{ a: 1 }, { a: 2 }]` is fine.

- **Ternary branches must unify.** `cond ? state + [x] : null` is rejected
  because `list<T>` and `null` don't unify; use `cond ? state + [x] : state`.

- **Reaction `payload_mapping` binds differently per trigger.** For
  `credential_received`, use `event.credential.*`. For `exn_received` and
  `lifecycle_event`, use `event.payload.*` (the inbound exn body / lifecycle
  event payload). Verify by checking which fields the meta-schema says are
  populated.

- **Don't reference `now()` in folds, payload mappings, or idempotency keys.**
  These must be deterministic; runtime time is supplied via `event.timestamp`
  (set when the event is appended), which **is** deterministic on replay.

- **Pipes (`|aid8`) only work in templates.** They are a separate AST node
  (`PipeExpr`) and the parser only emits them in template mode. Inside a
  predicate or fold, write a normal expression (no pipe).

## 7. Quick reference: which position uses which return type

The compiler also enforces the expected return type:

| Position | Expected return |
|---|---|
| `predicate` (any purpose) | `bool` |
| `aggregate_invariant` | `bool` |
| `lifecycle_transition_requires` / `_condition` | `bool` |
| `validation` | `bool` |
| `projection_row_filter` | `bool` |
| `fold_expression` (event) | same as aggregate `state_schema` |
| `fold_expression` (projection) | `list<row>` |
| `payload_mapping` | same as the target event's `payload_schema` |
| `idempotency_key_expression` | any (typically `said` via `hash`) |
| `computational` | type of `result_attribute` |
| `lens_template`, `display_template`, `summary_template` | `string` |

If the return-shape doesn't match, the loader emits a `wrong-return-shape`
diagnostic — usually a sign that the expression returns the wrong type or
omits a required field.
