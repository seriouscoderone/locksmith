# -*- encoding: utf-8 -*-
"""
locksmith.ui.toolkit.widgets.region.py module

Region selection widget for witness creation.
"""
from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsOpacityEffect

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import LocksmithIconButton
from locksmith.ui.toolkit.widgets.fields import LocksmithLineEdit


def region_code_to_name(code: str) -> str:
    """Convert region code to display name."""
    match code:
        case "nyc":
            return "New York"
        case "sfo":
            return "San Francisco"
        case "syd":
            return "Sydney"
        case "sgp":
            return "Singapore"
        case "fra":
            return "Frankfurt"
        case _:
            return code


class RegionSelector(QFrame):
    """A selectable region box widget."""

    def __init__(self, parent=None, flag_path=None, resource_name="Witnesses", region_code="nyc", abbrv="wi", disabled=False):
        super().__init__(parent)
        self.flag_path = flag_path
        self.resource_name = resource_name
        self.region_code = region_code
        self.abbrv = abbrv  # Abbreviation for hostname generation (e.g., "wi" for witness, "wa" for watcher)
        self.region_id = None  # Backend region ID (MongoDB ObjectId string)
        self._identifier_alias = ""
        self._hostname_fields: list[LocksmithLineEdit] = []
        self._disabled = False
        self._setup_ui()
        self._connect_signals()

        # Apply initial disabled state if provided
        if disabled:
            self.set_disabled(True)

    def _setup_ui(self):
        """Set up the widget UI."""
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.setStyleSheet(f"border: 1px solid {colors.BACKGROUND_NEUTRAL};")

        # Main layout
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(25, 25, 25, 25)

        # Inner frame (label area)
        self._label_frame = QFrame()
        self._label_frame.setFrameShape(QFrame.Shape.Box)
        self._label_frame.setFrameShadow(QFrame.Shadow.Plain)
        self._label_frame.setStyleSheet(f"border: 1px solid {colors.BLUE_SELECTION}; border-radius: 4px;")
        self._label_frame.setMinimumSize(400, 45)
        self._label_frame.setMaximumSize(400, 45)
        
        self._label_frame_layout = QHBoxLayout(self._label_frame)
        self._label_frame_layout.setContentsMargins(15, 10, 15, 10)

        # Flag icon
        self._icon_label = QLabel()
        icon = QIcon(self.flag_path)
        pixmap = icon.pixmap(24, 24)
        self._icon_label.setPixmap(pixmap)
        self._icon_label.setStyleSheet("border: none;")
        self._label_frame_layout.addWidget(self._icon_label)

        self._label_frame_layout.addSpacing(10)

        self.region_label = QLabel(region_code_to_name(self.region_code))
        self.region_label.setStyleSheet("border: none;")
        self._label_frame_layout.addWidget(self.region_label)

        # Not Available label (hidden by default)
        self._not_available_label = QLabel("(Not Available)")
        self._not_available_label.setStyleSheet(f"border: none; color: {colors.DANGER}; font-size: 11px;")
        self._not_available_label.hide()
        self._label_frame_layout.addSpacing(8)
        self._label_frame_layout.addWidget(self._not_available_label)

        self._label_frame_layout.addStretch()

        self.quantity_label = QLabel("Quantity")
        self.quantity_label.setStyleSheet("font-weight: bold; border: none;")
        self.quantity_sub_label = QLabel("Deploy multiple witnesses for the same identifier")
        self.quantity_sub_label.setStyleSheet(f"color: {colors.TEXT_SUBTLE}; border: none;")

        self._main_layout.addWidget(self._label_frame)
        self._main_layout.addWidget(self.quantity_label)
        self._main_layout.addWidget(self.quantity_sub_label)

        self.resource_counter = LocksmithResourceCounter(resource_name=self.resource_name)
        self.resource_counter.setFixedWidth(230)
        self._main_layout.addWidget(self.resource_counter)

        self._main_layout.addSpacing(20)

        self.hostname_label = QLabel("Hostname")
        self.hostname_label.setStyleSheet("font-weight: bold; border: none;")
        self._main_layout.addWidget(self.hostname_label)

        self.hostname_sub_label = QLabel("Give your witnesses an identifying name you will remember them by.")
        self.hostname_sub_label.setStyleSheet(f"color: {colors.TEXT_SUBTLE}; font-size: 11px; border: none;")
        self._main_layout.addWidget(self.hostname_sub_label)

        # Container for hostname fields
        self._hostname_container = QVBoxLayout()
        self._hostname_container.setSpacing(10)
        self._main_layout.addLayout(self._hostname_container)

        self._main_layout.addSpacing(20)
        self._main_layout.addStretch()

    def _connect_signals(self):
        """Connect signals from child widgets."""
        self.resource_counter.count_changed.connect(self._on_count_changed)

    def set_disabled(self, disabled: bool):
        """
        Set the disabled state of the region selector.
        
        Args:
            disabled: True to disable the selector, False to enable it.
        """
        if self._disabled == disabled:
            return
            
        self._disabled = disabled
        
        if disabled:
            # Reset counter and clear hostnames
            self.reset()

            # Update label frame to disabled style
            self._label_frame.setStyleSheet(f"border: 1px solid {colors.BACKGROUND_NEUTRAL}; border-radius: 4px;")
            self.region_label.setStyleSheet(f"border: none; color: {colors.BACKGROUND_NEUTRAL};")
            
            # Show not available label
            self._not_available_label.show()
            
            # Grey out the flag icon with opacity effect
            opacity_effect = QGraphicsOpacityEffect()
            opacity_effect.setOpacity(0.4)
            self._icon_label.setGraphicsEffect(opacity_effect)
        else:
            # Restore normal style
            self._label_frame.setStyleSheet(f"border: 1px solid {colors.BLUE_SELECTION}; border-radius: 4px;")
            self.region_label.setStyleSheet(f"border: none; color: {colors.BLACK};")
            
            # Hide not available label
            self._not_available_label.hide()
            
            # Remove opacity effect from flag icon
            self._icon_label.setGraphicsEffect(None)
        
        # Update resource counter disabled state
        self.resource_counter.set_disabled(disabled)

    def is_disabled(self) -> bool:
        """Return whether the region selector is disabled."""
        return self._disabled

    def _update_selection_style(self, is_selected: bool):
        """Update the visual style based on selection state."""
        # Don't update selection style when disabled
        if self._disabled:
            return
            
        if is_selected:
            self._label_frame.setStyleSheet(
                f"border: 1px solid {colors.BLUE_SELECTION}; border-radius: 4px; background-color: {colors.BLUE_SELECTION_BG};"
            )
            self.region_label.setStyleSheet(f"border: none; color: {colors.BLUE_SELECTION};")
        else:
            self._label_frame.setStyleSheet(
                f"border: 1px solid {colors.BLUE_SELECTION}; border-radius: 4px; background-color: transparent;"
            )
            self.region_label.setStyleSheet(f"border: none; color: {colors.BLACK};")

    def _on_count_changed(self, new_count: int):
        """Handle count changes from the resource counter."""
        current_count = len(self._hostname_fields)
        
        # Update visual style based on count
        self._update_selection_style(new_count > 0)
        
        if new_count > current_count:
            # Add new fields
            for i in range(current_count, new_count):
                self._add_hostname_field(i + 1)
        elif new_count < current_count:
            # Remove excess fields
            for _ in range(current_count - new_count):
                self._remove_last_hostname_field()

    def _generate_hostname(self, index: int) -> str:
        """Generate a hostname for the given index."""
        # Format: {alias}-{abbrv}-{region_code}-{index:02d}
        # Default alias based on resource type if not set
        if self._identifier_alias:
            alias = self._identifier_alias
        else:
            alias = "watcher" if self.abbrv == "wa" else "witness"
        return f"{alias}-{self.abbrv}-{self.region_code}-{index:02d}"

    def _add_hostname_field(self, index: int):
        """Add a new hostname field."""
        hostname = self._generate_hostname(index)
        field = LocksmithLineEdit(placeholder_text="Hostname")
        field.setText(hostname)
        field.setFixedWidth(400)
        
        self._hostname_fields.append(field)
        self._hostname_container.addWidget(field)

    def _remove_last_hostname_field(self):
        """Remove the last hostname field."""
        if self._hostname_fields:
            field = self._hostname_fields.pop()
            self._hostname_container.removeWidget(field)
            field.deleteLater()

    def set_identifier_alias(self, alias: str):
        """
        Set the identifier alias used for generating hostnames.
        
        Args:
            alias: The identifier alias to use in hostname generation.
        """
        self._identifier_alias = alias
        # Update existing hostname fields with new alias
        self._refresh_hostnames()

    def _refresh_hostnames(self):
        """Refresh all hostname fields with current alias."""
        for i, field in enumerate(self._hostname_fields):
            field.setText(self._generate_hostname(i + 1))

    def get_hostnames(self) -> list[str]:
        """Return the list of hostname values entered by the user."""
        return [field.text() for field in self._hostname_fields]

    def set_region_id(self, region_id: str):
        """
        Set the backend region ID for this selector.

        Args:
            region_id: The MongoDB ObjectId string from the backend API.
        """
        self.region_id = region_id

    def get_count(self) -> int:
        """Return the current witness count for this region."""
        return self.resource_counter.get_count()

    def has_witnesses(self) -> bool:
        """Return True if this region has witnesses selected."""
        return self.get_count() > 0

    def get_witness_data(self) -> dict:
        """
        Get witness provisioning data for this region.

        Returns:
            Dict with 'region_id', 'count', and 'hostnames' keys.
            Returns None if no witnesses are selected.
        """
        count = self.get_count()
        if count == 0:
            return None

        return {
            'region_id': self.region_id,
            'region_code': self.region_code,
            'count': count,
            'hostnames': self.get_hostnames()
        }

    def set_counter_disabled(self, disabled: bool):
        """
        Disable or enable the resource counter (increment/decrement buttons).

        Args:
            disabled: True to disable the counter, False to enable it.
        """
        self.resource_counter.set_disabled(disabled)

    def set_hostname_fields_readonly(self, readonly: bool):
        """
        Set all hostname fields to read-only or editable.

        Args:
            readonly: True to make fields read-only, False to make them editable.
        """
        for field in self._hostname_fields:
            field.setReadOnly(readonly)

    def reset(self):
        """Reset the region selector to initial state."""
        self._identifier_alias = ""
        self.resource_counter.set_count(0)
        # Fields will be removed by the count_changed signal


