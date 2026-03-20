# -*- encoding: utf-8 -*-
"""
locksmith.ui.toolkit.widgets.fields module

This module contains reusable custom field widget components.
"""
from typing import cast, Optional

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property, QSize, Signal
from PySide6.QtGui import QIcon, QAction, QColor, QFont, QPalette
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QComboBox, QListView, QPlainTextEdit

from locksmith.ui import colors
from locksmith.ui.styles import get_monospace_font_family


def _get_monospace_font_css(widget) -> str:
    """Return font-family CSS if widget has 'monospace' class property."""
    if widget.property("class") == "monospace":
        return f'font-family: "{get_monospace_font_family()}", monospace;'
    return ""


class LocksmithPlainTextEdit(QPlainTextEdit):
    """
    Custom plain text edit with consistent Locksmith styling.
    A styled QPlainTextEdit with rounded grey border matching other Locksmith widgets.
    """

    def __init__(self, placeholder_text: str = "", parent=None):
        """
        Initialize the LocksmithPlainTextEdit.

        Args:
            placeholder_text: The placeholder text.
            parent: Parent widget.
        """
        super().__init__(parent)

        # Colors
        self._border_color = QColor(colors.BORDER_NEUTRAL)
        self._focused_border_color = QColor(colors.PRIMARY)
        self._bg_color = colors.BACKGROUND_CONTENT
        self._is_focused = False

        self._setup_ui(placeholder_text)

    def _setup_ui(self, placeholder_text: str):
        """Setup the UI components."""
        if placeholder_text:
            self.setPlaceholderText(placeholder_text)

        self.setMinimumHeight(50)
        self._update_styling()

    def _update_styling(self):
        """Update the stylesheet based on current state."""
        border_color = self._focused_border_color if self._is_focused else self._border_color
        border_width = "2px" if self._is_focused else "1px"

        font_family = _get_monospace_font_css(self)

        self.setStyleSheet(f"""
            QPlainTextEdit {{
                border: {border_width} solid {border_color.name()};
                border-radius: 6px;
                padding: 12px;
                font-size: 14px;
                color: {colors.TEXT_PRIMARY};
                background-color: {self._bg_color};
                {font_family}
            }}
        """)

    def focusInEvent(self, event):
        """Handle focus in event."""
        self._is_focused = True
        self._update_styling()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        """Handle focus out event."""
        self._is_focused = False
        self._update_styling()
        super().focusOutEvent(event)


