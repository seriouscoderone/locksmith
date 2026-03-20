# -*- encoding: utf-8 -*-
"""
locksmith.ui.toolkit.widgets.page module

This module contains reusable page widgets.
"""
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame
)
from keri import help

from locksmith.ui import colors

logger = help.ogler.getLogger(__name__)


class LocksmithFormPage(QWidget):
    """
    Reusable base page for forms with sticky header, scrollable content, and validation feedback.

    Features:
    - Sticky header with icon, title, and optional controls
    - Optional custom header widget to replace default header
    - Scrollable content area
    - Collapsible error and success banners
    - Consistent styling
    """

    def __init__(
            self,
            title: str,
            icon_path: str,
            parent: QWidget | None = None,
            header_content: QWidget | None = None
    ):
        """
        Initialize the LocksmithFormPage.

        Args:
            title: Title text to display in header.
            icon_path: Path to icon to display in header.
            parent: Parent widget.
            header_content: Optional custom widget to use as header. If provided,
                           replaces the default icon/title header.
        """
        super().__init__(parent)
        self._title = title
        self._icon_path = icon_path
        self._header_content = header_content

        self._setup_base_ui()

    def _setup_base_ui(self):
        """Set up the base UI structure."""
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Set background
        from PySide6.QtGui import QPalette, QColor
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(colors.BACKGROUND_CONTENT))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # Build Sticky Header
        self._build_header()

        # Build Banners (hidden by default)
        self._build_error_banner()
        self._build_success_banner()

        # Build Scrollable Content Area
        self._build_scroll_area()

    def _build_header(self):
        """Build the sticky header section."""
        # If custom header content is provided, use it directly
        if self._header_content is not None:
            self.main_layout.addWidget(self._header_content)
            return

        header_container = QWidget()
        header_container.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")
        
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(20, 30, 20, 20)
        header_layout.setSpacing(10)

        # Icon
        if self._icon_path:
            icon_label = QLabel()
            icon_pixmap = QIcon(self._icon_path).pixmap(52, 52)
            icon_label.setPixmap(icon_pixmap)
            header_layout.addWidget(icon_label)

        # Title
        title_label = QLabel(self._title)
        title_label.setStyleSheet("font-size: 42px; font-weight: 200;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()
        
        # Determine stack index for insertion (header should be at top)
        self.main_layout.addWidget(header_container)

    def _build_error_banner(self):
        """Build collapsible error banner."""
        self.error_banner = QFrame()
        self.error_banner.setObjectName("error-banner")
        self.error_banner.setStyleSheet(f"""
            QFrame#error-banner {{
                background-color: {colors.BACKGROUND_ERROR};
                border-left: 4px solid {colors.DANGER};
            }}
        """)
        self.error_banner.setMaximumHeight(0)  # Start hidden

        banner_layout = QHBoxLayout(self.error_banner)
        banner_layout.setContentsMargins(20, 12, 20, 12)  # Match header margins
        banner_layout.setSpacing(10)

        # Error icon
        error_icon = QLabel()
        error_pixmap = QIcon(":/assets/material-icons/error.svg").pixmap(QSize(20, 20))
        error_icon.setPixmap(error_pixmap)
        error_icon.setFixedSize(20, 20)
        banner_layout.addWidget(error_icon)

        # Error message
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {colors.DANGER}; font-size: 13px;")
        banner_layout.addWidget(self.error_label, 1) # Expand to fill

        # Close button for banner (optional, but good UX)
        # For now, we'll rely on programmatic clearing or new validations

        self.main_layout.addWidget(self.error_banner)

        # Animation
        self.error_animation = QPropertyAnimation(self.error_banner, b"maximumHeight")
        self.error_animation.setDuration(200)
        self.error_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _build_success_banner(self):
        """Build collapsible success banner."""
        self.success_banner = QFrame()
        self.success_banner.setObjectName("success-banner")
        self.success_banner.setStyleSheet(f"""
            QFrame#success-banner {{
                background-color: {colors.BACKGROUND_SUCCESS};
                border-left: 4px solid {colors.SUCCESS};
            }}
        """)
        self.success_banner.setMaximumHeight(0)  # Start hidden

        banner_layout = QHBoxLayout(self.success_banner)
        banner_layout.setContentsMargins(20, 12, 20, 12)
        banner_layout.setSpacing(10)

        # Success icon
        success_icon = QLabel()
        success_pixmap = QIcon(":/assets/material-icons/check_circle.svg").pixmap(QSize(20, 20))
        success_icon.setPixmap(success_pixmap)
        success_icon.setFixedSize(20, 20)
        banner_layout.addWidget(success_icon)

        # Success message
        self.success_label = QLabel()
        self.success_label.setWordWrap(True)
        self.success_label.setStyleSheet(f"color: {colors.SUCCESS_TEXT}; font-size: 13px;")
        banner_layout.addWidget(self.success_label, 1)

        self.main_layout.addWidget(self.success_banner)

        # Animation
        self.success_animation = QPropertyAnimation(self.success_banner, b"maximumHeight")
        self.success_animation.setDuration(200)
        self.success_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _build_scroll_area(self):
        """Build the main scrollable content area."""
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        # Create content widget to hold child form elements
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.scroll_area.setWidget(self.content_widget)

        # Layout for the content widget
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(20, 10, 20, 20) # Top margin reduced as header provides spacing
        self.content_layout.setSpacing(0)

        self.main_layout.addWidget(self.scroll_area)

    def show_error(self, message: str):
        """
        Show error banner with message.

        Args:
            message: Error message to display.
        """
        self.clear_success()

        self.error_label.setText(message)

        # Measure required height
        self.error_banner.setMaximumHeight(16777215)
        self.error_banner.adjustSize()
        banner_height = self.error_banner.sizeHint().height()
        self.error_banner.setMaximumHeight(0)

        self.error_animation.setStartValue(0)
        self.error_animation.setEndValue(banner_height)
        self.error_animation.start()

    def clear_error(self):
        """Hide error banner."""
        if self.error_banner.maximumHeight() > 0:
            self.error_animation.setStartValue(self.error_banner.height())
            self.error_animation.setEndValue(0)
            self.error_animation.start()

    def show_success(self, message: str):
        """
        Show success banner with message.

        Args:
            message: Success message to display.
        """
        self.clear_error()

        self.success_label.setText(message)

        # Measure required height
        self.success_banner.setMaximumHeight(16777215)
        self.success_banner.adjustSize()
        banner_height = self.success_banner.sizeHint().height()
        self.success_banner.setMaximumHeight(0)

        self.success_animation.setStartValue(0)
        self.success_animation.setEndValue(banner_height)
        self.success_animation.start()

    def clear_success(self):
        """Hide success banner."""
        if self.success_banner.maximumHeight() > 0:
            self.success_animation.setStartValue(self.success_banner.height())
            self.success_animation.setEndValue(0)
            self.success_animation.start()