class LocksmithResourceCounter(QFrame):
    """A counter widget with plus/minus buttons."""
    
    count_changed = Signal(int)  # Emitted when count changes
    
    def __init__(self, parent=None, resource_name=None, disabled=False):
        super().__init__(parent)
        self.resource_name = resource_name
        self._count = 0
        self._disabled = False
        self._setup_ui()
        self._connect_signals()
        
        # Apply initial disabled state if provided
        if disabled:
            self.set_disabled(True)

    def _setup_ui(self):
        """Set up the widget UI."""
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.setStyleSheet(f"border: 1px solid {colors.BACKGROUND_NEUTRAL}; border-radius: 4px;")

        self.minus_icon = LocksmithIconButton(":/assets/material-icons/subtract.svg", tooltip=f"Add {self.resource_name}", border=True)
        self.plus_icon = LocksmithIconButton(":/assets/material-icons/add.svg", tooltip=f"Remove {self.resource_name}", border=True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(0)

        layout.addWidget(self.minus_icon)
        layout.addSpacing(15)
        layout.addStretch()

        self.count_label = QLabel("0")
        self.count_label.setStyleSheet("border: none;")
        layout.addWidget(self.count_label)
        layout.addSpacing(8)

        self.resource_label = QLabel(self.resource_name)
        self.resource_label.setStyleSheet("border: none;")
        layout.addWidget(self.resource_label)
        layout.addSpacing(15)
        layout.addStretch()

        layout.addWidget(self.plus_icon)

    def _connect_signals(self):
        """Connect button signals to slots."""
        self.plus_icon.clicked.connect(self._increment)
        self.minus_icon.clicked.connect(self._decrement)

    def set_disabled(self, disabled: bool):
        """
        Set the disabled state of the resource counter.
        
        Args:
            disabled: True to disable the counter, False to enable it.
        """
        if self._disabled == disabled:
            return
            
        self._disabled = disabled
        
        # Disable/enable the buttons
        self.plus_icon.setEnabled(not disabled)
        self.minus_icon.setEnabled(not disabled)
        
        if disabled:
            # Grey out the labels
            self.count_label.setStyleSheet(f"border: none; color: {colors.BACKGROUND_NEUTRAL};")
            self.resource_label.setStyleSheet(f"border: none; color: {colors.BACKGROUND_NEUTRAL};")
        else:
            # Restore normal label colors
            self.count_label.setStyleSheet("border: none;")
            self.resource_label.setStyleSheet("border: none;")

    def is_disabled(self) -> bool:
        """Return whether the resource counter is disabled."""
        return self._disabled

    def _increment(self):
        """Increment the count."""
        if self._disabled:
            return
        self._count += 1
        self.count_label.setText(str(self._count))
        self.count_changed.emit(self._count)

    def _decrement(self):
        """Decrement the count, but not below 0."""
        if self._disabled:
            return
        if self._count > 0:
            self._count -= 1
            self.count_label.setText(str(self._count))
            self.count_changed.emit(self._count)

    def get_count(self) -> int:
        """Return the current count value."""
        return self._count

    def set_count(self, value: int):
        """Set the count to a specific value (minimum 0)."""
        self._count = max(0, value)
        self.count_label.setText(str(self._count))
        self.count_changed.emit(self._count)

