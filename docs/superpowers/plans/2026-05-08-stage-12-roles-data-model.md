# Stage 12: Roles Data Model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a credential-qualified `RoleRecord` primitive to `EcosystemBaser` plus the `EcosystemRecord` field additions that let an ecosystem express "any AID holding a valid credential of schema S issued by role R is a permitted issuer of schema T" — replacing pure AID-enumeration with composable role-based qualification. Pure data-layer work; **no UI in this stage** (UI lands in Stage 13).

**Architecture:** New `RoleRecord` dataclass keyed `(ecosystem_name, role_name)` in a new `rle.` Komer subkey. Four new optional fields on `EcosystemRecord` (`issuer_qualification_rules`, `role_names`, `schema_version`, `governance_url`) — all with defaults so existing on-disk records read without migration. Resolver helper takes a `find_credentials_of_schema` callable so tests can mock without instantiating a full keripy `Regery`. The combined `is_permitted_issuer(eco, schema, aid, vault)` checks both explicit `permitted_issuers` AND role-qualification chains.

**Tech Stack:** Python 3.13, `keri.db.koming.Komer` for the per-record store, `pytest` with the existing temp-LMDB fixture pattern. No Qt in this stage. No new dependencies.

**Design source:** `docs/superpowers/designs/2026-05-08-ecosystem-governance-roadmap.md` §2 — read for the conceptual rationale; this plan is the executable shape.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/locksmith/plugins/ecosystem_viewer/db.py` | Modify | New `RoleRecord` dataclass; new `rle.` Komer; four new `EcosystemRecord` fields; CRUD methods (`put_role`, `get_role`, `list_roles`, `delete_role`); resolver helpers (`resolve_role_members`, `is_permitted_issuer`); cascading cleanup in `delete_ecosystem` |
| `tests/test_ecosystem_baser.py` | Modify | Append three new test sections — EcosystemRecord field additions, role CRUD, resolver helpers |

No UI files touched. No new tests files. Existing tests stay green.

---

## Task 1: EcosystemRecord field additions

Goal: add four optional fields to `EcosystemRecord`. All have defaults so existing on-disk records continue to deserialize. No methods change yet.

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/db.py` — `EcosystemRecord` dataclass
- Test: `tests/test_ecosystem_baser.py` — append after the existing role/permitted-issuer tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ecosystem_baser.py`:

```python
# ---------------------------------------------------------------------------
# Stage 12: EcosystemRecord field additions
# ---------------------------------------------------------------------------


def test_new_ecosystem_record_has_default_role_fields(baser):
    """A freshly-created EcosystemRecord initializes the four new fields
    with safe defaults — empty dict / list / 1 / empty string."""
    rec = EcosystemRecord(name="eco")
    assert rec.issuer_qualification_rules == {}
    assert rec.role_names == []
    assert rec.schema_version == 1
    assert rec.governance_url == ""


def test_ecosystem_record_round_trips_new_fields(baser):
    """Setting the new fields persists across put/get."""
    rec = EcosystemRecord(
        name="eco",
        schema_saids=["ES1"],
        issuer_qualification_rules={"ES1": "state-doi"},
        role_names=["state-doi"],
        schema_version=1,
        governance_url="https://example.com/charter",
    )
    baser.put_ecosystem(rec)
    fresh = baser.get_ecosystem("eco")
    assert fresh.issuer_qualification_rules == {"ES1": "state-doi"}
    assert fresh.role_names == ["state-doi"]
    assert fresh.schema_version == 1
    assert fresh.governance_url == "https://example.com/charter"


def test_legacy_record_constructor_without_new_fields_still_works(baser):
    """An EcosystemRecord built without the new fields (the way every
    pre-Stage-12 caller does it) round-trips cleanly with defaulted
    new fields. Validates the non-breaking-change discipline."""
    rec = EcosystemRecord(name="legacy", schema_saids=["ES1"], issuer_aids=["EA1"])
    baser.put_ecosystem(rec)
    fresh = baser.get_ecosystem("legacy")
    assert fresh.issuer_qualification_rules == {}
    assert fresh.role_names == []
    assert fresh.schema_version == 1
    assert fresh.governance_url == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/python -m pytest tests/test_ecosystem_baser.py::test_new_ecosystem_record_has_default_role_fields tests/test_ecosystem_baser.py::test_ecosystem_record_round_trips_new_fields tests/test_ecosystem_baser.py::test_legacy_record_constructor_without_new_fields_still_works -v
