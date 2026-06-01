"""Tests for locksmith_publisher.witnesses (5-witness federation)."""
from locksmith_publisher.witnesses import (
    KERI_HOST_FEDERATION,
    WitnessInfo,
    default_witness_pool,
)


def test_federation_has_five_witnesses():
    assert len(KERI_HOST_FEDERATION) == 5


def test_federation_aids_are_distinct():
    aids = {w.aid for w in KERI_HOST_FEDERATION}
    assert len(aids) == 5


def test_federation_oobi_pattern():
    for w in KERI_HOST_FEDERATION:
        assert w.oobi.startswith("https://witness.")
        assert "/witness/oobi/" in w.oobi
        assert w.oobi.endswith(w.aid)


def test_witness_info_base_url_strips_path():
    w = WitnessInfo.from_domain("witness.example.com", "BABC")
    assert w.base_url == "https://witness.example.com"


def test_default_witness_pool_returns_fresh_list():
    a = default_witness_pool()
    b = default_witness_pool()
    assert a == b
    # New list each call (callers may mutate without affecting the constant).
    a.pop()
    assert len(default_witness_pool()) == 5


def test_specific_federation_members():
    by_domain = {w.oobi.split("/")[2]: w.aid for w in KERI_HOST_FEDERATION}
    assert by_domain["witness.keri.host"] == "BE4B4CjpxNrCv8_HjLYvcwz-sui6AcJdygO-afEoTpmi"
    assert by_domain["witness.legitim.us"] == "BFuK9vjfkaGd5DdyAABzd00vmsxQ3bDDnUAAGpxc7ZGP"
    assert by_domain["witness.goonei.com"] == "BE7l4TEmGGpDAccj5Hc0bcIm5nABU2V2gFTrcF5NfT2j"
    assert by_domain["witness.verdadero.me"] == "BGR9eydkMxsAniqb3FSJwA24ADRM96STzWE_aaOeiyC5"
    assert by_domain["witness.honest.town"] == "BKCg06XEU80byz4ioN4Iim-7x2TzuklqKKuWRrViDqGV"
