"""Parse a backend's raw structured output back into an inert ResolvedIntent.

Trust nothing in `raw` except the fields the schema constrained: `route` and `kind` come from the
matched Verb, never from the model, and `schema_said` is the verb's pinned value. The grounding
check is re-run as belt-and-braces: under a HARD binding it can never fail, so a failure means the
binding did not actually enforce the grammar -> refuse loudly rather than proceed.
"""
from __future__ import annotations

from dataclasses import dataclass

from .actionschema import CLARIFY, UNSUPPORTED, grounded_set_for, verb_alternative
from .grounding import Grounding, check_grounded
from .intent import ResolvedIntent
from .surface import CommandSurface


class GrammarViolation(RuntimeError):
    """The backend emitted something the proposal schema forbade."""


def _check_payload_grounded(payload: dict, grounding: Grounding) -> str | None:
    """Belt-and-braces for entity-naming payload fields (`*_aid` / `*_said`), at ANY depth.

    `actionschema` already enum-constrains these, so under a HARD binding this cannot fail —
    a failure means the binding did not really enforce the grammar. Reuses `grounded_set_for`
    so the constraint and this check can never drift apart.

    MUST RECURSE. Amended 2026-07-30 after an adversarial review: the original version iterated
    only `payload.items()`, which mirrored a matching depth-1 blind spot in the compiler. The
    compiler now grounds entity fields nested under `properties`/`items` at any depth
    (commits ccea1be6 + 83450b24), and a real template — actuary `ingest_rate_workbook`, whose
    `shards[].shard_said` the template itself calls "the commitment" — exercises that path. A
    top-level-only check here would leave the *second* layer of defence holed exactly where the
    first one was, so a nested hallucinated identifier would pass BOTH.
    """
    def walk(node: object, path: str) -> str | None:
        if isinstance(node, dict):
            for key, value in node.items():
                allowed = grounded_set_for(key, grounding)
                where = f"{path}.{key}" if path else key
                if allowed is not None:
                    if not isinstance(value, str) or value not in allowed:
                        return f"payload field {where!r} holds ungrounded value {value!r}"
                    continue  # a grounded scalar needs no further descent
                reason = walk(value, where)
                if reason is not None:
                    return reason
        elif isinstance(node, list):
            for index, item in enumerate(node):
                reason = walk(item, f"{path}[{index}]")
                if reason is not None:
                    return reason
        return None

    return walk(payload, "")


@dataclass(frozen=True)
class Proposal:
    status: str  # "intent" | "clarify" | "unsupported"
    intent: ResolvedIntent | None = None
    message: str = ""


def parse_proposal(raw: dict, surface: CommandSurface, grounding: Grounding) -> Proposal:
    verb_id = raw.get("verb_id")
    if not isinstance(verb_id, str) or not verb_id:
        raise GrammarViolation(f"proposal has no verb_id: {raw!r}")

    # Escape hatches are checked BEFORE the surface lookup, and this order is load-bearing: the
    # `__`-prefix guard lives in `build_proposal_schema`, not in `build_micro_app_surface`, so a
    # template that declares a command literally named `__clarify__`/`__unsupported__` still
    # produces a real Verb that `surface.by_id(...)` will happily return. The compiled grammar
    # only ever offers the hatch *shape* for that const, so if the surface lookup ran first, a
    # template-declared hatch-named command could be parsed as a dispatchable exchange the
    # grammar never authorized — a confused deputy. Checking the hatch consts first means the
    # hatch always wins, regardless of what a template tries to smuggle into the surface.
    if verb_id == CLARIFY:
        question = raw.get("question", "")
        # `minLength: 1` on the hatch's compiled schema is layer-1 only; re-check here too, or a
        # non-HARD/lying backend can hand back a clarify with nothing to clarify -- an empty out
        # is not a truthful out.
        if not isinstance(question, str) or not question:
            raise GrammarViolation(f"clarify hatch has an empty/missing question: {raw!r}")
        return Proposal(status="clarify", message=question)
    if verb_id == UNSUPPORTED:
        reason = raw.get("reason", "")
        if not isinstance(reason, str) or not reason:
            raise GrammarViolation(f"unsupported hatch has an empty/missing reason: {raw!r}")
        return Proposal(status="unsupported", message=reason)

    verb = surface.by_id(verb_id)
    if verb is None:
        raise GrammarViolation(f"proposal names an unknown verb: {verb_id!r}")
    if verb.kind != "exchange":
        raise GrammarViolation(f"verb {verb_id!r} is not proposable (kind={verb.kind!r})")

    # Belt-and-braces for layer 1's OWN decisions: `verb_alternative` is the exact function that
    # decided whether this verb is even reachable under `grounding`, and which top-level fields
    # it required if so. Re-deriving it here (rather than duplicating that logic) means a future
    # compiler hardening can never silently leave this layer behind — both read one decision. A
    # `None` branch means the compiled grammar never actually offered this verb (e.g. no grounded
    # receiver), so a proposal naming it means the grammar was not enforced. A branch missing one
    # of its required top-level fields (e.g. a bare `{"verb_id": ...}`) is the same failure: the
    # backend emitted something the grammar could not have produced.
    branch = verb_alternative(verb, grounding)
    if branch is None:
        raise GrammarViolation(
            f"verb {verb_id!r} was omitted from the compiled schema — grammar was not enforced"
        )
    for name in branch["required"]:
        if name not in raw:
            raise GrammarViolation(f"proposal omits required field {name!r} for {verb_id!r}")

    payload = raw.get("payload", {})
    if not isinstance(payload, dict):
        raise GrammarViolation(f"payload must be an object, got {type(payload).__name__}")

    receiver_aid = raw.get("receiver_aid") if verb.counterparty_role is not None else None

    intent = ResolvedIntent(
        route=verb.route,          # from the verb — never from raw
        verb_id=verb.id,
        kind=verb.kind,
        payload=payload,
        receiver_aid=receiver_aid,
        schema_said=verb.schema_said,   # pinned by the verb, not chosen by the model
    )

    reason = check_grounded(intent, grounding) or _check_payload_grounded(payload, grounding)
    if reason is not None:
        raise GrammarViolation(f"proposal is not grounded ({reason}) — grammar was not enforced")

    return Proposal(status="intent", intent=intent)
