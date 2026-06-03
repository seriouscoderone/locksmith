"""Regression test: rotation auto-attempts bare receipt collection
(pure-KERI flow) before falling through to the TOTP dialog.

For witness operators that DON'T require TOTP (the spec-default behavior
— kerox, generic keripy-witness deployments, anyone who isn't kerihost),
the bare attempt succeeds and the user sees no extra dialog. For
witnesses that DO require TOTP (kerihost-managed), the bare attempt
returns 0 wigs, ``auth_pending=True`` stays set, and the existing
witness-auth dialog appears so the user can enter their code.

This test pins both branches by stubbing receiptor.receipt to control
how many wigs land in db.wigs.
"""
from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from hio.base import doing


@pytest.fixture
def rotation_env(monkeypatch, tmp_path):
    """Spin up a real Habery + a Hab with one witness so the rotate path
    has something to drive. Then monkeypatch the receiptor with a
    controllable stub so we can simulate both "witness accepts bare"
    and "witness rejects bare → 0 wigs" outcomes.
    """
    from keri.app import habbing
    from keri.core import signing
    from locksmith.db.basing import LocksmithBaser

    hby = habbing.Habery(
        name="rottest", bran="A" * 21,
        salt=signing.Salter(raw=b"0123456789abcdef").qb64, temp=True,
    )
    # Pre-load a fake witness AID into the hby so makeHab(wits=[...]) works.
    # Easiest: build a second hab that's non-transferable.
    wit_hab = hby.makeHab(name="fakewit", transferable=False,
                          isith="1", icount=1, ncount=0, nsith="0")
    wit_pre = wit_hab.pre
    # Inception with this witness
    alice = hby.makeHab(name="alice", transferable=True,
                        isith="1", icount=1, ncount=1, nsith="1",
                        wits=[wit_pre], toad=1)

    baser = LocksmithBaser(name="rottest_baser", headDirPath=str(tmp_path),
                           reopen=True, temp=True)

    # Fake the vault enough to drive RotateDoer
    receipt_calls = []
    wigs_to_produce = {"count": 0}

    def stub_receipt(pre, sn=None, auths=None):
        receipt_calls.append({"pre": pre, "sn": sn, "auths": auths or {}})
        # Insert fake wig records based on wigs_to_produce["count"]
        # The check below uses .get(keys=dgKey(...)) so we need to seed
        # alice.hab.db.wigs with that many entries. Since wigs_to_produce
        # is set per test, just yield once and return — the wigs are
        # already there from setup.
        if False:
            yield
        return
        yield  # make this a generator

    fake_receiptor = SimpleNamespace(receipt=stub_receipt)
    fake_vault = SimpleNamespace(
        hby=hby, db=baser, receiptor=fake_receiptor,
        swain=SimpleNamespace(), postman=SimpleNamespace(),
    )
    app = SimpleNamespace(vault=fake_vault, plugin_manager=None)
    yield {
        "hby": hby, "baser": baser, "alice": alice,
        "wit_pre": wit_pre, "app": app, "receipt_calls": receipt_calls,
        "wigs_to_produce": wigs_to_produce,
    }
    baser.close(clear=True)
    hby.close()


def _seed_wigs(hab, count):
    """Plant `count` fake wig records under the current event SAID."""
    from keri.db import dbing
    from keri.core import indexing
    if count <= 0:
        return
    key = dbing.dgKey(hab.pre, hab.kever.serder.said)
    # Encode any indexed signature shape — content doesn't matter; we
    # only check len(wigs) downstream.
    fake_siger = indexing.Siger(
        raw=b"\x00" * 64, code=indexing.IdxSigDex.Ed25519_Sig, index=0,
    )
    hab.db.wigs.put(keys=key, vals=[fake_siger for _ in range(count)])


def test_rotate_skips_auth_dialog_when_bare_receipts_succeed(rotation_env):
    """Pure-KERI happy path: witness accepts the bare receipt request,
    enough wigs land, auth_pending stays False, the success signal
    reports needs_auth=False (so the dialog never shows the TOTP step).
    """
    from locksmith.core.rotating import RotateDoer

    env = rotation_env
    alice = env["alice"]

    # Wrap the stub so it plants wigs BEFORE the doer reads them.
    def stub_with_wigs(pre, sn=None, auths=None):
        env["receipt_calls"].append({"pre": pre, "sn": sn, "auths": auths or {}})
        _seed_wigs(alice, 1)  # TOAD is 1 → 1 wig meets it
        return
        yield
    env["app"].vault.receiptor.receipt = stub_with_wigs

    captured: list[tuple[str, str, dict]] = []
    bridge = SimpleNamespace(
        emit_doer_event=lambda doer_name, event_type, data: captured.append(
            (doer_name, event_type, data)
        )
    )

    doer = RotateDoer(
        app=env["app"], hab=alice,
        isith="1", nsith="1", count=1, toad=1,
        cuts=[], adds=[], signal_bridge=bridge,
    )
    doist = doing.Doist(limit=2.0, tock=0.03125, real=False)
    doist.do(doers=[doer])

    # Bare attempt must have happened
    bare_calls = [c for c in env["receipt_calls"] if not c["auths"]]
    assert len(bare_calls) >= 1, "bare receipt collection must be attempted"

    # auth_pending must have been cleared (or never set)
    idm = env["app"].vault.db.idm.get(keys=(alice.pre,))
    assert idm is None or idm.auth_pending is False, (
        f"auth_pending should be False after successful bare receipts; "
        f"got {idm}"
    )

    # Signal payload must tell the UI no auth needed
    complete = [e for e in captured if e[1] == "rotation_complete"]
    assert len(complete) == 1
    data = complete[0][2]
    assert data.get("needs_auth") is False, (
        f"needs_auth should be False so the dialog skips the auth step; "
        f"got {data}"
    )


