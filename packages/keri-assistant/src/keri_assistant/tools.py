"""ToolRegistry — the assistant's autonomous action space (design spec 4.2).

Two sources, one registry:

* READ tools come from the micro-app template's `projections[]` (compiled to `kind="query"` verbs).
  Reading framework state is a framework act, so it is declared.
* COMPUTE tools are WORKBENCH tools, registered by the host. Per ugard's 2026-07-29 workbench
  amendment they are the framework's peer, not one of its layers: a workbench tool (a domain
  parser/generator, a validator, an engine) is invoked by the person, gated by nothing, and the
  protocol never witnesses that it ran. The boundary test is "does this need to be provable later,
  to someone who wasn't there?" Declaring such tools in a micro-app template would put workbench
  work inside the membrane — a category error. They are bespoke to the deploying host.

`kind == "exchange"` verbs are deliberately NOT tools. Authority-bearing work can only become a
proposal, never an autonomous call.

Execution goes through `ToolExecutor`, which is deliberately NOT the `Dispatcher` seam: "runs with no
human in the way" and "runs after a human's signature" must not be confusable at the type level.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .role import RoleContext
from .surface import CommandSurface

_NO_ARGS: dict = {"type": "object", "additionalProperties": False, "properties": {}}


@dataclass(frozen=True)
class ToolSpec:
    id: str
    kind: str  # "read" | "compute"
    description: str
    input_schema: dict
    tags: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ToolResult:
    tool_id: str
    ok: bool
    content: str
    detail: str = ""


@runtime_checkable
class ToolExecutor(Protocol):
    def execute(self, tool_id: str, args: dict) -> ToolResult: ...


@dataclass(frozen=True)
class ToolRegistry:
    specs: tuple[ToolSpec, ...]

    def by_id(self, tool_id: str) -> ToolSpec | None:
        for s in self.specs:
            if s.id == tool_id:
                return s
        return None

    def ids(self) -> tuple[str, ...]:
        # sorted so the compiled decide-grammar is byte-stable across runs
        return tuple(sorted(s.id for s in self.specs))

    def filtered_for(self, role: RoleContext) -> ToolRegistry:
        """Narrow WORKBENCH tools to the role's purpose. Reads are never filtered — they are the
        role's own framework state. An UNTAGGED compute tool is treated as general-purpose and
        survives: dropping it would punish authors for not tagging."""
        kept = tuple(
            s for s in self.specs
            if s.kind != "compute" or not s.tags or (s.tags & role.tool_tags)
        )
        return ToolRegistry(specs=kept)


def read_tools_from_surface(surface: CommandSurface) -> tuple[ToolSpec, ...]:
    return tuple(
        # deepcopy: `dict(_NO_ARGS)` is only a shallow copy, so every read tool's `input_schema`
        # and the module constant would share the SAME `properties` dict -- mutating one rewrites
        # all of them process-wide. `actionschema` deep-copies for exactly this reason.
        ToolSpec(id=v.id, kind="read", description=f"read: {v.id}",
                 input_schema=copy.deepcopy(_NO_ARGS))
        for v in surface.verbs
        if v.kind == "query"
    )


def build_tool_registry(
    surface: CommandSurface,
    compute: tuple[ToolSpec, ...] = (),
    *,
    role: RoleContext | None = None,
) -> ToolRegistry:
    specs = read_tools_from_surface(surface) + tuple(compute)
    # `commands[]` and `projections[]` are compiled independently (surface.py) and appended into
    # one tuple with no cross-list id check, so a template that reuses an id across both lists
    # would otherwise slip an exchange verb into the autonomous tool registry -- exactly the
    # authority-bearing-work-becomes-a-tool hole this module's own docstring says cannot happen.
    exchange_ids = {v.id for v in surface.verbs if v.kind == "exchange"}
    seen: set[str] = set()
    for s in specs:
        if s.id in exchange_ids:
            raise ValueError(
                f"tool id {s.id!r} names an exchange verb; an exchange verb cannot be a tool"
            )
        if s.id.startswith("__"):
            # reserved for escape hatches (actionschema.CLARIFY/UNSUPPORTED) -- a template verb or
            # host-registered compute tool cannot claim this namespace.
            raise ValueError(f"tool id {s.id!r} uses the reserved '__' escape-hatch namespace")
        if s.id in seen:
            raise ValueError(f"duplicate tool id: {s.id!r}")
        seen.add(s.id)
    registry = ToolRegistry(specs=specs)
    return registry.filtered_for(role) if role is not None else registry