```

Expected: all three FAIL with `AttributeError: 'EcosystemRecord' object has no attribute 'issuer_qualification_rules'` (or similar).

- [ ] **Step 3: Add the four new fields to `EcosystemRecord`**

In `src/locksmith/plugins/ecosystem_viewer/db.py`, locate `class EcosystemRecord`. The existing fields end with `permitted_issuers: dict = field(default_factory=dict)`. Append the four new fields immediately after `permitted_issuers`:

```python
    permitted_issuers: dict = field(default_factory=dict)
    """schema_said -> list[AID]. See class docstring."""

    # --- Stage 12 (role-based qualification) — all optional with defaults
    # so on-disk records pre-dating this stage read cleanly. See
    # docs/superpowers/designs/2026-05-08-ecosystem-governance-roadmap.md §2.

    issuer_qualification_rules: dict = field(default_factory=dict)
    """schema_said -> role_name. When set, ANY AID that is a member of
    role_name is a permitted issuer of that schema — in addition to (or
    instead of) AIDs enumerated in `permitted_issuers[schema_said]`.
    Convention overlay: spec defines no such rule; this is the wallet-
    level expression of an EGF membership policy."""

    role_names: list[str] = field(default_factory=list)
    """Names of roles defined in this ecosystem. The actual RoleRecords
    live in the rle. Komer subkey; this list is a convenience cache for
    iteration without scanning the role-Komer."""

    schema_version: int = 1
    """Wallet-internal version tag for forward-compatibility. Bumped
    when the record's schema changes in a way that needs migration
    detection. Pre-Stage-12 records read as version 1 by default."""

    governance_url: str = ""
    """Optional URL or OOBI to the ecosystem's human-readable charter
    / governance framework document. The wallet does not model framework
    artifacts (Risk Register, Liability, Audit, etc — see roadmap §1.5);
    this link surfaces the framework's existence to the user."""
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv/bin/python -m pytest tests/test_ecosystem_baser.py -v
```

Expected: all tests pass — the 22 pre-existing + the 3 new ones = 25 total.

- [ ] **Step 5: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
git add src/locksmith/plugins/ecosystem_viewer/db.py tests/test_ecosystem_baser.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): EcosystemRecord role-related field additions (Stage 12)

Four new optional fields on EcosystemRecord, all with defaults so
existing on-disk records read without migration:

- issuer_qualification_rules: dict[schema_said, role_name] — when
  set, role-membership is a permitted-issuer condition (in addition
  to the explicit permitted_issuers list).
- role_names: list[str] — convenience iteration of role names defined
  in this ecosystem (RoleRecord-s themselves live in a separate rle.
  Komer added in a follow-up task).
- schema_version: int = 1 — forward-compat version tag.
- governance_url: str — optional link to the ecosystem's framework
  document; the wallet does not model framework artifacts.

Per design 2026-05-08-ecosystem-governance-roadmap §2.2 and §6.4.
3 new tests verifying defaults + round-trip + legacy-record behavior.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: RoleRecord dataclass + Komer + CRUD

Goal: add the `RoleRecord` dataclass, wire it into a new `rle.` Komer subkey, and provide CRUD methods on `EcosystemBaser` (`put_role`, `get_role`, `list_roles`, `delete_role`). Includes validation (qualification schema must be a member of the ecosystem; `issuer_role_name` must be empty or a known role) and cascading cleanup (deleting a role removes any `issuer_qualification_rules` entries pointing at it; deleting an ecosystem removes its roles).

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/db.py`
- Test: `tests/test_ecosystem_baser.py` — append after Task 1's tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ecosystem_baser.py`:

