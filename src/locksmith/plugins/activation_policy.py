# -*- encoding: utf-8 -*-
"""
locksmith.plugins.activation_policy module

**Whether a discovered plugin loads at all** — the ordered veto chain that used
to be a run of ``if`` statements braided through two discovery methods. Design:
``docs/superpowers/specs/2026-07-25-plugin-origin-strategy-design.md``.

Each rule answers one question about a ``Candidate`` and returns either a skip
*reason* or ``None`` to allow. Reasons are the pre-existing strings — they are
the observability contract (``plugin.skipped reason=<reason>``) and the
``PluginState.status`` values that the HOA tests assert on, so they are
preserved verbatim:

``excluded`` · ``incompatible`` · ``files_missing`` · ``hoa_peel`` · ``not_bundled``

Rules that only need a plugin's *identity* run before its module is imported
(defect D1). ``FilesMissing`` needs the filesystem, which is still pre-import.

NOT here: credential gating. That is not a load decision but a *reveal*
decision, already handled by ``RoleActivationStrategy`` at vault-UI time. This
module answers "should this load"; that one answers "what does unlock do".
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from locksmith.plugins.origins import (
    COMPOSED_ENTRY_POINT_GROUP,  # noqa: F401 — re-exported for callers/tests
    Candidate,
    clone_path,
)

#: In-tree plugin ids removed by an HOA peel (``brand().peel_core_pages``).
#: Stays a FRAMEWORK constant on purpose: "the built-in wallet-provider surface
#: is what a peel removes" is a framework statement, not per-brand config — and
#: expressing it by deleting the pyproject entry point broke the default
#: Locksmith build (backlog/2026-07-09-kerifoundation-plugin-brand-leak-and-
#: onboarding-crash.md). Contrast with the composed group, which IS brand config.
HOA_PEELED_PLUGIN_IDS = frozenset({"kerifoundation"})


@runtime_checkable
class ActivationRule(Protocol):
    def veto(self, candidate: Candidate) -> str | None:
        """Return a skip reason, or None to allow this candidate to load."""


class ExcludedByUser:
    """This wallet's per-vault exclude list (Plugins page toggle)."""

    def __init__(self, excluded: set[str]):
        self._excluded = excluded

    def veto(self, candidate: Candidate) -> str | None:
        return "excluded" if candidate.plugin_id in self._excluded else None


class HoaPeeled:
    """An HOA brand removes the built-in wallet-provider plugin.

    The brand is INJECTED, not read from the global here: rules stay pure and
    testable, and the caller (``PluginManager.discover``) resolves ``brand()``
    once — which also keeps ``manager.brand`` as the single monkeypatch point
    the existing HOA tests use.
    """

    def __init__(self, brand_cfg: Any):
        self._brand = brand_cfg

    def veto(self, candidate: Candidate) -> str | None:
        if not candidate.in_tree:
            return None
        if self._brand.peel_core_pages and candidate.plugin_id in HOA_PEELED_PLUGIN_IDS:
            return "hoa_peel"
        return None


class NotBrandComposed:
    """Composed-group plugins load only when the brand lists them.

    Membership comes from the candidate's ORIGIN (the composed entry-point
    group), not from a framework id list — that is the substance of retiring
    ``BUNDLED_ONLY_PLUGIN_IDS``.
    """

    COMPOSED_ORIGIN_ID = "entry-point-composed"

    def __init__(self, brand_cfg: Any):
        self._brand = brand_cfg

    def veto(self, candidate: Candidate) -> str | None:
        if candidate.origin_id != self.COMPOSED_ORIGIN_ID:
            return None
        if candidate.plugin_id not in self._brand.bundled_plugins:
            return "not_bundled"
        return None


class Incompatible:
    """``requires_locksmith`` gate. Stage 1 always passes; tightens later."""

    def veto(self, candidate: Candidate) -> str | None:
        if candidate.record is None:
            return None
        return None if self._compat_ok(candidate.record) else "incompatible"

    @staticmethod
    def _compat_ok(record: dict[str, Any]) -> bool:
        return True


class FilesMissing:
    """An index-recorded clone whose files are gone from disk."""

    def veto(self, candidate: Candidate) -> str | None:
        if candidate.record is None:
            return None
        return None if clone_path(candidate.plugin_id).exists() else "files_missing"


def default_rules(excluded: set[str],
                  brand_cfg: Any) -> tuple[ActivationRule, ...]:
    """The chain, in evaluation order.

    Order matters for which reason a doubly-vetoed candidate reports; it matches
    the pre-change code: the exclude list was consulted before compatibility and
    files-present, and the peel before brand composition.
    """
    return (
        ExcludedByUser(excluded),
        HoaPeeled(brand_cfg),
        NotBrandComposed(brand_cfg),
        Incompatible(),
        FilesMissing(),
    )


def first_veto(candidate: Candidate,
               rules: tuple[ActivationRule, ...]) -> str | None:
    for rule in rules:
        reason = rule.veto(candidate)
        if reason is not None:
            return reason
    return None
