# -*- encoding: utf-8 -*-
"""
archie.ui.global module

This module contains global setting for the Archimedes UI
"""
import logging

from PySide6.QtGui import QIcon, QFontDatabase
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle

logger = logging.getLogger(__name__)

# Default monospace font family (updated when custom font loads successfully)
MONOSPACE_FONT_FAMILY = "monospace"


def get_monospace_font_family() -> str:
    """Get the current monospace font family name.

    Use this function instead of importing MONOSPACE_FONT_FAMILY directly,
    since the variable is updated at runtime when set_global_styles() is called.
    """
    return MONOSPACE_FONT_FAMILY

from locksmith.ui import colors

# This is used to increase the size of menu item icons.
class IconSizeProxyStyle(QProxyStyle):
    def pixelMetric(self, QStyle_PixelMetric, option=None, widget=None):

        if QStyle_PixelMetric == QStyle.PM_SmallIconSize:
            return 24
        else:
            return super(IconSizeProxyStyle, self).pixelMetric(QStyle_PixelMetric, option, widget)


def set_global_styles(app: QApplication):
    global MONOSPACE_FONT_FAMILY

    app.setWindowIcon(QIcon(':/assets/custom/SymbolLogo.svg'))
    app.setApplicationName("Locksmith")

    # Load bundled Source Code Pro font using absolute path to avoid cwd issues
    from pathlib import Path
    project_root = Path(__file__).parent.parent.parent.parent
    font_path = project_root / "assets" / "fonts" / "SourceCodePro-Regular.ttf"

    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id != -1:
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            MONOSPACE_FONT_FAMILY = families[0]
            logger.info(f"Loaded monospace font: {MONOSPACE_FONT_FAMILY}")
    else:
        logger.warning(f"Failed to load font at {font_path}, using system fallback")

    app.setStyle(IconSizeProxyStyle())

    app.setStyleSheet(f"""
        QMainWindow {{
            background-color: {colors.BACKGROUND_WINDOW};
        }}
        QLabel, QPushButton, QLineEdit, QListWidget::Item {{
            color: {colors.TEXT_PRIMARY};
            letter-spacing: 0.8px;
        }}

        .monospace {{
            font-family: "{MONOSPACE_FONT_FAMILY}", monospace;
        }}

        QToolTip {{
            background-color: {colors.WHITE};
            color: {colors.TEXT_PRIMARY};
        }}
        
        /* Scrollbar styling */
        QScrollBar:vertical {{
            background: transparent;
            width: 12px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {colors.BACKGROUND_NEUTRAL_HOVER};
            border-radius: 6px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {colors.SCROLLBAR_HANDLE_HOVER};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
    """)
