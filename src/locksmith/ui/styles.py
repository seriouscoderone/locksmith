# -*- encoding: utf-8 -*-
"""
archie.ui.global module

This module contains global setting for the Archimedes UI
"""
import logging
import sys

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
    from locksmith.core import branding
    branding.register_brand_resources()      # single atomic asset surface — must be first

    # Runtime window/taskbar icon from the active brand's bundle dir (atomic
    # with the registered logos); the .app/.exe embedded icon is a packaging
    # concern. Fall back to the compiled symbol logo.
    _src = branding.brand_source_dir()
    _icon_names = (
        ("AppIcon.icns", "AppIcon.ico") if sys.platform == "darwin"
        else ("AppIcon.ico", "AppIcon.icns")
    )
    _set = False
    if _src is not None:
        for _name in _icon_names:
            cand = _src / _name
            if cand.exists():
                app.setWindowIcon(QIcon(str(cand)))
                _set = True
                break
    if not _set:
        app.setWindowIcon(QIcon(":/assets/custom/SymbolLogo.svg"))
    from locksmith.core.branding import brand
    from locksmith.ui import colors as _colors

    _b = brand()
    # Apply the brand's accent theme BEFORE the QSS below is built from it.
    _colors.apply_theme_overrides(_b.theme)

    app.setApplicationName(_b.display_name)
    # setOrganizationName is required for QSettings() with no args to
    # write to a stable per-user location on Windows. Without it,
    # consent_seen / last_checked / other UpdatePrefs values would land
    # somewhere ephemeral and consent dialog would re-fire every launch.
    app.setOrganizationName(_b.org_name)
    app.setOrganizationDomain(_b.org_domain)

    font_id = QFontDatabase.addApplicationFont(":/assets/fonts/SourceCodePro-Regular.ttf")
    if font_id != -1:
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            MONOSPACE_FONT_FAMILY = families[0]
            logger.info(f"Loaded monospace font: {MONOSPACE_FONT_FAMILY}")
    else:
        logger.warning("Failed to load font at :/assets/fonts/SourceCodePro-Regular.ttf, using system fallback")

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