```python
# ---------------------------------------------------------------------------
# Stage 12: RoleRecord CRUD
# ---------------------------------------------------------------------------


def _seed_eco_with_schema_and_aid(baser, name="eco", schema="ES1", aid="EA1"):
    baser.put_ecosystem(EcosystemRecord(
        name=name, schema_saids=[schema], issuer_aids=[aid],
    ))


def test_put_and_get_root_role(baser):
    """A root role enumerates its trust-root AIDs and has no issuer_role."""
    _seed_eco_with_schema_and_aid(baser)
    role = RoleRecord(
        ecosystem_name="eco",
        name="state-doi",
        description="State Department of Insurance issuers",
        qualification_schema_said="ES1",
        issuer_role_name="",
        root_issuer_aids=["EA1"],
    )
    baser.put_role(role)
    fetched = baser.get_role("eco", "state-doi")
    assert fetched is not None
    assert fetched.name == "state-doi"
    assert fetched.qualification_schema_said == "ES1"
    assert fetched.root_issuer_aids == ["EA1"]
    assert fetched.issuer_role_name == ""


def test_put_role_appends_to_ecosystem_role_names(baser):
    """Putting a role updates the parent ecosystem's role_names cache."""
    _seed_eco_with_schema_and_aid(baser)
    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="state-doi",
        qualification_schema_said="ES1",
    ))
    eco = baser.get_ecosystem("eco")
    assert "state-doi" in eco.role_names


def test_put_role_rejects_unknown_ecosystem(baser):
    with pytest.raises(KeyError):
        baser.put_role(RoleRecord(
            ecosystem_name="nope", name="whatever",
            qualification_schema_said="ES1",
        ))


def test_put_role_rejects_qualification_schema_not_in_ecosystem(baser):
    _seed_eco_with_schema_and_aid(baser)
    with pytest.raises(ValueError, match="qualification_schema"):
        baser.put_role(RoleRecord(
            ecosystem_name="eco", name="rogue",
            qualification_schema_said="ES_NOT_HERE",
        ))


def test_put_role_rejects_unknown_issuer_role(baser):
    _seed_eco_with_schema_and_aid(baser)
    with pytest.raises(ValueError, match="issuer_role"):
        baser.put_role(RoleRecord(
            ecosystem_name="eco", name="downstream",
            qualification_schema_said="ES1",
            issuer_role_name="missing-parent",
        ))


def test_chained_role_references_known_parent(baser):
    """A non-root role references an existing role; both round-trip."""
    _seed_eco_with_schema_and_aid(baser)
    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="state-doi",
        qualification_schema_said="ES1",
        root_issuer_aids=["EA1"],
    ))
    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="qualified-producer",
        qualification_schema_said="ES1",
        issuer_role_name="state-doi",
    ))
    roles = baser.list_roles("eco")
    by_name = {r.name: r for r in roles}
    assert set(by_name) == {"state-doi", "qualified-producer"}
    assert by_name["qualified-producer"].issuer_role_name == "state-doi"


def test_delete_role_removes_record_and_cascades_qualification_rules(baser):
    """Deleting a role removes the RoleRecord, drops its name from
    role_names, and removes any issuer_qualification_rules pointing
    at it. Other rules are untouched."""
    _seed_eco_with_schema_and_aid(baser, schema="ES1", aid="EA1")
    # Add a second schema to the ecosystem so we can test selective cleanup.
    rec = baser.get_ecosystem("eco")
    rec.schema_saids = ["ES1", "ES2"]
    baser.put_ecosystem(rec)

    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="state-doi",
        qualification_schema_said="ES1",
        root_issuer_aids=["EA1"],
    ))
    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="qualified-producer",
        qualification_schema_said="ES2",
    ))
    rec = baser.get_ecosystem("eco")
    rec.issuer_qualification_rules = {
        "ES1": "state-doi",
        "ES2": "qualified-producer",
    }
    baser.put_ecosystem(rec)

    baser.delete_role("eco", "state-doi")

    assert baser.get_role("eco", "state-doi") is None
    fresh = baser.get_ecosystem("eco")
    assert "state-doi" not in fresh.role_names
    assert "qualified-producer" in fresh.role_names
    assert fresh.issuer_qualification_rules == {"ES2": "qualified-producer"}


def test_delete_ecosystem_cascades_role_cleanup(baser):
    """Deleting an ecosystem also removes all its roles."""
    _seed_eco_with_schema_and_aid(baser)
    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="state-doi",
        qualification_schema_said="ES1",
    ))
    baser.delete_ecosystem("eco")
    assert baser.get_role("eco", "state-doi") is None
    assert baser.list_roles("eco") == []


def test_delete_role_idempotent_on_unknown_role(baser):
    _seed_eco_with_schema_and_aid(baser)
    baser.delete_role("eco", "never-existed")  # no exception


def test_list_roles_empty_for_ecosystem_with_no_roles(baser):
    _seed_eco_with_schema_and_aid(baser)
    assert baser.list_roles("eco") == []


def test_put_role_updates_role_names_idempotently(baser):
    """Putting the same role twice doesn't duplicate it in role_names."""
    _seed_eco_with_schema_and_aid(baser)
    role = RoleRecord(
        ecosystem_name="eco", name="state-doi",
        qualification_schema_said="ES1",
    )
    baser.put_role(role)
    baser.put_role(role)
    eco = baser.get_ecosystem("eco")
    assert eco.role_names.count("state-doi") == 1
```

Also add `RoleRecord` to the existing import line at the top of `tests/test_ecosystem_baser.py`:

```python
from locksmith.plugins.ecosystem_viewer.db import (
    AnnotationKind,
    AnnotationRecord,
    DiscoveryEvent,
    EcosystemBaser,
    EcosystemRecord,
    RoleRecord,
)
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/python -m pytest tests/test_ecosystem_baser.py -k "role or test_delete_ecosystem_cascades_role" -v 2>&1 | head -40
```

Expected: most fail with `ImportError: cannot import name 'RoleRecord'` from db.

- [ ] **Step 3: Add `RoleRecord` dataclass to `db.py`**

In `src/locksmith/plugins/ecosystem_viewer/db.py`, find the existing `_MembershipRecord` dataclass (currently the last record class before the `EcosystemBaser` class begins). Insert the `RoleRecord` dataclass directly above `_MembershipRecord`:

