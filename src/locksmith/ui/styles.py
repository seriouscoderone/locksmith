# -*- encoding: utf-8 -*-
"""
archie.ui.global module

This module contains global setting for the Archimedes UI
"""
import logging
import sys

from PySide6.QtGui import QColor, QFontDatabase, QIcon, QPalette
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
    #
    # NOT on macOS. There, setWindowIcon REPLACES the Dock icon that the .app's
    # own AppIcon.icns already supplied — and macOS shows no per-window icon, so
    # the call buys nothing and can only make things worse: when the brand dir
    # lookup below missed (the staged AppIcon.* were not bundled), the flat
    # transparent SymbolLogo fallback overwrote the correct plated Dock icon the
    # moment Qt started — the icon visibly "reverted" after the launch bounce.
    # The bundle icon is authoritative on macOS; leave it alone.
    if sys.platform != "darwin":
        _src = branding.brand_source_dir()
        _set = False
        if _src is not None:
            for _name in ("AppIcon.ico", "AppIcon.icns"):
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

    # Pin a light palette BEFORE the stylesheet. Locksmith renders light
    # surfaces unconditionally, but inherits whatever palette the OS supplies;
    # on macOS in Dark appearance that means white WindowText, so any widget
    # the stylesheet does not explicitly colour draws white-on-white. Naming
    # widget classes in the QSS only ever covers the ones somebody remembered
    # (the peer card's open_inbound checkbox was not one of them), and it can
    # never reach a combo-box POPUP, which is its own top-level view. Owning
    # the palette fixes the whole class at once.
    app.setPalette(light_palette())

    app.setStyleSheet(global_stylesheet())


def light_palette() -> QPalette:
    """The app's own palette: dark text on light surfaces, always.

    Values mirror the stylesheet's own colours so a widget covered by a QSS
    rule and one falling back to the palette look identical.
    """
    palette = QPalette()
    for role, value in (
        (QPalette.ColorRole.Window, colors.BACKGROUND_WINDOW),
        (QPalette.ColorRole.Base, colors.WHITE),
        (QPalette.ColorRole.AlternateBase, colors.BACKGROUND_WINDOW),
        (QPalette.ColorRole.Button, colors.WHITE),
        (QPalette.ColorRole.ToolTipBase, colors.WHITE),
        (QPalette.ColorRole.Highlight, colors.BACKGROUND_NEUTRAL_HOVER),
        (QPalette.ColorRole.WindowText, colors.TEXT_PRIMARY),
        (QPalette.ColorRole.Text, colors.TEXT_PRIMARY),
        (QPalette.ColorRole.ButtonText, colors.TEXT_PRIMARY),
        (QPalette.ColorRole.ToolTipText, colors.TEXT_PRIMARY),
        (QPalette.ColorRole.HighlightedText, colors.TEXT_PRIMARY),
        (QPalette.ColorRole.PlaceholderText, colors.TEXT_SECONDARY),
    ):
        palette.setColor(role, QColor(value))
    # Disabled text still has to read as *text*, just muted — the default
    # disabled role under a dark palette is another near-white.
    for group in (QPalette.ColorGroup.Disabled,):
        for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                     QPalette.ColorRole.ButtonText):
            palette.setColor(group, role, QColor(colors.TEXT_SECONDARY))
    return palette


def global_stylesheet() -> str:
    """The app-wide QSS. Split out of ``set_global_styles`` so the legibility
    contract below is directly testable (``tests/ui/test_dark_palette_legibility``).

    Load-bearing: the app paints its own LIGHT surfaces but never overrides the
    palette, so on an OS in dark appearance Qt's WindowText is white. Every
    text-bearing widget class therefore needs an explicit colour here —
    anything left out renders white-on-white, invisible and unlogged. That is
    how the peer card's ``open_inbound`` checkbox shipped as a bare tick box
    with no label.
    """
    return f"""
        QMainWindow {{
            background-color: {colors.BACKGROUND_WINDOW};
        }}
        QLabel, QPushButton, QLineEdit, QListWidget::Item,
        QCheckBox, QRadioButton, QGroupBox {{
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
    """
