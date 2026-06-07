from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

from PySide6.QtWidgets import QFrame, QMainWindow

from locksmith.ui.vaults.drawer import VaultDrawer


def _live_row_count(drawer):
    return len(
        [
            w
            for w in drawer.vault_list.viewport().findChildren(QFrame)
            if w.objectName().startswith("vaultDrawer.row.")
        ]
    )


def _row_names(drawer):
    return {
        w.objectName()
        for w in drawer.vault_list.viewport().findChildren(QFrame)
        if w.objectName().startswith("vaultDrawer.row.")
    }


def _make_window(vaults, current, probe_running):
    win = QMainWindow()
    coord = SimpleNamespace(
        probe=lambda v: v in probe_running,
        request_raise=MagicMock(return_value=True),
    )
    win.app = SimpleNamespace(
        environments=lambda: vaults,
        name=current,
        coordinator=coord,
        config=SimpleNamespace(base="/tmp"),
    )
    return win, coord


def test_row_state_classification(qapp):
    win, coord = _make_window(
        vaults=["treasurer", "auditor", "notary"],
        current="treasurer",
        probe_running={"auditor"},
    )
    toolbar = SimpleNamespace(height=lambda: 0)
    drawer = VaultDrawer(parent=win, toolbar_ref=toolbar)
    try:
        assert drawer._vault_state("treasurer") == "current"
        assert drawer._vault_state("auditor") == "running"
        assert drawer._vault_state("notary") == "idle"
    finally:
        drawer.deleteLater()
        win.close()


def test_open_in_new_instance_launches_process(qapp):
    win, coord = _make_window(["notary"], current=None, probe_running=set())
    toolbar = SimpleNamespace(height=lambda: 0)
    drawer = VaultDrawer(parent=win, toolbar_ref=toolbar)
    try:
        with patch("locksmith.ui.vaults.drawer.InstanceLauncher") as launcher:
            drawer._open_in_new_instance("notary")
            # Passes the launching window's position so the new instance cascades.
            launcher.launch_new.assert_called_once_with("notary", origin_xy=ANY)
    finally:
        drawer.deleteLater()
        win.close()


def test_switch_to_raises_running_instance(qapp):
    win, coord = _make_window(["auditor"], current=None, probe_running={"auditor"})
    toolbar = SimpleNamespace(height=lambda: 0)
    drawer = VaultDrawer(parent=win, toolbar_ref=toolbar)
    try:
        drawer._switch_to_running("auditor")
        coord.request_raise.assert_called_once_with("auditor")
    finally:
        drawer.deleteLater()
        win.close()


def test_open_refreshes_vault_list(qapp):
    """Opening the drawer must re-enumerate vaults.

    The drawer is built once at startup; another instance can create a
    vault afterward. Opening the drawer (toggle → slide-in) must re-read
    app.environments() so the new vault's row appears, instead of showing
    the stale construction-time set.
    """
    vaults = ["treasurer"]
    win, coord = _make_window(vaults, current=None, probe_running=set())
    win.resize(800, 600)
    # toggle()'s slide-in branch calls toolbar_ref.raise_() (z-order); the
    # real toolbar is a QWidget. Stub it as a no-op for this unit test.
    toolbar = SimpleNamespace(height=lambda: 0, raise_=lambda: None)
    drawer = VaultDrawer(parent=win, toolbar_ref=toolbar)
    try:
        # Built with one vault; no row for the not-yet-existing "auditor".
        assert _live_row_count(drawer) == 1
        assert _row_names(drawer) == {"vaultDrawer.row.treasurer"}

        # Another instance creates "auditor" after construction.
        vaults.append("auditor")

        # Opening the drawer must pick it up.
        drawer.toggle()
        qapp.processEvents()

        assert drawer.vault_list.count() == 2
        assert _live_row_count(drawer) == 2
        # The newly-created vault's row now exists in the drawer.
        assert "vaultDrawer.row.auditor" in _row_names(drawer)
    finally:
        drawer.deleteLater()
        win.close()


def test_refresh_does_not_leak_row_widgets(qapp):
    """Refreshing the drawer must free old row widgets, not accumulate them.

    QListWidget.clear() leaves setItemWidget widgets parented to the
    viewport; _refresh_vault_list must release them so live row frames stay
    at one-per-vault no matter how many times the drawer refreshes.
    """
    vaults = ["treasurer", "auditor", "notary"]
    win, coord = _make_window(vaults, current="treasurer", probe_running={"auditor"})
    toolbar = SimpleNamespace(height=lambda: 0)
    drawer = VaultDrawer(parent=win, toolbar_ref=toolbar)
    try:
        for _ in range(5):
            drawer._refresh_vault_list()
        # Honor the deleteLater() scheduled for released row widgets.
        qapp.processEvents()
        assert _live_row_count(drawer) == len(vaults)
    finally:
        drawer.deleteLater()
        win.close()


def test_current_row_has_close_button_that_closes_vault(qapp):
    """The current vault's row renders a Close button wired to the window's
    lock/close flow (replacing the removed top-toolbar Close button)."""
    from PySide6.QtWidgets import QPushButton

    win, coord = _make_window(["solo"], current="solo", probe_running=set())
    win.on_lock_vault = MagicMock()
    toolbar = SimpleNamespace(height=lambda: 0)
    drawer = VaultDrawer(parent=win, toolbar_ref=toolbar)
    try:
        # Row widgets live under the list (setItemWidget → viewport), not under
        # the drawer controller object.
        close_btn = drawer.vault_list.findChild(QPushButton, "vaultDrawer.close.solo")
        assert close_btn is not None, "current row should have a Close button"
        # Clicking it runs the window's close-vault flow.
        drawer._close_current_vault("solo")
        win.on_lock_vault.assert_called_once()
    finally:
        drawer.deleteLater()
        win.close()
