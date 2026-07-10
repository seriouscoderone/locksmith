import json
from locksmith_publisher import publish
from locksmith_publisher.seal import build_release_sad

_PRE = "B" + "A" * 43   # 44-char qb64 prefix
_SAID = "E" + "A" * 43


class _Serder:
    """Minimal SerderKERI stand-in: carries a ked and a said."""
    def __init__(self, ked, said=_SAID):
        self.ked = ked
        self.said = said


class _Toader:
    num = 0  # toad=0 → the receipt wait is satisfied immediately (empty wigs OK)


class _Kever:
    def __init__(self, ked, sn=1):
        self.serder = _Serder(ked)
        self.sn = sn
        self.toader = _Toader()


class _Hab:
    def __init__(self, ked):
        self.pre = _PRE
        self.kever = _Kever(ked)
        self.interacts = []  # records data passed to interact()

    def interact(self, *, data, framed=False):
        self.interacts.append(data)


class _Hby:
    def __init__(self, ked):
        self._hab = _Hab(ked)

    class db:
        class wigs:
            @staticmethod
            def get(*, keys):
                return []  # toad=0 → no receipts required

    def habByName(self, alias):
        return self._hab

    def close(self):
        pass


def _patch(monkeypatch, ked):
    """Wire anchor_release onto a fake v2 hab whose latest event has ``ked``.

    Returns the fake hab so the test can inspect interact() calls.
    """
    hby = _Hby(ked)
    monkeypatch.setattr(publish.habbing, "Habery", lambda **kw: hby)
    monkeypatch.setattr(
        publish, "export_kel",
        lambda h, hab, *, version, brand: (b"kel", dict(said=_SAID, sn=1, bytes=b"anchor")))
    return hby.habByName("p")


def test_anchor_release_creates_ixn_programmatically_with_the_seal(tmp_path, monkeypatch):
    """anchor_release must create the ixn via hab.interact (NOT kli), passing the
    digest seal wrapped in a list (the ixn `a` field is a list of seals)."""
    a = tmp_path / "app.dmg"; a.write_bytes(b"m")
    w = tmp_path / "app.msi"; w.write_bytes(b"w")
    # Latest event is the icp (t=icp, no anchor) → a new ixn must be created.
    hab = _patch(monkeypatch, ked={"t": "icp", "a": []})

    publish.anchor_release(name="p", alias="p", bran="b", base="p",
                           version="0.2.20", brand="locksmith",
                           artifacts=[("macos", a), ("windows", w)], out_dir=str(tmp_path))

    assert len(hab.interacts) == 1, "exactly one ixn must be created"
    data = hab.interacts[0]
    assert isinstance(data, list) and len(data) == 1, "seal must be list-wrapped"
    seal = data[0]
    assert set(seal) == {"d", "brand", "ver"}
    assert seal["brand"] == "locksmith" and seal["ver"] == "0.2.20"
    assert len(seal["d"]) == 44  # qb64 SAID


def test_anchor_release_is_idempotent_when_latest_event_already_anchors(tmp_path, monkeypatch):
    """If the latest event is already an ixn carrying this (version, brand) seal,
    anchor_release must REUSE it (no duplicate ixn) — recovers a run whose ixn was
    created but not receipted."""
    a = tmp_path / "app.dmg"; a.write_bytes(b"m")
    w = tmp_path / "app.msi"; w.write_bytes(b"w")
    existing_seal = {"d": _SAID, "brand": "locksmith", "ver": "0.2.20"}
    hab = _patch(monkeypatch, ked={"t": "ixn", "a": [existing_seal]})

    publish.anchor_release(name="p", alias="p", bran="b", base="p",
                           version="0.2.20", brand="locksmith",
                           artifacts=[("macos", a), ("windows", w)], out_dir=str(tmp_path))

    assert hab.interacts == [], "must NOT create a duplicate ixn when already anchored"


def test_anchor_release_creates_ixn_when_latest_anchors_a_different_brand(tmp_path, monkeypatch):
    """A different brand's anchor at the latest event must NOT satisfy idempotency
    (the second brand of a multi-brand cut still needs its own ixn)."""
    a = tmp_path / "app.dmg"; a.write_bytes(b"m")
    w = tmp_path / "app.msi"; w.write_bytes(b"w")
    other = {"d": _SAID, "brand": "usurance", "ver": "0.2.20"}
    hab = _patch(monkeypatch, ked={"t": "ixn", "a": [other]})

    publish.anchor_release(name="p", alias="p", bran="b", base="p",
                           version="0.2.20", brand="locksmith",
                           artifacts=[("macos", a), ("windows", w)], out_dir=str(tmp_path))

    assert len(hab.interacts) == 1, "different brand → a new ixn is required"


def test_anchor_release_returns_release_sad(tmp_path, monkeypatch):
    """anchor_release must return a dict containing release_sad equal to
    build_release_sad() for the same inputs, with per-platform sha256s."""
    version, brand = "0.2.20", "locksmith"
    a = tmp_path / "app.dmg"; a.write_bytes(b"mac-payload")
    w = tmp_path / "app.msi"; w.write_bytes(b"win-payload")
    artifacts = [("macos", a), ("windows", w)]
    expected_sad = build_release_sad(version=version, artifacts=artifacts, brand=brand)

    _patch(monkeypatch, ked={"t": "icp", "a": []})

    result = publish.anchor_release(
        name="p", alias="p", bran="b", base="p",
        version=version, brand=brand, artifacts=artifacts, out_dir=str(tmp_path))

    assert result["release_sad"] == expected_sad
    assert result["release_sad"]["brand"] == brand
    assert result["release_sad"]["ver"] == version
    art = result["release_sad"]["artifacts"]
    assert {e["platform"] for e in art} == {"macos", "windows"}
    for entry in art:
        assert len(entry["sha256"]) == 64
    for key in ("anchor_said", "anchor_sn", "kel_path", "anchor_event_path"):
        assert key in result
