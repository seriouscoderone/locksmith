"""Cross-reference reverse index for micro-app template documents.

This module is the reverse direction of ``locksmith.micro_app_template.xref``
(which validates forward references). Given a parsed template document,
:func:`compute_crossrefs` walks every consumer relationship in the canonical
meta-schema and builds an inverted index: for each referenced primitive,
which consumers reference it?

Keys use the ``"<kind>:<id>"`` format, e.g. ``"rule:solvency"``,
``"export:license"``, ``"workflow:revoke_wf"``. The resulting
:class:`CrossRefIndex` is consumed by the "Used by" chip strips in every
primitive editor view.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CrossRef:
    """A single consumer of a referenced primitive."""
    surface: str           # "commands" | "exports" | "imports" | "workflows" | …
    primitive_label: str   # human-readable name of the consumer
    primitive_path: str    # JSON pointer to the consumer entry (e.g. "/commands/2")


@dataclass(frozen=True)
class CrossRefIndex:
    """Immutable reverse index: referenced key → tuple of consumers."""
    _consumers: dict[str, tuple[CrossRef, ...]]

    def consumers_of(self, key: str) -> tuple[CrossRef, ...]:
        return self._consumers.get(key, ())

    def all_keys(self) -> tuple[str, ...]:
        return tuple(self._consumers.keys())


def _entry_label(entry: dict, fallback: str) -> str:
    return (entry.get("display_name") or entry.get("name")
            or entry.get("title") or entry.get("id") or fallback)


def _walk_emissions(
    emissions: list[dict],
    surface: str,
    label: str,
    path: str,
    out: defaultdict[str, list[CrossRef]],
) -> None:
    """Walk an emissions list (shared between commands and reactions)."""
    for j, emission in enumerate(emissions):
        kind = emission.get("kind")
        if kind == "exchange":
            exch = emission.get("exchange") or {}
            imported_id = exch.get("imported_credential_id")
            exported_id = exch.get("exported_credential_id")
            schema_said = exch.get("schema_said_referenced")
            if imported_id:
                out[f"import:{imported_id}"].append(CrossRef(surface, label, path))
            if exported_id:
                out[f"export:{exported_id}"].append(CrossRef(surface, label, path))
            if schema_said:
                out[f"schema:{schema_said}"].append(CrossRef(surface, label, path))
        elif kind == "lifecycle_advance":
            exported_id = emission.get("exported_credential_id")
            if exported_id:
                out[f"export:{exported_id}"].append(CrossRef(surface, label, path))
        elif kind == "aggregate_event":
            aggregate_id = emission.get("aggregate_id")
            if aggregate_id:
                out[f"aggregate:{aggregate_id}"].append(CrossRef(surface, label, path))


def compute_crossrefs(doc: dict[str, Any]) -> CrossRefIndex:
    """Walk the canonical meta-schema reference graph in reverse.

    For each forward reference (command → rule_ref, export → workflow, etc.)
    record the consumer as a :class:`CrossRef` tagged with surface and JSON
    pointer. Returns a :class:`CrossRefIndex` mapping referenced keys to the
    consumers that reference them.
    """
    out: defaultdict[str, list[CrossRef]] = defaultdict(list)

    # ------------------------------------------------------------------ #
    # Commands                                                             #
    # ------------------------------------------------------------------ #
    for i, command in enumerate(doc.get("commands") or []):
        surface = "commands"
        path = f"/commands/{i}"
        label = _entry_label(command, f"commands[{i}]")

        # auth/state/temporal preconditions
        for precond_key in ("auth_preconditions", "state_preconditions", "temporal_preconditions"):
            for precond in command.get(precond_key) or []:
                rule_ref = precond.get("rule_ref")
                if rule_ref:
                    out[f"rule:{rule_ref}"].append(CrossRef(surface, label, path))

        # emissions
        _walk_emissions(command.get("emissions") or [], surface, label, path, out)

    # ------------------------------------------------------------------ #
    # Exports (credentials.exports)                                        #
    # ------------------------------------------------------------------ #
    exports = (doc.get("credentials") or {}).get("exports") or []
    for i, export in enumerate(exports):
        surface = "exports"
        path = f"/credentials/exports/{i}"
        label = _entry_label(export, f"exports[{i}]")

        # envelope.edges[].credential_id → both export:<id> and import:<id>
        envelope = export.get("envelope") or {}
        for edge in envelope.get("edges") or []:
            cred_id = edge.get("credential_id")
            if cred_id:
                out[f"export:{cred_id}"].append(CrossRef(surface, label, path))
                out[f"import:{cred_id}"].append(CrossRef(surface, label, path))

        # lifecycle transitions
        lifecycle = export.get("lifecycle") or {}
        for k, transition in enumerate(lifecycle.get("transitions") or []):
            via_workflow = transition.get("via_workflow")
            if via_workflow:
                out[f"workflow:{via_workflow}"].append(CrossRef(surface, label, path))

            condition_rule_ref = transition.get("condition_rule_ref")
            if condition_rule_ref:
                out[f"rule:{condition_rule_ref}"].append(CrossRef(surface, label, path))

            for req in transition.get("requires") or []:
                rule_ref = req.get("rule_ref")
                if rule_ref:
                    out[f"rule:{rule_ref}"].append(CrossRef(surface, label, path))

        # rule_refs[]
        for rule_id in export.get("rule_refs") or []:
            if rule_id:
                out[f"rule:{rule_id}"].append(CrossRef(surface, label, path))

        # value_flow.implied_credentials[].credential_id → both
        value_flow = export.get("value_flow") or {}
        for implied in value_flow.get("implied_credentials") or []:
            cred_id = implied.get("credential_id")
            if cred_id:
                out[f"export:{cred_id}"].append(CrossRef(surface, label, path))
                out[f"import:{cred_id}"].append(CrossRef(surface, label, path))

    # ------------------------------------------------------------------ #
    # Workflows                                                            #
    # ------------------------------------------------------------------ #
    for i, workflow in enumerate(doc.get("workflows") or []):
        surface = "workflows"
        path = f"/workflows/{i}"
        label = _entry_label(workflow, f"workflows[{i}]")

        # trigger
        trigger = workflow.get("trigger") or {}
        trigger_cred_id = trigger.get("credential_id")
        if trigger_cred_id:
            out[f"export:{trigger_cred_id}"].append(CrossRef(surface, label, path))
        trigger_import_id = trigger.get("imported_credential_id")
        if trigger_import_id:
            out[f"import:{trigger_import_id}"].append(CrossRef(surface, label, path))

        # steps
        for step in workflow.get("steps") or []:
            command_id = step.get("command_id")
            if command_id:
                out[f"command:{command_id}"].append(CrossRef(surface, label, path))

            reaction_id = step.get("reaction_id")
            if reaction_id:
                out[f"reaction:{reaction_id}"].append(CrossRef(surface, label, path))

            advance_lifecycle = step.get("advance_lifecycle")
            if advance_lifecycle:
                cred_id = advance_lifecycle.get("credential_id")
                if cred_id:
                    out[f"export:{cred_id}"].append(CrossRef(surface, label, path))

            for expected in step.get("expected_inbound") or []:
                import_id = expected.get("imported_credential_id")
                if import_id:
                    out[f"import:{import_id}"].append(CrossRef(surface, label, path))

            for branch in step.get("branches") or []:
                rule_ref = branch.get("rule_ref")
                if rule_ref:
                    out[f"rule:{rule_ref}"].append(CrossRef(surface, label, path))

    # ------------------------------------------------------------------ #
    # Reactions                                                            #
    # ------------------------------------------------------------------ #
    for i, reaction in enumerate(doc.get("reactions") or []):
        surface = "reactions"
        path = f"/reactions/{i}"
        label = _entry_label(reaction, f"reactions[{i}]")

        trigger = reaction.get("trigger") or {}
        import_id = trigger.get("imported_credential_id")
        if import_id:
            out[f"import:{import_id}"].append(CrossRef(surface, label, path))
        export_id = trigger.get("exported_credential_id")
        if export_id:
            out[f"export:{export_id}"].append(CrossRef(surface, label, path))

        _walk_emissions(reaction.get("emissions") or [], surface, label, path, out)

    # ------------------------------------------------------------------ #
    # Aggregates                                                           #
    # ------------------------------------------------------------------ #
    for i, aggregate in enumerate(doc.get("aggregates") or []):
        surface = "aggregates"
        path = f"/aggregates/{i}"
        label = _entry_label(aggregate, f"aggregates[{i}]")

        for invariant in aggregate.get("invariants") or []:
            rule_ref = invariant.get("rule_ref")
            if rule_ref:
                out[f"rule:{rule_ref}"].append(CrossRef(surface, label, path))

    # ------------------------------------------------------------------ #
    # Projections                                                          #
    # ------------------------------------------------------------------ #
    for i, projection in enumerate(doc.get("projections") or []):
        surface = "projections"
        path = f"/projections/{i}"
        label = _entry_label(projection, f"projections[{i}]")

        access = projection.get("access") or {}
        row_filter = access.get("row_filter_rule_ref")
        if row_filter:
            out[f"rule:{row_filter}"].append(CrossRef(surface, label, path))

    # ------------------------------------------------------------------ #
    # Rules (binding_link type only)                                       #
    # ------------------------------------------------------------------ #
    for i, rule in enumerate(doc.get("rules") or []):
        if rule.get("type") == "binding_link":
            surface = "rules"
            path = f"/rules/{i}"
            label = _entry_label(rule, f"rules[{i}]")

            for link in rule.get("links") or []:
                rule_id = link.get("rule_id")
                if rule_id:
                    out[f"rule:{rule_id}"].append(CrossRef(surface, label, path))

    # Convert lists to tuples for the immutable index
    frozen: dict[str, tuple[CrossRef, ...]] = {
        key: tuple(refs) for key, refs in out.items()
    }
    return CrossRefIndex(_consumers=frozen)
