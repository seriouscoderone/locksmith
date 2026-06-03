from datetime import datetime, timezone

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerRecord
from locksmith.ui.vault.peers.list import PairedPeersPage


class _StubVault:
    def __init__(self, baser):
        self.db = baser


def _seed(baser, aid="EAID_BOB"):
    PeerAllowlist(baser).add(PeerRecord(
        aid=aid, label="Bob", endpoint_url="tcp://10.0.0.2:5621",
        paired_at=datetime.now(timezone.utc).isoformat(),
    ))


def test_page_renders_paired_rows(qapp, baser):
    _seed(baser)
    page = PairedPeersPage(vault=_StubVault(baser))
    page.refresh()
    rows = page.list_widget.count()
    assert rows == 1


def test_unpair_removes_row(qapp, baser):
    _seed(baser)
    page = PairedPeersPage(vault=_StubVault(baser))
    page.refresh()
    page.unpair("EAID_BOB")
    page.refresh()
    assert page.list_widget.count() == 0