class LocksmithLineEdit(QLineEdit):
    """
    Custom line edit with consistent Locksmith styling.
    A simplified styled QLineEdit without floating label animations.
    """

    def __init__(self, placeholder_text: str = "", parent=None, password_mode: bool = False,
                 leading_icon: str | None = None):
        """
        Initialize the LocksmithLineEdit.

        Args:
            placeholder_text: The placeholder text.
            parent: Parent widget.
            password_mode: If True, display text as password dots.
            leading_icon: Path to icon file to display on the left side (optional).
        """
        super().__init__(parent)

        self._password_mode = password_mode
        self._password_visible = False
        self._leading_icon = leading_icon
        self._has_leading_icon = leading_icon is not None

        # Colors
        self._border_color = QColor(colors.BORDER_NEUTRAL)
        self._focused_border_color = QColor(colors.PRIMARY)
        self._bg_color = colors.BACKGROUND_CONTENT
        self._is_focused = False

        self._setup_ui(placeholder_text)

    def _setup_ui(self, placeholder_text: str):
        """Setup the UI components."""
        # Set placeholder
        if placeholder_text:
            self.setPlaceholderText(placeholder_text)

        # Set minimum height
        self.setMinimumHeight(50)

        # Add leading icon if specified
        if self._has_leading_icon:
            self._add_leading_icon_action()

        # Set password mode if enabled
        if self._password_mode:
            self.setEchoMode(QLineEdit.EchoMode.Password)
            self._add_password_toggle_action()

        # Apply initial styling
        self._update_styling()

        # Set initial cursor position
        self.setCursorPosition(0)

    def _add_leading_icon_action(self):
        """Add a leading (left side) icon action."""
        self.leading_icon_action = QAction(self)
        self.leading_icon_action.setIcon(QIcon(cast(str, self._leading_icon)))
        self.addAction(self.leading_icon_action, QLineEdit.ActionPosition.LeadingPosition)

    def _add_password_toggle_action(self):
        """Add the password visibility toggle action."""
        self.toggle_password_action = QAction(self)
        self.toggle_password_action.setIcon(QIcon(":/assets/material-icons/visibility_off.svg"))
        self.toggle_password_action.triggered.connect(self._toggle_password_visibility)
        self.addAction(self.toggle_password_action, QLineEdit.ActionPosition.TrailingPosition)

    def _toggle_password_visibility(self):
        """Toggle password visibility."""
        self._password_visible = not self._password_visible
        if self._password_visible:
            self.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_password_action.setIcon(QIcon(":/assets/material-icons/visibility.svg"))
        else:
            self.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_password_action.setIcon(QIcon(":/assets/material-icons/visibility_off.svg"))

    def _update_styling(self):
        """Update the stylesheet based on current state."""
        border_color = self._focused_border_color if self._is_focused else self._border_color
        border_width = "2px" if self._is_focused else "1px"
        left_padding = "40px" if self._has_leading_icon else "12px"

        font_family = _get_monospace_font_css(self)

        self.setStyleSheet(f"""
            QLineEdit {{
                border: {border_width} solid {border_color.name()};
                border-radius: 6px;
                padding: 12px {left_padding} 12px 12px;
                font-size: 14px;
                background-color: {self._bg_color};
                {font_family}
            }}
        """)

    def focusInEvent(self, event):
        """Handle focus in event."""
        self._is_focused = True
        self._update_styling()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        """Handle focus out event."""
        self._is_focused = False
        self._update_styling()
        super().focusOutEvent(event)

    def setPasswordMode(self, enabled: bool):
        """Enable or disable password mode."""
        if enabled == self._password_mode:
            return

        self._password_mode = enabled
        if enabled:
            self.setEchoMode(QLineEdit.EchoMode.Password)
            self._add_password_toggle_action()
        else:
            self.setEchoMode(QLineEdit.EchoMode.Normal)
            if hasattr(self, 'toggle_password_action'):
                self.removeAction(self.toggle_password_action)

    def isPasswordMode(self) -> bool:
        """Check if password mode is enabled."""
        return self._password_mode

    def setLeadingIcon(self, icon_path: str):
        """
        Set or update the leading icon.

        Args:
            icon_path: Path to the icon file.
        """
        self._leading_icon = icon_path
        was_has_icon = self._has_leading_icon
        self._has_leading_icon = icon_path is not None

        if self._has_leading_icon:
            if hasattr(self, 'leading_icon_action'):
                self.leading_icon_action.setIcon(QIcon(icon_path))
            else:
                self._add_leading_icon_action()
        elif hasattr(self, 'leading_icon_action'):
            self.removeAction(self.leading_icon_action)
            delattr(self, 'leading_icon_action')

        # Update styling if icon state changed
        if was_has_icon != self._has_leading_icon:
            self._update_styling()

    def getLeadingIcon(self) -> Optional[str]:
        """Get the current leading icon path."""
        return self._leading_icon

    def hasLeadingIcon(self) -> bool:
        """Check if a leading icon is set."""
        return self._has_leading_icon


