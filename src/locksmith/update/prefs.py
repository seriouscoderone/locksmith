"""QSettings-backed user preferences for the update system.

All keys live under the ``Updates/`` group so they're co-located with
future settings groups (the Settings -> Updates widget reads/writes via
this wrapper exclusively).
"""
from __future__ import annotations

from PySide6.QtCore import QSettings


_GROUP = "Updates"


class UpdatePrefs:
    """Thin typed wrapper over QSettings for update-related prefs.

    The wrapper accepts an injected ``QSettings`` instance so tests can
    point at an isolated ini file; the default constructor uses the
    process-wide QCoreApplication org/app name.
    """

    def __init__(self, settings: QSettings | None = None):
        self._s = settings or QSettings()

    # --- check_automatically (default True) ---
    @property
    def check_automatically(self) -> bool:
        v = self._s.value(f"{_GROUP}/check_automatically", True, type=bool)
        return bool(v)

    @check_automatically.setter
    def check_automatically(self, value: bool) -> None:
        self._s.setValue(f"{_GROUP}/check_automatically", bool(value))
        self._s.sync()

    # --- consent_seen (default False; flipped after one-time dialog) ---
    @property
    def consent_seen(self) -> bool:
        v = self._s.value(f"{_GROUP}/consent_seen", False, type=bool)
        return bool(v)

    @consent_seen.setter
    def consent_seen(self, value: bool) -> None:
        self._s.setValue(f"{_GROUP}/consent_seen", bool(value))
        self._s.sync()

    # --- first_deferred_at (ISO-8601 UTC of when a deferral chain began) ---
    @property
    def first_deferred_at(self) -> str | None:
        v = self._s.value(f"{_GROUP}/first_deferred_at", None)
        return str(v) if v else None

    @first_deferred_at.setter
    def first_deferred_at(self, value: str | None) -> None:
        if value is None:
            self._s.remove(f"{_GROUP}/first_deferred_at")
        else:
            self._s.setValue(f"{_GROUP}/first_deferred_at", value)
        self._s.sync()

    # --- last_deferred_at (most recent "Remind Me Tomorrow" click) ---
    @property
    def last_deferred_at(self) -> str | None:
        v = self._s.value(f"{_GROUP}/last_deferred_at", None)
        return str(v) if v else None

    @last_deferred_at.setter
    def last_deferred_at(self, value: str | None) -> None:
        if value is None:
            self._s.remove(f"{_GROUP}/last_deferred_at")
        else:
            self._s.setValue(f"{_GROUP}/last_deferred_at", value)
        self._s.sync()

    # --- deferred_version (which version the deferral chain applies to) ---
    @property
    def deferred_version(self) -> str | None:
        v = self._s.value(f"{_GROUP}/deferred_version", None)
        return str(v) if v else None

    @deferred_version.setter
    def deferred_version(self, value: str | None) -> None:
        if value is None:
            self._s.remove(f"{_GROUP}/deferred_version")
        else:
            self._s.setValue(f"{_GROUP}/deferred_version", value)
        self._s.sync()
