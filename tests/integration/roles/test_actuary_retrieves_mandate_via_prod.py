# -*- encoding: utf-8 -*-
"""The actuary retrieves the mandate BY ASKING — no test-only push.

`watch_cuo_mandate_via_peer` (roles/conftest.py) proves the scan and the
acceptance, and says plainly what it does not prove: a `sitecustomize` hook
inside wallet A writes the credential bytes to a file and the TEST pushes them
over the wire, "exactly as A itself would have, HAD THIS TRANSPORT ALREADY
GROWN A pro/bar RESPONDER (design's own open item)".

It has now grown one. This test deletes that shortcut: wallet A is never asked
to export anything, and the pytest process never pushes a credential. The
actuary's own `PeerSyncDoer` observes A's KEL, finds the mandate's anchoring
seal, sends a `pro`, and A's `ProdResponder` answers with a `bar` that the
actuary verifies and stores.

That end-to-end path had EIGHT distinct defects, every one of which produced
identical silence on the wire, and none of which this suite could see while the
artifact was hand-delivered:

  1. the query minted v2 against a v1-pinned parser
  2. cigar-signed queries died on KeyError('source') in msgProcess
  3. `peer_send` closed the socket before the reply could be read
  4. `anchoringPre` matched only bare digest seals, never an issuance SealEvent
  5. `cueDo` pulled the prod cue off the deck and discarded it
  6. `disclosable` was empty and the policy denied by default
  7. the prod carried no introduction, so it was dropped as "Unknown sender"
  8. the bar was signed by the non-transferable listener EID, so the recipient
     rejected it as "not anchored"

and finally `processBar` verified the body and cued it, and nothing drained the
cue -- so the credential arrived every five seconds and was thrown away.
"""
import time

import pytest

from tests.integration.peer.conftest import (  # noqa: F401 (two_hoa_wallets)
    free_port, import_peer_blob_via_ui, set_peer_mode_via_ui, two_hoa_wallets,
)
from tests.integration.roles.conftest import (
    _export_current_blob, declare_mandate_via_ui, open_vault_holding_actuary_role,
)

pytestmark = pytest.mark.integration


def test_the_actuary_retrieves_the_mandate_by_prodding_for_it(two_hoa_wallets):
    # BRANDED wallets. PeerSyncDoer is registered by HoaShellPlugin, which
    # only loads for a branded app -- on `two_wallets` (vanilla) the watch
    # under test does not exist and the test would fail for the wrong reason.
    devctl = two_hoa_wallets["devctl"]
    a, b = two_hoa_wallets["cuo"], two_hoa_wallets["actuary"]

    # 1. The CUO declares a mandate. Its ACDC is anchored in A's KEL by a
    #    3-field SealEvent; the body lives only in A's registry.
    declare_mandate_via_ui(devctl, a["sock"])

    # 2. The actuary takes up its role.
    open_vault_holding_actuary_role(devctl, b["sock"])

    # Both pages leave the nav in the credentials submenu (see
    # watch_cuo_mandate_via_peer's note); pop it so identifiers/settings are
    # reachable again.
    devctl(b["sock"], "click", target="vaultNavMenu.credentialsBackButton")
    devctl(a["sock"], "click", target="vaultNavMenu.credentialsBackButton")
    devctl(a["sock"], "click", target="vaultNavMenu.identifiersButton")

    # 3. Both sides listen, and B learns how to reach A. A is NOT told how to
    #    reach B and is never asked to send anything -- the whole point is that
    #    the actuary does the asking.
    set_peer_mode_via_ui(devctl, b["sock"], port=free_port())
    set_peer_mode_via_ui(devctl, a["sock"], port=free_port())
    import_peer_blob_via_ui(devctl, b["sock"],
                            _export_current_blob(devctl, a["sock"], "cuo"))

    # Peering settles asynchronously — the listener binds, the imported KEL is
    # parsed, and the peer record's endpoint becomes resolvable — with no
    # deterministic UI end-state to wait_for. A commented sleep is the harness's
    # sanctioned tool for exactly this (see docs/development/ui-driven-testing.md
    # "Waiting"); everything downstream of it is polled, not slept through.
    time.sleep(3.0)

    # 4. Wait for B's OWN watch. PeerSyncDoer ticks every 5s: sync A's KEL,
    #    spot the anchor, prod for the body, ingest the bar. Generous budget --
    #    several ticks plus TCP settling -- and polled rather than slept
    #    through, so a fast pass finishes fast.
    deadline, rows = time.time() + 90.0, None
    while time.time() < deadline:
        r = devctl(b["sock"], "get_list_items",
                   target="actuaryPage.observedMandates")
        rows = r.get("items") or r.get("rows") or []
        if rows:
            break
        time.sleep(2.0)

    assert rows, (
        "the actuary never retrieved the mandate. Nothing pushed it — this is "
        "the real pro/bar path, so an empty list means the ask, the answer, or "
        "the storing of the body failed. Check the wallet logs "
        f"({b['log']}, {a['log']}) for 'peer_sync', 'Prod:' and 'Bare'."
    )
