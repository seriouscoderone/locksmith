"""Replay a publisher KEL stream against witness receipts.

Per spec §7.3 / §7.6 / §7.7:
- Embedded ``publisher_anchor.json`` provides AID prefix + KEL SAID at build time.
- Verifier fetches the live KEL from the appcast's ``publisher_kel_url``.
- Replays forward, validating each event's signature against the running key
  state and counting witness receipts (toad).
- Rotation events update the running key state but must satisfy pre-rotation
  digest commitments from the prior establishment event.

Uses keripy primitives directly (``Kevery``, ``Parser``) so KERI semantics
are reused; this module adds only the policy layer (toad enforcement, seal
extraction, error-type translation, and rejection of unknown publishers).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from keri import kering
from keri.core import eventing, parsing, serdering
from keri.core.counting import Vrsn_1_0
from keri.db import basing, dbing

from locksmith.update.errors import (
    RotationMismatchError,
    SchemaError,
    SignatureError,
    WitnessThresholdError,
)


# Establishment event ilks per KERI: icp, dip, rot, drt.
EST_ILKS = ("icp", "dip", "rot", "drt")


@dataclass
class ReplayedEvent:
    sn: int
    said: str
    ilk: str
    seals: list[dict]  # ``a`` field — anchored seals for ixn (and est events)
    receipts: int


@dataclass
class KelState:
    publisher_aid: str
    current_sn: int
    current_said: str
    current_keys: tuple[str, ...]
    next_digest: str
    toad: int
    events: list[ReplayedEvent] = field(default_factory=list)


def _translate_keripy_error(ex: Exception, *, publisher_aid: str) -> Exception:
    """Map keripy validation errors to ``locksmith.update.errors`` subclasses."""
    msg = str(ex).lower()
    if isinstance(ex, kering.SignatureError):
        return SignatureError(
            f"KEL signature invalid: {ex}",
            log_fields={"publisher_aid": publisher_aid},
        )
    if isinstance(ex, kering.ValidationError):
        if "rotat" in msg or "pre-rotation" in msg or "digest" in msg:
            return RotationMismatchError(
                f"rotation invalid: {ex}",
                log_fields={"publisher_aid": publisher_aid},
            )
        return SignatureError(
            f"KEL event invalid: {ex}",
            log_fields={"publisher_aid": publisher_aid},
        )
    return SchemaError(
        f"KEL parse failed: {ex}",
        log_fields={"publisher_aid": publisher_aid},
    )


def replay_kel(
    *,
    kel_stream: bytes,
    publisher_aid: str,
    embedded_sn: int,
    embedded_said: str | None,
    toad: int,
) -> KelState:
    """Replay ``kel_stream`` through a transient keripy DB and return ``KelState``.

    Raises one of ``locksmith.update.errors.*`` on any failure.
    """
    db = basing.Baser(name="locksmith_verify_replay", temp=True, reopen=True)
    try:
        kvy = eventing.Kevery(db=db, lax=True, local=False, cloned=True)
        parser = parsing.Parser(kvy=kvy, version=Vrsn_1_0)
        try:
            parser.parse(ims=bytearray(kel_stream))
        except kering.SignatureError as ex:
            raise _translate_keripy_error(ex, publisher_aid=publisher_aid) from ex
        except kering.ValidationError as ex:
            raise _translate_keripy_error(ex, publisher_aid=publisher_aid) from ex
        except Exception as ex:
            raise SchemaError(
                f"KEL parse failed: {ex}",
                log_fields={"publisher_aid": publisher_aid},
            ) from ex

        if publisher_aid not in kvy.kevers:
            raise SignatureError(
                f"publisher_aid {publisher_aid} not found in replayed KEL",
                log_fields={"publisher_aid": publisher_aid},
            )

        kever = kvy.kevers[publisher_aid]

        # Iterate events from sn=0 forward and check witness receipts.
        events: list[ReplayedEvent] = []
        for msg in db.clonePreIter(pre=publisher_aid, fn=0):
            serder = serdering.SerderKERI(raw=bytearray(msg))
            sn = serder.sn
            ilk = serder.ked.get("t", "")
            # ``a`` field is the anchored seals list (ixn) or established-state
            # seals (icp/rot — usually empty).
            seals_raw = serder.ked.get("a", [])
            seals = list(seals_raw) if isinstance(seals_raw, list) else []

            dgkey = dbing.dgKey(publisher_aid.encode(), serder.said.encode())
            wigs = db.wigs.get(keys=dgkey) or []
            num_receipts = len(wigs)

            # Enforce toad only on events at or past embedded_sn.
            if sn >= embedded_sn and num_receipts < toad:
                raise WitnessThresholdError(
                    f"event sn={sn} has {num_receipts} witness receipts, "
                    f"need toad={toad}",
                    log_fields={
                        "sn": sn,
                        "said": serder.said,
                        "receipts": num_receipts,
                        "toad": toad,
                    },
                )

            events.append(
                ReplayedEvent(
                    sn=sn,
                    said=serder.said,
                    ilk=ilk,
                    seals=seals,
                    receipts=num_receipts,
                )
            )

        if embedded_said is not None:
            matching = [
                e for e in events
                if e.sn == embedded_sn and e.said == embedded_said
            ]
            if not matching:
                raise SignatureError(
                    f"embedded_said {embedded_said} not found at sn={embedded_sn}",
                    log_fields={
                        "embedded_sn": embedded_sn,
                        "embedded_said": embedded_said,
                    },
                )

        next_dig = (
            kever.ndigers[0].qb64
            if kever.ndigers and kever.ndigers[0] is not None
            else ""
        )

        return KelState(
            publisher_aid=publisher_aid,
            current_sn=kever.sner.num,
            current_said=kever.serder.said,
            current_keys=tuple(v.qb64 for v in kever.verfers),
            next_digest=next_dig,
            toad=toad,
            events=events,
        )
    finally:
        db.close()


def extract_release_seal(state: KelState, *, anchor_said: str) -> dict:
    """Find the event with SAID == ``anchor_said`` and return its release seal.

    Returns the first seal dict in ``a`` that contains a ``release`` key.
    Raises ``SchemaError`` if no such event or seal exists.
    """
    for ev in state.events:
        if ev.said == anchor_said:
            for s in ev.seals:
                if isinstance(s, dict) and "release" in s:
                    return s
            raise SchemaError(
                f"event {anchor_said} has no `release` seal",
                log_fields={"anchor_said": anchor_said, "sn": ev.sn},
            )
    raise SchemaError(
        f"no event in KEL matches anchor_said={anchor_said}",
        log_fields={"anchor_said": anchor_said},
    )
