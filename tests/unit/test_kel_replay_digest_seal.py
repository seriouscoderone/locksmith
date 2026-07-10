from types import SimpleNamespace
from locksmith.update.kel_replay import extract_release_seal, highest_version_for_brand


def _state(events):
    return SimpleNamespace(events=events)


def _ev(said, sn, seals):
    return SimpleNamespace(said=said, sn=sn, seals=seals)


def test_extract_returns_digest_seal():
    st = _state([_ev("Eanchor", 1, [{"d": "Esad", "brand": "locksmith", "ver": "0.2.20"}])])
    seal = extract_release_seal(st, anchor_said="Eanchor")
    assert seal == {"d": "Esad", "brand": "locksmith", "ver": "0.2.20"}


def test_highest_version_reads_ver_from_digest_seals():
    st = _state([
        _ev("E1", 1, [{"d": "Ea", "brand": "locksmith", "ver": "0.2.19"}]),
        _ev("E2", 2, [{"d": "Eb", "brand": "locksmith", "ver": "0.2.20"}]),
        _ev("E3", 3, [{"d": "Ec", "brand": "usurance", "ver": "0.3.0"}]),
    ])
    assert highest_version_for_brand(st, "locksmith") == "0.2.20"
    assert highest_version_for_brand(st, "usurance") == "0.3.0"
