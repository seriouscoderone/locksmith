import importlib

import pytest

colors = importlib.import_module("locksmith.ui.colors")


@pytest.fixture(autouse=True)
def _restore_defaults():
    saved = {k: getattr(colors, k) for k in
             ("PRIMARY", "PRIMARY_HOVER", "PRIMARY_PRESSED", "TOOLBAR_DARK",
              "BACKGROUND_WINDOW", "DANGER")}
    yield
    for k, v in saved.items():
        setattr(colors, k, v)


def test_overrides_accent_only():
    colors.apply_theme_overrides({
        "primary": "#112233", "primary_hover": "#0A1722",
        "primary_pressed": "#2A4458", "toolbar_dark": "#000010",
    })
    assert colors.PRIMARY == "#112233"
    assert colors.PRIMARY_HOVER == "#0A1722"
    assert colors.PRIMARY_PRESSED == "#2A4458"
    assert colors.TOOLBAR_DARK == "#000010"
    # neutrals / semantic colors are untouched
    assert colors.BACKGROUND_WINDOW == "#F2F3FA"
    assert colors.DANGER == "#DC2626"


def test_missing_keys_leave_defaults():
    before = colors.PRIMARY_HOVER
    colors.apply_theme_overrides({"primary": "#999999"})
    assert colors.PRIMARY == "#999999"
    assert colors.PRIMARY_HOVER == before


def test_unknown_keys_ignored():
    colors.apply_theme_overrides({"banana": "#FFFFFF"})
    assert not hasattr(colors, "banana")
