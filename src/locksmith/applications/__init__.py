# -*- encoding: utf-8 -*-
"""
locksmith.applications package

Shared types for declaring KERI-native application manifests. An Application
manifest is the loadable, content-addressable description of one thin slice
of a KERI-native enterprise app: its credentials, commands, events,
projections, and policies. Plugins consume these manifests to render
first-person UI.

The format is intentionally minimal — additive primitives that map to
ACDC/IPEX/TEL semantics, no Cedar/OPA/policy-engine coupling.
"""
from locksmith.applications.types import (
    Application,
    RegistryDef,
    CredentialDef,
    AttributeDef,
    EdgeDef,
    CommandDef,
    AuthorizationDef,
    PreconditionsDef,
    EventDef,
    CommitsTo,
    ProjectionDef,
    GateDef,
    SubscriptionDef,
    PolicyDef,
)

__all__ = [
    "Application",
    "RegistryDef",
    "CredentialDef",
    "AttributeDef",
    "EdgeDef",
    "CommandDef",
    "AuthorizationDef",
    "PreconditionsDef",
    "EventDef",
    "CommitsTo",
    "ProjectionDef",
    "GateDef",
    "SubscriptionDef",
    "PolicyDef",
]
