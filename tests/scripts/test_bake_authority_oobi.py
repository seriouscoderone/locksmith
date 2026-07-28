"""Tests for scripts/bake_authority_oobi.py — the authority-OOBI re-bake path.

The bundled ``brands/<brand>/egf/oobis/<aid>.cesr`` is a SIGNED artifact: the
``/loc/scheme`` rpy inside it is signed by the authority's own AID, so the
endpoint cannot be corrected with a text editor. It has to be re-exported from
the authority's vault and re-validated. This script is that path, and its job
is to make the bad-bake failure (a loopback endpoint) impossible to commit by
accident.
"""
import base64
import importlib.util
import sys
from pathlib import Path

import pytest
from keri import Vrsn_1_0, kering
from keri.app import habbing

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "bake_authority_oobi.py"


def _load():
    spec = importlib.util.spec_from_file_location("bake_authority_oobi", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bake_authority_oobi"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def authority():
    """A real signing AID that publishes a peer role, like a custody vault."""
    with habbing.openHby(name="auth", temp=True, version=Vrsn_1_0) as hby:
        hab = hby.makeHab(name="auth", transferable=True, version=Vrsn_1_0)

        def export(url: str) -> bytes:
            for msg in (
                hab.reply(route="/loc/scheme",
                          data=dict(eid=hab.pre, scheme=kering.Schemes.tcp,
                                    url=url)),
                hab.reply(route="/end/role/add",
                          data=dict(cid=hab.pre, role=kering.Roles.peer,
                                    eid=hab.pre)),
            ):
                hby.psr.parse(ims=bytearray(msg))
            return bytes(hab.replyToOobi(aid=hab.pre, role=kering.Roles.peer))

        yield hab.pre, export


def test_decodes_a_wallet_exported_blob_token():
    mod = _load()
    raw = b"some-cesr-bytes"
    token = "locksmith-peer-oobi:v1:" + base64.b64encode(raw).decode("ascii")
    assert mod.decode_input(token) == raw


def test_passes_raw_cesr_through_unchanged():
    mod = _load()
    assert mod.decode_input('{"v":"KERI10JSON"...}') == b'{"v":"KERI10JSON"...}'


def test_inspect_reports_the_signed_endpoint(authority):
    mod = _load()
    aid, export = authority
    assert mod.inspect(export("tcp://192.168.1.20:5621"), aid) == \
        "tcp://192.168.1.20:5621"


def test_bake_writes_the_artifact_named_by_its_aid(authority, tmp_path):
    mod = _load()
    aid, export = authority
    cesr = export("tcp://192.168.1.20:5621")
    out = mod.bake(cesr, aid, tmp_path)
    assert out == tmp_path / f"{aid}.cesr"
    assert out.read_bytes() == cesr


def test_bake_refuses_a_loopback_endpoint(authority, tmp_path):
    """The whole reason this script exists."""
    mod = _load()
    aid, export = authority
    with pytest.raises(mod.BakeError) as ei:
        mod.bake(export("tcp://127.0.0.1:5621"), aid, tmp_path)
    assert "127.0.0.1" in str(ei.value)
    assert not list(tmp_path.iterdir())


def test_bake_refuses_a_wildcard_endpoint(authority, tmp_path):
    mod = _load()
    aid, export = authority
    with pytest.raises(mod.BakeError):
        mod.bake(export("tcp://0.0.0.0:5621"), aid, tmp_path)


def test_bake_refuses_when_the_aid_is_not_the_expected_authority(authority, tmp_path):
    """Guards against baking the wrong wallet's export into a brand — the
    EGF pins the authority AID, an artifact for any other AID is inert."""
    mod = _load()
    aid, export = authority
    with pytest.raises(mod.BakeError) as ei:
        mod.bake(export("tcp://192.168.1.20:5621"), "E" + "Z" * 43, tmp_path)
    assert "does not carry" in str(ei.value) or "expected" in str(ei.value)
    assert not list(tmp_path.iterdir())


def test_baked_artifact_passes_the_shipped_brand_guard(authority, tmp_path):
    """End to end: what this script writes is what
    tests/core/test_brand_oobi_endpoints.py accepts."""
    guard_spec = importlib.util.spec_from_file_location(
        "brand_oobi_guard", REPO / "tests" / "core" / "test_brand_oobi_endpoints.py")
    guard = importlib.util.module_from_spec(guard_spec)
    guard_spec.loader.exec_module(guard)
    _URL_RE, _host_of, _is_unroutable = (
        guard._URL_RE, guard._host_of, guard._is_unroutable)
    mod = _load()
    aid, export = authority
    out = mod.bake(export("tcp://192.168.1.20:5621"), aid, tmp_path)
    urls = [m.group(1).decode() for m in _URL_RE.finditer(out.read_bytes())]
    assert urls and not [u for u in urls if _is_unroutable(_host_of(u))]