class FloatingLabelLineEdit(QWidget):
    """
    Custom line edit with floating label animation.
    The placeholder text animates up to become an inline label when focused or filled.
    """

    def __init__(self, label_text: str = "", parent=None, password_mode: bool = False, leading_icon: str | None = None,
                 font_family: str = "none"):
        """
        Initialize the FloatingLabelLineEdit.

        Args:
            label_text: The placeholder/label text.
            parent: Parent widget.
            password_mode: If True, display text as password dots.
            leading_icon: Path to icon file to display on the left side (optional).
        """

        self._label_text = label_text
        self._is_floating = False
        self._label_y_pos = 21  # Start position (centered in input) - adjusted from 35
        self._password_mode = password_mode
        self._password_visible = False
        self._leading_icon = leading_icon
        self._has_leading_icon = leading_icon is not None

        # Colors
        self._border_color = QColor(colors.BORDER_NEUTRAL)
        self._focused_border_color = QColor(colors.PRIMARY)
        self._label_color = QColor(colors.TEXT_SECONDARY)
        self._focused_label_color = QColor(colors.PRIMARY)
        self._is_focused = False
        self._bg_color = colors.BACKGROUND_CONTENT

        self._font_family = font_family

        super().__init__(parent)

        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI components."""
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.setLayout(layout)

        # Container for proper spacing - adjusted from 70
        self.setMinimumHeight(55)

        # Calculate padding based on whether there's a leading icon
        left_padding = "40px" if self._has_leading_icon else "12px"

        # Line edit (add first so label appears on top)
        self.line_edit = QLineEdit(self)
        self.line_edit.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {self._border_color.name()};
                border-radius: 6px;
                padding: 12px {left_padding} 12px 12px;
                font-size: 14px;
                font-family: {self._font_family};
                background-color: {self._bg_color};
                margin-top: 2px;
            }}
            QLineEdit:focus {{
                border: 1px solid {self._focused_border_color.name()};
            }}
            QLineEdit QToolButton {{
                padding: 0px;
                margin-right: -4px;  /* Reduce right margin to bring icon closer */
            }}
        """)
        self.line_edit.setMinimumHeight(50)

        # Add leading icon if specified
        if self._has_leading_icon:
            self._add_leading_icon_action()

        # Set password mode if enabled
        if self._password_mode:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            # Add eye icon action
            self._add_password_toggle_action()

        layout.addWidget(self.line_edit)

        # Calculate label starting position based on whether there's a leading icon
        label_x_pos = 44 if self._has_leading_icon else 12

        # Floating label (positioned absolutely, not in layout)
        self.label = QLabel(self._label_text, self)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # Allow clicks through
        self.label.setStyleSheet(f"""
            QLabel {{
                color: {self._label_color.name()};
                background-color: {self._bg_color};
                padding: 0 4px;
            }}
        """)
        label_font = QFont()
        label_font.setPointSize(14)  # Start slightly larger
        self.label.setFont(label_font)
        self.label.adjustSize()  # Make label container tight to text
        self.label.move(label_x_pos, int(self._label_y_pos))
        self.label.raise_()  # Bring label to front
        self.label.show()  # Explicitly show the label

        # Connect signals
        self.line_edit.focusInEvent = self._on_focus_in  # type: ignore
        self.line_edit.focusOutEvent = self._on_focus_out  # type: ignore
        self.line_edit.textChanged.connect(self._on_text_changed)

        # Animation for label position
        self.label_animation = QPropertyAnimation(self, b"labelYPos")
        self.label_animation.setDuration(200)
        self.label_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Set initial cursor position
        self.setCursorPosition(0)

    def reset_style(self):
        left_padding = "40px" if self._has_leading_icon else "12px"
        self.line_edit.setStyleSheet(f"""
                    QLineEdit {{
                        border: 1px solid {self._border_color.name()};
                        border-radius: 6px;
                        padding: 12px {left_padding} 12px 12px;
                        font-size: 14px;
                        font-family: {self._font_family};
                        background-color: {self._bg_color};
                        margin-top: 2px;
                    }}
                    QLineEdit:focus {{
                        border: 1px solid {self._focused_border_color.name()};
                    }}
                    QLineEdit QToolButton {{
                        padding: 0px;
                        margin-right: -4px;  /* Reduce right margin to bring icon closer */
                    }}
                """)

    def setCursorPosition(self, position: int):
        """Set the cursor position."""
        self.line_edit.setCursorPosition(position)

    def _add_leading_icon_action(self):
        """Add a leading (left side) icon action."""
        # Create the leading icon action
        self.leading_icon_action = QAction(self)
        self.leading_icon_action.setIcon(QIcon(cast(str, self._leading_icon)))

        # Add action to the leading (left) position
        self.line_edit.addAction(self.leading_icon_action, QLineEdit.ActionPosition.LeadingPosition)

    def _add_password_toggle_action(self):
        """Add the password visibility toggle action using QLineEdit's built-in action support."""
        # Create the toggle action
        self.toggle_password_action = QAction(self)
        self.toggle_password_action.setIcon(QIcon(":/assets/material-icons/visibility_off.svg"))
        self.toggle_password_action.triggered.connect(self._toggle_password_visibility)

        # Add action to the trailing (right) position
        self.line_edit.addAction(self.toggle_password_action, QLineEdit.ActionPosition.TrailingPosition)

    def _toggle_password_visibility(self):
        """Toggle password visibility."""
        self._password_visible = not self._password_visible
        if self._password_visible:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_password_action.setIcon(QIcon(":/assets/material-icons/visibility.svg"))
        else:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_password_action.setIcon(QIcon(":/assets/material-icons/visibility_off.svg"))

    def _get_parent_background_color(self):
        """Get the background color from parent widget."""
        if self.parent():
            parent = cast(QWidget, self.parent())
            palette = parent.palette()
            bg_color = palette.color(palette.ColorRole.Window)
            return bg_color.name()
        return colors.BACKGROUND_WINDOW

    def _on_focus_in(self, event):
        """Handle focus in event."""
        self._is_focused = True
        self._animate_label_up()
        self._update_label_color(True)
        self._update_border_color(True)
        QLineEdit.focusInEvent(self.line_edit, event)

    def _on_focus_out(self, event):
        """Handle focus out event."""
        self._is_focused = False
        if not self.line_edit.text():
            self._animate_label_down()
        self._update_label_color(False)
        self._update_border_color(False)
        QLineEdit.focusOutEvent(self.line_edit, event)

    def _on_text_changed(self, text):
        """Handle text changed."""
        if text and not self._is_floating:
            self._animate_label_up()
        elif not text and not self._is_focused:
            self._animate_label_down()

    def _animate_label_up(self):
        """Animate label to floating position."""
        if self._is_floating:
            return
        self._is_floating = True
        self.label_animation.setStartValue(self._label_y_pos)
        self.label_animation.setEndValue(-2)  # Position on the border - adjusted from 13
        self.label_animation.start()

        # Make label smaller
        font = self.label.font()
        font.setPointSize(12)
        self.label.setFont(font)
        self.label.adjustSize()  # Resize label to new font size

    def _animate_label_down(self):
        """Animate label to default position."""
        if not self._is_floating:
            return
        self._is_floating = False
        self.label_animation.setStartValue(self._label_y_pos)
        self.label_animation.setEndValue(19)  # Centered in input - adjusted from 35
        self.label_animation.start()

        # Make label larger
        font = self.label.font()
        font.setPointSize(14)
        self.label.setFont(font)
        self.label.adjustSize()  # Resize label to new font size

    def _update_label_color(self, focused: bool):
        """Update label color based on focus state."""
        color = self._focused_label_color if focused else self._label_color
        self.label.setStyleSheet(f"""
            QLabel {{
                color: {color.name()};
                background-color: {self._bg_color};
                padding: 0 4px;
            }}
        """)

    def _update_border_color(self, focused: bool):
        """Update border color based on focus state."""
        border_color = self._focused_border_color if focused else self._border_color
        left_padding = "40px" if self._has_leading_icon else "12px"
        self.line_edit.setStyleSheet(f"""
            QLineEdit {{
                border: {"2px" if focused else "1px"} solid {border_color.name()};
                border-radius: 6px;
                padding: 12px {left_padding} 12px 12px;
                font-size: 14px;
                background-color: {self._bg_color};
                margin-top: 2px;
            }}
        """)

    def _getLabelYPos(self):
        """Get label Y position."""
        return self._label_y_pos

    def _setLabelYPos(self, value):
        """Set label Y position."""
        self._label_y_pos = value
        label_x_pos = 44 if self._has_leading_icon else 12
        self.label.move(label_x_pos, int(value))

    labelYPos = Property(float, _getLabelYPos, _setLabelYPos)

    # Convenience methods to access line edit properties
    def text(self):
        """Get the text from the line edit."""
        return self.line_edit.text()

    def setText(self, text: str):
        """Set the text in the line edit."""
        self.line_edit.setText(text)
        if text:
            self._animate_label_up()

    def setPlaceholderText(self, text: str):
        """Set the floating label text."""
        self._label_text = text
        self.label.setText(text)
        self.label.adjustSize()  # Resize after text change

    def setReadOnly(self, read_only: bool):
        """Set read-only state."""
        self.line_edit.setReadOnly(read_only)

    def setPasswordMode(self, enabled: bool):
        """Enable or disable password mode."""
        if enabled == self._password_mode:
            return

        self._password_mode = enabled
        if enabled:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._add_password_toggle_action()
        else:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            # Remove the toggle action if it exists
            if hasattr(self, 'toggle_password_action'):
                self.line_edit.removeAction(self.toggle_password_action)

    def isPasswordMode(self) -> bool:
        """Check if password mode is enabled."""
        return self._password_mode

    def setLeadingIcon(self, icon_path: str):
        """
        Set or update the leading icon.

        Args:
            icon_path: Path to the icon file.
        """
        self._leading_icon = icon_path
        was_has_icon = self._has_leading_icon
        self._has_leading_icon = icon_path is not None

        if self._has_leading_icon:
            # Add or update the icon
            if hasattr(self, 'leading_icon_action'):
                self.leading_icon_action.setIcon(QIcon(icon_path))
            else:
                self._add_leading_icon_action()
        elif hasattr(self, 'leading_icon_action'):
            # Remove the icon
            self.line_edit.removeAction(self.leading_icon_action)
            delattr(self, 'leading_icon_action')

        # Update padding and label position if icon state changed
        if was_has_icon != self._has_leading_icon:
            self._update_border_color(self._is_focused)
            label_x_pos = 44 if self._has_leading_icon else 12
            self.label.move(label_x_pos, int(self._label_y_pos))

    def getLeadingIcon(self) -> Optional[str]:
        """Get the current leading icon path."""
        return self._leading_icon

    def hasLeadingIcon(self) -> bool:
        """Check if a leading icon is set."""
        return self._has_leading_icon

    def sizeHint(self):
        """Return the recommended size for this widget."""
        # Use the line edit's size hint as the base, accounting for our minimum height
        line_edit_hint = self.line_edit.sizeHint()
        return QSize(line_edit_hint.width(), max(55, line_edit_hint.height()))

    def minimumSizeHint(self):
        """Return the minimum size for this widget."""
        line_edit_min = self.line_edit.minimumSizeHint()
        return QSize(line_edit_min.width(), 55)

    def clear(self):
        self.line_edit.clear()


