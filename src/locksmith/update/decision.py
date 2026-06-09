"""Pure-function decision tree for update UX (spec §8.2).

Given the current installed version and a candidate ``Release`` from the
appcast, returns one of:

  - ``NO_UPDATE``                — candidate is not newer
  - ``SILENT_INSTALL``           — minor/patch; install on quit, no UI
  - ``SHOW_WHATS_NEW_MODAL``     — major version; show modal first
  - ``SHOW_CRITICAL_BANNER``     — flagged critical; orange banner overrides

Precedence: critical > major > minor/patch. This module is the single
authoritative place that maps appcast flags to UI action; controller,
scheduler, and bridges all defer to it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from keri import help

logger = help.ogler.getLogger(__name__)


class UpdateAction(Enum):
    NO_UPDATE = "no_update"
    SILENT_INSTALL = "silent_install"
    SHOW_WHATS_NEW_MODAL = "show_whats_new_modal"
    SHOW_CRITICAL_BANNER = "show_critical_banner"


@dataclass(frozen=True)
class Release:
    """Decision-tree projection of an appcast release.

    Mirrors the subset of ``locksmith.update.appcast.Release`` fields that
    Phase 5's UI consumes. Defined here (and not re-exported from appcast)
    so the decision module can be imported on platforms where the appcast
    network/parse layer isn't desired (e.g. ctypes-only Windows callbacks).
    """
    version: str
    platform: str
    artifact_url: str
    artifact_sha256: str
    artifact_size: int
    anchor_url: str
    anchor_said: str
    is_major: bool
    is_critical: bool
    release_notes_url: str
    released_at: str
    minimum_system_version: str


@dataclass(frozen=True)
class UpdateDecision:
    action: UpdateAction
    release: Release | None = None

    @classmethod
    def evaluate(
        cls,
        *,
        current_version: str,
        release: Release,
    ) -> "UpdateDecision":
        """Spec §8.2 decision tree.

        Critical > Major > Minor/Patch. ``release`` is returned attached to
        the decision so the caller can pass it straight to the appropriate
        UI surface without re-fetching.
        """
        if _compare(release.version, current_version) <= 0:
            logger.info(
                "[update] decision=no_update current=%s candidate=%s",
                current_version, release.version,
            )
            return cls(action=UpdateAction.NO_UPDATE, release=None)

        if release.is_critical:
            logger.info(
                "[update] decision=show_critical_banner candidate=%s",
                release.version,
            )
            return cls(
                action=UpdateAction.SHOW_CRITICAL_BANNER,
                release=release,
            )

        if release.is_major:
            logger.info(
                "[update] decision=show_whats_new candidate=%s",
                release.version,
            )
            return cls(
                action=UpdateAction.SHOW_WHATS_NEW_MODAL,
                release=release,
            )

        logger.info(
            "[update] decision=silent_install candidate=%s",
            release.version,
        )
        return cls(action=UpdateAction.SILENT_INSTALL, release=release)


def _compare(a: str, b: str) -> int:
    """Return -1/0/1 like cmp() for two semver strings (X.Y.Z, no pre-release)."""
    pa = tuple(int(x) for x in a.split("."))
    pb = tuple(int(x) for x in b.split("."))
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0
