from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QMainWindow

from locksmith.ui.vaults.drawer import VaultDrawer


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
            launcher.launch_new.assert_called_once_with("notary")
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
