# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.credentials.schema.view module

Dialog for viewing credential schema details
"""
import json
import logging
from typing import TYPE_CHECKING

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout
)

from locksmith.ui.toolkit.widgets import (
    LocksmithInvertedButton
)
from locksmith.ui.toolkit.widgets.buttons import LocksmithCopyButton
from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog
from locksmith.ui.toolkit.widgets.fields import (
    LocksmithLineEdit,
    LocksmithPlainTextEdit
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ViewSchemaDialog(LocksmithDialog):
    """Dialog for viewing credential schema details."""
    def __init__(self, icon_path, app, schema_said, parent=None):
        """
        Initialize the ViewSchemaDialog.

        Args:
            icon_path: Path to the schema icon
            app: Application instance
            schema_said: SAID of the schema to view
            parent: Parent widget (typically VaultPage)
        """
        self.app = app
        self.schema_said = schema_said

        # Get the schema details from the app
        try:
            schemer = self.app.vault.hby.db.schema.get(keys=(schema_said,))
            if not schemer:
                raise ValueError(f"Schema with SAID {schema_said} not found")

            self.schemer = schemer
            self.schema = schemer.sed
        except Exception as e:
            logger.error(f"Error loading schema: {e}")
            raise

        # Create title content FIRST (before super().__init__)
        title_content_widget = QWidget()
        title_content = QHBoxLayout()
        icon = QIcon(icon_path)
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(32, 32))
        icon_label.setFixedSize(32, 32)
        title_content.addWidget(icon_label)

        title_label = QLabel(f"  {self.schema.get('title', 'Untitled Schema')}")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        title_content.addWidget(title_label)
        title_content_widget.setLayout(title_content)

        # Create content widget
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #F8F9FF;")
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(15)

        # Create button row
        button_row = QHBoxLayout()
        self.close_button = LocksmithInvertedButton("Close")
        button_row.addWidget(self.close_button)

        # Initialize parent dialog EARLY
        super().__init__(
            parent=parent,
            title_content=title_content_widget,
            show_close_button=True,
            content=content_widget,
            buttons=button_row,
            show_overlay=False
        )

        # Set initial size
        self.setFixedSize(520, 700)

        # NOW build sections (after super().__init__ has been called)
        # SAID Section
        self._build_said_section(layout)

        # Schema Name Section
        self._build_name_section(layout)

        # Version Section
        self._build_version_section(layout)

        # Issuable section
        self._build_issue_section(layout)
        
        # Type Section
        self._build_type_section(layout)

        # Description Section
        self._build_description_section(layout)

        # Schema Content Section (JSON)
        self._build_schema_content_section(layout)

        layout.addStretch()

        # Connect buttons
        self.close_button.clicked.connect(self.close)

    def _build_said_section(self, layout):
        """Build the SAID section with copy button."""
        said_label_row = QHBoxLayout()
        said_label_row.setSpacing(5)
        said_label = QLabel("SAID")
        said_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        said_label_row.addWidget(said_label)

        self.copy_said_button = LocksmithCopyButton(copy_content=self.schema_said)
        self.copy_said_button.setFixedHeight(36)
        said_label_row.addWidget(self.copy_said_button)
        said_label_row.addStretch()
        layout.addLayout(said_label_row)

        self.said_field = LocksmithLineEdit("SAID")
        self.said_field.setText(self.schema_said)
        self.said_field.setReadOnly(True)
        self.said_field.setCursorPosition(0)
        self.said_field.setMinimumWidth(420)
        layout.addWidget(self.said_field)

    def _build_name_section(self, layout):
        """Build the schema name section."""
        name_label = QLabel("Schema Name")
        name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(name_label)

        self.name_field = LocksmithLineEdit("Schema Name")
        self.name_field.setText(self.schema.get('title', 'N/A'))
        self.name_field.setReadOnly(True)
        self.name_field.setCursorPosition(0)
        self.name_field.setMinimumWidth(420)
        layout.addWidget(self.name_field)

    def _build_version_section(self, layout):
        """Build the version section."""
        version_label = QLabel("Version")
        version_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(version_label)

        self.version_field = LocksmithLineEdit("Version")
        self.version_field.setText(self.schema.get('version', 'N/A'))
        self.version_field.setReadOnly(True)
        self.version_field.setCursorPosition(0)
        self.version_field.setMinimumWidth(420)
        layout.addWidget(self.version_field)

    def _build_type_section(self, layout):
        """Build the schema type section."""
        type_label = QLabel("Schema Type")
        type_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(type_label)

        self.type_field = LocksmithLineEdit("Schema Type")
        self.type_field.setText(self.schema.get('$schema', 'N/A'))
        self.type_field.setReadOnly(True)
        self.type_field.setCursorPosition(0)
        self.type_field.setMinimumWidth(420)
        layout.addWidget(self.type_field)

    def _build_issue_section(self, layout):
        """Build the schema type section."""
        issue_lable = QLabel("Can Issue Credentials with this Schema")
        issue_lable.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(issue_lable)

        self.issue_field = LocksmithLineEdit("Schema Type")
        self.issue_field.setText("Yes" if self.app.vault.rgy.registryByName(self.schema_said) else "No")
        self.issue_field.setReadOnly(True)
        self.issue_field.setCursorPosition(0)
        self.issue_field.setMinimumWidth(420)
        layout.addWidget(self.issue_field)

    def _build_description_section(self, layout):
        """Build the description section."""
        description_label = QLabel("Description")
        description_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(description_label)

        self.description_field = LocksmithPlainTextEdit()
        self.description_field.setPlainText(self.schema.get('description', 'No description available'))
        self.description_field.setReadOnly(True)
        self.description_field.setFixedHeight(80)
        self.description_field.setMaximumWidth(480)
        layout.addWidget(self.description_field)

    def _build_schema_content_section(self, layout):
        """Build the schema content section showing full JSON."""
        content_label_row = QHBoxLayout()
        content_label_row.setSpacing(5)
        content_label = QLabel("Schema Content")
        content_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        content_label_row.addWidget(content_label)

        # Add copy button for schema content
        schema_json = json.dumps(self.schema, indent=2)
        self.copy_content_button = LocksmithCopyButton(copy_content=schema_json)
        self.copy_content_button.setFixedHeight(36)
        content_label_row.addWidget(self.copy_content_button)
        content_label_row.addStretch()
        layout.addLayout(content_label_row)

        self.content_field = LocksmithPlainTextEdit()
        self.content_field.setPlainText(schema_json)
        self.content_field.setReadOnly(True)
        self.content_field.setFixedHeight(200)
        self.content_field.setMaximumWidth(480)
        # Use monospace font for JSON
        font = self.content_field.font()
        font.setFamily("Menlo, SF Mono, Monaco, Courier New, monospace")
        font.setPointSize(11)
        self.content_field.setFont(font)
        layout.addWidget(self.content_field)
