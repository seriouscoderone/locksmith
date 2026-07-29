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
