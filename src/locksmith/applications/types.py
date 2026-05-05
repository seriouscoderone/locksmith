# -*- encoding: utf-8 -*-
"""
locksmith.applications.types module

Dataclass shapes for the loadable application manifest format. Every
primitive maps to a KERI/ACDC/IPEX concept; nothing here introduces
non-KERI semantics.

The format is deliberately minimal for slice 1 — predicate strings stay
free-text, source/fold expressions stay free-text. Tightening these into
a UEL-style language is a later concern.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class AttributeDef:
    """A single attribute on a credential's `a` block."""
    type: str
    description: str = ""
    enum: list[str] | None = None
    min_items: int | None = None
    min_length: int | None = None
    max_length: int | None = None


@dataclass(frozen=True)
class RegistryDef:
    """A TEL registry the application owns and issues credentials into.

    Anchored in the issuer AID's KEL via a SEAL event when created.
    """
    id: str
    name: str


@dataclass(frozen=True)
class EdgeDef:
    """An edge linking a credential to another credential.

    `target_credential_id` references another CredentialDef in this manifest
    (or in another loaded application).

    `operator` is the per-edge unary operator from the ACDC spec
    (spec-body.md:1099-1108). Governs the chain-of-authority relationship
    between this credential's issuer and the chained credential's issuee.
    Default (None) is `I2I` for targeted ACDCs — issuer of this credential
    must equal the issuee of the chained credential. Edge-group m-ary
    operators (AND, OR, NAND, NOR, AVG, WAVG) are not modeled here yet.

    Revocation propagation is *not* an edge-operator concern — it is
    EGF-dependent (spec-body.md:1112). For revocation-driven reactions,
    use SubscriptionDef + PolicyDef instead.
    """
    target_credential_id: str
    cardinality: Literal["one", "many"] = "one"
    operator: Literal["I2I", "NI2I", "DI2I", "NOT"] | None = None


@dataclass(frozen=True)
class CredentialDef:
    """An ACDC credential type the application issues."""
    id: str
    registry_id: str
    schema_path: str
    """Filesystem path (relative to the plugin package) to the saidified JSON schema."""
    attributes: dict[str, AttributeDef] = field(default_factory=dict)
    edges: dict[str, EdgeDef] = field(default_factory=dict)
    rule: str = ""


@dataclass(frozen=True)
class AuthorizationDef:
    """Who can issue a command.

    `principal` is one of:
      - `"control_of(issuer_aid)"` — must control the application's issuer AID
      - `"holder_of(<credential_id>)"` — must hold a credential of the given type
      - free-text predicate (TBD: tighten into UEL)

    `credential_pattern` declares an inbound credential pattern that must
    be presented alongside the command (None for commands that don't
    require an inbound credential).
    """
    principal: str
    credential_pattern: str | None = None


@dataclass(frozen=True)
class PreconditionsDef:
    """State / temporal preconditions on a command.

    Strings for now — a future linter would parse them into UEL predicates.
    """
    state: list[str] = field(default_factory=list)
    temporal: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CommandDef:
    """A command an actor can issue against this application.

    `produces` lists the EventDef ids the command appends on success.
    `issues` (optional) names a CredentialDef the command mints.
    `grants_to` (optional) names a payload field whose value is the AID
    to IPEX-grant the issued credential to.
    """
    id: str
    payload: dict[str, str]
    authorization: AuthorizationDef
    preconditions: PreconditionsDef = field(default_factory=PreconditionsDef)
    idempotency_key: str | None = None
    produces: list[str] = field(default_factory=list)
    issues: str | None = None
    grants_to: str | None = None


@dataclass(frozen=True)
class CommitsTo:
    """KERI-native cryptographic commitments an event carries."""
    prior_event: bool = True
    command: bool = True
    credential_presentation: bool = False
    credential_issued: str | None = None
    registry_id: str | None = None
    custom: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EventDef:
    """An event appended to a registry by a command."""
    id: str
    commits_to: CommitsTo
    payload_fields: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GateDef:
    """Who can read a projection.

    Set exactly one of: `principal`, `credential_pattern`, `public`.
    """
    principal: str | None = None
    credential_pattern: str | None = None
    public: bool = False


@dataclass(frozen=True)
class ProjectionDef:
    """A read-side view over the application's events.

    `lens` declares the first-person framing used by the wallet's renderer.
    `source` is a free-text fold description; tightening this is future work.
    """
    id: str
    lens: Literal["issuer", "holder", "subscriber", "public"]
    gate: GateDef
    source: str
    shape: list[str] = field(default_factory=list)
    freshness: Literal["eager", "lazy"] = "eager"
    query_input: str | None = None


@dataclass(frozen=True)
class SubscriptionDef:
    """An inbound subscription to events from other applications.

    `schemas` lists the event schema SAIDs this app subscribes to —
    KERI-native: subscriptions are by SAID, not by source app.
    """
    id: str
    schemas: list[str]
    filter: str | None = None
    reaction: str | None = None  # name of a CommandDef to invoke


@dataclass(frozen=True)
class PolicyDef:
    """A within-app reaction to an event."""
    id: str
    trigger_event_id: str
    reaction_command_id: str
    timeout: str | None = None
    compensation_command_id: str | None = None


@dataclass(frozen=True)
class Application:
    """A KERI-native application manifest.

    The issuer AID is *not* part of the manifest — it's resolved at install
    time from the publication source (the AID whose KEL the manifest hangs
    off of). Same manifest can be reissued by different AIDs (e.g., one
    DOI in each US state); each instance is its own running application.
    """
    id: str
    name: str
    description: str
    registries: list[RegistryDef] = field(default_factory=list)
    credentials: list[CredentialDef] = field(default_factory=list)
    commands: list[CommandDef] = field(default_factory=list)
    events: list[EventDef] = field(default_factory=list)
    projections: list[ProjectionDef] = field(default_factory=list)
    subscriptions: list[SubscriptionDef] = field(default_factory=list)
    policies: list[PolicyDef] = field(default_factory=list)

    def credential(self, credential_id: str) -> CredentialDef:
        """Look up a credential definition by id."""
        for c in self.credentials:
            if c.id == credential_id:
                return c
        raise KeyError(f"no credential '{credential_id}' in application '{self.id}'")

    def command(self, command_id: str) -> CommandDef:
        """Look up a command definition by id."""
        for c in self.commands:
            if c.id == command_id:
                return c
        raise KeyError(f"no command '{command_id}' in application '{self.id}'")

    def registry(self, registry_id: str) -> RegistryDef:
        """Look up a registry definition by id."""
        for r in self.registries:
            if r.id == registry_id:
                return r
        raise KeyError(f"no registry '{registry_id}' in application '{self.id}'")
