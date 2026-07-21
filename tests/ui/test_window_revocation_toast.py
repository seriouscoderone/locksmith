"""Tests for the HOA-aware ``role_revoked`` toast in
``LocksmithWindow._on_notification_event`` (Task 10).

Task 7 emits a ``RoleGate``/``role_revoked`` doer event on the
satisfied->unsatisfied gate transition; Task 9 synthesizes the durable
Notifications card from held TEL state. This task adds the ephemeral toast
for the same event: generic copy pointing at Notifications, gated on
``brand().onboarding_enabled`` since stock (non-onboarding) brands don't
surface role gates at all.

``LocksmithWindow.__init__`` needs a live QApplication + full plugin
discovery (out of scope here, per ``test_window_bootstrap_nav.py``'s
precedent), so this test builds the window via ``__new__`` -- bypassing
``__init__`` entirely -- and calls the bound ``_on_notification_event``
method directly. That method only reads ``brand()`` (module-level) and
``self.show_notification_toast`` in the paths under test, so no other
instance attributes need to be stubbed.
"""
from unittest.mock import MagicMock, patch

from locksmith.ui.window import LocksmithWindow


def _win():
    win = LocksmithWindow.__new__(LocksmithWindow)
    win.show_notification_toast = MagicMock()
    return win


def test_role_revoked_shows_hoa_toast():
    win = _win()
    with patch("locksmith.ui.window.brand") as brand:
        brand.return_value.onboarding_enabled = True
        win._on_notification_event("RoleGate", "role_revoked",
                                    {"plugin_id": "carrier", "schema_said": "E"})
    win.show_notification_toast.assert_called_once()
    args = win.show_notification_toast.call_args[0]
    assert any("revoked" in str(a).lower() for a in args)


def test_role_revoked_ignored_for_stock_brand():
    win = _win()
    with patch("locksmith.ui.window.brand") as brand:
        brand.return_value.onboarding_enabled = False
        win._on_notification_event("RoleGate", "role_revoked", {"plugin_id": "carrier"})
    win.show_notification_toast.assert_not_called()


def test_non_role_event_unaffected():
    # A NotificationToast/new_notification event must still work
    # (regression guard on the pre-existing branch this one is added after).
    win = _win()
    with patch("locksmith.ui.window.brand") as brand:
        brand.return_value.onboarding_enabled = False
        win._on_notification_event("NotificationToast", "new_notification",
                                   {"datetime": "", "message": "hi", "pending_count": 1, "route": ""})
    win.show_notification_toast.assert_called_once()
