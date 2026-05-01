from types import SimpleNamespace

from locksmith.plugins.manager import PluginManager


def test_get_witness_batches_merges_distinct_plugin_batches():
    manager = PluginManager(app=None)
    manager._plugins = {
        "one": SimpleNamespace(
            get_witness_batches=lambda vault, hab_pre: SimpleNamespace(
                batches=[["WIT_1", "WIT_2"], ["WIT_3"]]
            )
        ),
        "two": SimpleNamespace(
            get_witness_batches=lambda vault, hab_pre: SimpleNamespace(
                batches=[["WIT_2", "WIT_1"], ["WIT_4"]]
            )
        ),
        "three": SimpleNamespace(get_witness_batches=lambda vault, hab_pre: None),
    }

    result = manager.get_witness_batches(vault=object(), hab_pre="AID_SHARED")

    assert result is not None
    assert result.batches == [["WIT_1", "WIT_2"], ["WIT_3"], ["WIT_4"]]
