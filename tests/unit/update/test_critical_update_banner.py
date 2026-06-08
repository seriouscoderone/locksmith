"""Tests for CriticalUpdateBanner.

Exercises the show/hide state machine, signal emission, and version
label content. No visual assertions.
"""
from __future__ import annotations

import os
import sys

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from locksmith.ui.banners.critical_update import CriticalUpdateBanner


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def test_banner_constructs_hidden():
    banner = CriticalUpdateBanner()
    assert banner is not None
    # Hidden state on construction — controller decides when to show.
    assert banner.isVisible() is False
    assert banner.current_version is None


def test_show_for_version_records_version():
    banner = CriticalUpdateBanner()
    banner.show_for_version("0.1.2")
    assert banner.current_version == "0.1.2"


def test_show_for_version_updates_label_text():
    banner = CriticalUpdateBanner()
    banner.show_for_version("0.1.2")
    assert "0.1.2" in banner.message_label.text()
    assert "security" in banner.message_label.text().lower()
    assert "install" in banner.message_label.text().lower()


def test_show_for_version_is_idempotent_for_same_version():
    banner = CriticalUpdateBanner()
    banner.show_for_version("0.1.2")
    banner.show_for_version("0.1.2")
    assert banner.current_version == "0.1.2"


def test_show_for_version_updates_to_new_version():
    banner = CriticalUpdateBanner()
    banner.show_for_version("0.1.2")
    banner.show_for_version("0.1.3")
    assert banner.current_version == "0.1.3"
    assert "0.1.3" in banner.message_label.text()


def test_install_button_emits_install_requested():
    banner = CriticalUpdateBanner()
    banner.show_for_version("0.1.2")
    fired = []
    banner.install_requested.connect(lambda: fired.append(True))
    banner.install_button.click()
    assert fired == [True]


def test_install_does_not_hide_banner():
    """Install hand-off is async; the controller decides when to hide."""
    banner = CriticalUpdateBanner()
    banner.show_for_version("0.1.2")
    banner.install_button.click()
    assert banner.current_version == "0.1.2"


def test_dismiss_button_emits_dismissed_signal():
    banner = CriticalUpdateBanner()
    banner.show_for_version("0.1.2")
    fired = []
    banner.dismissed.connect(lambda: fired.append(True))
    banner.dismiss_button.click()
    assert fired == [True]


def test_dismiss_clears_current_version():
    banner = CriticalUpdateBanner()
    banner.show_for_version("0.1.2")
    banner.dismiss_button.click()
    assert banner.current_version is None


def test_hide_banner_clears_state_without_emitting_dismissed():
    """hide_banner() is the controller-driven path; no signal expected."""
    banner = CriticalUpdateBanner()
    banner.show_for_version("0.1.2")
    fired = []
    banner.dismissed.connect(lambda: fired.append(True))
    banner.hide_banner()
    assert banner.current_version is None
    assert fired == []


def test_buttons_have_object_names():
    banner = CriticalUpdateBanner()
    assert banner.install_button.objectName() == (
        "criticalUpdateBanner.installButton"
    )
    assert banner.dismiss_button.objectName() == (
        "criticalUpdateBanner.dismissButton"
    )


def test_no_install_anyway_button_present():
    """Spec §9 prohibits any bypass affordance; mirrored here just in case."""
    banner = CriticalUpdateBanner()
    banner.show_for_version("0.1.2")
    for btn in banner.findChildren(QPushButton):
        assert "anyway" not in btn.text().lower()
        assert "force" not in btn.text().lower()


def test_message_label_present_with_object_name():
    banner = CriticalUpdateBanner()
    labels = banner.findChildren(QLabel)
    names = [lbl.objectName() for lbl in labels]
    assert "criticalUpdateBanner.message" in names
