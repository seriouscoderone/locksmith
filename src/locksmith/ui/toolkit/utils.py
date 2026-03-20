# -*- encoding: utf-8 -*-
"""
locksmith.ui.utils module

This module contains utility functions for UI components.
"""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QAction, QIcon
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
