"""Greenfield publisher orchestration: build seal → kli interact (sign+witness) →
read the KEL back via clonePreIter (export + anchor lookup). No re-implemented
KERI logic — kli for keys, keri lib read-only for the KEL stream."""
import json
from pathlib import Path
from keri.app import habbing
from keri.core import serdering
from .seal import build_release_seal
from . import kli


def anchor_release(*, name, alias, bran, base, version,
                   artifacts: list[tuple[str, Path]], out_dir: str) -> dict:
    """Anchor one release. Returns {anchor_said, anchor_sn, kel_path, anchor_event_path}."""
    seal = build_release_seal(version=version, artifacts=artifacts)
    kli.kli_interact(name=name, alias=alias, bran=bran, base=base, data=json.dumps(seal))

    # Read the KEL back (no keys needed to read). clonePreIter yields one msg per
    # event = event bytes + its inline attachments (sigs/wigs); SerderKERI parses
    # the leading event. The anchor is the event whose `a` carries our release seal.
    hby = habbing.Habery(name=name, base=base, bran=bran)
    try:
        hab = hby.habByName(alias)
        kel = bytearray()
        anchor = None
        for msg in hby.db.clonePreIter(pre=hab.pre):
            kel.extend(msg)
            serder = serdering.SerderKERI(raw=bytes(msg))
            for s in serder.ked.get("a", []):
                if isinstance(s, dict) and s.get("release", {}).get("v") == version:
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
                kel_path=str(kel_path), anchor_event_path=str(anchor_event_path))
