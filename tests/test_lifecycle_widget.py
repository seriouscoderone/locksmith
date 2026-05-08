# -*- encoding: utf-8 -*-
"""Smoke tests for LifecycleWidget — Qt-required, uses the offscreen
QApplication fixture from conftest.py."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QPainter

from locksmith.plugins.ecosystem_viewer.widgets import LifecycleWidget


def test_lifecycle_widget_constructs_in_revocable_state(qapp):
    w = LifecycleWidget(revocable=True)
    assert w.revocable is True
    assert w.sizeHint() == QSize(LifecycleWidget._SIZE, LifecycleWidget._SIZE)


def test_lifecycle_widget_constructs_in_oneshot_state(qapp):
    w = LifecycleWidget(revocable=False)
    assert w.revocable is False


def test_lifecycle_widget_paints_without_crashing(qapp):
    """Render to an offscreen QImage and verify no painter errors."""
    w = LifecycleWidget(revocable=True)
    w.resize(w.sizeHint())
    image = QImage(w.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    from PySide6.QtCore import QPoint
    w.render(painter, QPoint(0, 0))
    painter.end()
    # If we reach here without exception, paint() succeeded.


def test_lifecycle_widget_revocable_setter_updates(qapp):
    w = LifecycleWidget(revocable=False)
    w.revocable = True
    assert w.revocable is True
