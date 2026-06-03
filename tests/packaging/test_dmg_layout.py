"""DMG layout sanity checks."""
import json
from pathlib import Path

DMG_DIR = Path(__file__).resolve().parents[2] / "packaging" / "dmg"
LAYOUT = DMG_DIR / "layout.json"
BG = DMG_DIR / "background.png"


def test_layout_exists():
    assert LAYOUT.is_file()


def test_background_exists():
    assert BG.is_file()
    assert BG.stat().st_size > 0


def test_layout_has_window_size():
    data = json.loads(LAYOUT.read_text())
    assert "window" in data and "size" in data["window"]
    w, h = data["window"]["size"]
    # Match create-dmg --window-size — width should accommodate the bg
    assert w >= 540 and h >= 380


def test_layout_has_app_icon_position():
    data = json.loads(LAYOUT.read_text())
    icons = {i["name"]: i for i in data["icons"]}
    assert "Locksmith.app" in icons
    assert "Applications" in icons
    # Drag-target should be on the right of the app icon
    assert icons["Applications"]["pos"][0] > icons["Locksmith.app"]["pos"][0]


def test_layout_has_icon_size():
    data = json.loads(LAYOUT.read_text())
    assert data["icon_size"] >= 80
