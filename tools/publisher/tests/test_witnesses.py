"""Tests for locksmith_publisher.witnesses (config-driven federation directory).

The witness directory is now built by iterating the deploy_config ``witnesses``
array (gitignored real config; committed ``example.com`` template), so these
tests assert structure/behaviour against the loaded config rather than baking in
the real federation domains (which are no longer committed).
"""
from locksmith.release import load_deploy_config
from locksmith_publisher.witnesses import (
    WitnessInfo,
    default_witness_pool,
)


def test_pool_matches_config_witness_count():
    config = load_deploy_config()
    assert len(default_witness_pool()) == len(config["witnesses"])


def test_pool_aids_are_distinct():
    pool = default_witness_pool()
    aids = {w.aid for w in pool}
    assert len(aids) == len(pool)


def test_pool_oobi_pattern():
    """OOBI URLs follow the KERI spec convention /oobi/<aid>/<role>.

    Matches keripy's OOBI_URL_TEMPLATE = "/oobi/{cid}/{role}" and the
    mailbox OOBI pattern. NOT the kerihost-internal `/witness/oobi/<aid>`
    API path (which is a different concern).
    """
    for w in default_witness_pool():
        assert w.oobi.startswith("https://")
        assert "/oobi/" in w.oobi
        assert w.oobi.endswith(f"/{w.aid}/witness"), (
            f"OOBI {w.oobi!r} does not match /<host>/oobi/<aid>/witness pattern"
        )


def test_witness_info_base_url_strips_path():
    w = WitnessInfo.from_domain("witness.example.com", "BABC")
    assert w.base_url == "https://witness.example.com"


def test_default_witness_pool_returns_fresh_list():
    a = default_witness_pool()
    b = default_witness_pool()
    assert a == b
    # New list each call (callers may mutate without affecting the next read).
    n = len(a)
    a.pop()
    assert len(default_witness_pool()) == n


def test_pool_built_from_config_hosts_and_aids():
    """Each pool entry's host + AID round-trips from the deploy_config entry."""
    config = load_deploy_config()
    pool = default_witness_pool()
    by_host = {w.oobi.split("/")[2]: w.aid for w in pool}
    for entry in config["witnesses"]:
        assert by_host[entry["host"]] == entry["aid"]
