# -*- encoding: utf-8 -*-
"""
locksmith.ui.toolkit.widgets.toast module

This module contains the NotificationToast widget for displaying notifications.
"""
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QCursor, QPixmap, QPainter, QPainterPath, QColor
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsOpacityEffect

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import LocksmithIconButton
from locksmith.ui.toolkit.widgets.fields import LocksmithPlainTextEdit


class NotificationToast(QFrame):
    """
    A notification toast that appears in the lower right corner of the screen.

    The toast displays a notification with a datetime, message, and pending count.
    It automatically disappears after 5 seconds with a fade-out animation.
    Clicking the toast navigates to the notification screen.
    Only one toast can be displayed at a time.
    """

    # Signal emitted when toast is clicked
    clicked = Signal()

    # Signal emitted when toast is closed (either by user or timeout)
    closed = Signal()

    def __init__(self, datetime: str, message: str, pending_notifications: int, parent=None):
        """
        Initialize the NotificationToast.

        Args:
            datetime: The datetime string to display
            message: The notification message text
            pending_notifications: Number of pending notifications
            parent: Parent widget (typically the main window)
        """
        super().__init__(parent)

        self.datetime = datetime
        self.message = message
        self.pending_notifications = pending_notifications

        # Fixed size for the toast
        self.setFixedSize(380, 140)

        # Make the toast stay on top but not block interaction with underlying widgets
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Set cursor to indicate clickability
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        # Setup opacity effect for fade animation
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity_effect)

        # Setup fade animation
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(300)
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.fade_animation.finished.connect(self._on_fade_finished)

        # Setup auto-dismiss timer (5 seconds)
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.fade_out)

        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI components of the toast."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(8)

        # Apply styling with border radius
        self.setStyleSheet(f"""
            NotificationToast {{
                background-color: {colors.WHITE};
                border: 1px solid {colors.BORDER};
                border-radius: 6px;
            }}
        """)

        # Top row: icon, text layout, close button
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)

        # Notification icon (using badge.svg as notification icon)
        icon_label = QLabel()
        icon_pixmap = QPixmap(":/assets/material-icons/badge.svg")
        if not icon_pixmap.isNull():
            scaled_pixmap = icon_pixmap.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
            icon_label.setPixmap(scaled_pixmap)
        icon_label.setFixedSize(24, 24)
        icon_label.setStyleSheet(f"color: {colors.TEXT_PRIMARY};")
        top_row.addWidget(icon_label)

        # Text layout (header and datetime)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        # Header with pending count
        header_label = QLabel(f"Notification ({self.pending_notifications})")
        header_label.setStyleSheet(f"""
            font-size: 14px;
            font-weight: bold;
            color: {colors.TEXT_PRIMARY};
        """)
        text_layout.addWidget(header_label)

        # Datetime subheader
        datetime_label = QLabel(self.datetime)
        datetime_label.setStyleSheet(f"""
            font-size: 12px;
            color: {colors.TEXT_SECONDARY};
        """)
        text_layout.addWidget(datetime_label)

        top_row.addLayout(text_layout)
        top_row.addStretch()

        # Close button
        close_button = LocksmithIconButton(
            icon_path=":/assets/material-icons/close.svg",
            tooltip="Close",
            icon_size=20
        )
        close_button.clicked.connect(self.close_toast)
        # Prevent close button from triggering toast click
        close_button.clicked.connect(lambda: None, Qt.ConnectionType.DirectConnection)
        top_row.addWidget(close_button)

        main_layout.addLayout(top_row)

        # Message text (scrollable with max 4 lines)
        self.message_edit = LocksmithPlainTextEdit("")
        self.message_edit.setPlainText(self.message)
        self.message_edit.setReadOnly(True)
        self.message_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.message_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.message_edit.setMaximumHeight(80)  # Approximately 4 lines of text
        self.message_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {colors.BACKGROUND_CONTENT};
                border: 1px solid {colors.BORDER_NEUTRAL};
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
                color: {colors.TEXT_PRIMARY};
            }}
        """)
        # Scroll to top to show first lines
        self.message_edit.moveCursor(self.message_edit.textCursor().MoveOperation.Start)
        self.message_edit.ensureCursorVisible()

        # Make the text edit not steal cursor
        self.message_edit.viewport().setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        main_layout.addWidget(self.message_edit)

    def mousePressEvent(self, event):
        """Handle mouse press to trigger navigation."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def show_toast(self):
        """Show the toast and start the auto-dismiss timer."""
        self.show()
        self.raise_()  # Bring to front
        self.dismiss_timer.start(5000)  # 5 seconds

    def fade_out(self):
        """Fade out the toast."""
        self.dismiss_timer.stop()
        self.fade_animation.start()

    def close_toast(self):
        """Close the toast immediately (called by close button)."""
        self.dismiss_timer.stop()
        self.closed.emit()
        self.hide()

    def _on_fade_finished(self):
        """Called when fade animation finishes."""
        self.closed.emit()
        self.hide()

    def position_in_parent(self, parent_width: int, parent_height: int, toolbar_height: int = 0):
        """
        Position the toast in the lower right corner of the parent window.

        Args:
            parent_width: Width of the parent window
            parent_height: Height of the parent window
            toolbar_height: Height of the toolbar (to account for offset)
        """
        if not self.parent():
            return

        # Position in lower right corner with 20px margin from edges
        margin = 20
        x = parent_width - self.width() - margin
        y = parent_height - self.height() - margin

        # Convert parent-relative coordinates to global screen coordinates
        # Since this is a top-level window (due to window flags), we need global coords
        global_pos = self.parent().mapToGlobal(self.parent().rect().topLeft())
        global_x = global_pos.x() + x
        global_y = global_pos.y() + y

        self.move(global_x, global_y)

    def paintEvent(self, event):
        """Paint the background with rounded corners."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Create rounded rectangle path
        path = QPainterPath()
        path.addRoundedRect(self.rect(), 6, 6)

        # Fill background
        painter.fillPath(path, QColor(colors.BACKGROUND_CONTENT))

        # Draw border
        painter.setPen(QColor(colors.BORDER))
        painter.drawPath(path)