def test_rotate_falls_back_to_auth_when_plugin_has_seed(rotation_env):
    """Kerihost-style path: witness ignores the bare request (no wigs
    land) AND a plugin holds TOTP material for one of the witnesses,
    so the TOTP step can actually unblock the user. needs_auth=True.
    """
    from locksmith.core.rotating import RotateDoer

    env = rotation_env
    alice = env["alice"]

    def stub_no_wigs(pre, sn=None, auths=None):
        env["receipt_calls"].append({"pre": pre, "sn": sn, "auths": auths or {}})
        return
        yield
    env["app"].vault.receiptor.receipt = stub_no_wigs

    # Plugin manager says: yes, we have auth material for one of these wits
    env["app"].plugin_manager = SimpleNamespace(
        has_witness_auth_for_any=lambda vault, hab_pre, wits: True,
    )

    captured: list[tuple[str, str, dict]] = []
    bridge = SimpleNamespace(
        emit_doer_event=lambda doer_name, event_type, data: captured.append(
            (doer_name, event_type, data)
        )
    )

    doer = RotateDoer(
        app=env["app"], hab=alice,
        isith="1", nsith="1", count=1, toad=1,
        cuts=[], adds=[], signal_bridge=bridge,
    )
    doist = doing.Doist(limit=2.0, tock=0.03125, real=False)
    doist.do(doers=[doer])

    assert env["receipt_calls"], "bare receipt collection must be attempted"

    idm = env["app"].vault.db.idm.get(keys=(alice.pre,))
    assert idm is not None and idm.auth_pending is True

    complete = [e for e in captured if e[1] == "rotation_complete"]
    assert len(complete) == 1
    data = complete[0][2]
    assert data.get("needs_auth") is True
    assert data.get("receipts_collected") is False


def test_rotate_does_not_show_auth_modal_when_no_plugin_seed(rotation_env):
    """Pure-KERI witness path that's *failing* (e.g. kerihost #6 keripy
    Verfer bug): bare receipts didn't collect AND no plugin has auth
    material (no TOTP seed registered for these wits). The TOTP modal
    would be useless — there's no code to type. needs_auth must stay
    False; receipts_collected=False signals to the dialog that the
    rotation is locally done but un-receipted, so the UI can show an
    informational warning rather than prompting for an OTP.
    """
    from locksmith.core.rotating import RotateDoer

    env = rotation_env
    alice = env["alice"]

    def stub_no_wigs(pre, sn=None, auths=None):
        env["receipt_calls"].append({"pre": pre, "sn": sn, "auths": auths or {}})
        return
        yield
    env["app"].vault.receiptor.receipt = stub_no_wigs

    # Plugin manager says: no plugin has auth material for these wits
    env["app"].plugin_manager = SimpleNamespace(
        has_witness_auth_for_any=lambda vault, hab_pre, wits: False,
    )

    captured: list[tuple[str, str, dict]] = []
    bridge = SimpleNamespace(
        emit_doer_event=lambda doer_name, event_type, data: captured.append(
            (doer_name, event_type, data)
        )
    )

    doer = RotateDoer(
        app=env["app"], hab=alice,
        isith="1", nsith="1", count=1, toad=1,
        cuts=[], adds=[], signal_bridge=bridge,
    )
    doist = doing.Doist(limit=2.0, tock=0.03125, real=False)
    doist.do(doers=[doer])

    assert env["receipt_calls"], "bare receipt collection must still be attempted"

    idm = env["app"].vault.db.idm.get(keys=(alice.pre,))
    # auth_pending must be False — we're not asking the user to fix it
    assert idm is None or idm.auth_pending is False, (
        f"auth_pending should be False when no plugin has material; got {idm}"
    )

    complete = [e for e in captured if e[1] == "rotation_complete"]
    assert len(complete) == 1
    data = complete[0][2]
    assert data.get("needs_auth") is False
    assert data.get("receipts_collected") is False, (
        "receipts_collected must distinguish the 'no auth needed because "
        "receipts succeeded' case from the 'no auth would help' case"
    )
