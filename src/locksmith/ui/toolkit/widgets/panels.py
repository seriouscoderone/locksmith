# -*- encoding: utf-8 -*-
"""
locksmith.ui.toolkit.widgets.panels module

Generic panel widgets including QR code panels for witness OOBI and OTP authentication.
Also includes collapsible panels and flow layout for watcher status display.
"""
import io
from typing import Any, Dict, Optional

import qrcode
from PySide6.QtCore import Qt, QSize, QRect, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QImage, QIcon
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QLayout, QLayoutItem, QSizePolicy
)
from keri import help

from locksmith.ui import colors
from locksmith.ui.colors import BORDER, BACKGROUND_CONTENT
from locksmith.ui.styles import get_monospace_font_family

logger = help.ogler.getLogger(__name__)

class LocksmithQRPanel(QFrame):
    """
    A panel widget that displays QR code information for witnesses.

    Used for both OOBI (witness connection) and OTP (authentication) purposes.
    Contains witness metadata (name, EID), controller info, URL with copy button,
    and a QR code with optional toggle visibility.

    Args:
        number: Display number/index for the panel (e.g., "1", "2", or custom text)
        witness_name: The name/alias of the witness
        witness_eid: The witness's enterprise identifier (EID)
        controller_alias: The controller's alias/name
        controller_aid: The controller's AID (autonomous identifier)
        url: The URL to encode in the QR code and display
        qr_visible: Whether QR code should be visible initially (default: True)
        parent: Parent widget
    """

    def __init__(
        self,
        number: str,
        witness_name: str,
        witness_eid: str,
        controller_alias: str,
        controller_aid: str,
        url: str,
        qr_visible: bool = True,
        parent=None
    ):
        super().__init__(parent)

        self.number = number
        self.witness_name = witness_name
        self.witness_eid = witness_eid
        self.controller_alias = controller_alias
        self.controller_aid = controller_aid
        self.url = url
        self._qr_visible = qr_visible

        # Generate QR code
        self.qr_pixmap = self._generate_qr_code(url)

        self.mono = get_monospace_font_family()

        self._setup_ui()

    def _generate_qr_code(self, data: str, size: int = 250) -> QPixmap:
        """Generate a QR code from the given data and return as QPixmap."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        # Create PIL image
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to QPixmap
        buffer = io.BytesIO()
        img.save(buffer, kind='PNG')
        buffer.seek(0)

        q_img = QImage.fromData(buffer.read())
        pixmap = QPixmap.fromImage(q_img)

        # Scale to desired size
        return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)

    def _setup_ui(self):
        """Set up the panel UI with all components."""
        # Set frame style
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.setStyleSheet(f"""
            LocksmithQRPanel {{
                border: 1px solid {BORDER};
                border-radius: 4px;
                background-color: {BACKGROUND_CONTENT};
            }}
        """)
        self.setFixedWidth(300)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header section (number, name, EID)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(8, 10, 8, 10)
        header_layout.setSpacing(3)

        number_label = QLabel(f"{self.number}. ")
        number_label.setStyleSheet("font-weight: 500;")
        header_layout.addWidget(number_label)

        name_label = QLabel(self.witness_name)
        name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        name_label.setToolTip(self.witness_name)
        header_layout.addWidget(name_label)

        header_layout.addWidget(QLabel("("))

        eid_label = QLabel()
        eid_label.setStyleSheet(f"font-family: {self.mono}; font-size: 12px;")
        eid_label.setToolTip(self.witness_eid)
        eid_label.setMaximumWidth(85)
        eid_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # Use elided text for truncation with ellipsis
        fm = eid_label.fontMetrics()
        elided_eid = fm.elidedText(self.witness_eid, Qt.TextElideMode.ElideMiddle, 85)
        eid_label.setText(elided_eid)
        header_layout.addWidget(eid_label)

        header_layout.addWidget(QLabel(")"))
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        divider.setStyleSheet(f"color: {BORDER};")
        divider.setFixedHeight(1)
        main_layout.addWidget(divider)

        # Controller section
        controller_layout = QVBoxLayout()
        controller_layout.setContentsMargins(20, 10, 20, 10)
        controller_layout.setSpacing(2)

        controller_header = QLabel("Controller")
        controller_header.setStyleSheet("font-weight: bold; font-size: 13px;")
        controller_layout.addWidget(controller_header)

        controller_info_layout = QHBoxLayout()
        controller_info_layout.setContentsMargins(8, 0, 0, 0)
        controller_info_layout.setSpacing(4)

        controller_alias_label = QLabel(self.controller_alias)
        controller_alias_label.setStyleSheet("font-size: 13px; font-weight: 500;")
        controller_alias_label.setToolTip(self.controller_alias)
        controller_info_layout.addWidget(controller_alias_label)

        controller_info_layout.addWidget(QLabel("("))

        controller_aid_label = QLabel()
        controller_aid_label.setStyleSheet(f"font-family: {self.mono}; font-size: 12px;")
        controller_aid_label.setToolTip(self.controller_aid)
        controller_aid_label.setMaximumWidth(110)
        controller_aid_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # Use elided text for truncation with ellipsis
        fm = controller_aid_label.fontMetrics()
        elided_aid = fm.elidedText(self.controller_aid, Qt.TextElideMode.ElideMiddle, 110)
        controller_aid_label.setText(elided_aid)
        controller_info_layout.addWidget(controller_aid_label)

        controller_info_layout.addWidget(QLabel(")"))
        controller_info_layout.addStretch()

        controller_layout.addLayout(controller_info_layout)
        main_layout.addLayout(controller_layout)

        # URL section
        url_layout = QVBoxLayout()
        url_layout.setContentsMargins(20, 0, 20, 10)
        url_layout.setSpacing(2)

        url_header = QLabel("URL:")
        url_header.setStyleSheet("font-weight: bold; font-size: 13px;")
        url_layout.addWidget(url_header)

        url_row_layout = QHBoxLayout()
        url_row_layout.setContentsMargins(8, 0, 0, 0)
        url_row_layout.setSpacing(2)

        url_label = QLabel(self.url)
        url_label.setStyleSheet("font-size: 12px;")
        url_label.setWordWrap(True)
        url_label.setMaximumWidth(230)
        url_label.setMaximumHeight(42)  # Approximately 3 lines at 12px font size
        url_label.setToolTip(self.url)
        url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        url_row_layout.addWidget(url_label)

        # Use LocksmithCopyButton
        from locksmith.ui.toolkit.widgets.buttons import LocksmithCopyButton
        copy_button = LocksmithCopyButton(
            copy_content=self.url,
            tooltip="Copy URL to clipboard",
            icon_size=20,
            border=False
        )
        url_row_layout.addWidget(copy_button, alignment=Qt.AlignmentFlag.AlignTop)

        url_layout.addLayout(url_row_layout)
        main_layout.addLayout(url_layout)

        # QR Code section (centered)
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setPixmap(self.qr_pixmap)
        self.qr_label.setVisible(self._qr_visible)
        main_layout.addWidget(self.qr_label)
        

        main_layout.addSpacing(10)  # Fixed 10px bottom space

    def toggle_qr_visibility(self):
        """Toggle the visibility of the QR code."""
        self._qr_visible = not self._qr_visible
        self.qr_label.setVisible(self._qr_visible)

    def set_qr_visible(self, visible: bool):
        """Set the QR code visibility explicitly."""
        self._qr_visible = visible
        self.qr_label.setVisible(visible)

    def is_qr_visible(self) -> bool:
        """Check if the QR code is currently visible."""
        return self._qr_visible


class FlowLayout(QLayout):
    """
    A layout that arranges items in a flow, wrapping to the next row when width is exceeded.

    Used for witness panels in the watcher status page.
    """

    def __init__(self, parent: Optional[QWidget] = None, margin: int = 0, spacing: int = -1):
        super().__init__(parent)

        if parent:
            self.setContentsMargins(margin, margin, margin, margin)

        self._item_list: list[QLayoutItem] = []
        self._spacing = spacing if spacing >= 0 else 10

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item: QLayoutItem):
        """Add an item to the layout."""
        self._item_list.append(item)

    def count(self) -> int:
        """Return the number of items in the layout."""
        return len(self._item_list)

    def itemAt(self, index: int) -> Optional[QLayoutItem]:
        """Return the item at the given index."""
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index: int) -> Optional[QLayoutItem]:
        """Remove and return the item at the given index."""
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        """Return which directions this layout can expand."""
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        """Whether this layout's height depends on its width."""
        return True

    def heightForWidth(self, width: int) -> int:
        """Calculate the height required for the given width."""
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect: QRect):
        """Set the geometry of the layout."""
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def minimumSize(self) -> QSize:
        """Return the minimum size of the layout."""
        size = QSize()

        for item in self._item_list:
            item_size = item.sizeHint()
            size = size.expandedTo(item_size)

        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        """Perform the actual layout calculation."""
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self._spacing

        for item in self._item_list:
            widget = item.widget()
            if not widget:
                continue

            space_x = spacing
            space_y = spacing

            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        # Return 0 if no items, otherwise return the total height used
        if line_height == 0:
            return 0
        return y + line_height - rect.y()

    def sizeHint(self) -> QSize:
        """Return the preferred size of the layout."""
        # Calculate width from minimum size
        min_size = self.minimumSize()
        # Use heightForWidth with a reasonable width estimate
        width = min_size.width()
        if self.parentWidget():
            width = max(width, self.parentWidget().width())
        height = self.heightForWidth(width)
        return QSize(width, height)