```python
@dataclass
class RoleRecord:
    """A credential-qualified class of AID within an ecosystem.

    "Role" is a wallet-level convention overlay; the ACDC spec has no
    such primitive. The vLEI ecosystem implements equivalent structure
    via credential-chain-rooted hierarchies. See
    docs/superpowers/designs/2026-05-08-ecosystem-governance-roadmap.md
    for the conceptual model and §1.5 for the framework-vs-trust-registry
    scope discussion.

    Membership is determined dynamically by the resolver: an AID is *in*
    this role iff it holds a valid credential of `qualification_schema_said`
    issued by an AID that is itself in `issuer_role_name` (recursively,
    with `root_issuer_aids` as the base case).

    Composite key: (ecosystem_name, name).
    """
    ecosystem_name: str = ""
    name: str = ""
    description: str = ""
    qualification_schema_said: str = ""
    """SAID of the schema whose holders qualify for this role."""
    issuer_role_name: str = ""
    """Name of the role whose members are the authorized issuers of the
    qualification credential. Empty string means 'root role' — see
    root_issuer_aids."""
    root_issuer_aids: list[str] = field(default_factory=list)
    """When this is a root role (issuer_role_name=""), the enumerated
    AIDs that bootstrap the chain. Otherwise empty (or treated as
    empty)."""
    created_at: str = ""
    updated_at: str = ""
```

- [ ] **Step 4: Wire the `rle.` Komer in `EcosystemBaser.reopen`**

Find `EcosystemBaser.reopen`. The current body looks like:

```python
    def reopen(self, **kwa):
        super(EcosystemBaser, self).reopen(**kwa)

        self.ecosystems = koming.Komer(db=self, subkey='eco.', schema=EcosystemRecord)
        self.annotations = koming.Komer(db=self, subkey='ann.', schema=AnnotationRecord)
        self.history = koming.Komer(db=self, subkey='his.', schema=DiscoveryEvent)
        self.schema_membership = koming.Komer(db=self, subkey='smbr.', schema=_MembershipRecord)
        self.aid_membership = koming.Komer(db=self, subkey='ambr.', schema=_MembershipRecord)

        return self.env
```

Add a `roles` Komer line and add the `roles = None` line to `__init__`:

In `EcosystemBaser.__init__`, find:

```python
    def __init__(self, name: str = "ecosystem", headDirPath: str | None = None, reopen: bool = True, **kwa):
        self.ecosystems = None
        self.annotations = None
        self.history = None
        self.schema_membership = None
        self.aid_membership = None
        super(EcosystemBaser, self).__init__(name=name, headDirPath=headDirPath, reopen=reopen, **kwa)
```

Add `self.roles = None` after `self.aid_membership = None`:

```python
    def __init__(self, name: str = "ecosystem", headDirPath: str | None = None, reopen: bool = True, **kwa):
        self.ecosystems = None
        self.annotations = None
        self.history = None
        self.schema_membership = None
        self.aid_membership = None
        self.roles = None
        super(EcosystemBaser, self).__init__(name=name, headDirPath=headDirPath, reopen=reopen, **kwa)
```

In `reopen`, add a corresponding Komer line:

```python
    def reopen(self, **kwa):
        super(EcosystemBaser, self).reopen(**kwa)

        self.ecosystems = koming.Komer(db=self, subkey='eco.', schema=EcosystemRecord)
        self.annotations = koming.Komer(db=self, subkey='ann.', schema=AnnotationRecord)
        self.history = koming.Komer(db=self, subkey='his.', schema=DiscoveryEvent)
        self.schema_membership = koming.Komer(db=self, subkey='smbr.', schema=_MembershipRecord)
        self.aid_membership = koming.Komer(db=self, subkey='ambr.', schema=_MembershipRecord)
        self.roles = koming.Komer(db=self, subkey='rle.', schema=RoleRecord)

        return self.env
```

- [ ] **Step 5: Add the role CRUD methods**

In `EcosystemBaser`, after the existing `# --- Authoritative issuers ---` (now `# --- Permitted issuers ---`) section and before the `# --- Annotations ---` section, insert a new role-CRUD section:

