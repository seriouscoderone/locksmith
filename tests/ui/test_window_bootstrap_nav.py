"""Tests for the first-run bootstrap -> vault navigation wiring in
``LocksmithWindow`` (Task 5b).

A real windowed launch confirmed the first-run bootstrap creates+opens the
brand's default vault, but the UI stayed on the home/vault-chooser screen —
no navigation into ``Pages.VAULT`` followed. A single-vault HOA should drop
straight into its (peeled) vault view.

``LocksmithWindow.__init__`` needs a live QApplication + full plugin
discovery to construct (out of scope for a fast/hermetic unit test, per
Task 5's precedent in ``tests/core/test_bootstrapping.py``). So this test
targets ``LocksmithWindow._run_default_bootstrap`` directly: a small,
side-effect-free method that reads ``self.app``/``self.nav_manager`` and
calls the module-level ``bootstrap_default_environment`` + ``brand()``
functions. It's invoked here as an unbound method against a bare stand-in
object carrying just the attributes it touches — no widgets, no QApplication
construction required beyond the module import.
"""
from unittest.mock import MagicMock

from locksmith.ui.window import LocksmithWindow
from locksmith.ui.navigation import Pages


class _FakeWindow:
    """Minimal stand-in exposing only what _run_default_bootstrap reads."""

    def __init__(self):
        self.app = MagicMock()
        self.nav_manager = MagicMock()


def test_true_return_navigates_into_the_opened_vault(monkeypatch):
    """bootstrap_default_environment() -> True means it created+opened the
    default vault this run; the window must navigate straight into it."""
    fake_brand = MagicMock()
    fake_brand.default_vault_name = "Carrier"

    monkeypatch.setattr("locksmith.ui.window.bootstrap_default_environment", lambda app, b: True)
    monkeypatch.setattr("locksmith.ui.window.brand", lambda: fake_brand)

    win = _FakeWindow()
    LocksmithWindow._run_default_bootstrap(win)

    win.nav_manager.navigate_to.assert_called_once_with(Pages.VAULT, vault_name="Carrier")


def test_false_return_does_not_force_navigation(monkeypatch):
    """False means not-first-run or a non-HOA brand — behavior must stay
    unchanged (no forced navigation away from wherever the user already is)."""
    fake_brand = MagicMock()
    fake_brand.default_vault_name = "Carrier"

    monkeypatch.setattr("locksmith.ui.window.bootstrap_default_environment", lambda app, b: False)
    monkeypatch.setattr("locksmith.ui.window.brand", lambda: fake_brand)

    win = _FakeWindow()
    LocksmithWindow._run_default_bootstrap(win)

    win.nav_manager.navigate_to.assert_not_called()
