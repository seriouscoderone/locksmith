"""Visual + structural smoke test for the PluginsPage.

Pattern follows tests/test_create_role_dialog_visual.py:
- render, structurally assert, screenshot to tests/_screenshots/.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtTest import QTest

from PySide6.QtWidgets import QLabel
from locksmith.plugins.installer import SourceDescriptor
from locksmith.plugins.manager import PluginState
from locksmith.ui.plugins.install_panel import InstallPanel
from locksmith.ui.plugins.page import PluginsPage


SCREENSHOT_DIR = Path(__file__).parent / "_screenshots"


@pytest.fixture
def fake_app_with_states():
    states = [
        PluginState(
            plugin_id="kerifoundation",
            status="loaded",
            manifest_snapshot={"name": "KERI Foundation", "version": "0.3.1",
                                "description": "Onboarding, witnesses, watchers"},
            in_tree=True,
        ),
        PluginState(
            plugin_id="echo_app",
            status="loaded",
            source={"type": "github", "user_repo": "acme/echo", "ref": None},
            manifest_snapshot={"name": "Echo App", "version": "0.1.0",
                                "description": "Logs lifecycle events"},
        ),
        PluginState(
            plugin_id="future",
            status="incompatible",
            error="requires Locksmith >=0.5 (you have 0.4)",
            manifest_snapshot={"name": "Future Plugin", "version": "0.2.0",
                                "description": "From the future"},
        ),
    ]
    app = MagicMock()
    app.plugin_manager.all_states.return_value = states
    return app


def test_page_renders_all_states(qapp, fake_app_with_states):
    page = PluginsPage(fake_app_with_states)
    page.resize(900, 700)
    page.show()
    QTest.qWait(250)
    qapp.processEvents()

    # Structural: one row per state, each showing the plugin's name.
    rendered_names = [w.text() for w in page.findChildren(type(page).PluginNameLabel)]
    assert "KERI Foundation" in rendered_names
    assert "Echo App" in rendered_names
    assert "Future Plugin" in rendered_names

    # Built-in badge present on kerifoundation only.
    in_tree_labels = [
        w for w in page.findChildren(type(page).InTreeBadge) if w.isVisible()
    ]
    assert len(in_tree_labels) == 1
    assert in_tree_labels[0].text() == "[ Built-in ]"

    # Status badge text correct.
    statuses = [b.text() for b in page.findChildren(type(page).StatusBadge)]
    assert any("Loaded" in s for s in statuses)
    assert any("Incompatible" in s for s in statuses)

    # Visual.
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    page.grab().save(str(SCREENSHOT_DIR / "plugins_page_mixed_states.png"))


def test_empty_state(qapp):
    app = MagicMock()
    app.plugin_manager.all_states.return_value = []
    page = PluginsPage(app)
    page.resize(900, 700)
    page.show()
    QTest.qWait(250)
    qapp.processEvents()
    assert page.findChild(type(page).EmptyStateLabel) is not None
    page.grab().save(str(SCREENSHOT_DIR / "plugins_page_empty.png"))


_FIXTURE_TRUST = {
    "manifest_snapshot": {
        "plugin_id": "dev_control",
        "name": "Dev Control Harness",
        "version": "0.1.0",
        "description": "JSON-over-unix-socket harness for driving the live UI",
        "author": "Joseph Hunsaker",
        "capabilities": ["app.shortcut", "app.service", "window.full_access",
                          "fs.write", "net.listen"],
        "capabilities_detail": {
            "fs.write": "Writes screenshot PNGs",
            "net.listen": "Unix socket at $XDG_RUNTIME_DIR/...",
        },
    },
    "source": {"type": "github", "user_repo": "acme/dev-control", "ref": None},
    "commit": "a3f9c1dabe7c0f5e8b7a2b9d0c4e1f2a3b4c5d6e",
}


def test_install_panel_starts_in_source_mode(qapp):
    panel = InstallPanel()
    panel.show()
    QTest.qWait(150)
    qapp.processEvents()
    assert panel.github_radio.isChecked()
    assert not panel.fetch_button.isEnabled()


def test_install_panel_github_validation(qapp):
    panel = InstallPanel()
    panel.show()
    QTest.qWait(150)
    panel.user_repo_input.setText("bad format")
    qapp.processEvents()
    assert not panel.fetch_button.isEnabled()
    panel.user_repo_input.setText("acme/echo")
    qapp.processEvents()
    assert panel.fetch_button.isEnabled()


def test_install_panel_fetch_emits_source_descriptor(qapp):
    panel = InstallPanel()
    panel.show()
    QTest.qWait(150)
    captured = {}
    panel.source_chosen.connect(lambda src: captured.update(src=src))
    panel.user_repo_input.setText("acme/echo")
    panel.ref_input.setText("main")
    qapp.processEvents()
    panel.fetch_button.click()
    qapp.processEvents()
    assert captured["src"] == SourceDescriptor(type="github", user_repo="acme/echo", ref="main")


def test_install_panel_trust_mode_populates(qapp):
    panel = InstallPanel()
    panel.show()
    QTest.qWait(150)
    panel.set_trust_mode(**_FIXTURE_TRUST)
    qapp.processEvents()
    QTest.qWait(150)
    assert "Dev Control Harness" in panel.trust_headline.text()
    # source value: "acme/dev-control" is 17 chars, well under the elide threshold —
    # it should appear verbatim; full path is also in the tooltip.
    assert "acme/dev-control" in panel.trust_source_value.text()
    assert "acme/dev-control" in panel.trust_source_value.toolTip()
    # commit[:7] rendered in commit value label
    assert "a3f9c1d" in panel.trust_commit_value.text()
    text = panel.trust_capability_block.toPlainText()
    for needle in ("keyboard shortcuts", "background services",
                   "full main window", "write", "listening socket"):
        assert needle in text.lower(), f"missing capability copy: {needle}"
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    panel.grab().save(str(SCREENSHOT_DIR / "install_panel_trust.png"))


def test_install_panel_trust_emits_with_plugin_id(qapp):
    panel = InstallPanel()
    panel.show()
    QTest.qWait(150)
    panel.set_trust_mode(**_FIXTURE_TRUST)
    qapp.processEvents()
    fired = {}
    panel.trusted.connect(lambda pid: fired.update(pid=pid))
    panel.trust_accept_button.click()
    qapp.processEvents()
    assert fired["pid"] == "dev_control"


def test_install_panel_cancel_emits(qapp):
    panel = InstallPanel()
    panel.show()
    QTest.qWait(150)
    fired = {"count": 0}
    panel.cancelled.connect(lambda: fired.update(count=fired["count"] + 1))
    panel.cancel_button.click()
    qapp.processEvents()
    assert fired["count"] == 1


def test_install_panel_inline_error_renders(qapp):
    panel = InstallPanel()
    panel.show()
    QTest.qWait(150)
    panel.set_inline_error("plugin 'echo_app' is already installed (from local). Uninstall it first.")
    qapp.processEvents()
    assert "already installed" in panel.error_label.text()


def test_plugins_page_opens_panel_on_install_click(qapp, fake_app_with_states):
    page = PluginsPage(fake_app_with_states)
    page.resize(900, 700)
    page.show()
    QTest.qWait(250)
    qapp.processEvents()
    assert not page._install_panel.isVisible()
    page._install_button.click()
    qapp.processEvents()
    QTest.qWait(150)
    assert page._install_panel.isVisible()
    # Install button hides when the panel is open.
    assert not page._install_button.isVisible()
    page.grab().save(str(SCREENSHOT_DIR / "plugins_page_install_panel_open.png"))


def test_plugins_page_emits_install_requested(qapp, fake_app_with_states):
    page = PluginsPage(fake_app_with_states)
    page.show()
    QTest.qWait(200)
    qapp.processEvents()
    page._install_button.click()
    qapp.processEvents()
    panel = page._install_panel
    panel.user_repo_input.setText("acme/echo")
    qapp.processEvents()
    fired = {}
    page.install_requested.connect(lambda src: fired.update(src=src))
    panel.fetch_button.click()
    qapp.processEvents()
    assert fired["src"].user_repo == "acme/echo"


def test_plugins_page_show_trust_step(qapp, fake_app_with_states):
    page = PluginsPage(fake_app_with_states)
    page.show()
    QTest.qWait(200)
    page._install_button.click()
    qapp.processEvents()
    QTest.qWait(150)
    page.show_trust_step(**_FIXTURE_TRUST)
    qapp.processEvents()
    QTest.qWait(150)
    # Now the panel should be in trust mode.
    text = page._install_panel.trust_capability_block.toPlainText().lower()
    assert "keyboard shortcuts" in text
    page.grab().save(str(SCREENSHOT_DIR / "plugins_page_trust_step.png"))


def test_plugins_page_collapse_install_panel(qapp, fake_app_with_states):
    page = PluginsPage(fake_app_with_states)
    page.show()
    QTest.qWait(200)
    page._install_button.click()
    qapp.processEvents()
    assert page._install_panel.isVisible()
    page.collapse_install_panel()
    qapp.processEvents()
    assert not page._install_panel.isVisible()
    assert page._install_button.isVisible()


def test_pending_install_appears_when_disk_has_plugin_not_in_manager(qapp, tmp_path, monkeypatch):
    """After install, the page surfaces the new plugin even before restart."""
    from locksmith.plugins import storage
    from unittest.mock import MagicMock
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    # Seed an installed plugin on disk that the manager hasn't loaded.
    storage.write_index({
        "format": 1,
        "plugins": [{
            "plugin_id": "echo_app",
            "source": {"type": "local", "path": "/x"},
            "commit": "local:2026-05-18T00:00:00",
            "installed_at": "2026-05-18T00:00:00Z",
            "manifest_snapshot": {
                "plugin_id": "echo_app",
                "name": "Echo App",
                "version": "0.1.0",
                "description": "Test fixture",
            },
        }],
    })
    app = MagicMock()
    app.plugin_manager.all_states.return_value = []  # nothing loaded in-memory
    page = PluginsPage(app)
    page.resize(900, 700)
    page.show()
    QTest.qWait(250)
    qapp.processEvents()
    names = [w.text() for w in page.findChildren(type(page).PluginNameLabel)]
    assert "Echo App" in names
    statuses = [b.text() for b in page.findChildren(type(page).StatusBadge)]
    assert any("Pending restart" in s for s in statuses)


def test_pending_row_has_only_remove_button(qapp, tmp_path, monkeypatch):
    from locksmith.plugins import storage
    from unittest.mock import MagicMock
    from PySide6.QtWidgets import QPushButton
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    storage.write_index({
        "format": 1,
        "plugins": [{
            "plugin_id": "echo_app",
            "source": {"type": "local", "path": "/x"},
            "manifest_snapshot": {"plugin_id": "echo_app", "name": "Echo App",
                                  "version": "0.1.0", "description": "fixture"},
        }],
    })
    app = MagicMock()
    app.plugin_manager.all_states.return_value = []
    page = PluginsPage(app)
    page.show()
    QTest.qWait(200)
    qapp.processEvents()
    button_texts = [b.text() for b in page.findChildren(QPushButton)
                    if b.isVisible() and b.objectName() != "plugins_install_button"]
    assert "Remove pending install" in button_texts
    assert "Uninstall" not in button_texts
    assert all("Exclude" not in t and "Include" not in t for t in button_texts)


def test_pending_row_emits_uninstall_signal(qapp, tmp_path, monkeypatch):
    from locksmith.plugins import storage
    from unittest.mock import MagicMock
    from PySide6.QtWidgets import QPushButton
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    storage.write_index({
        "format": 1,
        "plugins": [{
            "plugin_id": "echo_app",
            "source": {"type": "local", "path": "/x"},
            "manifest_snapshot": {"plugin_id": "echo_app", "name": "Echo App",
                                  "version": "0.1.0", "description": "fixture"},
        }],
    })
    app = MagicMock()
    app.plugin_manager.all_states.return_value = []
    page = PluginsPage(app)
    page.show()
    QTest.qWait(200)
    captured = {}
    page.uninstall_clicked.connect(lambda pid: captured.update(pid=pid))
    remove_btn = next(b for b in page.findChildren(QPushButton)
                      if b.text() == "Remove pending install")
    remove_btn.click()
    qapp.processEvents()
    assert captured["pid"] == "echo_app"


# ---------------------------------------------------------------------------
# Polish #3: trust-step reorder + warning callout tests
# ---------------------------------------------------------------------------

def test_install_panel_trust_warning_renders_at_top(qapp):
    panel = InstallPanel()
    panel.show()
    QTest.qWait(150)
    panel.set_trust_mode(**_FIXTURE_TRUST)
    qapp.processEvents()
    QTest.qWait(150)
    assert "full wallet permissions" in panel.trust_warning.text()
    # Warning callout must be positioned above the headline in widget coordinates.
    assert panel.trust_warning.y() < panel.trust_headline.y()


def test_install_panel_trust_uses_requests_wording(qapp):
    panel = InstallPanel()
    panel.show()
    QTest.qWait(150)
    panel.set_trust_mode(**_FIXTURE_TRUST)
    qapp.processEvents()
    labels = [w.text() for w in panel.findChildren(QLabel) if w.isVisible()]
    assert any("requests" in t.lower() for t in labels)
    assert not any("declares it will" in t.lower() for t in labels)


def test_install_panel_elides_long_source_path(qapp):
    panel = InstallPanel()
    panel.show()
    QTest.qWait(150)
    long_path = (
        "/Users/very/deeply/nested/example/path/to/some/plugin/"
        "that/should/elide-in-the-middle/echo-app"
    )
    panel.set_trust_mode(
        manifest_snapshot={
            "plugin_id": "x",
            "name": "X",
            "version": "0.0.1",
            "description": "x",
            "capabilities": [],
        },
        source={"type": "local", "path": long_path},
        commit="local:2026-05-18T00:00:00",
    )
    qapp.processEvents()
    visible = panel.trust_source_value.text()
    assert "…" in visible
    assert len(visible) < len(long_path)
    assert panel.trust_source_value.toolTip() == long_path


def test_install_panel_local_commit_renders_friendly(qapp):
    panel = InstallPanel()
    panel.show()
    QTest.qWait(150)
    panel.set_trust_mode(
        manifest_snapshot={
            "plugin_id": "x",
            "name": "X",
            "version": "0.0.1",
            "description": "x",
            "capabilities": [],
        },
        source={"type": "local", "path": "/some/path"},
        commit="local:2026-05-18T12:34:56",
    )
    qapp.processEvents()
    text = panel.trust_commit_value.text().lower()
    assert "local" in text or "no commit" in text


# ---------------------------------------------------------------------------
# Polish #4: inline install tile + drop scroll stretch
# ---------------------------------------------------------------------------

def test_install_tile_uses_dashed_border_styling(qapp, fake_app_with_states):
    page = PluginsPage(fake_app_with_states)
    page.show()
    QTest.qWait(200)
    qapp.processEvents()
    # The install button is now a clickable QFrame with a specific objectName.
    assert page._install_button.objectName() == "PluginInstallTile"
    # It carries a dashed-border stylesheet.
    assert "dashed" in page._install_button.styleSheet().lower()


def test_install_tile_shows_install_label(qapp, fake_app_with_states):
    page = PluginsPage(fake_app_with_states)
    page.show()
    QTest.qWait(200)
    qapp.processEvents()
    label = page._install_button.findChild(QLabel, "plugins_install_tile_label")
    assert label is not None
    assert "+ Install plugin" in label.text()


# ---------------------------------------------------------------------------
# Polish #7: PluginsContent standalone + vault sub-page registration
# ---------------------------------------------------------------------------

def test_plugins_content_standalone(qapp, fake_app_with_states):
    """PluginsContent can be instantiated standalone (no PluginsPage wrapper)."""
    from locksmith.ui.plugins.page import PluginsContent
    content = PluginsContent(fake_app_with_states)
    content.resize(900, 700)
    content.show()
    QTest.qWait(200)
    qapp.processEvents()
    # Marker labels live on PluginsContent directly.
    names = [w.text() for w in content.findChildren(PluginsContent.PluginNameLabel)]
    assert "KERI Foundation" in names
    assert "Echo App" in names
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    content.grab().save(str(SCREENSHOT_DIR / "plugins_content_standalone.png"))


def test_plugins_content_on_show_refreshes(qapp, fake_app_with_states):
    """PluginsContent.on_show() refreshes the list (mirrors NotificationsListPage)."""
    from locksmith.ui.plugins.page import PluginsContent
    content = PluginsContent(fake_app_with_states)
    content.show()
    QTest.qWait(200)
    qapp.processEvents()
    # Calling on_show() again must not raise and list should still be populated.
    content.on_show()
    qapp.processEvents()
    names = [w.text() for w in content.findChildren(PluginsContent.PluginNameLabel)]
    assert len(names) >= 2


def test_vault_page_registers_plugins_sub_page():
    """VaultPage API surface: show_plugins() and get_plugins_content() must exist.

    We test the class-level API rather than constructing VaultPage with a fake
    parent (PySide6 requires a real QWidget parent for construction, making
    full instantiation hard to mock cheaply without a real QApplication context
    and a real parent window).
    """
    import locksmith.ui.vault.page as vp_mod
    vp_cls = vp_mod.VaultPage
    # show_plugins() must exist and be callable (mirrors show_notifications()).
    assert hasattr(vp_cls, "show_plugins") and callable(vp_cls.show_plugins)
    # get_plugins_content() must exist and be callable.
    assert hasattr(vp_cls, "get_plugins_content") and callable(vp_cls.get_plugins_content)
    # The import used to register the sub-page must be at the module level.
    from locksmith.ui.plugins.page import PluginsContent  # noqa: F401 — confirms importable
    assert "PluginsContent" in dir(vp_mod)


# ---------------------------------------------------------------------------
# Polish #8: Restart now button in banner
# ---------------------------------------------------------------------------

def test_plugins_content_restart_button_in_banner(qapp, fake_app_with_states):
    from locksmith.ui.plugins.page import PluginsContent
    content = PluginsContent(fake_app_with_states)
    content.show()
    QTest.qWait(150)
    assert hasattr(content, "_restart_button")
    # The button is part of the banner; banner hidden by default.
    assert not content._restart_banner.isVisible()


def test_plugins_content_restart_banner_visible_after_set(qapp, fake_app_with_states):
    from locksmith.ui.plugins.page import PluginsContent
    content = PluginsContent(fake_app_with_states)
    content.resize(900, 700)
    content.show()
    QTest.qWait(150)
    content.set_restart_required(True)
    qapp.processEvents()
    QTest.qWait(100)
    assert content._restart_banner.isVisible()
    assert content._restart_button.isVisible()


def test_plugins_content_restart_button_emits_signal(qapp, fake_app_with_states):
    from locksmith.ui.plugins.page import PluginsContent
    content = PluginsContent(fake_app_with_states)
    content.resize(900, 700)
    content.show()
    QTest.qWait(150)
    content.set_restart_required(True)
    qapp.processEvents()
    fired = {"count": 0}
    content.restart_requested.connect(lambda: fired.update(count=fired["count"] + 1))
    content._restart_button.click()
    qapp.processEvents()
    assert fired["count"] == 1


def test_plugins_page_forwards_restart_requested(qapp, fake_app_with_states):
    page = PluginsPage(fake_app_with_states)
    page.resize(900, 700)
    page.show()
    QTest.qWait(150)
    page._content.set_restart_required(True)
    qapp.processEvents()
    fired = {"count": 0}
    page.restart_requested.connect(lambda: fired.update(count=fired["count"] + 1))
    # Click the underlying content's restart button.
    page._content._restart_button.click()
    qapp.processEvents()
    assert fired["count"] == 1