```python
    # --------------------------- Roles ---------------------------

    def put_role(self, rec: RoleRecord) -> None:
        """Insert or update a role record. Validates ecosystem membership
        of qualification_schema_said and issuer_role_name."""
        if not rec.ecosystem_name or not rec.name:
            raise ValueError("RoleRecord requires ecosystem_name and name")
        eco = self.get_ecosystem(rec.ecosystem_name)
        if eco is None:
            raise KeyError(f"unknown ecosystem '{rec.ecosystem_name}'")
        if rec.qualification_schema_said and rec.qualification_schema_said not in eco.schema_saids:
            raise ValueError(
                f"qualification_schema_said '{rec.qualification_schema_said}' "
                f"is not a member of ecosystem '{rec.ecosystem_name}'"
            )
        if rec.issuer_role_name:
            parent = self.get_role(rec.ecosystem_name, rec.issuer_role_name)
            if parent is None:
                raise ValueError(
                    f"issuer_role '{rec.issuer_role_name}' is not a known "
                    f"role in ecosystem '{rec.ecosystem_name}'"
                )
        now = datetime.now(timezone.utc).isoformat()
        if not rec.created_at:
            rec.created_at = now
        rec.updated_at = now
        rec.root_issuer_aids = sorted(set(rec.root_issuer_aids))
        self.roles.pin(keys=(rec.ecosystem_name, rec.name), val=rec)

        # Update the parent ecosystem's role_names cache (idempotent).
        if rec.name not in eco.role_names:
            eco.role_names = sorted(set(eco.role_names) | {rec.name})
            self.put_ecosystem(eco)

    def get_role(self, ecosystem_name: str, role_name: str) -> RoleRecord | None:
        return self.roles.get(keys=(ecosystem_name, role_name))

    def list_roles(self, ecosystem_name: str) -> list[RoleRecord]:
        prefix = (ecosystem_name,)
        out: list[RoleRecord] = []
        for keys, val in self.roles.getItemIter(keys=prefix):
            # getItemIter returns all roles whose key tuple starts with
            # (ecosystem_name,) — exactly what we want.
            out.append(val)
        return out

    def delete_role(self, ecosystem_name: str, role_name: str) -> None:
        """Remove a role record. Cascades cleanup: drops role_name from
        the ecosystem's role_names list and removes any
        issuer_qualification_rules entries pointing at this role."""
        rec = self.get_role(ecosystem_name, role_name)
        if rec is None:
            return  # idempotent
        self.roles.rem(keys=(ecosystem_name, role_name))

        eco = self.get_ecosystem(ecosystem_name)
        if eco is None:
            return
        eco.role_names = [n for n in eco.role_names if n != role_name]
        eco.issuer_qualification_rules = {
            said: r for said, r in eco.issuer_qualification_rules.items()
            if r != role_name
        }
        self.put_ecosystem(eco)
```

- [ ] **Step 6: Add role cascade cleanup to `delete_ecosystem`**

Find the existing `delete_ecosystem` method:

```python
    def delete_ecosystem(self, name: str) -> None:
        rec = self.get_ecosystem(name)
        if rec is None:
            return
        for said in rec.schema_saids:
            self._remove_membership(self.schema_membership, said, name)
        for aid in rec.issuer_aids:
            self._remove_membership(self.aid_membership, aid, name)
        self.ecosystems.rem(keys=(name,))
```

Insert role removal between the membership cleanup and the ecosystem record removal:

```python
    def delete_ecosystem(self, name: str) -> None:
        rec = self.get_ecosystem(name)
        if rec is None:
            return
        for said in rec.schema_saids:
            self._remove_membership(self.schema_membership, said, name)
        for aid in rec.issuer_aids:
            self._remove_membership(self.aid_membership, aid, name)
        # Cascade role cleanup — every role under this ecosystem.
        for role in self.list_roles(name):
            self.roles.rem(keys=(name, role.name))
        self.ecosystems.rem(keys=(name,))
```

- [ ] **Step 7: Run tests to verify they pass**

```
.venv/bin/python -m pytest tests/test_ecosystem_baser.py -v 2>&1 | tail -20
```

Expected: all tests pass — the 25 from Task 1 + the 11 new role tests = 36 total.

- [ ] **Step 8: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
git add src/locksmith/plugins/ecosystem_viewer/db.py tests/test_ecosystem_baser.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): RoleRecord + role CRUD on EcosystemBaser (Stage 12)

New RoleRecord dataclass keyed (ecosystem_name, role_name) in a new
rle. Komer subkey. CRUD methods: put_role (validates ecosystem
existence, qualification_schema_said membership, issuer_role_name
existence), get_role, list_roles, delete_role (cascades cleanup of
role_names and issuer_qualification_rules entries).

delete_ecosystem now cascades role cleanup as well — deleting an
ecosystem removes every role defined under it. put_role updates the
parent ecosystem's role_names cache idempotently.

Per design 2026-05-08-ecosystem-governance-roadmap §2. 11 new tests
covering CRUD + validation + cascading + idempotency.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Resolver helpers — `resolve_role_members` + `is_permitted_issuer`

Goal: two helpers on `EcosystemBaser` that walk role chains. Both take a `find_credentials_of_schema(schema_said) -> list[Credential]` callable so tests can pass a simple mock without instantiating a keripy `Regery`. The plugin layer (later, in Stage 13) will pass a real implementation that walks `vault.rgy.reger`.

A `Credential` for the purpose of the resolver is a duck-typed object with `.holder_aid: str`, `.issuer_aid: str`, and `.schema_said: str` attributes. Tests provide a minimal namedtuple-based mock.

`is_permitted_issuer(eco_name, schema_said, aid, find_credentials_of_schema)` returns True if:
1. `aid` appears in `eco.permitted_issuers.get(schema_said, [])` — explicit list
2. OR `eco.issuer_qualification_rules.get(schema_said)` is a role whose members include `aid` — qualification

