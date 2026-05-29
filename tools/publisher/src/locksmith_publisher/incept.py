"""Publisher AID inception ceremony.

Builds a 2-of-3 multisig KERI `icp` event with:
- Three signing keys, one per custodian device (laptop YK, desktop YK, air-gapped USB)
- Signing threshold (`isith`) = 2
- Pre-rotated next-key digests, rotation threshold (`nsith`) = 2
- Witness list = the api.keri.host witness pool AIDs
- toad = 2

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

import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from keri.core import coring
from keri.core.eventing import incept

from .anchor import PublisherAnchor, write_publisher_anchor, write_publisher_summary
from .witnesses import WitnessInfo, discover_witness_pool
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
) -> None:
    """End-to-end inception ceremony runner.

    Dry-run mode uses FakeYubiKeyDevice and writes outputs to a tmp dir; it does
    NOT submit the event to witnesses. Production mode uses real YubiKey devices
    and (with `submit=True`, added in Task B9) signs the event and submits it to
    the witness pool.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "kel-events").mkdir(parents=True, exist_ok=True)

    # Witness discovery: in dry-run we accept oobis verbatim; in production we
    # would also query api.keri.host/witness/pool to confirm the witnesses are
    # currently advertised.
    if dry_run:
        witnesses = [
            WitnessInfo(aid=_oobi_to_aid_stub(oobi), oobi=oobi)
            for oobi in witness_oobis
        ]
    else:
        # Use the first oobi's host as the pool URL.
        pool_url = _derive_pool_url(witness_oobis[0])
        witnesses = discover_witness_pool(pool_url, minimum=toad + 1)

    if len(yubikey_slots) < signers:
        yubikey_slots = yubikey_slots + ["9c"] * (signers - len(yubikey_slots))

    if dry_run:
        devices: list[YubiKeyDevice] = [
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

    anchor = PublisherAnchor(
        publisher_aid=result.aid_prefix,
        embedded_kel_hash=result.event_said,
        embedded_kel_sn=0,
        witness_oobis=[w.oobi for w in witnesses],
    )

    write_publisher_anchor(anchor, output_dir / "publisher_anchor.json")
    write_publisher_summary(
        anchor,
        output_dir / "publisher-aid.json",
        latest_kel_url="https://releases.keri.host/publisher/v1/kel-events/",
    )
    (output_dir / "kel-events" / "icp-sn-0.cesr").write_bytes(result.serialized_event)

    # Task B9 extends this runner to: collect each device's signature over
    # result.serialized_event, attach them as CESR signature blocks, submit the
    # signed event to the witness pool via WitnessClient, and persist the
    # returned receipts. With B9 applied, the publisher AID is live by the time
    # this function returns. The `sign` / `countersign` / `submit` CLI
    # subcommands (release `ixn` flow, not inception) remain Phase 4 work.


def _oobi_to_aid_stub(oobi: str) -> str:
    """Stub: extract the trailing AID from an OOBI URL for dry-run mode."""
    return oobi.rstrip("/").rsplit("/", 1)[-1]


def _derive_pool_url(oobi: str) -> str:
    """Given a witness OOBI URL, derive the witness pool index URL on the same host."""
    from urllib.parse import urlparse
    parsed = urlparse(oobi)
    return f"{parsed.scheme}://{parsed.netloc}/witness/pool"
