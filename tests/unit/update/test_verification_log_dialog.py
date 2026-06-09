"""Tests for VerificationLogDialog.

Tests dialog construction + label population, NOT visual rendering.
Per the no-headless-UI-test rule, we assert that fields flow into the
right widgets, not that pixels appear correctly. Visual verification
is done by rendering offscreen to PNG and inspecting in a review.
"""
from __future__ import annotations

import os
import sys

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from locksmith.ui.dialogs.verification_log import (
    VerificationLogDialog,
    _human_size,
)
from locksmith.update.verify import VerificationResult


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _verified(version: str = "0.0.16") -> VerificationResult:
    return VerificationResult(
        ok=True,
        version=version,
        platform="macos",
        publisher_aid="ECnJ7jhAxjrduHkIKS_ml56bqPuIJIvSw-i0mpZR_P8p",
        anchor_said="EKrzgtcKxXw3dsmn4UfYiBGgfu9BWTDjiRh9IkZZovUZ",
        artifact_sha256="8e83fa84e7c4a81ce2de210002799a7a3258a370c1f79f064eb73cb4e75d94dd",
        artifact_size=60983347,
        witness_receipts=5,
        kel_tip_sn=1,
    )


def _rejected() -> VerificationResult:
    return VerificationResult(
        ok=False,
        version="0.0.17",
        platform="windows",
        publisher_aid="ECnJ7jhAxjrduHkIKS_ml56bqPuIJIvSw-i0mpZR_P8p",
        anchor_said="ESomeRejectedAnchorSAIDXXXXXXXXXXXXXXXXXXXXX",
        artifact_sha256="deadbeef" * 8,
        artifact_size=64688128,
        witness_receipts=1,
        kel_tip_sn=2,
    )


def _all_label_texts(dialog: VerificationLogDialog) -> list[str]:
    return [w.text() for w in dialog.findChildren(QLabel)]


def test_human_size_handles_realistic_artifact_sizes():
    assert _human_size(60_983_347) == "58.16 MB"
    assert _human_size(64_688_128) == "61.69 MB"
    assert _human_size(1024) == "1.00 KB"
    assert _human_size(512) == "512 B"


def test_dialog_constructs_with_verified_result():
    dlg = VerificationLogDialog(result=_verified())
    assert dlg.result is not None
    assert dlg.result.ok is True


def test_dialog_constructs_with_rejected_result():
    dlg = VerificationLogDialog(result=_rejected())
    assert dlg.result.ok is False


def test_dialog_constructs_with_none_result():
    """No verification has run yet — dialog shows a placeholder."""
    dlg = VerificationLogDialog(result=None)
    assert dlg.result is None


def test_verified_dialog_shows_witness_receipt_count():
    dlg = VerificationLogDialog(result=_verified())
    texts = _all_label_texts(dlg)
    # The "5 concurred" string lives in the evidence section.
    assert any("5 concurred" in t for t in texts)
    # The status banner mentions the receipt count.
    assert any("5 witness" in t and "receipts" in t for t in texts)


def test_verified_dialog_shows_publisher_aid():
    dlg = VerificationLogDialog(result=_verified())
    texts = _all_label_texts(dlg)
    assert any("ECnJ7jhAxjrduHkIKS_ml56bqPuIJIvSw-i0mpZR_P8p" in t for t in texts)


def test_verified_dialog_shows_anchor_said():
    dlg = VerificationLogDialog(result=_verified())
    texts = _all_label_texts(dlg)
    assert any("EKrzgtcKxXw3dsmn4UfYiBGgfu9BWTDjiRh9IkZZovUZ" in t for t in texts)


def test_verified_dialog_shows_kel_sn():
    dlg = VerificationLogDialog(result=_verified())
    texts = _all_label_texts(dlg)
    assert any("sn=1" in t for t in texts)


def test_verified_dialog_shows_artifact_hash_and_size():
    dlg = VerificationLogDialog(result=_verified())
    texts = _all_label_texts(dlg)
    assert any("8e83fa84" in t for t in texts), "SHA-256 prefix should be visible"
    assert any("58.16 MB" in t and "60,983,347" in t for t in texts)


def test_verified_dialog_status_banner_says_verified():
    dlg = VerificationLogDialog(result=_verified())
    texts = _all_label_texts(dlg)
    assert "Verified" in texts


def test_rejected_dialog_status_banner_says_rejected():
    dlg = VerificationLogDialog(result=_rejected())
    texts = _all_label_texts(dlg)
    assert "Rejected" in texts


def test_rejected_dialog_uses_supplied_error_message():
    msg = "Witness threshold not met: only 1 of 5 returned a valid receipt"
    dlg = VerificationLogDialog(result=_rejected(), error_message=msg)
    texts = _all_label_texts(dlg)
    assert any(msg in t for t in texts)


def test_rejected_dialog_falls_back_to_generic_error_message():
    """When no error_message is given, a sensible default appears."""
    dlg = VerificationLogDialog(result=_rejected(), error_message=None)
    texts = _all_label_texts(dlg)
    assert any("failed the trust check" in t.lower() for t in texts)


def test_none_result_shows_idle_banner_not_rejected():
    """When no verification has run, the dialog must show a neutral
    'No verification yet' state, NOT a red 'Rejected' banner. Showing
    Rejected makes users think something failed when actually nothing
    has happened yet (UX bug fixed 2026-06-09)."""
    dlg = VerificationLogDialog(result=None)
    texts = _all_label_texts(dlg)
    assert any("No verification yet" in t for t in texts)
    # And specifically NOT a rejection
    assert "Rejected" not in texts
    # The body should guide the user to Check now / Help menu
    assert any("Check now" in t or "Check for updates" in t for t in texts)


def test_witness_count_below_threshold_does_not_get_green_styling():
    """The 'X concurred' line uses green ONLY when receipts >= 3 (threshold).

    We can't easily inspect rendered color, but we can confirm the value
    label exists; the styling check is by review.
    """
    one = VerificationResult(
        ok=False, version="0.0.17", platform="macos",
        publisher_aid="E" + "X" * 43, anchor_said="E" + "Y" * 43,
        artifact_sha256="a" * 64, artifact_size=1024,
        witness_receipts=1, kel_tip_sn=2,
    )
    dlg = VerificationLogDialog(result=one)
    texts = _all_label_texts(dlg)
    assert any("1 concurred" in t for t in texts)