`resolve_role_members(eco_name, role_name, find_credentials_of_schema)` returns the set of AIDs currently in the role:
- If root role (issuer_role_name == ""): return `set(root_issuer_aids)` directly
- Else: find all credentials of `qualification_schema_said` whose `issuer_aid` is in `resolve_role_members(eco_name, issuer_role_name)`. The holders of those credentials are the members. Apply cycle protection (track visited role names; raise on cycle).

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/db.py`
- Test: `tests/test_ecosystem_baser.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ecosystem_baser.py`:

```python
# ---------------------------------------------------------------------------
# Stage 12: Resolver — resolve_role_members + is_permitted_issuer
# ---------------------------------------------------------------------------

from collections import namedtuple

# Minimal credential shape used by the resolver. Real plugin will pass a
# keripy-backed object with the same three attributes.
_Cred = namedtuple("_Cred", ["holder_aid", "issuer_aid", "schema_said"])


def _make_finder(creds: list[_Cred]):
    """Build a find_credentials_of_schema(schema_said) -> list[Credential]
    callable from a fixed credential pool."""
    def finder(schema_said: str):
        return [c for c in creds if c.schema_said == schema_said]
    return finder


def test_resolve_root_role_returns_root_issuer_aids(baser):
    """A root role (no issuer_role_name) resolves to its enumerated AIDs."""
    _seed_eco_with_schema_and_aid(baser, schema="ES1", aid="EGLEIF")
    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="root",
        qualification_schema_said="ES1",
        root_issuer_aids=["EGLEIF", "EOTHER"],
    ))
    members = baser.resolve_role_members("eco", "root", _make_finder([]))
    assert members == {"EGLEIF", "EOTHER"}


def test_resolve_chained_role_walks_credentials(baser):
    """A role with issuer_role_name="parent" resolves to the holders of
    qualification credentials issued by parent-role members."""
    # Ecosystem with two schemas, both members; one root role + one
    # chained role under it.
    baser.put_ecosystem(EcosystemRecord(
        name="eco",
        schema_saids=["ES_DOI", "ES_PROD"],
        issuer_aids=["EGLEIF", "ECA-DOI"],
    ))
    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="root",
        qualification_schema_said="ES_DOI",
        root_issuer_aids=["EGLEIF"],
    ))
    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="state-doi",
        qualification_schema_said="ES_DOI",
        issuer_role_name="root",
    ))
    # Credential pool: ES_DOI was issued by EGLEIF (a root member) to
    # ECA-DOI; nothing else.
    creds = [_Cred(holder_aid="ECA-DOI", issuer_aid="EGLEIF", schema_said="ES_DOI")]
    members = baser.resolve_role_members("eco", "state-doi", _make_finder(creds))
    assert members == {"ECA-DOI"}


def test_resolve_filters_credentials_with_unauthorized_issuer(baser):
    """Credentials whose issuer is NOT in the parent role are ignored."""
    baser.put_ecosystem(EcosystemRecord(
        name="eco", schema_saids=["ES1"], issuer_aids=["EROOT"],
    ))
    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="root",
        qualification_schema_said="ES1",
        root_issuer_aids=["EROOT"],
    ))
    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="downstream",
        qualification_schema_said="ES1",
        issuer_role_name="root",
    ))
    # Two credentials of ES1: one issued by EROOT (good), one by ESQUATTER (bad).
    creds = [
        _Cred(holder_aid="EVALID", issuer_aid="EROOT", schema_said="ES1"),
        _Cred(holder_aid="EBAD", issuer_aid="ESQUATTER", schema_said="ES1"),
    ]
    members = baser.resolve_role_members("eco", "downstream", _make_finder(creds))
    assert members == {"EVALID"}


def test_resolve_returns_empty_set_when_no_credentials_match(baser):
    baser.put_ecosystem(EcosystemRecord(
        name="eco", schema_saids=["ES1"], issuer_aids=["EROOT"],
    ))
    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="root",
        qualification_schema_said="ES1",
        root_issuer_aids=["EROOT"],
    ))
    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="downstream",
        qualification_schema_said="ES1",
        issuer_role_name="root",
    ))
    members = baser.resolve_role_members("eco", "downstream", _make_finder([]))
    assert members == set()


def test_resolve_unknown_role_returns_empty_set(baser):
    baser.put_ecosystem(EcosystemRecord(name="eco"))
    members = baser.resolve_role_members("eco", "ghost", _make_finder([]))
    assert members == set()


def test_resolve_detects_cycle_in_role_chain(baser):
    """A role chain that loops back on itself raises a clear error
    rather than recursing forever. Cycles are forbidden by put_role's
    validation, but a database tampered with externally could still
    create one — the resolver must defend itself."""
    _seed_eco_with_schema_and_aid(baser)
    # Build the cycle by writing directly to the Komer (bypassing put_role).
    baser.roles.pin(keys=("eco", "a"), val=RoleRecord(
        ecosystem_name="eco", name="a",
        qualification_schema_said="ES1", issuer_role_name="b",
    ))
    baser.roles.pin(keys=("eco", "b"), val=RoleRecord(
        ecosystem_name="eco", name="b",
        qualification_schema_said="ES1", issuer_role_name="a",
    ))
    with pytest.raises(ValueError, match="cycle"):
        baser.resolve_role_members("eco", "a", _make_finder([]))


