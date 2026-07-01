# -*- encoding: utf-8 -*-
"""
locksmith.ui.utils module

This module contains utility functions for UI components.
"""
from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QPixmap, QAction, QIcon, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget, QSizePolicy

from locksmith.ui.toolkit.widgets.buttons import HoverIconButton


# remove this, replace with .addspacing
def create_spacer(width=None, expanding=False) -> QWidget:
    """
    Create a spacer widget for layouts.

    Args:
        width: Fixed width in pixels. Ignored if expanding=True.
        expanding: If True, creates an expanding spacer that fills available space.

    Returns:
        QWidget configured as a spacer.
    """
    spacer = QWidget()
    if expanding:
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    else:
        spacer.setFixedWidth(width if width is not None else 0)
        spacer.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    return spacer


def load_scaled_pixmap(path: str, width: int, height: int) -> QPixmap:
    """
    Load and scale a pixmap from a file path.

    Args:
        path: Path to the image file.
        width: Target width in pixels.
        height: Target height in pixels.

    Returns:
        Scaled QPixmap with smooth transformation.
    """
    # Auto-convert to resource path
    path = ensure_resource_path(path)

    # Use QIcon for SVG files to render at target size without blur
    if path.lower().endswith('.svg'):
        icon = QIcon(path)
        if not icon.isNull():
            return icon.pixmap(QSize(width, height))

    # Fallback to QPixmap for non-SVG formats
    return QPixmap(path).scaled(
        width, height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation
    )


def load_symbol_pixmap(path: str, box: int, y_offset: float = 0.0,
                       dpr: float = 2.0) -> QPixmap:
    """Render an SVG symbol, aspect-fit, into a transparent ``box``x``box``
    square: horizontally centered, vertically centered plus ``y_offset``.

    ``load_scaled_pixmap`` returns a tightly-cropped pixmap whose placement is
    then re-centered by the host widget, so a wide mark (e.g. the eye+globe)
    can only ever land on the geometric center. This bakes the symbol's
    position into a fixed square canvas instead, so it can be nudged to
    *optically* align with adjacent text — a word with no descenders sits high
    in its line box, so the mark must drop a hair to read as centered.
    ``y_offset`` > 0 shifts the mark down. Rendered at ``dpr`` for retina.
    """
    path = ensure_resource_path(path)
    renderer = QSvgRenderer(path)
    vb = renderer.viewBoxF()
    if vb.width() <= 0 or vb.height() <= 0:
        return load_scaled_pixmap(path, box, box)
    scale = min(box / vb.width(), box / vb.height())
    w, h = vb.width() * scale, vb.height() * scale
    pm = QPixmap(round(box * dpr), round(box * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)  # paints in logical (box) coordinates
    renderer.render(painter, QRectF((box - w) / 2, (box - h) / 2 + y_offset, w, h))
    painter.end()
    return pm

def ensure_resource_path(path: str) -> str:
    """
    Ensure a path uses the Qt resource prefix.

    Args:
        path: File path, with or without :/ prefix.

    Returns:
        Path with :/ prefix for Qt resource system.
    """
    if path and not path.startswith(":/"):
        return f":/{path}"
    return path


def create_hover_action_with_widget(
        toolbar,
        icon_normal: str,
        icon_hover: str,
        tooltip: str,
        callback,
        shortcut: str | None = None
) -> tuple[QAction, HoverIconButton | None]:
    """
    Helper function to create a QAction with a HoverIconButton widget for toolbars.
    ...
    """
    # Auto-convert to resource paths
    icon_normal = ensure_resource_path(icon_normal)
    icon_hover = ensure_resource_path(icon_hover)

    # Create the action
    action = QAction(toolbar.parent())
    action.setIcon(QIcon(icon_normal))
    action.setToolTip(tooltip)
    if shortcut:
        action.setShortcut(shortcut)
    if callback:
        action.triggered.connect(callback)

    # Add to toolbar
    toolbar.addAction(action)

    # Get the widget and replace with custom button
    default_widget = toolbar.widgetForAction(action)
    if default_widget:
        # Create custom hover button
        hover_button = HoverIconButton(icon_normal, icon_hover, tooltip, toolbar)
        hover_button.clicked.connect(action.trigger)

        # Replace the default widget with our custom one
        toolbar.removeAction(action)
        toolbar.addWidget(hover_button)

        return action, hover_button

    return action, None
