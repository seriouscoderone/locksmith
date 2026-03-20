
from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame, QApplication
from keri import help

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import LocksmithIconButton
from locksmith.ui.toolkit.widgets.fields import FloatingLabelComboBox

logger = help.ogler.getLogger(__name__)


class ExtensibleSelectorWidget(QWidget):

    itemAdded = Signal(str, object)
    itemRemoved = Signal(str, object)

    def __init__(self, dropdown_label, selector_dropdown_items, parent=None, max_scrollable_height=300):
        super().__init__(parent)

        # Flag to prevent cascading signals
        self._processing_selection = False
        self._max_scrollable_height = max_scrollable_height

        # Dialog integration
        self._dialog = None
        self._dialog_animation = None
        self._previous_scroll_height = 0
        self._initial_widget_height = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Dropdown setup
        self.selector_dropdown = FloatingLabelComboBox(label_text=dropdown_label)
        self._populate_dropdown(selector_dropdown_items)

        # Scrollable area setup
        self.scrollable_area = QScrollArea()
        self.scrollable_area.setWidgetResizable(True)
        self.scrollable_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scrollable_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scrollable_area.setMinimumHeight(0)
        self.scrollable_area.setMaximumHeight(0)  # Start collapsed

        # Container widget inside scroll area
        self._scroll_container = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_container)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(4)

        self.scrollable_area.setWidget(self._scroll_container)

        # Track selected items: {text: (data, row_widget)}
        self._selected_items = {}

        layout.addWidget(self.selector_dropdown)
        layout.addWidget(self.scrollable_area)
        layout.addStretch()

        self.selector_dropdown.currentIndexChanged.connect(self._on_selection_changed)

    def _populate_dropdown(self, items):
        """Populate dropdown from list of (text, data) tuples or just strings."""
        self.selector_dropdown.clear()
        for item in items:
            if isinstance(item, tuple):
                text, data = item
                self.selector_dropdown.addItem(text, userData=data)
            else:
                self.selector_dropdown.addItem(item)
        self.selector_dropdown.setCurrentIndex(-1)  # No initial selection

    def _on_selection_changed(self, index: int):
        """Handle dropdown selection - move item to scrollable area."""

        # Prevent cascading signals
        if self._processing_selection:
            return

        if index < 0:
            return

        self._processing_selection = True

        try:
            selected_text = self.selector_dropdown.currentText()
            selected_data = self.selector_dropdown.currentData()


            # Remove from dropdown
            self.selector_dropdown.removeItem(index)
            self.selector_dropdown.setCurrentIndex(-1)


            # Add to scrollable area
            self._add_scrollable_item(selected_text, selected_data)

            self.itemAdded.emit(selected_text, selected_data)

        finally:
            self._processing_selection = False
    def _add_scrollable_item(self, text: str, data):
        """Add an item row to the scrollable area."""

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        # Create content widget from data dict, or fallback to label
        if isinstance(data, dict) and ("alias" in data or "name" in data):
            content_widget = self._create_item_widget(data)
        elif isinstance(data, QWidget):
            content_widget = data
        else:
            from PySide6.QtWidgets import QLabel
            content_widget = QLabel(text)

        row_layout.addWidget(content_widget, stretch=1)

        # Copy button (only for dict data with 'oobi')
        if isinstance(data, dict) and "oobi" in data and data["oobi"]:
            copy_button = LocksmithIconButton(icon_path=":/assets/material-icons/content_copy.svg", tooltip="Copy OOBI to clipboard")
            oobi = data["oobi"]
            copy_button.clicked.connect(lambda checked=False, oobi_val=oobi: self._copy_to_clipboard(oobi_val))
            row_layout.addWidget(copy_button, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Remove button - capture text value explicitly with default argument
        remove_button = LocksmithIconButton(icon_path=":/assets/material-icons/close.svg", tooltip="Remove")
        item_text = text  # Capture current value
        remove_button.clicked.connect(lambda checked=False, t=item_text: self._on_remove_clicked(t))
        row_layout.addWidget(remove_button, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Add to end of layout
        self._scroll_layout.addWidget(row_widget)

        # Track the item
        self._selected_items[text] = (data, row_widget)

        # Schedule height update after layout processes
        QTimer.singleShot(0, self._update_scroll_area_height)

    def _on_remove_clicked(self, text: str):
        """Handle remove button click."""
        self._remove_item(text)

    def _copy_to_clipboard(self, text: str):
        """Copy text to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    def _create_item_widget(self, data: dict) -> QWidget:
        """Create a display widget from item data.

        Supports multiple formats: alias/aid, alias/id, name/endpoint.
        """
        from PySide6.QtWidgets import QLabel

        widget = QWidget()
        widget_layout = QVBoxLayout(widget)
        widget_layout.setContentsMargins(8, 4, 8, 4)
        widget_layout.setSpacing(2)

        # Support multiple formats: alias/aid, alias/id, name/endpoint
        primary_text = data.get("alias") or data.get("name", "Unknown")
        secondary_text = data.get("aid") or data.get("id") or data.get("endpoint")

        primary_label = QLabel(primary_text)
        primary_label.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {colors.TEXT_DARK};")
        widget_layout.addWidget(primary_label)

        if secondary_text:
            secondary_label = QLabel(secondary_text)
            secondary_label.setStyleSheet(f"font-size: 11px; color: {colors.TEXT_SUBTLE}; font-family: 'Menlo', 'SF Mono', monospace;")
            widget_layout.addWidget(secondary_label)

        return widget

    def _remove_item(self, text: str):
        """Remove item from scrollable area and restore to dropdown."""

        if text not in self._selected_items:
            logger.warning(f"Item '{text}' not found in selected items!")
            return

        # Prevent cascading signals when we add back to dropdown
        self._processing_selection = True

        try:
            data, row_widget = self._selected_items.pop(text)

            # Remove from scroll area
            self._scroll_layout.removeWidget(row_widget)
            row_widget.setParent(None)
            row_widget.deleteLater()

            # Restore to dropdown
            self.selector_dropdown.addItem(text, userData=data)
            self.selector_dropdown.setCurrentIndex(-1)

            self.itemRemoved.emit(text, data)

            # Schedule height update after layout processes
            QTimer.singleShot(0, self._update_scroll_area_height)

        finally:
            self._processing_selection = False

    def _update_scroll_area_height(self):
        """Adjust scroll area height based on content, up to max."""
        # Force layout to recalculate
        self._scroll_container.adjustSize()

        # Get the actual height needed
        content_height = self._scroll_container.sizeHint().height()

        # Clamp between 0 and max
        target_height = min(content_height, self._max_scrollable_height)

        # Calculate height delta
        old_height = self._previous_scroll_height
        new_height = target_height
        height_delta = new_height - old_height

        # Apply the height constraints
        self.scrollable_area.setMinimumHeight(target_height)
        self.scrollable_area.setMaximumHeight(target_height)

        # Update tracking
        self._previous_scroll_height = new_height

        # Animate dialog if connected and there's a change
        if self._dialog and self._dialog_animation and height_delta != 0:
            # Disable scrollbars during animation
            if hasattr(self._dialog, 'scroll_area'):
                self._dialog.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                self._dialog.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

            current_dialog_height = self._dialog.height()
            target_dialog_height = current_dialog_height + height_delta

            self._dialog_animation.setStartValue(current_dialog_height)
            self._dialog_animation.setEndValue(target_dialog_height)
            self._dialog_animation.start()

    def add_item_programmatically(self, text: str, data):
        """
        Programmatically add an item to the selected area.

        This bypasses the dropdown selection and directly adds the item to the scrollable area.
        Use this when you want to prepopulate selections programmatically.

        Args:
            text: Display text for the item
            data: Associated data for the item
        """
        # Find and remove from dropdown if present
        for i in range(self.selector_dropdown.count()):
            if self.selector_dropdown.itemText(i) == text:
                self.selector_dropdown.removeItem(i)
                break

        # Add to scrollable area
        self._add_scrollable_item(text, data)

        # Emit signal
        self.itemAdded.emit(text, data)

    def get_selected_items(self):
        """Return list of (text, data) for all selected items."""
        return [(text, data) for text, (data, _) in self._selected_items.items()]

    def clear_selections(self):
        """Remove all items from scrollable area and restore to dropdown."""
        for text in list(self._selected_items.keys()):
            self._remove_item(text)

    def set_dialog(self, dialog):
        """
        Connect this widget to a dialog for coordinated height animation.

        Args:
            dialog: LocksmithDialog instance that contains this widget.
        """
        self._dialog = dialog

        # Capture initial widget height (dropdown + collapsed scroll area)
        self._initial_widget_height = self.sizeHint().height()

        # Initialize previous scroll height to current (should be 0)
        self._previous_scroll_height = self.scrollable_area.height()

        # Create animation for dialog height
        self._dialog_animation = QPropertyAnimation(dialog, b"dialogHeight")
        self._dialog_animation.setDuration(300)
        self._dialog_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Connect to animation finished for cleanup
        self._dialog_animation.finished.connect(self._on_animation_finished)

        # Connect to dialog's destroyed signal to clean up references
        dialog.destroyed.connect(self._on_dialog_destroyed)

    def _on_animation_finished(self):
        """Re-enable scrollbars and re-center dialog after animation completes."""
        if self._dialog and hasattr(self._dialog, 'scroll_area'):
            self._dialog.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Re-center dialog
        if self._dialog:
            self._dialog.center_on_parent()

    def _on_dialog_destroyed(self):
        """Clean up references when the dialog is destroyed."""
        self._dialog = None
        self._dialog_animation = None
        self._previous_scroll_height = 0
        self._initial_widget_height = None