class FloatingLabelComboBox(QWidget):
    """
    Custom combo box with floating label animation.
    The label animates up to become an inline label when focused or has selection.
    """

    # Signal emitted when the current selection changes
    currentIndexChanged = Signal(int)
    currentTextChanged = Signal(str)

    def __init__(self, label_text: str = "", parent=None, leading_icon: str | None = None):
        """
        Initialize the FloatingLabelComboBox.

        Args:
            label_text: The placeholder/label text.
            parent: Parent widget.
            leading_icon: Path to icon file to display on the left side (optional).
        """

        self._label_text = label_text
        self._is_floating = False
        self._label_y_pos = 21  # Start position (centered in input)
        self._leading_icon = leading_icon
        self._has_leading_icon = leading_icon is not None

        # Colors
        self._border_color = QColor(colors.BORDER_NEUTRAL)
        self._focused_border_color = QColor(colors.PRIMARY)
        self._label_color = QColor(colors.TEXT_MUTED)
        self._focused_label_color = QColor(colors.PRIMARY)
        self._is_focused = False
        self._bg_color = colors.BACKGROUND_CONTENT

        super().__init__(parent)

        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI components."""
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.setLayout(layout)

        # Container for proper spacing
        self.setMinimumHeight(55)

        # Combo box
        self.combo_box = QComboBox(self)
        self._apply_combo_box_style(focused=False)
        self.combo_box.setMinimumHeight(50)

        # Create custom list view with proper highlighting
        list_view = QListView(self.combo_box)
        list_view.setAutoFillBackground(True)

        # Set palette for hover/selection colors
        palette = list_view.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(self._bg_color))
        palette.setColor(QPalette.ColorRole.Text, QColor(colors.TEXT_MENU))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(colors.BACKGROUND_HIGHLIGHT))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors.TEXT_MENU))
        list_view.setPalette(palette)

        self.combo_box.setView(list_view)

        # Style the popup container
        container = list_view.parentWidget()
        if container:
            container.setAutoFillBackground(True)
            container.setStyleSheet(f"background-color: {self._bg_color}; border: none; border-radius: 6px;")

        layout.addWidget(self.combo_box)

        # Calculate label starting position based on whether there's a leading icon
        label_x_pos = 44 if self._has_leading_icon else 12

        # Floating label (positioned absolutely, not in layout)
        self.label = QLabel(self._label_text, self)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.label.setStyleSheet(f"""
            QLabel {{
                color: {self._label_color.name()};
                background-color: {self._bg_color};
                padding: 0px;
            }}
        """)
        label_font = QFont()
        label_font.setPointSize(14)
        self.label.setFont(label_font)
        self.label.adjustSize()
        self.label.move(label_x_pos, int(self._label_y_pos))
        self.label.raise_()
        self.label.show()

        # Connect signals
        self.combo_box.currentIndexChanged.connect(self._on_index_changed)
        self.combo_box.currentTextChanged.connect(self.currentTextChanged.emit)

        # Override focus events
        self._original_focus_in = self.combo_box.focusInEvent
        self._original_focus_out = self.combo_box.focusOutEvent
        self.combo_box.focusInEvent = self._on_focus_in  # type: ignore
        self.combo_box.focusOutEvent = self._on_focus_out  # type: ignore

        # Animation for label position
        self.label_animation = QPropertyAnimation(self, b"labelYPos")
        self.label_animation.setDuration(200)
        self.label_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Set initial selection to none
        self.combo_box.setCurrentIndex(-1)

    def findText(self, text: str):
        return self.combo_box.findText(text)

    def _apply_combo_box_style(self, focused: bool = False):
        """Apply styling to the combo box."""
        border_color = self._focused_border_color if focused else self._border_color
        border_width = "2px" if focused else "1px"
        left_padding = "40px" if self._has_leading_icon else "12px"

        # Build icon path for leading icon if present
        icon_style = ""
        if self._has_leading_icon and self._leading_icon:
            icon_style = f"""
                QComboBox::before {{
                    image: url({self._leading_icon});
                    width: 20px;
                    height: 20px;
                }}
            """

        self.combo_box.setStyleSheet(f"""
            QComboBox {{
                border: {border_width} solid {border_color.name()};
                border-radius: 6px;
                padding: 12px 32px 12px {left_padding};
                font-size: 14px;
                background-color: {self._bg_color};
                margin-top: 2px;
                color: {colors.TEXT_MENU};
            }}
            QComboBox:focus {{
                border: 2px solid {self._focused_border_color.name()};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 24px;
                border: none;
                padding-right: 8px;
            }}
            QComboBox::down-arrow {{
                image: url(:/assets/material-icons/chevron_down.svg);
                width: 20px;
                height: 20px;
            }}
            QComboBox QAbstractItemView {{
                border: 1px solid {self._border_color.name()};
                background-color: {self._bg_color};
                selection-background-color: {colors.BACKGROUND_SELECTION};
                selection-color: {colors.TEXT_MENU};
                color: {colors.TEXT_MENU};
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 8px 12px;
                min-height: 32px;
                background-color: {self._bg_color};
                color: {colors.TEXT_MENU};
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {colors.BACKGROUND_HIGHLIGHT};
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {colors.BACKGROUND_SELECTION};
                color: {colors.TEXT_MENU};
            }}
            QComboBox QAbstractItemView::item:selected:hover {{
                background-color: {colors.BACKGROUND_HIGHLIGHT};
            }}
            {icon_style}
        """)

    def _on_focus_in(self, event):
        """Handle focus in event."""
        self._is_focused = True
        self._animate_label_up()
        self._update_label_color(True)
        self._apply_combo_box_style(focused=True)
        self._original_focus_in(event)

    def _on_focus_out(self, event):
        """Handle focus out event."""
        self._is_focused = False
        if self.combo_box.currentIndex() == -1 or not self.combo_box.currentText():
            self._animate_label_down()
        self._update_label_color(False)
        self._apply_combo_box_style(focused=False)
        self._original_focus_out(event)

    def _on_index_changed(self, index: int):
        """Handle index changed."""
        if index >= 0 and self.combo_box.currentText():
            self._animate_label_up()
        elif index == -1 or not self.combo_box.currentText():
            self._animate_label_down()
        self.currentIndexChanged.emit(index)

    def _animate_label_up(self):
        """Animate label to floating position."""
        if self._is_floating:
            return
        self._is_floating = True
        self.label_animation.stop()  # Stop any running animation
        self.label_animation.setStartValue(self._label_y_pos)
        self.label_animation.setEndValue(-2)
        self.label_animation.start()

        # Make label smaller
        font = self.label.font()
        font.setPointSize(12)
        self.label.setFont(font)
        self.label.adjustSize()

    def _animate_label_down(self):
        """Animate label to default position."""
        if not self._is_floating:
            return
        self._is_floating = False
        self.label_animation.stop()  # Stop any running animation
        self.label_animation.setStartValue(self._label_y_pos)
        self.label_animation.setEndValue(19)
        self.label_animation.start()

        # Make label larger
        font = self.label.font()
        font.setPointSize(14)
        self.label.setFont(font)
        self.label.adjustSize()

    def _update_label_color(self, focused: bool):
        """Update label color based on focus state."""
        color = self._focused_label_color if focused else self._label_color
        self.label.setStyleSheet(f"""
            QLabel {{
                color: {color.name()};
                background-color: {self._bg_color};
                padding: 0px;
            }}
        """)

    def _getLabelYPos(self):
        """Get label Y position."""
        return self._label_y_pos

    def _setLabelYPos(self, value):
        """Set label Y position."""
        self._label_y_pos = value
        label_x_pos = 44 if self._has_leading_icon else 12
        self.label.move(label_x_pos, int(value))

    labelYPos = Property(float, _getLabelYPos, _setLabelYPos)

    # Convenience methods to access combo box properties
    def addItem(self, text: str, userData=None):
        """Add an item to the combo box."""
        self.combo_box.addItem(text, userData)

    def addItems(self, texts: list):
        """Add multiple items to the combo box."""
        self.combo_box.addItems(texts)

    def insertItem(self, index: int, text: str, userData=None):
        """Insert an item at the specified index."""
        self.combo_box.insertItem(index, text, userData)

    def removeItem(self, index: int):
        """Remove an item at the specified index."""
        self.combo_box.removeItem(index)

    def clear(self):
        """Clear all items from the combo box."""
        self.combo_box.clear()
        self._animate_label_down()

    def currentIndex(self) -> int:
        """Get the current index."""
        return self.combo_box.currentIndex()

    def setCurrentIndex(self, index: int):
        """Set the current index."""
        self.combo_box.setCurrentIndex(index)
        if index >= 0 and self.combo_box.currentText():
            self._animate_label_up()
        elif index == -1:
            self._animate_label_down()

    def currentText(self) -> str:
        """Get the current text."""
        return self.combo_box.currentText()

    def setCurrentText(self, text: str):
        """Set the current text."""
        self.combo_box.setCurrentText(text)
        if text:
            self._animate_label_up()

    def currentData(self):
        """Get the current item's user data."""
        return self.combo_box.currentData()

    def itemText(self, index: int) -> str:
        """Get the text at the specified index."""
        return self.combo_box.itemText(index)

    def itemData(self, index: int):
        """Get the user data at the specified index."""
        return self.combo_box.itemData(index)

    def count(self) -> int:
        """Get the number of items."""
        return self.combo_box.count()

    def setPlaceholderText(self, text: str):
        """Set the floating label text."""
        self._label_text = text
        self.label.setText(text)
        self.label.adjustSize()

    def setEnabled(self, enabled: bool):
        """Enable or disable the combo box."""
        super().setEnabled(enabled)
        self.combo_box.setEnabled(enabled)

    def setLeadingIcon(self, icon_path: str):
        """
        Set or update the leading icon.

        Args:
            icon_path: Path to the icon file.
        """
        self._leading_icon = icon_path
        was_has_icon = self._has_leading_icon
        self._has_leading_icon = icon_path is not None

        # Update styling and label position if icon state changed
        if was_has_icon != self._has_leading_icon:
            self._apply_combo_box_style(self._is_focused)
            label_x_pos = 44 if self._has_leading_icon else 12
            self.label.move(label_x_pos, int(self._label_y_pos))

    def getLeadingIcon(self) -> Optional[str]:
        """Get the current leading icon path."""
        return self._leading_icon

    def hasLeadingIcon(self) -> bool:
        """Check if a leading icon is set."""
        return self._has_leading_icon

    def setEditable(self, editable: bool):
        """Set whether the combo box is editable."""
        self.combo_box.setEditable(editable)

    def isEditable(self) -> bool:
        """Check if the combo box is editable."""
        return self.combo_box.isEditable()

    def sizeHint(self):
        """Return the recommended size for this widget."""
        combo_hint = self.combo_box.sizeHint()
        return QSize(combo_hint.width(), max(55, combo_hint.height()))

    def minimumSizeHint(self):
        """Return the minimum size for this widget."""
        combo_min = self.combo_box.minimumSizeHint()
        return QSize(combo_min.width(), 55)

    def clearFocus(self):
        """Clear focus from the combo box and reset visual state."""
        # Move focus to parent or main window first
        if self.parent():
            self.parent().setFocus()

        self.combo_box.clearFocus()

        # Manually trigger the unfocused visual state
        self._is_focused = False
        self._update_label_color(False)
        self._apply_combo_box_style(focused=False)

        if self.combo_box.currentIndex() == -1 or not self.combo_box.currentText():
            self._animate_label_down()
