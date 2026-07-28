"""No shipped brand may bundle an authority OOBI that points at loopback.

Every ``brands/<brand>/egf/oobis/*.cesr`` is baked on somebody's dev machine,
from that machine's peer settings. If those settings advertise 127.0.0.1 the
signed ``/loc/scheme`` rpy carries it, every install pairs the authority at
its OWN loopback, and the only symptom is "the administrator's application
isn't reachable". The rpy is signed by the authority's AID, so the artifact
cannot be hand-corrected — it has to be regenerated and re-signed. This guard
catches the bad bake at commit time instead.

See ``scripts/bake_authority_oobi.py`` for the re-bake path.
"""
import ipaddress
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_URL_RE = re.compile(rb'"url"\s*:\s*"([^"]*)"')
_UNROUTABLE_NAMES = {"localhost", "localhost.localdomain", "", "*"}


def _oobi_artifacts() -> list[Path]:
    return sorted((_REPO / "brands").glob("*/egf/oobis/*.cesr"))


def _host_of(url: str) -> str:
    from urllib.parse import urlparse
    return (urlparse(url).hostname or "").strip()


def _is_unroutable(host: str) -> bool:
    if host.lower() in _UNROUTABLE_NAMES:
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False          # a DNS name we can't judge here — allowed
    return addr.is_loopback or addr.is_unspecified


def test_the_guard_actually_has_artifacts_to_scan():
    """A moved/renamed bundle directory would turn every check below into a
    vacuous pass — the exact way this class of guard rots."""
    assert _oobi_artifacts(), "no brands/*/egf/oobis/*.cesr found to scan"


@pytest.mark.parametrize(
    "artifact", _oobi_artifacts(), ids=lambda p: f"{p.parents[2].name}/{p.name}")
def test_bundled_oobi_advertises_a_routable_endpoint(artifact: Path):
    raw = artifact.read_bytes()
    urls = [m.group(1).decode("utf-8", "replace") for m in _URL_RE.finditer(raw)]
    assert urls, f"{artifact} carries no /loc/scheme url at all"
    bad = [u for u in urls if u and _is_unroutable(_host_of(u))]
    assert not bad, (
        f"{artifact.relative_to(_REPO)} advertises unroutable endpoint(s) "
        f"{bad}. Every install pairs this authority at its own loopback and "
        f"can never reach it. The rpy is signed — regenerate it from the "
        f"authority's vault (scripts/bake_authority_oobi.py), do not edit."
    )


def test_unroutable_classification():
    """Pins what the guard treats as unroutable, so a future edit to
    _is_unroutable can't quietly widen the hole."""
    assert _is_unroutable("127.0.0.1")
    assert _is_unroutable("127.1.2.3")
    assert _is_unroutable("0.0.0.0")
    assert _is_unroutable("::1")
    assert _is_unroutable("::")
    assert _is_unroutable("localhost")
    assert not _is_unroutable("192.168.1.20")
    assert not _is_unroutable("100.64.0.7")
    assert not _is_unroutable("admin.usurance.com")
