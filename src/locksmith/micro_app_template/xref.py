"""Cross-reference validation for micro-app templates.

JSON-Schema validates structural shape. This module validates the
references *within* the document: rule_refs resolve to declared rule
ids, credential_held_id references resolve to entries in
credentials.held, lifecycle transition workflow references resolve to
declared workflows, etc.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class XrefError:
    """A cross-reference that does not resolve."""
    path: str
    reference: str
    target_type: str

    @property
    def message(self) -> str:
        return f"{self.path}: {self.target_type} {self.reference!r} not found"


def _collect_rule_ids(doc: dict[str, Any]) -> set[str]:
    return {r["id"] for r in doc.get("rules", []) if "id" in r}


def _collect_credential_ids(doc: dict[str, Any]) -> tuple[set[str], set[str]]:
    creds = doc.get("credentials", {})
    held = {c["id"] for c in creds.get("held", []) if "id" in c}
    issued = {c["id"] for c in creds.get("issued", []) if "id" in c}
    return held, issued


def _collect_workflow_ids(doc: dict[str, Any]) -> set[str]:
    return {w["id"] for w in doc.get("workflows", []) if "id" in w}


def _collect_command_ids(doc: dict[str, Any]) -> set[str]:
    return {c["id"] for c in doc.get("commands", []) if "id" in c}


def _collect_reaction_ids(doc: dict[str, Any]) -> set[str]:
    return {r["id"] for r in doc.get("reactions", []) if "id" in r}


def _collect_aggregate_ids(doc: dict[str, Any]) -> set[str]:
    return {a["id"] for a in doc.get("aggregates", []) if "id" in a}


def validate_xrefs(doc: dict[str, Any]) -> list[XrefError]:
    """Return a list of unresolved cross-references found in doc."""
    errors: list[XrefError] = []
    rule_ids = _collect_rule_ids(doc)
    held_ids, issued_ids = _collect_credential_ids(doc)
    workflow_ids = _collect_workflow_ids(doc)
    command_ids = _collect_command_ids(doc)
    reaction_ids = _collect_reaction_ids(doc)
    aggregate_ids = _collect_aggregate_ids(doc)

    # credentials.issued[].rule_refs
    for i, c in enumerate(doc.get("credentials", {}).get("issued", [])):
        for j, ref in enumerate(c.get("rule_refs", [])):
            if ref not in rule_ids:
                errors.append(XrefError(
                    path=f"credentials.issued[{i}].rule_refs[{j}]",
                    reference=ref, target_type="rule",
                ))
        # lifecycle transitions
        for k, t in enumerate(c.get("lifecycle", {}).get("transitions", [])):
            wf = t.get("via_workflow")
            if wf is not None and wf not in workflow_ids:
                errors.append(XrefError(
                    path=f"credentials.issued[{i}].lifecycle.transitions[{k}].via_workflow",
                    reference=wf, target_type="workflow",
                ))
            cond = t.get("condition_rule_ref")
            if cond is not None and cond not in rule_ids:
                errors.append(XrefError(
                    path=f"credentials.issued[{i}].lifecycle.transitions[{k}].condition_rule_ref",
                    reference=cond, target_type="rule",
                ))
            for m, req in enumerate(t.get("requires", []) or []):
                rr = req.get("rule_ref") if isinstance(req, dict) else None
                if rr is not None and rr not in rule_ids:
                    errors.append(XrefError(
                        path=f"credentials.issued[{i}].lifecycle.transitions[{k}].requires[{m}].rule_ref",
                        reference=rr, target_type="rule",
                    ))

    # commands[].*_preconditions
    for i, cmd in enumerate(doc.get("commands", [])):
        for kind in ("auth_preconditions", "state_preconditions", "temporal_preconditions"):
            for j, pre in enumerate(cmd.get(kind, []) or []):
                rr = pre.get("rule_ref") if isinstance(pre, dict) else None
                if rr is not None and rr not in rule_ids:
                    errors.append(XrefError(
                        path=f"commands[{i}].{kind}[{j}].rule_ref",
                        reference=rr, target_type="rule",
                    ))
        # commands[].emissions: lifecycle_advance.credential_issued_id and aggregate_event.aggregate_id
        for j, em in enumerate(cmd.get("emissions", []) or []):
            if not isinstance(em, dict):
                continue
            kind = em.get("kind")
            if kind == "lifecycle_advance":
                cid = em.get("credential_issued_id")
                if cid is not None and cid not in issued_ids:
                    errors.append(XrefError(
                        path=f"commands[{i}].emissions[{j}].credential_issued_id",
                        reference=cid, target_type="credentials.issued",
                    ))
            elif kind == "aggregate_event":
                aid = em.get("aggregate_id")
                if aid is not None and aid not in aggregate_ids:
                    errors.append(XrefError(
                        path=f"commands[{i}].emissions[{j}].aggregate_id",
                        reference=aid, target_type="aggregate",
                    ))

    # reactions[].trigger / reactions[].emissions
    for i, rx in enumerate(doc.get("reactions", [])):
        trig = rx.get("trigger") or {}
        if isinstance(trig, dict):
            ttype = trig.get("type")
            if ttype == "credential_received":
                hid = trig.get("credential_held_id")
                if hid is not None and hid not in held_ids:
                    errors.append(XrefError(
                        path=f"reactions[{i}].trigger.credential_held_id",
                        reference=hid, target_type="credentials.held",
                    ))
            elif ttype == "lifecycle_event":
                cid = trig.get("credential_issued_id")
                if cid is not None and cid not in issued_ids:
                    errors.append(XrefError(
                        path=f"reactions[{i}].trigger.credential_issued_id",
                        reference=cid, target_type="credentials.issued",
                    ))
        for j, em in enumerate(rx.get("emissions", []) or []):
            if not isinstance(em, dict):
                continue
            kind = em.get("kind")
            if kind == "lifecycle_advance":
                cid = em.get("credential_issued_id")
                if cid is not None and cid not in issued_ids:
                    errors.append(XrefError(
                        path=f"reactions[{i}].emissions[{j}].credential_issued_id",
                        reference=cid, target_type="credentials.issued",
                    ))
            elif kind == "aggregate_event":
                aid = em.get("aggregate_id")
                if aid is not None and aid not in aggregate_ids:
                    errors.append(XrefError(
                        path=f"reactions[{i}].emissions[{j}].aggregate_id",
                        reference=aid, target_type="aggregate",
                    ))

    # aggregates[].invariants
    for i, agg in enumerate(doc.get("aggregates", [])):
        for j, inv in enumerate(agg.get("invariants", []) or []):
            rr = inv.get("rule_ref") if isinstance(inv, dict) else None
            if rr is not None and rr not in rule_ids:
                errors.append(XrefError(
                    path=f"aggregates[{i}].invariants[{j}].rule_ref",
                    reference=rr, target_type="rule",
                ))

    # workflows[].steps[].command_id / reaction_id / branches[].rule_ref
    for i, wf in enumerate(doc.get("workflows", [])):
        for j, step in enumerate(wf.get("steps", []) or []):
            cid = step.get("command_id")
            if cid is not None and cid not in command_ids:
                errors.append(XrefError(
                    path=f"workflows[{i}].steps[{j}].command_id",
                    reference=cid, target_type="command",
                ))
            rid = step.get("reaction_id")
            if rid is not None and rid not in reaction_ids:
                errors.append(XrefError(
                    path=f"workflows[{i}].steps[{j}].reaction_id",
                    reference=rid, target_type="reaction",
                ))
            for k, br in enumerate(step.get("branches", []) or []):
                rr = br.get("rule_ref") if isinstance(br, dict) else None
                if rr is not None and rr not in rule_ids:
                    errors.append(XrefError(
                        path=f"workflows[{i}].steps[{j}].branches[{k}].rule_ref",
                        reference=rr, target_type="rule",
                    ))
            # expected_inbound[].credential_held_id
            for k, ei in enumerate(step.get("expected_inbound", []) or []):
                hid = ei.get("credential_held_id") if isinstance(ei, dict) else None
                if hid is not None and hid not in held_ids:
                    errors.append(XrefError(
                        path=f"workflows[{i}].steps[{j}].expected_inbound[{k}].credential_held_id",
                        reference=hid, target_type="credentials.held",
                    ))

    # projections[].access.row_filter_rule_ref
    for i, p in enumerate(doc.get("projections", [])):
        rr = p.get("access", {}).get("row_filter_rule_ref")
        if rr is not None and rr not in rule_ids:
            errors.append(XrefError(
                path=f"projections[{i}].access.row_filter_rule_ref",
                reference=rr, target_type="rule",
            ))

    # rules[].links (binding_link references)
    for i, r in enumerate(doc.get("rules", [])):
        for j, link in enumerate(r.get("links", []) or []):
            tid = link.get("rule_id") if isinstance(link, dict) else None
            if tid is not None and tid not in rule_ids:
                errors.append(XrefError(
                    path=f"rules[{i}].links[{j}].rule_id",
                    reference=tid, target_type="rule",
                ))

    return errors
