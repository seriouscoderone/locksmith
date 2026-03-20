# -*- encoding: utf-8 -*-
"""
locksmith.ui.toolkit.widgets.toggle module

Custom toggle switch widget with animated transitions.
"""
from PySide6.QtCore import (
    Qt,
    Property,
    Slot,
    QPoint,
    QSize,
    QPropertyAnimation,
    QEasingCurve,
    QPointF,
    QRectF
)
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import QAbstractButton

from locksmith.ui import colors


class ToggleSwitch(QAbstractButton):
    """
    A custom animated toggle switch widget.

    Features:
    - Smooth animation between on/off states
    - Customizable colors for track, thumb, and border
    - Clickable anywhere within the widget bounds
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Settings (Colors & Sizes)
        self._track_width = 60
        self._track_height = 32

        # Colors
        self._track_off_color = QColor(colors.TOGGLE_TRACK_OFF)
        self._track_on_color = QColor(colors.TOGGLE_TRACK_ON)
        self._thumb_color = QColor(colors.TOGGLE_THUMB)
        self._border_off_color = QColor(colors.TEXT_MUTED)

        # Animation setup
        self._position = 0.0  # 0.0 = Off (Left), 1.0 = On (Right)

        self._anim = QPropertyAnimation(self, b"position")
        self._anim.setDuration(250)  # Speed in ms
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuad)  # Smooth deceleration

        # Resize the widget to fit the drawing
        self.setFixedSize(QSize(self._track_width, self._track_height))

        # Connect the click signal to the animation trigger
        self.toggled.connect(self.start_transition)

    @Property(float)
    def position(self) -> float:
        return self._position

    @position.setter
    def position(self, pos: float) -> None:
        self._position = pos
        self.update()  # Trigger a repaint whenever position changes

    @Slot(bool)
    def start_transition(self, checked: bool) -> None:
        """Start the animation transition to the new state."""
        self._anim.stop()
        self._anim.setStartValue(self._position)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def hitButton(self, pos: QPoint) -> bool:
        """Allow clicking anywhere in the widget."""
        return self.contentsRect().contains(pos)

    def paintEvent(self, e) -> None:
        """Paint the toggle switch."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Setup Geometry
        # Use a slight margin so the border doesn't get clipped
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        corner_radius = rect.height() / 2.0

        # 2. Determine Colors (Interpolate based on animation position)
        track_color = self._lerp_color(
            self._track_off_color, self._track_on_color, self._position
        )
        border_color = self._lerp_color(
            self._border_off_color, self._track_on_color, self._position
        )

        # 3. Draw Track (The background pill)
        p.setPen(QPen(border_color, 2))  # 2px border
        p.setBrush(QBrush(track_color))
        p.drawRoundedRect(rect, corner_radius, corner_radius)

        # 4. Draw Thumb (The colored circle)
        # Calculate X position:
        # Min X = Radius + Margin, Max X = Width - Radius - Margin
        margin = 4
        thumb_radius = (rect.height() / 2.0) - margin

        min_x = rect.x() + thumb_radius + margin + 1  # +1 for visual balance with border
        max_x = rect.width() - thumb_radius - margin

        # Current X based on animation position
        curr_x = min_x + (max_x - min_x) * self._position

        thumb_point = QPointF(curr_x, rect.center().y())

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self._thumb_color))
        p.drawEllipse(thumb_point, thumb_radius, thumb_radius)

        p.end()

    @staticmethod
    def _lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
        """Linearly interpolate between two colors."""
        r = c1.red() + (c2.red() - c1.red()) * t
        g = c1.green() + (c2.green() - c1.green()) * t
        b = c1.blue() + (c2.blue() - c1.blue()) * t
        return QColor(int(r), int(g), int(b))
