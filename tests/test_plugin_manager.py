from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from locksmith.plugins.base import VaultPlugin
from locksmith.plugins.manager import PluginManager


def _make_vault_plugin(plugin_id, batches_result):
    """Build a minimal VaultPlugin concrete subclass for direct _plugins injection."""

    class _TestVaultPlugin(VaultPlugin):
        @property
        def plugin_id(self):
            return plugin_id

        def initialize(self, app):
            pass

        def on_vault_opened(self, vault):
            pass

        def on_vault_closed(self, vault, *, clear=False):
            pass

        def get_menu_entry(self):
            return MagicMock()

        def get_menu_section(self):
            return []

        def get_pages(self):
            return {}

        def get_witness_batches(self, vault, hab_pre):
            return batches_result

    return _TestVaultPlugin()


def test_get_witness_batches_merges_distinct_plugin_batches(tmp_path):
    manager = PluginManager(app=None, keri_base=tmp_path / "keri")
    manager._plugins = {
        "one": _make_vault_plugin(
            "one",
            SimpleNamespace(batches=[["WIT_1", "WIT_2"], ["WIT_3"]]),
        ),
        "two": _make_vault_plugin(
            "two",
            SimpleNamespace(batches=[["WIT_2", "WIT_1"], ["WIT_4"]]),
        ),
        "three": _make_vault_plugin("three", None),
    }

    result = manager.get_witness_batches(vault=object(), hab_pre="AID_SHARED")

    assert result is not None
    assert result.batches == [["WIT_1", "WIT_2"], ["WIT_3"], ["WIT_4"]]