class WatchedWitnessSubPanel(QFrame):
    """
    Sub-panel displaying witness status information.

    Fixed width panel showing witness AID, event info, state, digest, keys, and last query time.
    """

    def __init__(self, witness_data: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.witness_data = witness_data
        self.mono = get_monospace_font_family()
        self._setup_ui()


    def _setup_ui(self):
        """Set up the panel UI."""
        self.setFrameShape(QFrame.Shape.Box)
        self.setStyleSheet(f"""
            WatchedWitnessSubPanel {{
                border: 2px solid {colors.BORDER};
                border-radius: 8px;
                background-color: {colors.BACKGROUND_CONTENT};
            }}
        """)
        self.setFixedWidth(458)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        self._populate_layout(layout)

    def _populate_layout(self, layout: QVBoxLayout):
        """Populate the given layout with witness data."""
        # Witness AID
        witness_id = self.witness_data.get('witness_id', 'Unknown')
        aid_layout = QHBoxLayout()
        aid_layout.setContentsMargins(0, 0, 0, 0)
        aid_layout.setSpacing(5)
        
        aid_title_label = QLabel("AID:")
        aid_title_label.setStyleSheet(f"font-weight: bold; color: {colors.TEXT_PRIMARY}; font-size: 13px;")
        aid_title_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        aid_layout.addWidget(aid_title_label)

        self.aid_label = QLabel(witness_id)
        self.aid_label.setStyleSheet(f"font-family: {self.mono}; color: {colors.TEXT_PRIMARY}; font-size: 13px;")

        self.aid_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        aid_layout.addWidget(self.aid_label)

        layout.addLayout(aid_layout)

        # Divider
        layout.addWidget(self._create_divider())

        # Event descriptor (conditional)
        keystate = self.witness_data.get('keystate')
        self.event_label = QLabel()
        self.event_label.setStyleSheet(f"color: {colors.TEXT_PRIMARY}; font-size: 13px;")
        self.event_label.setWordWrap(True)
        layout.addWidget(self.event_label)

        if keystate and isinstance(keystate, dict):
            event_type = keystate.get('et')
            sequence = keystate.get('s')

            if event_type and sequence is not None:
                self.event_label.setText(f"Most current event is a <span style='color: {colors.PRIMARY};'>{event_type}</span> event at sequence <span style='color: {colors.PRIMARY};'>{sequence}</span>")

        # State row (conditional - only show if not "even")
        response_received = self.witness_data.get('response_received', False)
        state = self.witness_data.get('state', 'even')

        self.state_label = QLabel()
        self.state_label.setStyleSheet(f"color: {colors.TEXT_PRIMARY}; font-size: 13px;")
        layout.addWidget(self.state_label)
        if not response_received:
            self.state_label.setText(f"State: <span style='color: {colors.DANGER};'>unresponsive</span>")
        elif state and state != 'even':
            self.state_label.setText(f"State: <span style='color: {colors.PRIMARY};'>{state}</span>")

        # Divider
        layout.addWidget(self._create_divider())

        # Digest section (conditional)
        digest_label = QLabel("Digest:")
        digest_label.setStyleSheet(f"font-weight: bold; color: {colors.TEXT_PRIMARY}; font-size: 13px;")
        layout.addWidget(digest_label)
        self.digest_value = QLabel()
        layout.addWidget(self.digest_value)

        if keystate and isinstance(keystate, dict):
            digest = keystate.get('d')
            if digest:
                self.digest_value.setText(f"  {digest}")
                self.digest_value.setStyleSheet(f"font-family: {self.mono}; color: {colors.TEXT_PRIMARY}; font-size: 12px;")

        # Public keys section (conditional)
        keys_label = QLabel("Public Keys:")
        keys_label.setStyleSheet(f"font-weight: bold; color: {colors.TEXT_PRIMARY}; font-size: 13px;")
        layout.addWidget(keys_label)
        self.key_value = QLabel()
        self.key_value.setStyleSheet(f"font-family: {self.mono}; color: {colors.TEXT_PRIMARY}; font-size: 12px;")
        self.key_value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.key_value.setWordWrap(True)
        layout.addWidget(self.key_value)

        if keystate and isinstance(keystate, dict):
            keys = keystate.get('k')
            key_text = ""
            if keys and isinstance(keys, list) and len(keys) > 0:
                for key in keys:
                    key_text += f"  {key}\n"
            self.key_value.setText(key_text)

        # Divider
        layout.addWidget(self._create_divider())

        # Last query timestamp
        timestamp = self.witness_data.get('last_query_timestamp', '')
        if timestamp:
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_time = dt.strftime("%Y-%m-%d %I:%M:%S %p")
                time_text = f"Last Query: <span style='color: {colors.PRIMARY};'>{formatted_time}</span>"
            except Exception:
                time_text = f"Last Query: <span style='color: {colors.PRIMARY};'>{timestamp}</span>"
        else:
            time_text = f"Last Query: <span style='color: {colors.PRIMARY};'>Never</span>"

        self.time_label = QLabel(time_text)
        self.time_label.setStyleSheet(f"color: {colors.TEXT_PRIMARY}; font-size: 13px;")
        layout.addWidget(self.time_label)

        layout.addStretch()

    @staticmethod
    def _create_divider() -> QFrame:
        """Create a horizontal divider."""
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background-color: {colors.DIVIDER}; border: none;")
        divider.setFixedHeight(1)
        return divider

    def update_data(self, witness_data: Dict[str, Any]):
        """Update the panel with new witness data."""
        self.witness_data = witness_data
        keystate = self.witness_data.get('keystate')

        if keystate and isinstance(keystate, dict):
            event_type = keystate.get('et')
            sequence = keystate.get('s')

            if event_type and sequence is not None:
                self.event_label.setText(f"Most current event is a <span style='color: {colors.PRIMARY};'>{event_type}</span> event at sequence <span style='color: {colors.PRIMARY};'>{sequence}</span>")

        response_received = self.witness_data.get('response_received', False)
        state = self.witness_data.get('state', 'even')

        if not response_received:
            self.state_label.setText(f"State: <span style='color: {colors.DANGER};'>unresponsive</span>")
        elif state and state != 'even':
            self.state_label.setText(f"State: <span style='color: {colors.PRIMARY};'>{state}</span>")

        if keystate and isinstance(keystate, dict):
            digest = keystate.get('d')
            if digest:
                self.digest_value.setText(f"  {digest}")
                self.digest_value.setStyleSheet(f"font-family: {self.mono}; color: {colors.TEXT_PRIMARY}; font-size: 12px;")

        if keystate and isinstance(keystate, dict):
            keys = keystate.get('k')
            key_text = ""
            if keys and isinstance(keys, list) and len(keys) > 0:
                for key in keys:
                    key_text += f"  {key}\n"
            self.key_value.setText(key_text)


        timestamp = self.witness_data.get('last_query_timestamp', '')
        if timestamp:
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_time = dt.strftime("%Y-%m-%d %I:%M:%S %p")
                time_text = f"Last Query: <span style='color: {colors.PRIMARY};'>{formatted_time}</span>"
            except Exception:
                time_text = f"Last Query: <span style='color: {colors.PRIMARY};'>{timestamp}</span>"
        else:
            time_text = f"Last Query: <span style='color: {colors.PRIMARY};'>Never</span>"

        self.time_label.setText(time_text)

class WatchedIdentifierPanel(QWidget):
    """
    Collapsible panel for a watched identifier (AID) showing witness status.

    Has a clickable header with AID info, responsive/duplicity counts, and chevron.
    Content area contains FlowLayout with WatchedWitnessSubPanel children.
    """

    def __init__(self, aid: str, aid_data: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.aid = aid
        self.aid_data = aid_data
        self._is_expanded = False
        self._content_height = 0
        self._header_height = 0
        self._animation = None
        self._animation_max = None
        self._pending_update = None  # Queue for updates during animation
        self._witness_panels: Dict[str, WatchedWitnessSubPanel] = {}  # Cache witness panels by key
        self.mono = get_monospace_font_family()

        self._setup_ui()

    def _setup_ui(self):
        """Set up the panel UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Outer container with the border - clips children
        self.container = QFrame()
        self.container.setFrameShape(QFrame.Shape.Box)
        self.container.setStyleSheet(f"""
            QFrame#panelContainer {{
                border: 1px solid {colors.BORDER};
                border-radius: 6px;
                background-color: {colors.BACKGROUND_CONTENT};
            }}
        """)
        self.container.setObjectName("panelContainer")

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Header (no border, just content)
        self.header = QWidget()
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.mousePressEvent = lambda e: self._toggle_expanded()
        self.header.setStyleSheet(f"""
            QWidget#headerWidget {{
                background-color: transparent;
                border-radius: 6px;
            }}
        """)
        self.header.setObjectName("headerWidget")

        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(15, 12, 15, 12)
        header_layout.setSpacing(10)

        # AID title label
        aid_title_label = QLabel("AID:")
        aid_title_label.setStyleSheet(f"font-weight: bold; color: {colors.TEXT_PRIMARY}; font-size: 14px; background: transparent;")
        header_layout.addWidget(aid_title_label)

        # AID label
        aid_label = QLabel(self.aid)
        aid_label.setStyleSheet(f"font-family: {self.mono}; color: {colors.TEXT_PRIMARY}; font-size: 14px; background: transparent;")
        header_layout.addWidget(aid_label)

        # Divider
        l = QLabel("|")
        l.setStyleSheet(f"color: {colors.DIVIDER}; background: transparent;")
        header_layout.addWidget(l)

        # Responsive count
        witness_summary = self.aid_data.get('witness_summary', {})
        total = witness_summary.get('total', 0)
        responsive = witness_summary.get('responsive', 0)
        responsive_text = f"Responsive: <span style='color: {colors.PRIMARY};'>{responsive}/{total}</span>"
        self.responsive_label = QLabel(responsive_text)
        self.responsive_label.setStyleSheet(f"color: {colors.TEXT_PRIMARY}; font-size: 13px; background: transparent;")
        header_layout.addWidget(self.responsive_label)

        # Divider
        l = QLabel("|")
        l.setStyleSheet(f"color: {colors.DIVIDER}; background: transparent;")
        header_layout.addWidget(l)

        # Duplicity count
        states = witness_summary.get('states', {})
        duplicitous = states.get('duplicitous', 0)
        dup_color = colors.SUCCESS if duplicitous == 0 else colors.DANGER
        dup_text = f"Duplicity: <span style='color: {dup_color};'>{duplicitous}</span>"
        self.dup_label = QLabel(dup_text)
        self.dup_label.setStyleSheet(f"color: {colors.TEXT_PRIMARY}; font-size: 13px; background: transparent;")
        header_layout.addWidget(self.dup_label)

        header_layout.addStretch()

        # Chevron icon
        self.chevron = QLabel()
        self.chevron.setFixedSize(20, 20)
        self.chevron.setStyleSheet("background: transparent;")
        self._update_chevron()
        header_layout.addWidget(self.chevron)

        # Cache header height and fix it
        self._header_height = self.header.sizeHint().height()
        self.header.setFixedHeight(self._header_height)

        container_layout.addWidget(self.header)

        # Content area (collapsible) - no border
        self.content = QWidget()

        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(15, 0, 15, 15)
        content_layout.setSpacing(10)

        # Divider between header and content - keep reference to toggle visibility

        self.header_content_divider = QFrame()
        self.header_content_divider.setFrameShape(QFrame.Shape.HLine)
        self.header_content_divider.setStyleSheet(f"background-color: transparent; border: none;")
        self.header_content_divider.setFixedHeight(1)
        # self.header_content_divider.setVisible(False)  # Hidden initially since collapsed
        content_layout.addWidget(self.header_content_divider)

        content_layout.addSpacing(15)
        # Title for witnesses section
        self.witnesses_title = QLabel("Witnesses")
        self.witnesses_title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {colors.TEXT_PRIMARY};")
        self.witnesses_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.witnesses_title)

        # FlowLayout for witness sub-panels
        self.flow_layout = FlowLayout(spacing=10)
        witnesses = self.aid_data.get('witnesses', {})
        for wit_key, wit_data in witnesses.items():
            witness_panel = WatchedWitnessSubPanel(wit_data)
            self.flow_layout.addWidget(witness_panel)
            # Cache the panel for future updates
            self._witness_panels[wit_key] = witness_panel

        content_layout.addLayout(self.flow_layout)

        # Calculate and fix content height
        self._content_height = self.content.sizeHint().height()
        self.content.setFixedHeight(self._content_height)

        container_layout.addWidget(self.content)

        # Set initial container height to just the header
        self.container.setFixedHeight(self._header_height)

        # Add container aligned to top so it expands downward only
        main_layout.addWidget(self.container, 0, Qt.AlignmentFlag.AlignTop)


    def _update_chevron(self):
        """Update the chevron icon based on expansion state."""
        icon_name = ":/assets/material-icons/chevron_up.svg" if self._is_expanded else ":/assets/material-icons/chevron_down.svg"
        pixmap = QIcon(icon_name).pixmap(20, 20)
        self.chevron.setPixmap(pixmap)

    def _calculate_content_height(self) -> int:
        """Calculate the actual content height."""
        self.content.adjustSize()
        height = self.content.sizeHint().height()
        self.content.setFixedHeight(height)
        return height

    def _toggle_expanded(self):
        """Toggle the expansion state with animation."""
        # Stop any running animations
        if self._animation and self._animation.state() == QPropertyAnimation.State.Running:
            self._animation.stop()

        self._is_expanded = not self._is_expanded
        self._update_chevron()

        # Always recalculate content height
        self._content_height = self._calculate_content_height()

        collapsed_height = self._header_height
        expanded_height = self._header_height + self._content_height

        self._animation = QPropertyAnimation(self.container, b"maximumHeight")
        self._animation.setDuration(300)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Hide divider during any animation
        self.header_content_divider.setStyleSheet(f"background-color: transparent; border: none;")

        if self._is_expanded:
            start = collapsed_height
            end = expanded_height
        else:
            start = self.container.height()
            end = collapsed_height

        self._animation.setStartValue(start)
        self._animation.setEndValue(end)

        # Keep min and max in sync via valueChanged
        self._animation.valueChanged.connect(self._sync_height)

        # Connect finished signal for both expand and collapse
        self._animation.finished.connect(self._on_animation_finished)

        self._animation.start()

    def _sync_height(self, value):
        """Keep minimum height in sync with maximum during animation."""
        self.container.setMinimumHeight(value)

    def _on_animation_finished(self):
        """Handle animation completion for both expand and collapse."""
        # Show divider if expanded
        if self._is_expanded:
            self.header_content_divider.setStyleSheet(f"background-color: {colors.DIVIDER}; border: none;")

        # Disconnect to prevent accumulating connections
        try:
            self._animation.finished.disconnect(self._on_animation_finished)
        except RuntimeError:
            pass

        # Process any pending updates after animation completes
        self._process_pending_update()

    def _is_animating(self) -> bool:
        """Check if animation is currently running."""
        return self._animation is not None and self._animation.state() == QPropertyAnimation.State.Running

    def _process_pending_update(self):
        """Process any pending update after animation completes."""
        if self._pending_update is not None:
            data = self._pending_update
            self._pending_update = None
            self._apply_update(data)

    def is_expanded(self) -> bool:
        """Check if the panel is currently expanded."""
        return self._is_expanded

    def set_expanded(self, expanded: bool):
        """Set the expansion state without animation."""
        if self._is_expanded != expanded:
            self._toggle_expanded()

    def _apply_update(self, aid_data: Dict[str, Any]):
        """
        Apply the actual data update to the panel.

        Reuses existing witness panels where possible to avoid widget recreation
        and the associated timing issues with deleteLater().
        """
        self.aid_data = aid_data

        # Update header labels with new witness summary data
        witness_summary = aid_data.get('witness_summary', {})
        total = witness_summary.get('total', 0)
        responsive = witness_summary.get('responsive', 0)
        states = witness_summary.get('states', {})
        duplicitous = states.get('duplicitous', 0)

        # Update responsive count label
        responsive_text = f"Responsive: <span style='color: {colors.PRIMARY};'>{responsive}/{total}</span>"
        self.responsive_label.setText(responsive_text)

        # Update duplicity count label with appropriate color
        dup_color = colors.SUCCESS if duplicitous == 0 else colors.DANGER
        dup_text = f"Duplicity: <span style='color: {dup_color};'>{duplicitous}</span>"
        self.dup_label.setText(dup_text)

        witnesses = aid_data.get('witnesses', {})

        # Track which witness keys are in the new data
        new_witness_keys = set(witnesses.keys())
        existing_witness_keys = set(self._witness_panels.keys())

        # Update existing panels
        for wit_key in new_witness_keys & existing_witness_keys:
            panel = self._witness_panels[wit_key]
            panel.update_data(witnesses[wit_key])

        # Add new witness panels for witnesses not already cached
        for wit_key in new_witness_keys - existing_witness_keys:
            witness_panel = WatchedWitnessSubPanel(witnesses[wit_key])
            self.flow_layout.addWidget(witness_panel)
            self._witness_panels[wit_key] = witness_panel

        # Remove panels for witnesses no longer in data
        for wit_key in existing_witness_keys - new_witness_keys:
            panel = self._witness_panels[wit_key]
            # Remove from layout
            self.flow_layout.removeWidget(panel)
            # Schedule for deletion
            panel.deleteLater()
            # Remove from cache
            del self._witness_panels[wit_key]

        # Recalculate content height
        self._content_height = self._calculate_content_height()

        # Update container if currently expanded
        if self._is_expanded:
            expanded_height = self._header_height + self._content_height
            self.container.setFixedHeight(expanded_height)
            self.container.setMinimumHeight(expanded_height)
            self.container.setMaximumHeight(expanded_height)

    def update_data(self, aid_data: Dict[str, Any]):
        """
        Update the panel with new AID data.

        If an animation is running, the update is queued and will be applied
        after the animation completes to prevent display corruption.
        """
        if self._is_animating():
            # Queue the update to happen after animation finishes
            self._pending_update = aid_data
        else:
            # Apply update immediately
            self._apply_update(aid_data)