def test_is_permitted_issuer_via_explicit_list(baser):
    """An AID listed in eco.permitted_issuers[schema] is a permitted
    issuer regardless of any role chain."""
    _seed_eco_with_schema_and_aid(baser, schema="ES1", aid="EA1")
    baser.set_permitted_issuers("eco", "ES1", ["EA1"])
    assert baser.is_permitted_issuer("eco", "ES1", "EA1", _make_finder([])) is True
    assert baser.is_permitted_issuer("eco", "ES1", "EOTHER", _make_finder([])) is False


def test_is_permitted_issuer_via_role_qualification(baser):
    """An AID that's a member of the role named in
    issuer_qualification_rules[schema] is a permitted issuer, even if
    not listed in permitted_issuers."""
    baser.put_ecosystem(EcosystemRecord(
        name="eco", schema_saids=["ES_DOI", "ES_PROD"],
        issuer_aids=["EROOT", "ECA-DOI"],
    ))
    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="root",
        qualification_schema_said="ES_DOI",
        root_issuer_aids=["EROOT"],
    ))
    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="state-doi",
        qualification_schema_said="ES_DOI",
        issuer_role_name="root",
    ))
    rec = baser.get_ecosystem("eco")
    rec.issuer_qualification_rules = {"ES_PROD": "state-doi"}
    baser.put_ecosystem(rec)

    creds = [_Cred(holder_aid="ECA-DOI", issuer_aid="EROOT", schema_said="ES_DOI")]
    assert baser.is_permitted_issuer("eco", "ES_PROD", "ECA-DOI", _make_finder(creds)) is True
    assert baser.is_permitted_issuer("eco", "ES_PROD", "EUNKNOWN", _make_finder(creds)) is False


def test_is_permitted_issuer_combines_explicit_and_role(baser):
    """Both paths are checked; True if either matches."""
    _seed_eco_with_schema_and_aid(baser, schema="ES1", aid="EROOT")
    baser.put_role(RoleRecord(
        ecosystem_name="eco", name="root",
        qualification_schema_said="ES1",
        root_issuer_aids=["EROOT"],
    ))
    rec = baser.get_ecosystem("eco")
    rec.issuer_qualification_rules = {"ES1": "root"}
    rec.permitted_issuers = {"ES1": ["EEXPLICIT"]}
    baser.put_ecosystem(rec)

    # EEXPLICIT matches via explicit list; EROOT matches via role.
    assert baser.is_permitted_issuer("eco", "ES1", "EEXPLICIT", _make_finder([])) is True
    assert baser.is_permitted_issuer("eco", "ES1", "EROOT", _make_finder([])) is True
    assert baser.is_permitted_issuer("eco", "ES1", "ENEITHER", _make_finder([])) is False


def test_is_permitted_issuer_unknown_ecosystem_returns_false(baser):
    assert baser.is_permitted_issuer("nope", "ES1", "EA1", _make_finder([])) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/python -m pytest tests/test_ecosystem_baser.py -k "resolve or is_permitted" -v 2>&1 | tail -20
