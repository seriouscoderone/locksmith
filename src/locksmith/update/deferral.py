"""Sliding-window deferral logic per spec §8.3.

- "Remind Me Tomorrow" reschedules the prompt by 24h.
- After 7 days from the first deferral on a given candidate version, the
  prompt becomes mandatory and dismiss-to-defer is disabled.
- A new candidate version (e.g., 1.4.0 supersedes 1.3.0 mid-chain) resets
  the deferral chain.

This module is pure-functional: callers pass current QSettings values +
the candidate version + ``now`` and read back booleans / a new state
record to persist.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


_DEFERRAL_WINDOW = timedelta(hours=24)
_MAX_DEFERRAL = timedelta(days=7)


def _parse(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts) if ts else None


@dataclass(frozen=True)
class DeferralState:
    """New state to persist after the user clicks 'Remind Me Tomorrow'."""
    first_deferred_at: str
    last_deferred_at: str
    deferred_version: str


@dataclass
class Deferral:
    """Read-only evaluation of "should we re-prompt now?".

    Construct from current QSettings values + candidate version + now;
    call ``is_due_again()`` / ``is_mandatory()``.
    """
    first_deferred_at: str | None
    last_deferred_at: str | None
    deferred_version: str | None
    candidate_version: str
    now: datetime

    def _chain_applies(self) -> bool:
        return (
            self.deferred_version is not None
            and self.deferred_version == self.candidate_version
        )

    def is_due_again(self) -> bool:
        """True if the user should see the prompt again right now."""
        if not self._chain_applies():
            # Fresh candidate — show immediately
            return True
        last = _parse(self.last_deferred_at)
        if last is None:
            return True
        return self.now - last >= _DEFERRAL_WINDOW

    def is_mandatory(self) -> bool:
        """True if 7-day cap reached on this candidate — no more deferring."""
        if not self._chain_applies():
            return False
        first = _parse(self.first_deferred_at)
        if first is None:
            return False
        return self.now - first >= _MAX_DEFERRAL

    @staticmethod
    def record_deferral(
        *,
        first_deferred_at: str | None,
        deferred_version: str | None,
        candidate_version: str,
        now: datetime,
    ) -> DeferralState:
        """Return the new state after the user clicks 'Remind Me Tomorrow'."""
        same_chain = (
            deferred_version is not None
            and deferred_version == candidate_version
            and first_deferred_at is not None
        )
        first = first_deferred_at if same_chain else now.isoformat()
        return DeferralState(
            first_deferred_at=first,
            last_deferred_at=now.isoformat(),
            deferred_version=candidate_version,
        )
