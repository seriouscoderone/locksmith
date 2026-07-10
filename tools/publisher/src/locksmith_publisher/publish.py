"""Greenfield publisher orchestration: build seal → kli interact (sign+witness) →
read the KEL back via clonePreIter (export + anchor lookup). No re-implemented
KERI logic — kli for keys, keri lib read-only for the KEL stream."""
import json
import time
from pathlib import Path
from keri.app import agenting, habbing
from keri.core import serdering
from keri.db import dbing
from hio.base import doing
from .seal import build_release_seal, build_release_sad
from . import kli
from locksmith.update.kel_replay import replay_kel


def _wait_for_receipts(hby, hab, *, toad, timeout_s=90.0, recollect):
    """Poll the latest event's witness-receipt count until >= toad, re-collecting
    from the witnesses each round while short. Raises TimeoutError on timeout."""
    deadline = time.monotonic() + timeout_s
    def _count():
        dgkey = dbing.dgKey(hab.pre, hab.kever.serder.said)
        return len(hby.db.wigs.get(keys=dgkey) or [])
    n = _count()
    while n < toad and time.monotonic() < deadline:
        recollect()
        time.sleep(2.0)
        n = _count()
    if n < toad:
        raise TimeoutError(
            f"only {n}/{toad} witness receipts for sn={hab.kever.sn} after {timeout_s}s")
    return n


def anchor_release(*, name, alias, bran, base, version, brand,
                   artifacts: list[tuple[str, Path]], out_dir: str) -> dict:
    """Anchor one release. Returns {anchor_said, anchor_sn, kel_path, anchor_event_path, release_sad}."""
    seal = build_release_seal(version=version, artifacts=artifacts, brand=brand)
    sad = build_release_sad(version=version, artifacts=artifacts, brand=brand)
    kli.kli_interact(name=name, alias=alias, bran=bran, base=base, data=json.dumps(seal))

    # Read the KEL back (no keys needed to read). clonePreIter yields one msg per
    # event = event bytes + its inline attachments (sigs/wigs); SerderKERI parses
    # the leading event. The anchor is the event whose `a` carries our release seal.
    hby = habbing.Habery(name=name, base=base, bran=bran)
    try:
        hab = hby.habByName(alias)

        # Wait until the just-anchored ixn has >= toad witness receipts BEFORE the
        # clonePreIter export. Federation receipts arrive async (witness-side
        # eventual consistency), so a too-soon export carries an under-receipted
        # anchor that the client gate escrows + rejects (the 0.2.4-class failure).
        # Re-collect each short round via a stock keripy Receiptor pass — NOT
        # WitnessReceiptor, which hangs over HTTP (see ~/code/KERI-COMMUNICATION-MODEL.md).
        toad = hab.kever.toader.num

        def _recollect():
            receiptor = agenting.Receiptor(hby=hby)

            def _pass(tymth, tock=0.0, **opts):
                receiptor.wind(tymth)
                _ = (yield tock)
                try:
                    yield from receiptor.receipt(hab.pre, sn=hab.kever.sn)
                finally:
                    receiptor.remove(list(receiptor.doers))
                return

            doing.Doist(tock=0.03125, real=True).do(
                doers=[receiptor, doing.doify(_pass)], limit=30.0)

        n = _wait_for_receipts(hby, hab, toad=toad, timeout_s=120.0,
                               recollect=_recollect)
        print(f"anchor: {n}/{toad} witness receipts for sn={hab.kever.sn} "
              f"before export")

        kel = bytearray()
        anchor = None
        for msg in hby.db.clonePreIter(pre=hab.pre):
            kel.extend(msg)
            serder = serdering.SerderKERI(raw=bytes(msg))
            for s in serder.ked.get("a", []):
                if isinstance(s, dict) and s.get("ver") == version and s.get("brand") == brand:
                    anchor = dict(said=serder.said, sn=serder.sn, bytes=bytes(msg))
        if anchor is None:
            raise RuntimeError(f"no anchor event for version {version} in publisher KEL")
        pre = hab.pre
    finally:
        hby.close()

    kel_path = Path(out_dir) / f"{pre}-kel.cesr"
    kel_path.write_bytes(bytes(kel))
    anchor_event_path = Path(out_dir) / f"{anchor['said']}.cesr"
    anchor_event_path.write_bytes(anchor["bytes"])
    return dict(anchor_said=anchor["said"], anchor_sn=anchor["sn"],
                kel_path=str(kel_path), anchor_event_path=str(anchor_event_path),
                release_sad=sad)


def assert_kel_anchors_release(*, kel_bytes: bytes, publisher_aid: str,
                               version: str, anchor_said: str, toad: int) -> None:
    """Replay the exported KEL through the toad-gated verifier and confirm the
    release's anchor is ACCEPTED. Raises if the anchor is missing/escrowed —
    e.g. published with < toad witness receipts (the 0.2.4-class failure)."""
    state = replay_kel(kel_stream=kel_bytes, publisher_aid=publisher_aid,
                       embedded_sn=0, embedded_said=publisher_aid, toad=toad)
    for ev in state.events:
        if ev.said == anchor_said:
            for s in ev.seals:
                if isinstance(s, dict) and s.get("ver") == version:
                    return
            raise RuntimeError(
                f"anchor {anchor_said} accepted but does not carry release v{version}")
    raise RuntimeError(
        f"release v{version} anchor {anchor_said} not accepted in published KEL "
        f"(missing/escrowed — likely < toad={toad} witness receipts)")
