# -*- encoding: utf-8 -*-
"""
archie.ui.global module

This module contains global setting for the Archimedes UI
"""
import logging
import sys
from pathlib import Path

from PySide6.QtGui import QIcon, QFontDatabase
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle

logger = logging.getLogger(__name__)


def _asset_root() -> Path:
    """Directory where `assets/` lives.

    - Dev: the repo root (4 levels up from src/locksmith/ui/styles.py).
    - Frozen PyInstaller .app: sys._MEIPASS, which is where the spec's
      datas put the assets tree.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[3]

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

    asset_root = _asset_root()

    # Pick a window-icon format the running platform's Qt can actually render.
    # Qt on Windows can't load .icns (a macOS format) — setting it yields an
    # empty icon, which overrides the exe's embedded .ico and leaves a blank
    # taskbar button. .ico renders on every platform; macOS prefers .icns (its
    # dock icon comes from the app bundle regardless).
    icon_dir = asset_root / "assets" / "custom"
    _icon_names = (
        ("AppIcon.icns", "AppIcon.ico") if sys.platform == "darwin"
        else ("AppIcon.ico", "AppIcon.icns")
    )
    for _name in _icon_names:
        cand = icon_dir / _name
        if cand.exists():
            app.setWindowIcon(QIcon(str(cand)))
            break
    else:
        logger.warning(
            f"App icon not found in {icon_dir}; falling back to symbol logo"
        )
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

    font_path = asset_root / "assets" / "fonts" / "SourceCodePro-Regular.ttf"

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