```

Expected: all the new resolver tests FAIL with `AttributeError: 'EcosystemBaser' object has no attribute 'resolve_role_members'` (and similar for `is_permitted_issuer`).

- [ ] **Step 3: Add the resolver methods**

In `EcosystemBaser`, after the role CRUD section (added in Task 2) and before the annotations section, append a resolver section:

```python
    # --------------------------- Resolver helpers ---------------------------

    def resolve_role_members(
        self,
        ecosystem_name: str,
        role_name: str,
        find_credentials_of_schema,
    ) -> set[str]:
        """Compute the current AID members of a role.

        Root role (issuer_role_name=""): returns the role's
        root_issuer_aids verbatim.

        Chained role: returns the holders of qualification credentials
        whose issuer is a member of the parent role. Walks the chain
        recursively with cycle protection.

        Parameters
        ----------
        ecosystem_name, role_name : str
            The role to resolve. Returns set() if unknown.
        find_credentials_of_schema : callable(str) -> Iterable
            Returns credentials of a given schema_said. Each credential
            must have .holder_aid, .issuer_aid, .schema_said attributes.
            The plugin layer passes a vault.rgy.reger-backed
            implementation; tests pass a mock.

        Raises
        ------
        ValueError
            If a cycle is detected in the role chain. (put_role validates
            against cycles on insert; this defends against externally-
            tampered databases.)
        """
        return self._resolve_role_members(
            ecosystem_name, role_name, find_credentials_of_schema, visited=set(),
        )

    def _resolve_role_members(
        self, ecosystem_name, role_name, find_credentials_of_schema, visited,
    ) -> set[str]:
        if role_name in visited:
            raise ValueError(
                f"cycle detected in role chain at '{role_name}' "
                f"(ecosystem '{ecosystem_name}')"
            )
        visited = visited | {role_name}

        role = self.get_role(ecosystem_name, role_name)
        if role is None:
            return set()
        if not role.issuer_role_name:
            # Root role.
            return set(role.root_issuer_aids)

        parent_members = self._resolve_role_members(
            ecosystem_name, role.issuer_role_name, find_credentials_of_schema, visited,
        )
        if not parent_members:
            return set()

        members: set[str] = set()
        for cred in find_credentials_of_schema(role.qualification_schema_said) or []:
            if cred.issuer_aid in parent_members:
                members.add(cred.holder_aid)
        return members

    def is_permitted_issuer(
        self,
        ecosystem_name: str,
        schema_said: str,
        aid: str,
        find_credentials_of_schema,
    ) -> bool:
        """Return True iff `aid` is a permitted issuer of `schema_said`
        in `ecosystem_name`, by either path:

        - Explicit: `aid` is in `permitted_issuers[schema_said]`
        - Qualification: `issuer_qualification_rules[schema_said]` is
          a role and `aid` is a current member of that role
        """
        eco = self.get_ecosystem(ecosystem_name)
        if eco is None:
            return False
        # Explicit list path.
        if aid in eco.permitted_issuers.get(schema_said, []):
            return True
        # Role-qualification path.
        role_name = eco.issuer_qualification_rules.get(schema_said)
        if not role_name:
            return False
        members = self.resolve_role_members(
            ecosystem_name, role_name, find_credentials_of_schema,
        )
        return aid in members
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv/bin/python -m pytest tests/test_ecosystem_baser.py -v 2>&1 | tail -10
```

Expected: all tests pass — 36 from prior tasks + 10 new resolver tests = 46 total.

- [ ] **Step 5: Run the full ecosystem-viewer test suite as a regression check**

```
.venv/bin/python -m pytest tests/test_ecosystem_baser.py tests/test_layout.py tests/test_acdc_inspector.py tests/test_lifecycle_widget.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
git add src/locksmith/plugins/ecosystem_viewer/db.py tests/test_ecosystem_baser.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): role-chain resolver + is_permitted_issuer (Stage 12)

resolve_role_members(eco, role, find_credentials_of_schema) walks the
role chain: root role returns root_issuer_aids; chained roles return
holders of qualification credentials whose issuer is in the parent
role. Cycle-protected (put_role rejects cycles on insert; resolver
raises ValueError if it encounters one anyway).

is_permitted_issuer(eco, schema, aid, find_credentials_of_schema)
combines both governance paths: explicit permitted_issuers list AND
role-membership via issuer_qualification_rules. True iff either matches.

The find_credentials_of_schema callable parameter lets tests pass a
simple mock; the plugin layer (Stage 13) will pass a vault.rgy.reger-
backed implementation. 10 new tests covering root + chain + cycle +
filtering by issuer + is_permitted-via-both-paths + edge cases.

Per design 2026-05-08-ecosystem-governance-roadmap §2.3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-review checklist results

**Spec coverage** — every recommendation in `2026-05-08-ecosystem-governance-roadmap.md` §2 (Stage 12 scope) has a task:
- §2.1 RoleRecord dataclass + rle. Komer → Task 2 ✓
- §2.2 EcosystemRecord field additions (issuer_qualification_rules, role_names, schema_version, governance_url) → Task 1 ✓
- §2.3 EcosystemBaser CRUD methods (put_role, get_role, list_roles, delete_role) → Task 2 ✓
- §2.3 Resolver helpers (resolve_role_members, is_permitted_issuer) → Task 3 ✓
- §2.4 What stays unchanged → enforced by tests-only-add-tests discipline ✓

**Open question §6.1** (per-ecosystem roles): satisfied — `RoleRecord.ecosystem_name` is part of the composite key. Cross-ecosystem composition deferred per the user's confirmed design call (semantic alignment via shared schema SAIDs, not shared role records).

**Open question §6.2** (lazy resolution): satisfied — the resolver is pure and re-runs on every call. No caching layer; no invalidation logic. Adds complexity later if measured to be needed.

**Open question §6.3** (root_issuer_aids enumeration): satisfied — root roles enumerate AIDs directly. No richer trust-root mechanism in v1.

**Open question §6.4** (governance_url): satisfied — Task 1 adds the field with empty-string default.

**Placeholder scan:** every test step shows actual test code; every implementation step shows actual code. No "TBD".

**Type consistency across tasks:**
- `RoleRecord` declared in Task 2; consumed in Task 3
- New EcosystemRecord fields declared in Task 1; consumed in Task 2 (role_names cache update) and Task 3 (issuer_qualification_rules lookup)
- `find_credentials_of_schema` callable signature is the same in all Task 3 helpers
- Cascading cleanup (delete_role, delete_ecosystem) referenced in Task 2 tests; implemented in Task 2 step 5

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-08-stage-12-roles-data-model.md`.

The user has already chosen subagent-driven execution. Proceed with that flow.
