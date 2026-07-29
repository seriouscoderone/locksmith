# Embedded Assistant — Library Core + Deterministic Harness (Phase 0/1, Subsystem A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the UI-agnostic assistant library core — the pure-Python harness that turns an utterance into a grounded, grammar-constrained KERI-protocol intent and drives it through match → preview → confirm → dispatch → audit, provable end-to-end against a fixture micro-app template with fake host seams (no LLM, no Locksmith, no keripy).

**Architecture:** A self-contained package `keri_assistant` (src layout, zero runtime deps). It defines the value object (`ResolvedIntent`), the grounded verb surface (`CommandSurface` + `MicroAppSurface` provider compiled from a micro-app template's `commands[]`/`projections[]`), the grounding constraint-set, the host-seam Protocols (`Confirmer`/`Dispatcher`/`AuditSink`), a deterministic matcher, and the `Assistant` harness that orchestrates the flow and enforces the never-verb invariant. Hosts (Locksmith, concierge) are follow-on plans that implement the seams.

**Tech Stack:** Python 3.14, stdlib only (`dataclasses`, `typing.Protocol`), `pytest` for tests. Runs in the worktree's **isolated** `.venv`.

## Global Constraints

- **Package lives at** `packages/keri-assistant/` in the `embedded-assistant` worktree; src layout `packages/keri-assistant/src/keri_assistant/`, tests `packages/keri-assistant/tests/`. It is a standalone package (sibling to `ai-identicon`), extractable later — **it MUST NOT import `locksmith` or `keri`/keripy.** Core is pure stdlib.
- **Use the worktree's isolated venv only:** `/Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python`. Do NOT run `pip install` against the shared main-checkout venv. No install is needed — `[tool.pytest.ini_options] pythonpath=["src"]` makes `import keri_assistant` resolve.
- **Run tests from** `packages/keri-assistant/`: `<worktree>/.venv/bin/python -m pytest -q`.
- **BE KERI NATIVE (LAW):** the library compiles the *grammar of what verbs exist*; it never computes authority. `authz` is carried as opaque data, never evaluated. Design ref: `docs/superpowers/specs/2026-07-29-embedded-assistant-keri-native-design.md`.
- **Never-verbs are structurally absent:** the surface builder MUST drop any command whose route contains a never-verb token (`rotate/rot/delegate/dip/drt/revoke/rev/recover/seed/passcode/admit`). `admit` is included per the spec's §9.5 "human-only until reconciled" note.
- **Emit ≠ execute:** `ResolvedIntent` is inert data; the library never signs, never touches keys, never serializes CESR. Dispatch happens only through the injected `Dispatcher`, only after `Confirmer` returns True.
- **Commit style:** conventional commits; end each commit message with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

### Task 1: Package scaffold + `ResolvedIntent`

**Files:**
- Create: `packages/keri-assistant/pyproject.toml`
- Create: `packages/keri-assistant/src/keri_assistant/__init__.py`
- Create: `packages/keri-assistant/src/keri_assistant/intent.py`
- Test: `packages/keri-assistant/tests/test_intent.py`

**Interfaces:**
- Produces: `ResolvedIntent(route:str, verb_id:str, kind:str, payload:dict, receiver_aid:str|None=None, schema_said:str|None=None)` — frozen dataclass; validates in `__post_init__`; `kind ∈ {"exchange","query"}`. Raises `ValueError` on invalid.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "keri-assistant"
version = "0.0.1"
description = "UI-agnostic KERI-native assistant harness (Phase 0/1 core)"
requires-python = ">=3.14"
dependencies = []

[tool.hatch.build.targets.wheel]
packages = ["src/keri_assistant"]

[tool.pytest.ini_options]
pythonpath = ["src"]
```

- [ ] **Step 2: Create empty `src/keri_assistant/__init__.py`** (empty file).

- [ ] **Step 3: Write the failing test** (`tests/test_intent.py`)

```python
import pytest
from keri_assistant.intent import ResolvedIntent


def test_valid_intent_roundtrips_fields():
    it = ResolvedIntent(route="/ipex/grant", verb_id="grant_license", kind="exchange", payload={"x": 1})
    assert it.route == "/ipex/grant"
    assert it.verb_id == "grant_license"
    assert it.kind == "exchange"
    assert it.payload == {"x": 1}
    assert it.receiver_aid is None and it.schema_said is None


def test_intent_is_frozen():
    it = ResolvedIntent(route="/q", verb_id="v", kind="query", payload={})
    with pytest.raises(Exception):
        it.route = "/other"


@pytest.mark.parametrize("kind", ["exchange", "query"])
def test_kind_allowed(kind):
    ResolvedIntent(route="/r", verb_id="v", kind=kind, payload={})


def test_bad_kind_rejected():
    with pytest.raises(ValueError):
        ResolvedIntent(route="/r", verb_id="v", kind="mutate", payload={})


def test_empty_route_rejected():
    with pytest.raises(ValueError):
        ResolvedIntent(route="", verb_id="v", kind="query", payload={})


def test_non_dict_payload_rejected():
    with pytest.raises(ValueError):
        ResolvedIntent(route="/r", verb_id="v", kind="query", payload=["not", "a", "dict"])
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_intent.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'keri_assistant.intent'`.

- [ ] **Step 5: Write `intent.py`**

```python
"""ResolvedIntent — the inert, grammar-constrained action object the harness emits.

It is NOT CESR, NOT a signed event, NOT a key operation. A trusted host Dispatcher
executes it only after a human confirms. See the design spec, §4.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_KINDS = frozenset({"exchange", "query"})


@dataclass(frozen=True)
class ResolvedIntent:
    route: str
    verb_id: str
    kind: str
    payload: dict = field(default_factory=dict)
    receiver_aid: str | None = None
    schema_said: str | None = None

    def __post_init__(self) -> None:
        if not self.route:
            raise ValueError("route must be a non-empty string")
        if self.kind not in _KINDS:
            raise ValueError(f"kind must be one of {sorted(_KINDS)}, got {self.kind!r}")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_intent.py -q`
Expected: PASS (6 passed).

- [ ] **Step 7: Commit**

```bash
git add packages/keri-assistant/pyproject.toml packages/keri-assistant/src/keri_assistant/__init__.py packages/keri-assistant/src/keri_assistant/intent.py packages/keri-assistant/tests/test_intent.py
git commit -m "feat(keri-assistant): package scaffold + ResolvedIntent value object"
```

---

### Task 2: Never-verb exclusion

**Files:**
- Create: `packages/keri-assistant/src/keri_assistant/neververbs.py`
- Test: `packages/keri-assistant/tests/test_neververbs.py`

**Interfaces:**
- Produces: `NEVER_VERB_TOKENS: frozenset[str]`; `is_never_verb(route: str) -> bool` — tokenizes a route on `/` and `_`, lowercased, and returns True if any token is a never-verb.

- [ ] **Step 1: Write the failing test** (`tests/test_neververbs.py`)

```python
import pytest
from keri_assistant.neververbs import is_never_verb, NEVER_VERB_TOKENS


@pytest.mark.parametrize("route", [
    "/keri/cmd/rotate_key",
    "/x/revoke_credential",
    "/ipex/admit",
    "/vault/seed_display",
    "/y/delegate_authority",
])
def test_never_verbs_detected(route):
    assert is_never_verb(route) is True


@pytest.mark.parametrize("route", [
    "/ipex/grant",
    "/ipex/apply",
    "/insurance/cmd/submit_quote",
    "/qry/issued_credentials",
])
def test_allowed_verbs_not_flagged(route):
    assert is_never_verb(route) is False


def test_token_set_includes_admit_per_reconciliation_note():
    assert "admit" in NEVER_VERB_TOKENS  # spec §9.5: human-only until reconciled
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_neververbs.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'keri_assistant.neververbs'`.

- [ ] **Step 3: Write `neververbs.py`**

```python
"""Never-verbs: routes that must be structurally absent from any assistant surface.

KEL establishment + secret display + (provisionally) IPEX admit. See design spec
Global Constraints and §9.5. This is a STRUCTURAL exclusion, not a runtime authz check.
"""
from __future__ import annotations

import re

NEVER_VERB_TOKENS: frozenset[str] = frozenset({
    "rotate", "rot",
    "delegate", "dip", "drt",
    "revoke", "rev",
    "recover",
    "seed", "passcode",
    "admit",  # spec §9.5 — human-only until reconciled with the KERI-protocol action space
})

_SPLIT = re.compile(r"[/_]+")


def is_never_verb(route: str) -> bool:
    tokens = {t for t in _SPLIT.split(route.lower()) if t}
    return bool(tokens & NEVER_VERB_TOKENS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_neververbs.py -q`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/keri-assistant/src/keri_assistant/neververbs.py packages/keri-assistant/tests/test_neververbs.py
git commit -m "feat(keri-assistant): never-verb token set + structural route exclusion"
```

---

### Task 3: `Verb`, `CommandSurface`, and the `MicroAppSurface` provider

**Files:**
- Create: `packages/keri-assistant/src/keri_assistant/surface.py`
- Create: `packages/keri-assistant/tests/fixtures/__init__.py` (empty)
- Create: `packages/keri-assistant/tests/fixtures/sample_template.py`
- Test: `packages/keri-assistant/tests/test_surface.py`

**Interfaces:**
- Consumes: `is_never_verb` (Task 2).
- Produces:
  - `Verb(id:str, route:str, phrasings:tuple[str,...], payload_schema:dict, kind:str, schema_said:str|None=None, counterparty_role:str|None=None, authz:dict=…)` — frozen.
  - `CommandSurface(verbs:tuple[Verb,...])` with `by_id(self, verb_id:str)->Verb|None` and `routes(self)->frozenset[str]`.
  - `build_micro_app_surface(template:dict)->CommandSurface` — compiles `commands[]` (kind `"exchange"`) and `projections[]` (kind `"query"`, route `/qry/<id>`), dropping any command whose route `is_never_verb`. Phrasings = lowercased word tokens of `name` + `id` (+ projection `name`). `schema_said` = `command["authz"].get("schema_said")` when present.

- [ ] **Step 1: Write the fixture** (`tests/fixtures/sample_template.py`)

```python
"""A minimal micro-app template shaped like the real ones (commands[]/projections[]),
plus one command carrying a never-verb route to prove structural exclusion.
"""

SAMPLE_TEMPLATE = {
    "d": "EFixtureTemplateSAID000000000000000000000000",
    "spec_version": "micro-app-template/0.1",
    "header": {"id": "carrier-quote", "display_name": "Carrier — submit quote"},
    "role": {"id": "carrier", "kind": "organization"},
    "commands": [
        {
            "id": "submit_quote",
            "name": "Submit the quote",
            "description": "Send the prepared quote to the counterparty",
            "route": "/insurance/cmd/submit_quote",
            "counterparty_role": "broker",
            "payload_schema": {"type": "object", "properties": {"amount": {"type": "number"}},
                               "required": ["amount"], "additionalProperties": False},
            "authz": {"method": "credential", "schema_said": "ESchemaQuote0000000000000000000000000000000"},
        },
        {
            "id": "create_application",
            "name": "Create an application",
            "description": "Open a new application record",
            "route": "/insurance/cmd/create_application",
            "counterparty_role": None,
            "payload_schema": {"type": "object", "properties": {}, "additionalProperties": True},
            "authz": {"method": "open"},
        },
        {
            # MUST be dropped by the surface builder (never-verb route).
            "id": "rotate_signing_key",
            "name": "Rotate signing key",
            "description": "rotate the carrier key",
            "route": "/keri/cmd/rotate_key",
            "payload_schema": {"type": "object"},
            "authz": {"method": "open"},
        },
    ],
    "projections": [
        {"id": "issued_credentials", "name": "Issued credentials", "display": {"view_type": "table"}},
    ],
}
```

- [ ] **Step 2: Write the failing test** (`tests/test_surface.py`)

```python
from keri_assistant.surface import Verb, CommandSurface, build_micro_app_surface
from tests.fixtures.sample_template import SAMPLE_TEMPLATE


def test_commands_and_projections_become_verbs():
    surf = build_micro_app_surface(SAMPLE_TEMPLATE)
    ids = {v.id for v in surf.verbs}
    assert "submit_quote" in ids
    assert "create_application" in ids
    assert "issued_credentials" in ids  # projection -> query verb


def test_never_verb_command_is_excluded():
    surf = build_micro_app_surface(SAMPLE_TEMPLATE)
    assert surf.by_id("rotate_signing_key") is None
    assert "/keri/cmd/rotate_key" not in surf.routes()


def test_command_verb_fields():
    surf = build_micro_app_surface(SAMPLE_TEMPLATE)
    v = surf.by_id("submit_quote")
    assert v.route == "/insurance/cmd/submit_quote"
    assert v.kind == "exchange"
    assert v.schema_said == "ESchemaQuote0000000000000000000000000000000"
    assert v.counterparty_role == "broker"
    assert "quote" in v.phrasings and "submit" in v.phrasings


def test_projection_verb_is_query_kind():
    surf = build_micro_app_surface(SAMPLE_TEMPLATE)
    v = surf.by_id("issued_credentials")
    assert v.kind == "query"
    assert v.route == "/qry/issued_credentials"


def test_authz_is_carried_as_opaque_data_not_evaluated():
    surf = build_micro_app_surface(SAMPLE_TEMPLATE)
    v = surf.by_id("submit_quote")
    assert v.authz == {"method": "credential", "schema_said": "ESchemaQuote0000000000000000000000000000000"}


def test_routes_returns_frozenset_of_surviving_routes():
    surf = build_micro_app_surface(SAMPLE_TEMPLATE)
    assert surf.routes() == frozenset({
        "/insurance/cmd/submit_quote", "/insurance/cmd/create_application", "/qry/issued_credentials",
    })
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_surface.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'keri_assistant.surface'`.

- [ ] **Step 4: Write `surface.py`**

```python
"""CommandSurface — the grounded verb vocabulary compiled from a micro-app template.

commands[] -> exchange verbs; projections[] -> query verbs. Never-verb routes are
dropped structurally. authz is carried verbatim as opaque data (never evaluated here).
See design spec §4, §5.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .neververbs import is_never_verb

_WORDS = re.compile(r"[a-z0-9]+")


def _phrasings(*texts: str) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for t in texts:
        for w in _WORDS.findall((t or "").lower()):
            seen.setdefault(w, None)
    return tuple(seen)


@dataclass(frozen=True)
class Verb:
    id: str
    route: str
    phrasings: tuple[str, ...]
    payload_schema: dict
    kind: str  # "exchange" | "query"
    schema_said: str | None = None
    counterparty_role: str | None = None
    authz: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CommandSurface:
    verbs: tuple[Verb, ...]

    def by_id(self, verb_id: str) -> Verb | None:
        for v in self.verbs:
            if v.id == verb_id:
                return v
        return None

    def routes(self) -> frozenset[str]:
        return frozenset(v.route for v in self.verbs)


def build_micro_app_surface(template: dict) -> CommandSurface:
    verbs: list[Verb] = []

    for cmd in template.get("commands", []):
        route = cmd["route"]
        if is_never_verb(route):
            continue  # structural exclusion — never even a proposable verb
        authz = dict(cmd.get("authz", {}))
        verbs.append(Verb(
            id=cmd["id"],
            route=route,
            phrasings=_phrasings(cmd.get("name", ""), cmd.get("id", "")),
            payload_schema=dict(cmd.get("payload_schema", {})),
            kind="exchange",
            schema_said=authz.get("schema_said"),
            counterparty_role=cmd.get("counterparty_role"),
            authz=authz,
        ))

    for proj in template.get("projections", []):
        route = f"/qry/{proj['id']}"
        if is_never_verb(route):
            continue
        verbs.append(Verb(
            id=proj["id"],
            route=route,
            phrasings=_phrasings(proj.get("name", ""), proj.get("id", "")),
            payload_schema={},
            kind="query",
        ))

    return CommandSurface(verbs=tuple(verbs))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_surface.py -q`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add packages/keri-assistant/src/keri_assistant/surface.py packages/keri-assistant/tests/fixtures/ packages/keri-assistant/tests/test_surface.py
git commit -m "feat(keri-assistant): CommandSurface + MicroAppSurface builder (never-verbs excluded)"
```

---

### Task 4: Grounding constraint-set

**Files:**
- Create: `packages/keri-assistant/src/keri_assistant/grounding.py`
- Test: `packages/keri-assistant/tests/test_grounding.py`

**Interfaces:**
- Consumes: `ResolvedIntent` (Task 1).
- Produces: `Grounding(known_aids:frozenset[str], allowed_schema_saids:frozenset[str])`; `check_grounded(intent:ResolvedIntent, grounding:Grounding)->str|None` — returns `None` if the intent's `receiver_aid`/`schema_said` are grounded, else a human-readable reason string.

- [ ] **Step 1: Write the failing test** (`tests/test_grounding.py`)

```python
from keri_assistant.intent import ResolvedIntent
from keri_assistant.grounding import Grounding, check_grounded

G = Grounding(
    known_aids=frozenset({"EBroker000000000000000000000000000000000000"}),
    allowed_schema_saids=frozenset({"ESchemaQuote0000000000000000000000000000000"}),
)


def test_fully_grounded_intent_passes():
    it = ResolvedIntent(route="/insurance/cmd/submit_quote", verb_id="submit_quote", kind="exchange",
                        payload={"amount": 1}, receiver_aid="EBroker000000000000000000000000000000000000",
                        schema_said="ESchemaQuote0000000000000000000000000000000")
    assert check_grounded(it, G) is None


def test_unknown_receiver_is_refused():
    it = ResolvedIntent(route="/insurance/cmd/submit_quote", verb_id="submit_quote", kind="exchange",
                        payload={}, receiver_aid="EStranger000000000000000000000000000000000")
    reason = check_grounded(it, G)
    assert reason is not None and "receiver" in reason.lower()


def test_ungrounded_schema_is_refused():
    it = ResolvedIntent(route="/insurance/cmd/submit_quote", verb_id="submit_quote", kind="exchange",
                        payload={}, schema_said="EUnknownSchema00000000000000000000000000000")
    reason = check_grounded(it, G)
    assert reason is not None and "schema" in reason.lower()


def test_none_fields_are_not_checked():
    it = ResolvedIntent(route="/qry/issued_credentials", verb_id="issued_credentials", kind="query", payload={})
    assert check_grounded(it, G) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_grounding.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'keri_assistant.grounding'`.

- [ ] **Step 3: Write `grounding.py`**

```python
"""Grounding constraint-set (Phase-1 direct-lookup form).

The assistant may only address AIDs and reference schema SAIDs that the grounding
actually exposes (from the active template + vault state). It NEVER invents them,
and it NEVER decides authority — that is the recipient's KERI verification. See §5.
"""
from __future__ import annotations

from dataclasses import dataclass

from .intent import ResolvedIntent


@dataclass(frozen=True)
class Grounding:
    known_aids: frozenset[str]
    allowed_schema_saids: frozenset[str]


def check_grounded(intent: ResolvedIntent, grounding: Grounding) -> str | None:
    if intent.receiver_aid is not None and intent.receiver_aid not in grounding.known_aids:
        return f"receiver AID {intent.receiver_aid!r} is not a known counterparty"
    if intent.schema_said is not None and intent.schema_said not in grounding.allowed_schema_saids:
        return f"schema SAID {intent.schema_said!r} is not grounded"
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_grounding.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/keri-assistant/src/keri_assistant/grounding.py packages/keri-assistant/tests/test_grounding.py
git commit -m "feat(keri-assistant): grounding constraint-set (receiver/schema must be grounded)"
```

---

### Task 5: Host seams + test fakes

**Files:**
- Create: `packages/keri-assistant/src/keri_assistant/seams.py`
- Create: `packages/keri-assistant/tests/fakes.py`
- Test: `packages/keri-assistant/tests/test_seams.py`

**Interfaces:**
- Consumes: `ResolvedIntent` (Task 1).
- Produces:
  - `Preview(route:str, verb_id:str, kind:str, receiver_aid:str|None, schema_said:str|None, payload:dict, summary:str)` — frozen.
  - `DispatchResult(ok:bool, detail:str="")` — frozen.
  - `AuditEvent(proposed_by:str, authorized_by:str|None, intent:ResolvedIntent|None, outcome:str)` — frozen.
  - Protocols `Confirmer.confirm(self, preview:Preview)->bool`, `Dispatcher.dispatch(self, intent:ResolvedIntent)->DispatchResult`, `AuditSink.record(self, event:AuditEvent)->None`.
  - Test fakes: `FakeConfirmer(answer:bool)`, `RecordingDispatcher()`, `RecordingAudit()`.

- [ ] **Step 1: Write the failing test** (`tests/test_seams.py`)

```python
from keri_assistant.intent import ResolvedIntent
from keri_assistant.seams import Preview, DispatchResult, AuditEvent
from tests.fakes import FakeConfirmer, RecordingDispatcher, RecordingAudit


def test_fake_confirmer_returns_configured_answer():
    p = Preview(route="/r", verb_id="v", kind="exchange", receiver_aid=None, schema_said=None,
                payload={}, summary="do a thing")
    assert FakeConfirmer(True).confirm(p) is True
    assert FakeConfirmer(False).confirm(p) is False


def test_recording_dispatcher_captures_intent_and_returns_ok():
    d = RecordingDispatcher()
    it = ResolvedIntent(route="/r", verb_id="v", kind="exchange", payload={})
    res = d.dispatch(it)
    assert isinstance(res, DispatchResult) and res.ok is True
    assert d.dispatched == [it]


def test_recording_audit_captures_events():
    a = RecordingAudit()
    ev = AuditEvent(proposed_by="assistant", authorized_by="user", intent=None, outcome="dispatched")
    a.record(ev)
    assert a.events == [ev]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_seams.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'keri_assistant.seams'`.

- [ ] **Step 3: Write `seams.py`**

```python
"""Host seams — the thin interfaces a display (Locksmith, concierge) implements.

The library owns the harness; the host owns rendering the confirm ceremony, performing
the KERI protocol action (wrapping keripy), and recording the audit trail. See spec §2.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .intent import ResolvedIntent


@dataclass(frozen=True)
class Preview:
    route: str
    verb_id: str
    kind: str
    receiver_aid: str | None
    schema_said: str | None
    payload: dict
    summary: str


@dataclass(frozen=True)
class DispatchResult:
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class AuditEvent:
    proposed_by: str
    authorized_by: str | None
    intent: ResolvedIntent | None
    outcome: str  # "dispatched" | "rejected" | "refused_ungrounded" | "no_match"


@runtime_checkable
class Confirmer(Protocol):
    def confirm(self, preview: Preview) -> bool: ...


@runtime_checkable
class Dispatcher(Protocol):
    def dispatch(self, intent: ResolvedIntent) -> DispatchResult: ...


@runtime_checkable
class AuditSink(Protocol):
    def record(self, event: AuditEvent) -> None: ...
```

- [ ] **Step 4: Write `tests/fakes.py`**

```python
from keri_assistant.intent import ResolvedIntent
from keri_assistant.seams import Preview, DispatchResult, AuditEvent


class FakeConfirmer:
    def __init__(self, answer: bool):
        self.answer = answer
        self.previews: list[Preview] = []

    def confirm(self, preview: Preview) -> bool:
        self.previews.append(preview)
        return self.answer


class RecordingDispatcher:
    def __init__(self, ok: bool = True):
        self._ok = ok
        self.dispatched: list[ResolvedIntent] = []

    def dispatch(self, intent: ResolvedIntent) -> DispatchResult:
        self.dispatched.append(intent)
        return DispatchResult(ok=self._ok)


class RecordingAudit:
    def __init__(self):
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_seams.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add packages/keri-assistant/src/keri_assistant/seams.py packages/keri-assistant/tests/fakes.py packages/keri-assistant/tests/test_seams.py
git commit -m "feat(keri-assistant): host-seam Protocols (Confirmer/Dispatcher/AuditSink) + test fakes"
```

---

### Task 6: Deterministic matcher

**Files:**
- Create: `packages/keri-assistant/src/keri_assistant/matcher.py`
- Test: `packages/keri-assistant/tests/test_matcher.py`

**Interfaces:**
- Consumes: `CommandSurface`, `Verb` (Task 3).
- Produces: `MatchResult(verb:Verb|None, candidates:tuple[Verb,...], confident:bool)`; `match(utterance:str, surface:CommandSurface)->MatchResult`. Scoring: count of a verb's phrasing tokens present in the utterance's tokens. Best score wins; `confident` iff best > 0 and strictly greater than the second-best; `candidates` = all verbs sharing the best score when there is a tie; `verb=None`/`candidates=()` when best is 0.

- [ ] **Step 1: Write the failing test** (`tests/test_matcher.py`)

```python
from keri_assistant.surface import build_micro_app_surface
from keri_assistant.matcher import match
from tests.fixtures.sample_template import SAMPLE_TEMPLATE

SURF = build_micro_app_surface(SAMPLE_TEMPLATE)


def test_confident_match_on_clear_phrasing():
    r = match("please submit the quote now", SURF)
    assert r.confident is True
    assert r.verb is not None and r.verb.id == "submit_quote"


def test_no_match_returns_none():
    r = match("what is the weather", SURF)
    assert r.verb is None
    assert r.confident is False
    assert r.candidates == ()


def test_query_projection_is_matchable():
    r = match("show issued credentials", SURF)
    assert r.confident is True
    assert r.verb.id == "issued_credentials"


def test_tie_is_not_confident_and_lists_candidates():
    # "create the application" and "submit the quote" share no token, so craft a real tie:
    # both "create_application" and "issued_credentials" match zero here; instead force a tie
    # by an utterance overlapping one token of two verbs.
    r = match("credentials application", SURF)
    # 'application' -> create_application (1), 'credentials' -> issued_credentials (1): tie at score 1
    assert r.confident is False
    assert {v.id for v in r.candidates} == {"create_application", "issued_credentials"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_matcher.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'keri_assistant.matcher'`.

- [ ] **Step 3: Write `matcher.py`**

```python
"""Deterministic matcher (Phase 1, no LLM): utterance -> a grounded verb.

Scores each verb by how many of its phrasing tokens appear in the utterance. This is
the Phase-1 stand-in for the Phase-2 LLM proposer; both emit into the same surface. §4.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .surface import CommandSurface, Verb

_WORDS = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class MatchResult:
    verb: Verb | None
    candidates: tuple[Verb, ...]
    confident: bool


def _score(verb: Verb, tokens: set[str]) -> int:
    return sum(1 for p in verb.phrasings if p in tokens)


def match(utterance: str, surface: CommandSurface) -> MatchResult:
    tokens = set(_WORDS.findall(utterance.lower()))
    scored = [(v, _score(v, tokens)) for v in surface.verbs]
    best = max((s for _, s in scored), default=0)
    if best == 0:
        return MatchResult(verb=None, candidates=(), confident=False)
    top = tuple(v for v, s in scored if s == best)
    if len(top) == 1:
        return MatchResult(verb=top[0], candidates=top, confident=True)
    return MatchResult(verb=None, candidates=top, confident=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_matcher.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/keri-assistant/src/keri_assistant/matcher.py packages/keri-assistant/tests/test_matcher.py
git commit -m "feat(keri-assistant): deterministic phrasing matcher (utterance -> grounded verb)"
```

---

### Task 7: The `Assistant` harness (match → resolve → preview → confirm → dispatch → audit)

**Files:**
- Create: `packages/keri-assistant/src/keri_assistant/harness.py`
- Test: `packages/keri-assistant/tests/test_harness.py`

**Interfaces:**
- Consumes: `ResolvedIntent`, `CommandSurface`/`Verb`, `Grounding`/`check_grounded`, `Confirmer`/`Dispatcher`/`AuditSink`/`Preview`/`AuditEvent`, `match`, `is_never_verb`.
- Produces:
  - `Outcome(status:str, intent:ResolvedIntent|None=None, candidates:tuple[Verb,...]=(), reason:str="")` — frozen. `status ∈ {"dispatched","rejected","no_match","disambiguation","refused_ungrounded"}`.
  - `Assistant(surface, grounding, confirmer, dispatcher, audit, *, proposed_by:str)`; `handle(self, utterance:str, *, payload:dict|None=None, receiver_aid:str|None=None)->Outcome`.

Flow: match → (no verb & no candidates → `no_match`, audited) / (no verb but candidates → `disambiguation`, no dispatch) → build `ResolvedIntent` (receiver_aid from arg; schema_said from verb) → defensive `is_never_verb` guard (must not trigger) → `check_grounded` (fail → `refused_ungrounded`, audited) → `Preview` → `confirmer.confirm` → True: `dispatcher.dispatch` + audit `dispatched` (authorized_by=proposed-by's human, here the literal `"human"`) ; False: audit `rejected` (authorized_by=None). Never dispatch without a True confirm.

- [ ] **Step 1: Write the failing test** (`tests/test_harness.py`)

```python
import pytest
from keri_assistant.surface import build_micro_app_surface
from keri_assistant.grounding import Grounding
from keri_assistant.harness import Assistant, Outcome
from tests.fixtures.sample_template import SAMPLE_TEMPLATE
from tests.fakes import FakeConfirmer, RecordingDispatcher, RecordingAudit

SURF = build_micro_app_surface(SAMPLE_TEMPLATE)
BROKER = "EBroker000000000000000000000000000000000000"
QUOTE_SCHEMA = "ESchemaQuote0000000000000000000000000000000"
G = Grounding(known_aids=frozenset({BROKER}), allowed_schema_saids=frozenset({QUOTE_SCHEMA}))


def _assistant(confirm: bool):
    conf, disp, aud = FakeConfirmer(confirm), RecordingDispatcher(), RecordingAudit()
    a = Assistant(surface=SURF, grounding=G, confirmer=conf, dispatcher=disp, audit=aud,
                  proposed_by="assistant")
    return a, conf, disp, aud


def test_confirmed_command_dispatches_and_audits():
    a, conf, disp, aud = _assistant(confirm=True)
    out = a.handle("submit the quote", payload={"amount": 10}, receiver_aid=BROKER)
    assert out.status == "dispatched"
    assert len(disp.dispatched) == 1
    assert disp.dispatched[0].route == "/insurance/cmd/submit_quote"
    assert disp.dispatched[0].schema_said == QUOTE_SCHEMA
    assert len(conf.previews) == 1  # confirm ceremony always shown
    assert aud.events[-1].outcome == "dispatched"
    assert aud.events[-1].authorized_by == "human"
    assert aud.events[-1].proposed_by == "assistant"


def test_rejected_command_does_not_dispatch():
    a, conf, disp, aud = _assistant(confirm=False)
    out = a.handle("submit the quote", payload={"amount": 10}, receiver_aid=BROKER)
    assert out.status == "rejected"
    assert disp.dispatched == []  # NEVER dispatched without confirm
    assert aud.events[-1].outcome == "rejected"
    assert aud.events[-1].authorized_by is None


def test_no_match_is_audited_and_never_dispatches():
    a, conf, disp, aud = _assistant(confirm=True)
    out = a.handle("what is the weather")
    assert out.status == "no_match"
    assert disp.dispatched == [] and conf.previews == []
    assert aud.events[-1].outcome == "no_match"


def test_ambiguous_utterance_asks_to_disambiguate_without_dispatch():
    a, conf, disp, aud = _assistant(confirm=True)
    out = a.handle("credentials application")
    assert out.status == "disambiguation"
    assert {v.id for v in out.candidates} == {"create_application", "issued_credentials"}
    assert disp.dispatched == [] and conf.previews == []


def test_ungrounded_receiver_is_refused_before_confirm():
    a, conf, disp, aud = _assistant(confirm=True)
    out = a.handle("submit the quote", payload={"amount": 1}, receiver_aid="EStranger0000000000000000000000000000000000")
    assert out.status == "refused_ungrounded"
    assert conf.previews == [] and disp.dispatched == []
    assert aud.events[-1].outcome == "refused_ungrounded"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_harness.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'keri_assistant.harness'`.

- [ ] **Step 3: Write `harness.py`**

```python
"""Assistant — the Phase-1 harness. Matches an utterance to a grounded verb, builds an
inert ResolvedIntent, shows the confirm ceremony, and dispatches ONLY on a human yes.
The model/matcher proposes; the human authorizes; the trusted Dispatcher executes. §4, §7.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .grounding import Grounding, check_grounded
from .intent import ResolvedIntent
from .matcher import match
from .neververbs import is_never_verb
from .seams import AuditEvent, AuditSink, Confirmer, Dispatcher, Preview
from .surface import CommandSurface, Verb


@dataclass(frozen=True)
class Outcome:
    status: str  # dispatched | rejected | no_match | disambiguation | refused_ungrounded
    intent: ResolvedIntent | None = None
    candidates: tuple[Verb, ...] = ()
    reason: str = ""


def _summary(verb: Verb, receiver_aid: str | None) -> str:
    who = f" to {receiver_aid}" if receiver_aid else ""
    return f"{verb.id} ({verb.route}){who}"


class Assistant:
    def __init__(self, *, surface: CommandSurface, grounding: Grounding,
                 confirmer: Confirmer, dispatcher: Dispatcher, audit: AuditSink,
                 proposed_by: str):
        self._surface = surface
        self._grounding = grounding
        self._confirmer = confirmer
        self._dispatcher = dispatcher
        self._audit = audit
        self._proposed_by = proposed_by

    def _emit(self, outcome: str, intent: ResolvedIntent | None, authorized_by: str | None) -> None:
        self._audit.record(AuditEvent(proposed_by=self._proposed_by, authorized_by=authorized_by,
                                      intent=intent, outcome=outcome))

    def handle(self, utterance: str, *, payload: dict | None = None,
               receiver_aid: str | None = None) -> Outcome:
        m = match(utterance, self._surface)
        if m.verb is None:
            if m.candidates:
                return Outcome(status="disambiguation", candidates=m.candidates)
            self._emit("no_match", None, None)
            return Outcome(status="no_match")

        verb = m.verb
        intent = ResolvedIntent(
            route=verb.route, verb_id=verb.id, kind=verb.kind,
            payload=dict(payload or {}), receiver_aid=receiver_aid, schema_said=verb.schema_said,
        )

        # Defensive invariant — the surface already excluded never-verbs; this must never fire.
        assert not is_never_verb(intent.route), f"never-verb route reached harness: {intent.route}"

        reason = check_grounded(intent, self._grounding)
        if reason is not None:
            self._emit("refused_ungrounded", intent, None)
            return Outcome(status="refused_ungrounded", intent=intent, reason=reason)

        preview = Preview(route=intent.route, verb_id=intent.verb_id, kind=intent.kind,
                          receiver_aid=intent.receiver_aid, schema_said=intent.schema_said,
                          payload=intent.payload, summary=_summary(verb, receiver_aid))

        if self._confirmer.confirm(preview):
            self._dispatcher.dispatch(intent)
            self._emit("dispatched", intent, "human")
            return Outcome(status="dispatched", intent=intent)

        self._emit("rejected", intent, None)
        return Outcome(status="rejected", intent=intent)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_harness.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/keri-assistant/src/keri_assistant/harness.py packages/keri-assistant/tests/test_harness.py
git commit -m "feat(keri-assistant): Assistant harness — match->resolve->confirm->dispatch->audit"
```

---

### Task 8: Never-verb invariant (end-to-end) + golden surface snapshot

**Files:**
- Test: `packages/keri-assistant/tests/test_invariants.py`
- Test: `packages/keri-assistant/tests/test_golden_surface.py`

**Interfaces:**
- Consumes: everything above. No new production code (this task hardens the invariants the design's Global Constraints require).

- [ ] **Step 1: Write the invariant test** (`tests/test_invariants.py`)

```python
"""The load-bearing safety invariant (design Global Constraints): no never-verb is ever
constructible into the surface, matchable, or dispatchable — regardless of the template."""
from keri_assistant.surface import build_micro_app_surface
from keri_assistant.matcher import match
from keri_assistant.neververbs import is_never_verb


HOSTILE_TEMPLATE = {
    "commands": [
        {"id": "rotate", "name": "rotate key", "route": "/keri/cmd/rotate_key",
         "payload_schema": {}, "authz": {"method": "open"}},
        {"id": "revoke", "name": "revoke it", "route": "/x/revoke_credential",
         "payload_schema": {}, "authz": {"method": "open"}},
        {"id": "admit", "name": "admit the grant", "route": "/ipex/admit",
         "payload_schema": {}, "authz": {"method": "open"}},
        {"id": "grant", "name": "grant the license", "route": "/ipex/grant",
         "payload_schema": {}, "authz": {"method": "open"}},
    ],
}


def test_no_never_verb_survives_surface_compilation():
    surf = build_micro_app_surface(HOSTILE_TEMPLATE)
    ids = {v.id for v in surf.verbs}
    assert ids == {"grant"}  # rotate/revoke/admit all dropped
    for route in surf.routes():
        assert not is_never_verb(route)


def test_never_verb_utterance_cannot_match():
    surf = build_micro_app_surface(HOSTILE_TEMPLATE)
    for phrase in ["rotate the key", "revoke it", "admit the grant"]:
        r = match(phrase, surf)
        assert r.verb is None or not is_never_verb(r.verb.route)
```

- [ ] **Step 2: Run it to verify it passes** (production code already enforces this)

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_invariants.py -q`
Expected: PASS (2 passed). *(If it FAILS, the exclusion in `surface.build_micro_app_surface` is wrong — fix there, not in the test.)*

- [ ] **Step 3: Write the golden surface test** (`tests/test_golden_surface.py`)

```python
"""Pin the compiled surface for the sample template so accidental drift in the builder
(phrasings, routes, kinds, dropped verbs) is caught."""
from keri_assistant.surface import build_micro_app_surface
from tests.fixtures.sample_template import SAMPLE_TEMPLATE


def test_golden_surface_snapshot():
    surf = build_micro_app_surface(SAMPLE_TEMPLATE)
    snapshot = sorted(
        (v.id, v.route, v.kind, v.schema_said, v.counterparty_role, tuple(sorted(v.phrasings)))
        for v in surf.verbs
    )
    assert snapshot == [
        ("create_application", "/insurance/cmd/create_application", "exchange", None, None,
         ("an", "application", "create", "create_application")),
        ("issued_credentials", "/qry/issued_credentials", "query", None, None,
         ("credentials", "issued", "issued_credentials")),
        ("submit_quote", "/insurance/cmd/submit_quote", "exchange",
         "ESchemaQuote0000000000000000000000000000000", "broker",
         ("quote", "submit", "submit_quote", "the")),
    ]
```

- [ ] **Step 4: Run it; adjust the expected snapshot to the real output once, then re-run to PASS**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest tests/test_golden_surface.py -q`
Expected: PASS. *(The phrasing tuples above are derived from `_phrasings(name, id)` lowercased word-tokens; if tokenization differs, copy the actual `snapshot` value into the assertion once — this is a golden pin, not a behavioral claim.)*

- [ ] **Step 5: Run the whole suite**

Run: `cd packages/keri-assistant && /Users/seriouscoderone/code/locksmith/.claude/worktrees/embedded-assistant/.venv/bin/python -m pytest -q`
Expected: PASS (all tasks' tests green).

- [ ] **Step 6: Commit**

```bash
git add packages/keri-assistant/tests/test_invariants.py packages/keri-assistant/tests/test_golden_surface.py
git commit -m "test(keri-assistant): never-verb end-to-end invariant + golden surface snapshot"
```

---

## Self-Review (author checklist — run against the spec)

**Spec coverage (design §-by-§):**
- §2 architecture / host seams → Task 5 (`Confirmer`/`Dispatcher`/`AuditSink`). ✅ (Locksmith/concierge *impls* are Subsystems B/C, out of scope.)
- §4 action model / inert intent → Tasks 1, 7. ✅
- §4 grounding-constrained (route/schema/AID from grounding) → Tasks 3 (routes), 4 (aid/schema), 7 (wired). ✅
- §4.1 principle 5 (authz as data, never evaluated) → Task 3 (`authz` carried verbatim; test asserts it). ✅
- §7 invariants (never-verbs absent; emit≠execute; proposed-by/authorized-by; confirm gate) → Tasks 2, 8 (never-verbs), 7 + Task 7 tests (confirm gate, audit split). ✅
- §8 uniform confirm ceremony → Task 7 (`confirm` always called before dispatch; test asserts preview shown). ✅
- §5 grounding (Phase-1 direct-lookup, no RAG) → Task 4. ✅ (RAG deferred to Phase 2 — correctly absent.)
- **Deferred, correctly out of scope:** LLM/`AssistantBinding` (Phase 2), voice (Phase 3), multi-party `xip`/edges + `transaction`/`provenance` intent fields (design §6 — deferred; `ResolvedIntent` intentionally omits them for Phase 1; a follow-on plan adds them).

**Placeholder scan:** no TBD/TODO; every code + test step is concrete. The only "adjust once" is the golden snapshot in Task 8 Step 4, which is inherent to golden pinning (explicitly bounded). ✅

**Type consistency:** `ResolvedIntent`, `Verb`, `CommandSurface`, `Grounding`, `Preview`/`DispatchResult`/`AuditEvent`, `MatchResult`, `Outcome` signatures are identical everywhere referenced; `kind` values `{"exchange","query"}` consistent across intent/surface/matcher/harness; audit `outcome` strings consistent between `seams.AuditEvent` doc, harness `_emit` calls, and tests. ✅

## Follow-on (not this plan)

- **Subsystem B — Locksmith wiring:** Qt `Confirmer` dialog + in-process keripy `Dispatcher` (`core/serviceaid_bridge.py` doers) + palette UI + feature flag + `prometheus`/`DoerSignalBridge` instrumentation.
- **Subsystem C — concierge wiring:** CLI `Confirmer` + `hab.exchange` `Dispatcher`.
- **Multi-party extension:** add `transaction` (`xip` id) + `provenance` (ACDC edges) to `ResolvedIntent`; qry/rpy read path; per design §6.
- **Never-verb / IPEX-`admit` reconciliation** (design §9.5) — may change whether `admit` stays in `NEVER_VERB_TOKENS`.
