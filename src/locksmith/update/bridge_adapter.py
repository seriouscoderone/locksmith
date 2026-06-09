"""Bridge adapter — sits between ``UpdateController`` and the
platform-specific Sparkle/WinSparkle bridges, plus the appcast feed.

The controller asks: "what's the latest release for the platform I'm
running on?" The adapter answers by fetching the appcast JSON from
releases.keri.host, parsing it, and selecting the most recent stable
release for the current OS. (Sparkle and WinSparkle BOTH also fetch
the appcast for their own download mechanics; the adapter's fetch is
the separate path the controller uses to drive the *decision*
machinery — choose-to-install, defer, "what's new", critical-banner.)

The adapter is intentionally OS-agnostic; only the appcast URL +
platform string differ. The actual install hand-off goes through
sparkle_init / winsparkle_init at bootstrap time, not here.
"""
from __future__ import annotations

import logging
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

from keri import help

from locksmith.update.appcast import (
    Release,
    parse_appcast,
    select_latest_for_platform,
)

logger = help.ogler.getLogger(__name__)


DEFAULT_APPCAST_BASE = "https://releases.keri.host/appcast/v1"
_FETCH_TIMEOUT_SEC = 15


def current_platform() -> str:
    """Map ``sys.platform`` to the values the appcast schema uses."""
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    return sys.platform  # linux, etc. — not yet supported but visible


def default_appcast_url(platform: str | None = None) -> str:
    """``releases.keri.host/appcast/v1/{macos,windows}.json``."""
    platform = platform or current_platform()
    return f"{DEFAULT_APPCAST_BASE}/{platform}.json"


@dataclass
class BridgeAdapter:
    """Glue between the controller and the appcast feed.

    Args:
        appcast_url: HTTPS URL of the appcast JSON. Defaults to the
            keri.host CDN feed for the current platform.
        platform: One of ``"macos"`` / ``"windows"``. Defaults to the
            running OS.
        fetcher: Optional injection point for HTTP fetch — tests pass
            a function that returns bytes; production uses urllib.
    """

    appcast_url: str | None = None
    platform: str | None = None
    fetcher: object | None = None  # callable(url: str) -> bytes

    def __post_init__(self) -> None:
        if self.platform is None:
            self.platform = current_platform()
        if self.appcast_url is None:
            self.appcast_url = default_appcast_url(self.platform)

    def fetch_latest_release(self) -> Release | None:
        """Fetch + parse the appcast, return the newest release for the
        current platform. Returns ``None`` on any fetch/parse error so
        the controller can log + skip rather than crash."""
        try:
            raw = self._fetch(self.appcast_url)
        except (urllib.error.URLError, OSError, TimeoutError) as ex:
            logger.warning(
                "[update] bridge.fetch_failed url=%s reason=%s",
                self.appcast_url, ex,
            )
            return None

        try:
            ac = parse_appcast(raw)
        except Exception as ex:  # noqa: BLE001 — parse failures are intentionally swallowed at this layer
            logger.warning(
                "[update] bridge.parse_failed url=%s reason=%s",
                self.appcast_url, ex,
            )
            return None

        try:
            return select_latest_for_platform(ac, self.platform)
        except Exception as ex:  # noqa: BLE001 — no release for platform is non-fatal
            logger.info(
                "[update] bridge.no_release_for_platform platform=%s reason=%s",
                self.platform, ex,
            )
            return None

    # --- internals --------------------------------------------------------

    def _fetch(self, url: str) -> bytes:
        if self.fetcher is not None:
            return self.fetcher(url)
        with urllib.request.urlopen(url, timeout=_FETCH_TIMEOUT_SEC) as resp:
            return resp.read()
