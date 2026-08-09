"""The filled primary must be legible, and must stay the brand's own colour.

White label text on the brand ACCENT fails WCAG AA in both brands -- measured,
2.77:1 on Usurance Teal 600 #2AABB3 and 2.72:1 on vanilla orange #F57B03. The
suite mandates both halves and they contradict: design-system.md:218 fixes
"Primary = Teal 600 filled, White text" while :296-300 requires 4.5:1 for normal
text and 3:1 even for large buttons.

The resolution is a separate token. PRIMARY stays the accent (links, focus rings,
avatars, badges), where 3:1 as a graphical object is the applicable floor;
PRIMARY_BUTTON is darkened until white is legible on it.
"""
import collections
import importlib
import pathlib
import tomllib

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[2]


def _ratio(fg: str, bg: str) -> float:
    def lum(value: str) -> float:
        value = value.lstrip("#")
        channels = [int(value[i:i + 2], 16) for i in (0, 2, 4)]

        def linear(v: float) -> float:
            v /= 255
            return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

        return (0.2126 * linear(channels[0]) + 0.7152 * linear(channels[1])
                + 0.0722 * linear(channels[2]))

    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


@pytest.fixture
def colors():
    """A pristine colors module. `apply_theme_overrides` rewrites module-level
    constants IN PLACE, so a theme applied in one test leaks into every later
    one unless the module is reloaded on both sides."""
    from locksmith.ui import colors as module
    importlib.reload(module)
    yield module
    importlib.reload(module)


def test_the_contrast_helper_agrees_with_a_known_pair():
    """Guard on the guard: every assertion below is this function's output, so a
    broken implementation would silently pass them all. Black on white is 21:1
    exactly, by definition."""
    assert round(_ratio("#000000", "#FFFFFF"), 2) == 21.0
    assert round(_ratio("#FFFFFF", "#FFFFFF"), 2) == 1.0


def test_white_is_legible_on_the_usurance_button_fill(colors):
    """The reason this token exists. 4.5:1 is the normal-text floor from
    ui-conventions.md:74 and design-system.md:298; the button label is 14px
    Medium, which is neither >=18px nor bold, so the 3:1 relaxation for large
    text does not apply."""
    theme = tomllib.loads(
        (_REPO / "brands/usurance/brand.toml").read_text())["theme"]
    colors.apply_theme_overrides(theme)

    assert _ratio("#FFFFFF", colors.PRIMARY_BUTTON) >= 4.5
    for state in ("PRIMARY_BUTTON_HOVER", "PRIMARY_BUTTON_PRESSED"):
        assert _ratio("#FFFFFF", getattr(colors, state)) >= 4.5, state


def test_the_accent_is_still_the_accent(colors):
    """Splitting the token must not repaint links, focus rings or badges. The
    accent is judged as a graphical object (3:1), not as text."""
    theme = tomllib.loads(
        (_REPO / "brands/usurance/brand.toml").read_text())["theme"]
    colors.apply_theme_overrides(theme)

    assert colors.PRIMARY == theme["primary"]
    assert colors.PRIMARY != colors.PRIMARY_BUTTON, (
        "the button fill collapsed back onto the accent")


def test_a_brand_that_names_only_primary_keeps_its_own_colour(colors):
    """The fallback that matters. The module default is vanilla ORANGE, so a
    fallback computed before the overrides land would give any teal brand orange
    buttons. It has to resolve to the brand's own accent, after."""
    colors.apply_theme_overrides({"primary": "#8800CC"})

    assert colors.PRIMARY_BUTTON == "#8800CC"
    assert colors.PRIMARY_BUTTON_HOVER == colors.PRIMARY_HOVER


def test_an_unbranded_build_is_visually_unchanged(colors):
    """Adding the token must not alter any brand that has not opted in."""
    assert colors.PRIMARY_BUTTON == colors.PRIMARY == "#F57B03"


def test_the_button_actually_paints_the_fill_token(qtbot):
    """The token is only worth having if the widget uses it. Reads the rendered
    pixels rather than the stylesheet string -- a QSS rule that fails to apply
    leaves the string perfectly correct."""
    from locksmith.ui import colors as module
    importlib.reload(module)
    try:
        theme = tomllib.loads(
            (_REPO / "brands/usurance/brand.toml").read_text())["theme"]
        module.apply_theme_overrides(theme)
        from locksmith.ui.toolkit.widgets.buttons import LocksmithButton

        button = LocksmithButton("Attest Rate Program")
        qtbot.addWidget(button)
        button.resize(240, 43)
        button.show()
        qtbot.waitExposed(button)

        image = button.grab().toImage()
        dominant, count = collections.Counter(
            image.pixelColor(x, y).name()
            for y in range(image.height())
            for x in range(image.width())).most_common(1)[0]
        assert dominant.lower() == module.PRIMARY_BUTTON.lower()
        assert count > image.width() * image.height() * 0.5
    finally:
        importlib.reload(module)
