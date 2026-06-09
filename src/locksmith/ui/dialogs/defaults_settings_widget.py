"""Defaults for new vaults — extracted from SettingsPage so the toolbar
Settings dialog (app-wide) and the vault Settings sidebar (per-vault)
hold different concerns. Binds to ``LocksmithConfig.get_instance()``
exactly as the original section did."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from keri import help

from locksmith.core.configing import LocksmithConfig
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import (
    LocksmithIconButton,
    LocksmithRadioButton,
)
from locksmith.ui.toolkit.widgets.fields import FloatingLabelLineEdit
from locksmith.ui.toolkit.widgets.toggle import ToggleSwitch

logger = help.ogler.getLogger(__name__)


class DefaultsSettingsWidget(QWidget):
    """Default settings for new vaults and identifiers.

    Owns the temp datastore toggle, base-dir field, tier radio group,
    algo radio group, and salt field. Writes through to
    ``LocksmithConfig.get_instance()`` on every change, matching the
    semantics of the original ``SettingsPage._create_general_settings_section``.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("defaultsSettingsWidget")
        self.config: LocksmithConfig = LocksmithConfig.get_instance()
        self._build_layout()

    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        header = QLabel("Defaults for new vaults")
        header.setObjectName("defaultsSettingsWidget.header")
        header.setStyleSheet(
            f"color: {colors.TEXT_PRIMARY}; font-size: 14px; font-weight: bold;"
        )
        outer.addWidget(header)

        subheader = QLabel("Default settings applied when creating a new vault or identifier")
        subheader.setObjectName("defaultsSettingsWidget.subheader")
        subheader.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 12px; margin-bottom: 10px;"
        )
        outer.addWidget(subheader)

        container = QFrame()
        container.setObjectName("defaultsSettingsContainer")
        container.setStyleSheet(f"""
            #defaultsSettingsContainer {{
                background-color: {colors.WHITE};
                border: 1px solid {colors.BORDER_TABLE};
                border-radius: 24px;
            }}
            QWidget {{ background-color: transparent; }}
            QRadioButton {{ spacing: 8px; color: {colors.TOGGLE_TRACK_ON}; }}
            QRadioButton::indicator {{
                width: 14px; height: 14px;
                border-radius: 8px;
                border: 2px solid {colors.BLUE_ACCENT};
                background-color: transparent;
            }}
            QRadioButton::indicator:checked {{
                background-color: {colors.BLUE_ACCENT};
            }}
            QLineEdit {{
                border: 2px solid {colors.BORDER_TABLE};
                border-radius: 6px;
                padding: 5px;
                color: {colors.TOGGLE_TRACK_ON};
            }}
            QLineEdit:focus {{
                border: 2px solid {colors.BLUE_ACCENT};
            }}
        """)
        body = QVBoxLayout(container)
        body.setContentsMargins(25, 25, 25, 25)
        body.setSpacing(20)

        self._build_temp_row(body)
        self._build_base_dir_row(body)
        self._build_tier_row(body)
        self._build_algo_row(body)
        self._build_salt_row(body)

        outer.addWidget(container)
        self._update_salt_visibility()

    def _build_temp_row(self, parent_layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(20)
        label = QLabel("Temporary Datastore")
        label.setFixedWidth(220)
        label.setStyleSheet(f"font-size: 16px; color: {colors.TEXT_PRIMARY};")
        row.addWidget(label)

        self.temp_toggle = ToggleSwitch()
        self.temp_toggle.setObjectName("defaultsSettingsWidget.tempToggle")
        self.temp_toggle.setChecked(self.config.temp)
        self.temp_toggle.toggled.connect(self._on_temp_changed)
        row.addWidget(self.temp_toggle)

        row.addStretch()
        parent_layout.addLayout(row)

    def _build_base_dir_row(self, parent_layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(20)
        label = QLabel("Database Directory Base")
        label.setFixedWidth(220)
        label.setStyleSheet(f"font-size: 16px; color: {colors.TEXT_PRIMARY};")
        row.addWidget(label)

        self.base_dir_field = FloatingLabelLineEdit("Directory")
        self.base_dir_field.setObjectName("defaultsSettingsWidget.baseDirField")
        self.base_dir_field.setText(self.config.base)
        self.base_dir_field.setFixedWidth(300)
        self.base_dir_field.line_edit.textChanged.connect(self._on_base_changed)
        row.addWidget(self.base_dir_field)

        row.addStretch()
        parent_layout.addLayout(row)

    def _build_tier_row(self, parent_layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(20)
        label = QLabel("Cryptographic Key Strength")
        label.setFixedWidth(220)
        label.setStyleSheet(f"font-size: 16px; color: {colors.TEXT_PRIMARY};")
        row.addWidget(label)

        self.tier_group = QButtonGroup(self)
        tier_layout = QHBoxLayout()
        tier_layout.setSpacing(15)

        self.tier_low = LocksmithRadioButton("Low")
        self.tier_low.setObjectName("defaultsSettingsWidget.tierLow")
        self.tier_med = LocksmithRadioButton("Medium")
        self.tier_med.setObjectName("defaultsSettingsWidget.tierMedium")
        self.tier_high = LocksmithRadioButton("High")
        self.tier_high.setObjectName("defaultsSettingsWidget.tierHigh")

        self.tier_group.addButton(self.tier_low)
        self.tier_group.addButton(self.tier_med)
        self.tier_group.addButton(self.tier_high)

        if self.config.tier == "med":
            self.tier_med.setChecked(True)
        elif self.config.tier == "high":
            self.tier_high.setChecked(True)
        else:
            self.tier_low.setChecked(True)

        tier_layout.addWidget(self.tier_low)
        tier_layout.addWidget(self.tier_med)
        tier_layout.addWidget(self.tier_high)
        # buttonToggled (vs buttonClicked) fires for programmatic setChecked()
        # too, so config stays in sync regardless of how the radio was flipped.
        self.tier_group.buttonToggled.connect(self._on_tier_changed)

        row.addLayout(tier_layout)
        row.addStretch()
        parent_layout.addLayout(row)

    def _build_algo_row(self, parent_layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(20)
        label = QLabel("Default Key Generation")
        label.setFixedWidth(220)
        label.setStyleSheet(f"font-size: 16px; color: {colors.TEXT_PRIMARY};")
        row.addWidget(label)

        self.algo_group = QButtonGroup(self)
        algo_layout = QHBoxLayout()
        algo_layout.setSpacing(15)

        self.algo_salty = LocksmithRadioButton("Salty")
        self.algo_salty.setObjectName("defaultsSettingsWidget.algoSalty")
        self.algo_randy = LocksmithRadioButton("Randy")
        self.algo_randy.setObjectName("defaultsSettingsWidget.algoRandy")

        self.algo_group.addButton(self.algo_salty)
        self.algo_group.addButton(self.algo_randy)

        if self.config.algo == "salty":
            self.algo_salty.setChecked(True)
        else:
            self.algo_randy.setChecked(True)

        algo_layout.addWidget(self.algo_salty)
        algo_layout.addWidget(self.algo_randy)
        # buttonToggled (vs buttonClicked) fires for programmatic setChecked()
        # too, so config stays in sync regardless of how the radio was flipped.
        self.algo_group.buttonToggled.connect(self._on_algo_changed)

        row.addLayout(algo_layout)
        row.addStretch()
        parent_layout.addLayout(row)

    def _build_salt_row(self, parent_layout: QVBoxLayout) -> None:
        self.salt_row_widget = QWidget()
        self.salt_row_widget.setObjectName("defaultsSettingsWidget.saltRow")
        self.salt_row_widget.setStyleSheet("background-color: transparent;")
        row = QHBoxLayout(self.salt_row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(20)

        label = QLabel("Key Salt")
        label.setFixedWidth(220)
        label.setStyleSheet(f"font-size: 16px; color: {colors.TEXT_PRIMARY};")
        row.addWidget(label)

        self.salt_field = FloatingLabelLineEdit("Salt", password_mode=True)
        self.salt_field.setObjectName("defaultsSettingsWidget.saltField")
        self.salt_field.setText(self.config.salt)
        self.salt_field.setFixedWidth(300)
        self.salt_field.line_edit.textChanged.connect(self._on_salt_changed)
        row.addWidget(self.salt_field)

        resalt_button = LocksmithIconButton(
            icon_path=":/assets/material-icons/refresh.svg",
            tooltip="Generate new salt",
        )
        resalt_button.setObjectName("defaultsSettingsWidget.resaltButton")
        resalt_button.clicked.connect(self._on_resalt)
        row.addWidget(resalt_button)

        row.addStretch()
        parent_layout.addWidget(self.salt_row_widget)

    def _on_temp_changed(self, checked: bool) -> None:
        self.config.temp = checked
        logger.info("[defaults] temp=%s", self.config.temp)

    def _on_base_changed(self, text: str) -> None:
        self.config.base = text
        logger.info("[defaults] base=%s", self.config.base)

    def _on_tier_changed(self) -> None:
        if self.tier_low.isChecked():
            self.config.tier = "low"
        elif self.tier_med.isChecked():
            self.config.tier = "med"
        elif self.tier_high.isChecked():
            self.config.tier = "high"
        logger.info("[defaults] tier=%s", self.config.tier)

    def _on_algo_changed(self) -> None:
        if self.algo_salty.isChecked():
            self.config.algo = "salty"
        else:
            self.config.algo = "randy"
        logger.info("[defaults] algo=%s", self.config.algo)
        self._update_salt_visibility()

    def _update_salt_visibility(self) -> None:
        self.salt_row_widget.setVisible(self.config.algo == "salty")

    def _on_salt_changed(self, text: str) -> None:
        self.config.salt = text
        logger.info("[defaults] salt updated")

    def _on_resalt(self) -> None:
        new_salt = self.config.resalt()
        self.salt_field.setText(new_salt)
        logger.info("[defaults] new salt generated")
