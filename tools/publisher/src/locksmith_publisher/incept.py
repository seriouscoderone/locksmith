"""Publisher AID inception ceremony.

Builds a KERI `icp` event with:
- One signing key by default (single-sig); multi-device multisig is available
  as a future Phase 4 upgrade via key rotation — see docs/governance/publisher-ceremony.md.
- Pre-rotated next-key digests computed per KERI spec (Blake2b-256 of the
  qb64-encoded Verfer of each next public key), committed as real Ed25519
  keypairs persisted under ``<software_key_dir>/next/``.
- Witness list = the KERI.host 5-witness federation (hardcoded; no remote discovery)
- toad = 3 (3-of-5 majority) for production

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
- ``coring.MtrDex.Blake3_256`` is the correct self-addressing code for the AID
  prefix.
- Pre-rotation digests use Blake2b-256 of the qb64-encoded Verfer (KERI spec
  convention verified in keripy ``keri.core.eventing``):
    ``coring.Diger(ser=verfer.qb64b)``
  NOT ``Diger(raw=random_bytes)`` — that would produce an unrotatable AID.
- ``coring.MtrDex.Ed25519`` (transferable) is correct for a rotating AID;
  ``Ed25519N`` (non-transferable) would forbid future rotations.

Software-key directory layout
------------------------------
When ``--software-keys <dir>`` is used, the ceremony creates:

    <dir>/current/key-1.enc.pem   — current signing key
    <dir>/next/key-1.enc.pem      — pre-rotated next key (persisted for rotation)

For multi-signer ceremonies (Phase 4), ``key-2.enc.pem`` etc. appear in each
subdirectory. Re-running the ceremony with existing files is idempotent: existing
key files are loaded, not regenerated.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from keri.core import coring
from keri.core.eventing import incept

from .anchor import PublisherAnchor, write_publisher_anchor, write_publisher_summary
from .software_key import SoftwareKeyDevice, open_software_devices
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
    next_pubkeys: List[bytes] = field(default_factory=list)
    serialized_event: bytes = b""


def _generate_persistent_next_keys(
    next_dir: Path,
    passphrases: list[bytes],
    signers: int,
) -> tuple[list[bytes], list[Path]]:
    """Generate ``signers`` real Ed25519 keypairs, persist their private halves
    encrypted to ``next_dir/key-<i>.enc.pem``, and return the raw 32-byte
    public keys (in signer order) plus the list of file paths.

    If a key file already exists, the existing key is loaded (idempotent).
    The passphrase reuse across current/next keys is intentional: both are in
    the same operator's custody; separate passphrases add friction without
    adding meaningful security when the files are co-located.

    The pre-rotation digest committed in the inception event is computed
    *separately* in ``build_inception_event`` (via ``Diger(ser=verfer.qb64b)``)
    so that the digest construction stays close to the keripy idiom and is
    independently testable.
    """
    next_devices = open_software_devices(next_dir, passphrases[:signers])
    next_pubkeys = [d.generate_signing_key() for d in next_devices]
    next_paths = [d.key_path for d in next_devices]
    return next_pubkeys, next_paths


def build_inception_event(
    *,
    signers: list[YubiKeyDevice],
    signer_quorum: int,
    witnesses: list[WitnessInfo],
    toad: int,
    next_pubkeys: list[bytes],
) -> InceptionResult:
    """Build (but do not submit) the inception event.

    ``next_pubkeys`` must contain one raw 32-byte Ed25519 public key per signer.
    The pre-rotation digest committed in ``n:`` is computed as
    ``Blake2b_256(next_verfer.qb64b)`` per KERI spec, ensuring the rotation
    event can later be signed with the keys whose digest was committed.
    """
    if len(signers) < signer_quorum:
        raise ValueError(f"need at least {signer_quorum} signer devices; got {len(signers)}")
    if len(witnesses) < toad:
        raise ValueError(f"need at least {toad} witnesses; got {len(witnesses)}")
    if len(next_pubkeys) != len(signers):
        raise ValueError(
            f"next_pubkeys length {len(next_pubkeys)} must equal signers length {len(signers)}"
        )

    signer_pubkeys: list[bytes] = []
    for device in signers:
        pk = device.generate_signing_key()
        signer_pubkeys.append(pk)

    # Build using keripy primitives.
    # Ed25519 (transferable) allows future rotation; Ed25519N would forbid it.
    verfers = [coring.Verfer(raw=pk, code=coring.MtrDex.Ed25519) for pk in signer_pubkeys]

    # Pre-rotation: compute Blake2b-256 digest of the qb64-encoded Verfer for
    # each next public key.  This is the KERI spec convention (verified in
    # keripy keri.core.eventing): the digest is computed over the qb64
    # serialisation of the Verfer, NOT over the raw bytes.
    next_verfers = [coring.Verfer(raw=pk, code=coring.MtrDex.Ed25519) for pk in next_pubkeys]
    digers = [coring.Diger(ser=v.qb64b) for v in next_verfers]

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
        next_digests=[d.raw for d in digers],
        next_pubkeys=next_pubkeys,
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

    Software-key mode creates two subdirectories:
      - ``<software_key_dir>/current/`` — signing keys for this inception
      - ``<software_key_dir>/next/``    — pre-rotated keys committed via digest

    Both subdirectories use the same passphrases (one per signer slot). Reusing
    the passphrase across current/next is acceptable because both files are in
    the same operator custody; the only requirement is that the next-key file is
    stored safely for the future rotation event.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "kel-events").mkdir(parents=True, exist_ok=True)

    if witness_oobis:
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
        # --- Software-key path ---
        # Layout: <software_key_dir>/current/key-<i>.enc.pem (current signers)
        #         <software_key_dir>/next/key-<i>.enc.pem    (pre-rotated next keys)
        if software_passphrases is None or len(software_passphrases) < signers:
            raise ValueError(
                f"software_key_dir requires {signers} passphrases; "
                f"got {len(software_passphrases) if software_passphrases else 0}"
            )
        current_dir = software_key_dir / "current"
        next_dir = software_key_dir / "next"

        devices: list[YubiKeyDevice] = open_software_devices(
            current_dir, software_passphrases[:signers]
        )
        # Trigger key generation/load for current devices before next-key gen.
        for d in devices:
            d.generate_signing_key()

        # Generate and persist real next-key material.
        next_pubkeys, _ = _generate_persistent_next_keys(
            next_dir, software_passphrases, signers
        )

    elif dry_run:
        # --- Dry-run path (FakeYubiKeyDevice) ---
        devices = [
            FakeYubiKeyDevice(serial=f"fake-{i}", slot=slot)
            for i, slot in enumerate(yubikey_slots[:signers])
        ]
        # Generate fake next-key pubkeys (fresh ephemeral keys; not persisted).
        fake_next_devices = [
            FakeYubiKeyDevice(serial=f"fake-next-{i}", slot=slot)
            for i, slot in enumerate(yubikey_slots[:signers])
        ]
        next_pubkeys = [d.generate_signing_key() for d in fake_next_devices]

    else:
        # --- Real YubiKey path (Phase 4: multi-device multisig) ---
        devices = [
            open_real_device(serial=f"signer-{i}", slot=slot)
            for i, slot in enumerate(yubikey_slots[:signers])
        ]
        # Phase 4: generate real next-key material on each YubiKey / HSM.
        # For now raise a clear error so we don't accidentally produce an
        # unrotatable AID in production with hardware keys.
        raise NotImplementedError(
            "Real YubiKey next-key generation is a Phase 4 task. "
            "Use --software-keys for Phase 1 production inception."
        )

    result = build_inception_event(
        signers=devices,
        signer_quorum=quorum,
        witnesses=witnesses,
        toad=toad,
        next_pubkeys=next_pubkeys,
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
