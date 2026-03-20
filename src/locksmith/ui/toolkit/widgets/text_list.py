# -*- encoding: utf-8 -*-
"""
locksmith.ui.toolkit.widgets.text_list module

Widget for managing a list of text items with add/remove functionality.
"""
from keri import help
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame
)

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.fields import FloatingLabelLineEdit
from locksmith.ui.toolkit.widgets.buttons import LocksmithIconButton

logger = help.ogler.getLogger(__name__)


class LocksmithTextListWidget(QWidget):
    """
    Widget for managing a list of text items with add/remove functionality.

    Features:
    - Text input field with customizable label
    - Add button to append items to list
    - Scrollable list of items with remove buttons
    - Duplicate prevention
    - Signal emission for parent notification
    """

    # Signals (following PySide6 Signal pattern)
    itemAdded = Signal(str)      # Emitted when item is added
    itemRemoved = Signal(str)    # Emitted when item is removed
    itemsChanged = Signal(list)  # Emitted when list changes

    def __init__(self, label: str = "Enter text", parent=None, max_height: int = 300):
        """
        Initialize the text list widget.

        Args:
            label: Placeholder/label text for input field
            parent: Parent widget
            max_height: Maximum height for scrollable list area
        """
        super().__init__(parent)

        # State management
        self._items: dict[str, QWidget] = {}  # text -> row_widget mapping
        self._max_height = max_height
        self._dialog = None  # For dialog integration

        self._setup_ui(label)
        self._apply_styling()

    def _setup_ui(self, label: str):
        """Setup the UI structure."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # Input row: text field + add button
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.text_input = FloatingLabelLineEdit(label)
        # self.text_input.returnPressed.connect(self._add_item)  # Enter key support
        input_row.addWidget(self.text_input)

        self.add_button = LocksmithIconButton(
            icon_path=":/assets/material-icons/add.svg",
            tooltip="Add item",
            icon_size=24
        )
        self.add_button.setFixedHeight(50)  # Match input field height
        self.add_button.clicked.connect(self._add_item)
        input_row.addWidget(self.add_button)

        main_layout.addLayout(input_row)

        # Scrollable list area
        self.list_area = QScrollArea()
        self.list_area.setWidgetResizable(True)
        self.list_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_area.setFixedHeight(self._max_height)
        self.list_area.setMaximumHeight(self._max_height)
        self.list_area.setFrameShape(QFrame.Shape.NoFrame)

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()  # Push items to top

        self.list_area.setWidget(self.list_container)
        main_layout.addWidget(self.list_area)

        # Hide list area initially
        self._update_scrollbar_visibility()

    def _apply_styling(self):
        """Apply consistent styling to the widget."""
        self.setStyleSheet(f"""
            QScrollArea {{
                border: 1px solid {colors.BORDER};
                border-radius: 6px;
                background-color: {colors.BACKGROUND_CONTENT};
            }}
        """)

    def _update_scrollbar_visibility(self):
        """Update scrollbar visibility based on content."""
        if len(self._items) == 0:
            self.list_area.hide()
        else:
            self.list_area.show()

    def _add_item(self):
        """Handle add button click or Enter key press."""
        text = self.text_input.text().strip()

        # Validate: not empty and not duplicate
        if not text:
            return

        if text in self._items:
            # Already exists - log at debug level
            logger.debug(f"Item '{text}' already exists in list")
            return

        # Add to list
        self._add_item_to_list(text)

        # Clear input
        self.text_input.clear()
        self.text_input.setFocus()

        # Emit signals
        self.itemAdded.emit(text)
        self.itemsChanged.emit(self.get_items())

        # Resize dialog if integrated
        if self._dialog:
            self._dialog._resize_to_content()

    def _add_item_to_list(self, text: str):
        """Create and add a row widget for the item."""
        # Create row widget
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(8, 4, 8, 4)
        row_layout.setSpacing(8)

        # Item label
        label = QLabel(text)
        label.setStyleSheet(f"font-size: 13px; color: {colors.TEXT_DARK};")
        label.setWordWrap(False)
        row_layout.addWidget(label, stretch=1)

        # Remove button
        remove_button = LocksmithIconButton(
            icon_path=":/assets/material-icons/close.svg",
            tooltip="Remove item",
            icon_size=20
        )
        remove_button.setFixedSize(24, 24)
        remove_button.clicked.connect(lambda: self._remove_item(text))
        row_layout.addWidget(remove_button, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Style the row
        row_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {colors.BACKGROUND_NEUTRAL};
                border-radius: 4px;
            }}
            QWidget:hover {{
                background-color: {colors.BACKGROUND_NEUTRAL_HOVER};
            }}
        """)

        # Add to layout (before stretch)
        insert_index = self.list_layout.count() - 1  # Before stretch
        self.list_layout.insertWidget(insert_index, row_widget)

        # Store reference
        self._items[text] = row_widget

        # Update visibility
        self._update_scrollbar_visibility()

    def _remove_item(self, text: str):
        """Remove an item from the list."""
        if text not in self._items:
            return

        # Get and remove widget
        row_widget = self._items.pop(text)
        self.list_layout.removeWidget(row_widget)
        row_widget.deleteLater()

        # Update visibility
        self._update_scrollbar_visibility()

        # Emit signals
        self.itemRemoved.emit(text)
        self.itemsChanged.emit(self.get_items())

        # Resize dialog if integrated
        if self._dialog:
            self._dialog._resize_to_content()

    def get_items(self) -> list[str]:
        """
        Get all items in the list.

        Returns:
            list[str]: List of item texts in insertion order
        """
        return list(self._items.keys())

    @property
    def items(self) -> list[str]:
        """
        Property accessor for getting items.

        Returns:
            list[str]: List of item texts
        """
        return self.get_items()

    def set_items(self, items: list[str]):
        """
        Set items programmatically.

        Args:
            items: List of text items to set
        """
        # Clear existing
        self.clear()

        # Add new items
        for item in items:
            if item.strip():  # Skip empty strings
                self._add_item_to_list(item.strip())

        # Emit change signal
        self.itemsChanged.emit(self.get_items())

    def clear(self):
        """Remove all items from the list."""
        # Remove all widgets
        for text, widget in list(self._items.items()):
            self.list_layout.removeWidget(widget)
            widget.deleteLater()

        self._items.clear()
        self._update_scrollbar_visibility()
        self.itemsChanged.emit([])

        # Resize dialog if integrated
        if self._dialog:
            self._dialog._resize_to_content()

    def set_dialog(self, dialog):
        """
        Set parent dialog for coordinated animations.

        Args:
            dialog: LocksmithDialog instance
        """
        self._dialog = dialog
