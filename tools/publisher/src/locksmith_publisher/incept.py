"""Publisher AID inception ceremony.

Builds a 2-of-3 multisig KERI `icp` event with:
- Three signing keys, one per custodian device (laptop YK, desktop YK, air-gapped USB)
- Signing threshold (`isith`) = 2
- Pre-rotated next-key digests, rotation threshold (`nsith`) = 2
- Witness list = the KERI.host 5-witness federation (hardcoded; no remote discovery)
- toad = 3 (3-of-5 majority)

Emits:
- `publisher_anchor.json` (committed to `src/locksmith/release/`)
- `publisher-aid.json` (uploaded to S3 at `publisher/v1/publisher-aid.json`)
- `kel-events/icp-sn-0.cesr` (the serialized inception event itself)

keripy v2.0.0-dev6 API notes
----------------------------
- `incept()` uses ``isith`` (inception signing threshold), NOT ``sith``.
- `incept()` defaults to ``kind='CESR'`` but keripy v2 CESR is only valid for
  major protocol version 2. We force ``kind='JSON'`` so that the v1 event
  serialises correctly.
- ``coring.MtrDex.Blake3_256`` is the correct pre-rotation digest code.
- ``coring.MtrDex.Ed25519`` (transferable) is correct for a rotating multisig
  AID; ``Ed25519N`` (non-transferable) would forbid future rotations.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from keri.core import coring
from keri.core.eventing import incept

from .anchor import PublisherAnchor, write_publisher_anchor, write_publisher_summary
from .software_key import open_software_devices
from .witness_client import Receipt, WitnessClient
from .witnesses import WitnessInfo, default_witness_pool
from .yubikey import FakeYubiKeyDevice, YubiKeyDevice, open_real_device


@dataclass
class InceptionResult:
    aid_prefix: str
    event_said: str
    signing_threshold: int
    rotation_threshold: int
    toad: int
    signer_pubkeys: List[bytes] = field(default_factory=list)
    next_digests: List[bytes] = field(default_factory=list)
    serialized_event: bytes = b""


def _next_key_digest() -> bytes:
    """Generate a pre-rotation digest commitment.

    For Phase 1, the next-key set is freshly generated and not retained by the
    ceremony — production inception will record the next-key material to each
    custodian device's secure storage. The current event commits only to the
    Blake3 digest of each next key, which is all KERI requires.
    """
    raw = secrets.token_bytes(32)
    digest = coring.Diger(raw=raw, code=coring.MtrDex.Blake3_256)
    return digest.raw


def build_inception_event(
    *,
    signers: list[YubiKeyDevice],
    signer_quorum: int,
    witnesses: list[WitnessInfo],
    toad: int,
) -> InceptionResult:
    """Build (but do not submit) the multisig inception event."""
    if len(signers) < signer_quorum:
        raise ValueError(f"need at least {signer_quorum} signer devices; got {len(signers)}")
    if len(witnesses) < toad:
        raise ValueError(f"need at least {toad} witnesses; got {len(witnesses)}")

    signer_pubkeys: list[bytes] = []
    for device in signers:
        pk = device.generate_signing_key()
        signer_pubkeys.append(pk)

    # Pre-rotation: generate fresh ephemeral next-key material and commit to its
    # Blake3 digest. The raw digest bytes are stored so the caller can verify
    # they differ from the current signing pubkeys.
    next_digest_raws: list[bytes] = [_next_key_digest() for _ in signers]

    # Build using keripy primitives.
    # Ed25519 (transferable) allows future rotation; Ed25519N would forbid it.
    verfers = [coring.Verfer(raw=pk, code=coring.MtrDex.Ed25519) for pk in signer_pubkeys]
    digers = [coring.Diger(raw=d, code=coring.MtrDex.Blake3_256) for d in next_digest_raws]

    # keripy v2.0.0-dev6: signing threshold param is `isith` (not `sith`).
    # kind must be 'JSON' for protocol major version 1 events.
    serder = incept(
        keys=[v.qb64 for v in verfers],
        isith=str(signer_quorum),
        ndigs=[d.qb64 for d in digers],
        nsith=str(signer_quorum),
        wits=[w.aid for w in witnesses],
        toad=toad,
        code=coring.MtrDex.Blake3_256,
        kind="JSON",
    )

    return InceptionResult(
        aid_prefix=serder.pre,
        event_said=serder.said,
        signing_threshold=signer_quorum,
        rotation_threshold=signer_quorum,
        toad=toad,
        signer_pubkeys=signer_pubkeys,
        next_digests=next_digest_raws,
        serialized_event=serder.raw,
    )


def run_inception_ceremony(
    *,
    witness_oobis: list[str],
    toad: int,
    quorum: int,
    signers: int,
    dry_run: bool,
    output_dir: Path,
    yubikey_slots: list[str],
    submit: bool = False,
    software_key_dir: Path | None = None,
    software_passphrases: list[bytes] | None = None,
) -> None:
    """End-to-end inception ceremony runner.

    `dry_run=True` uses FakeYubiKeyDevice and writes outputs to a tmp dir.
    `submit=True` collects per-device signatures, attaches them to the inception
    event, submits the signed CESR stream to the witness pool, persists the
    returned receipts alongside the event, and marks the publisher-aid.json
    summary `status=live`. In production this is the step that brings the AID
    into existence.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "kel-events").mkdir(parents=True, exist_ok=True)

    if witness_oobis:
        if dry_run:
            witnesses = [
                WitnessInfo(aid=_oobi_to_aid_stub(oobi), oobi=oobi)
                for oobi in witness_oobis
            ]
        else:
            witnesses = [
                WitnessInfo(aid=_oobi_to_aid_stub(oobi), oobi=oobi)
                for oobi in witness_oobis
            ]
    else:
        witnesses = default_witness_pool()

    if len(witnesses) < toad:
        raise ValueError(
            f"witness pool has {len(witnesses)} witnesses; need at least {toad} for toad={toad}"
        )

    if len(yubikey_slots) < signers:
        yubikey_slots = yubikey_slots + ["9c"] * (signers - len(yubikey_slots))

    if software_key_dir is not None:
        if software_passphrases is None or len(software_passphrases) < signers:
            raise ValueError(
                f"software_key_dir requires {signers} passphrases; "
                f"got {len(software_passphrases) if software_passphrases else 0}"
            )
        devices: list[YubiKeyDevice] = open_software_devices(
            software_key_dir, software_passphrases[:signers]
        )
    elif dry_run:
        devices = [
            FakeYubiKeyDevice(serial=f"fake-{i}", slot=slot)
            for i, slot in enumerate(yubikey_slots[:signers])
        ]
    else:
        devices = [
            open_real_device(serial=f"signer-{i}", slot=slot)
            for i, slot in enumerate(yubikey_slots[:signers])
        ]

    result = build_inception_event(
        signers=devices,
        signer_quorum=quorum,
        witnesses=witnesses,
        toad=toad,
    )

    # Persist the unsigned event first so the operator can review it.
    icp_path = output_dir / "kel-events" / "icp-sn-0.cesr"
    icp_path.write_bytes(result.serialized_event)

    receipts: list[Receipt] = []
    if submit:
        # Collect per-device signatures over the serialized inception event.
        sigs: list[bytes] = []
        for device in devices[:quorum]:
            sigs.append(device.sign(result.serialized_event))
        signed_event = _attach_signatures(result.serialized_event, sigs)
        icp_path.write_bytes(signed_event)

        # Submit to the witness pool and gather receipts.
        wc = WitnessClient(
            witness_urls=[w.base_url for w in witnesses],
            threshold=toad,
        )
        receipts = wc.submit_event(signed_event)

        # Persist receipts next to the event.
        # The raw CESR bytes preserve the witness signatures end-to-end (each
        # receipt event in the stream carries its witness AID + signature
        # internally). The companion JSON index lists which witness URLs
        # contributed, for operational visibility.
        receipts_cesr_path = output_dir / "kel-events" / "icp-sn-0.receipts.cesr"
        receipts_cesr_path.write_bytes(b"".join(r.cesr_bytes for r in receipts))

        receipts_index_path = output_dir / "kel-events" / "icp-sn-0.receipts.json"
        receipts_index_path.write_text(
            json.dumps(
                {
                    "count": len(receipts),
                    "witnesses": [r.witness_url for r in receipts],
                    "receipts_cesr_file": "icp-sn-0.receipts.cesr",
                },
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )

    anchor = PublisherAnchor(
        publisher_aid=result.aid_prefix,
        embedded_kel_hash=result.event_said,
        embedded_kel_sn=0,
        witness_oobis=[w.oobi for w in witnesses],
    )

    write_publisher_anchor(anchor, output_dir / "publisher_anchor.json")
    _write_publisher_summary_with_status(
        anchor,
        output_dir / "publisher-aid.json",
        latest_kel_url="https://releases.keri.host/publisher/v1/kel-events/",
        status="live" if receipts else "unsubmitted",
        receipt_count=len(receipts),
    )


def _oobi_to_aid_stub(oobi: str) -> str:
    """Stub: extract the trailing AID from an OOBI URL for dry-run mode."""
    return oobi.rstrip("/").rsplit("/", 1)[-1]


def _attach_signatures(event_raw: bytes, sigs: list[bytes]) -> bytes:
    """Attach indexed CESR signature blocks to a serialized inception event.

    Produces the keripy `messagize`-equivalent stream:

        <event_raw> + Counter(ControllerIdxSigs, count=N).qb64 + N * Siger.qb64

    The Counter prefix is essential — without it, keripy's stream parser
    treats the trailing sigs as bare bytes and never associates them with
    the event, so the witness silently drops the signatures and returns 204
    No Content (no receipt) instead of 200 + receipt.

    Wire format matches `keri.core.eventing.messagize()` (lines 1549-1552
    in keripy's eventing.py).
    """
    from keri.core.eventing import Siger
    from keri.core.counting import Counter, Codens, Vrsn_1_0

    parts = [event_raw]
    parts.append(
        Counter(Codens.ControllerIdxSigs, count=len(sigs), version=Vrsn_1_0).qb64b
    )
    for idx, raw_sig in enumerate(sigs):
        siger = Siger(raw=raw_sig, code="A", index=idx)  # "A" = Ed25519_Sig
        parts.append(siger.qb64b)
    return b"".join(parts)


def _write_publisher_summary_with_status(
    anchor: PublisherAnchor,
    path: Path,
    *,
    latest_kel_url: str,
    status: str,
    receipt_count: int,
) -> None:
    body = {
        "publisher_aid": anchor.publisher_aid,
        "latest_kel_hash": anchor.embedded_kel_hash,
        "latest_kel_sn": anchor.embedded_kel_sn,
        "witnesses": list(anchor.witness_oobis),
        "kel_events_url": latest_kel_url,
        "status": status,
        "receipt_count": receipt_count,
    }
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
