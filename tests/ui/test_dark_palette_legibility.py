"""Every text-bearing widget class the UI uses must be coloured explicitly.

Locksmith paints its own light surfaces (``colors.WHITE`` cards on
``BACKGROUND_WINDOW``) but never overrides the Qt *palette*. On an OS in dark
appearance — macOS Dark, which is what this was found on — Qt's ``WindowText``
is white, so any widget class the global stylesheet leaves uncoloured renders
its label white-on-white: invisible, with nothing in the logs and no error.

That is how the peer settings card's "Accept introductions from verified
first-contact senders" checkbox shipped as a bare tick box with no label —
the one control an authority must find for a first-contact role request to get
past the shim's allowlist gate (``peer/shim.py``). ``QLabel``/``QPushButton``/
``QLineEdit`` were covered; ``QCheckBox`` was not.

This is a SOURCE-level check on purpose. The obvious test — render the widget
and look for ink — cannot be trusted here: under ``QT_QPA_PLATFORM=offscreen``
Qt uses the Fusion style rather than the macOS native style, and it renders
these labels legibly whether or not the stylesheet covers them. A pixel test
would pass on CI and on a dev machine while the bug shipped, which is worse
than no test.
"""
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtGui import QPalette

from locksmith.ui import colors
from locksmith.ui.styles import global_stylesheet, light_palette, set_global_styles

_UI_ROOT = Path(__file__).resolve().parents[2] / "src" / "locksmith" / "ui"

# Widget classes that draw a text label using a palette colour role, and so go
# invisible on a light surface under a dark palette unless the global sheet
# names them. QLabel/QPushButton/QLineEdit/QListWidget are the ones that were
# already covered; the rest are the gap this test closes.
_TEXT_BEARING = (
    "QLabel", "QPushButton", "QLineEdit", "QCheckBox", "QRadioButton",
    "QGroupBox",
)


def _colour_rule_selectors() -> set[str]:
    """Widget classes named by any QSS rule that sets a foreground `color`."""
    selectors: set[str] = set()
    for block in global_stylesheet().split("}"):
        if "{" not in block:
            continue
        selector, body = block.split("{", 1)
        declarations = [d.strip() for d in body.split(";")]
        if not any(d.startswith("color:") for d in declarations):
            continue          # background-color only — not a text colour
        selectors |= {s.strip().split("::")[0]
                      for s in selector.split(",") if s.strip()}
    assert selectors, "no foreground colour rule found in global_stylesheet()"
    return selectors


def _classes_instantiated_in_the_ui() -> set[str]:
    used = set()
    for path in _UI_ROOT.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        for cls in _TEXT_BEARING:
            if re.search(rf"\b{cls}\s*\(", src):
                used.add(cls)
    return used


# ---------------------------------------------------------------------------
# The systemic fix: pin a light palette, rather than chasing selectors.
#
# Naming widget classes in the QSS (below) only ever covers the ones somebody
# remembered. The root cause is that the app renders light surfaces on top of
# whatever palette the OS supplies, so the fix that actually generalises is to
# stop inheriting the OS palette at all — every unstyled widget then resolves
# against light colours instead of dark ones. The combo-box POPUP is what made
# this obvious: it is a separate top-level view, so no amount of styling the
# card it sits on reaches it.
# ---------------------------------------------------------------------------

def _luminance(qcolor) -> float:
    return (0.299 * qcolor.red() + 0.587 * qcolor.green()
            + 0.114 * qcolor.blue()) / 255


_FOREGROUND_ROLES = ("WindowText", "Text", "ButtonText", "ToolTipText",
                     "HighlightedText")
_SURFACE_ROLES = ("Window", "Base", "Button", "ToolTipBase", "AlternateBase")


@pytest.mark.parametrize("role", _FOREGROUND_ROLES)
def test_light_palette_keeps_foreground_roles_dark(role):
    colour = light_palette().color(getattr(QPalette.ColorRole, role))
    assert _luminance(colour) < 0.5, f"{role} is {colour.name()} — not legible on a light surface"


@pytest.mark.parametrize("role", _SURFACE_ROLES)
def test_light_palette_keeps_surface_roles_light(role):
    colour = light_palette().color(getattr(QPalette.ColorRole, role))
    assert _luminance(colour) > 0.5, f"{role} is {colour.name()} — a dark surface under dark text"


def test_light_palette_agrees_with_the_stylesheet_text_colour():
    """Palette and QSS must not disagree, or the same label changes colour
    depending on which widget class happens to be covered."""
    assert light_palette().color(
        QPalette.ColorRole.WindowText).name().lower() == colors.TEXT_PRIMARY.lower()


def test_set_global_styles_installs_the_light_palette():
    """The wiring, not just the value: a palette nobody applies fixes nothing."""
    from locksmith.core import branding
    app = MagicMock()
    try:
        set_global_styles(app)
    finally:
        branding.unregister_brand_resources()
    app.setPalette.assert_called_once()
    installed = app.setPalette.call_args.args[0]
    assert _luminance(installed.color(QPalette.ColorRole.WindowText)) < 0.5
    assert _luminance(installed.color(QPalette.ColorRole.Base)) > 0.5


def test_the_scan_finds_the_classes_it_is_meant_to_guard():
    """A moved ui/ tree or a renamed helper would make every check below
    vacuous — this is the guard on the guard."""
    used = _classes_instantiated_in_the_ui()
    assert {"QLabel", "QCheckBox"} <= used, f"scan looks broken: found {used}"


@pytest.mark.parametrize("cls", _TEXT_BEARING)
def test_text_bearing_widget_class_is_coloured_by_the_global_stylesheet(cls):
    if cls not in _classes_instantiated_in_the_ui():
        pytest.skip(f"{cls} is not used in locksmith.ui")
    assert cls in _colour_rule_selectors(), (
        f"{cls} is instantiated in locksmith/ui but has no explicit colour in "
        f"locksmith.ui.styles.global_stylesheet(). Under a dark OS palette its "
        f"label renders white-on-white on the app's light surfaces. Add it to "
        f"the TEXT_PRIMARY colour rule."
    )
