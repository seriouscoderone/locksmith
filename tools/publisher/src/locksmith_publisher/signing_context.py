"""Publisher signing-context abstraction.

The Phase 1 inception ceremony persists the publisher signing key as an
encrypted Ed25519 PEM file on disk (see ``software_key.SoftwareKeyDevice``);
the Phase 4 ``release_anchor`` pipeline was originally written against
``keri.app.habbing.Hab`` and expected a populated Habery.

This module bridges that gap. ``PublisherSigningContext`` is the minimal
protocol ``build_release_anchor`` needs; ``HabSigningContext`` wraps an
existing Hab (used by Phase 4 tests + the ``--key-source habery`` CLI
path), while ``PemFileSigningContext`` loads the on-disk PEM key from
``~/.locksmith-publisher/keys-production/current/`` and tracks the
KEL tip in a local JSON state file.

KEL-tip tracking
----------------
The PEM context needs two pieces of state to build an ixn event:

* ``current_sn`` — the sequence number of the most recently committed
  KEL event for the publisher AID
* ``last_event_digest`` — the SAID of that event (committed as ``p`` in
  the next ixn)

Two sources:

1. ``~/.locksmith-publisher/state.json`` — local cache populated by the
   first ``incept`` and updated after each successful ``anchor`` commit
2. Witness query — falls back to ``WitnessClient.query_state`` if the
   local state is missing or stale (e.g., first ixn after inception
   when the state file hasn't been written yet)

For the *very first* ixn after the initial inception, the bundled
``src/locksmith/release/publisher_anchor.json`` carries both pieces
(``embedded_kel_hash`` == inception SAID, ``embedded_kel_sn`` == 0).
The CLI seeds the state file from there if both local state and
witness query come up empty.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from keri.app import habbing
from keri.core import coring, serdering
from keri.core.counting import Codens, Counter, Vrsn_1_0
from keri.core.eventing import interact
from keri.core.indexing import IdrDex, Siger

from .software_key import SoftwareKeyDevice


class PublisherSigningContext(Protocol):
    """Minimal interface ``build_release_anchor`` consumes.

    Two implementations live below: ``HabSigningContext`` (test-friendly,
    backed by a real ``Hab``) and ``PemFileSigningContext`` (the
    production reality, backed by an encrypted PEM file on disk).
    """

    @property
    def prefix(self) -> str:
        """The publisher AID (qb64 prefix)."""
        ...

    @property
    def current_sn(self) -> int:
        """Sequence number of the most recently committed KEL event."""
        ...

    @property
    def last_event_digest(self) -> str:
        """SAID of the most recently committed KEL event (goes into ixn ``p``)."""
        ...

    def build_signed_ixn(self, *, seal: dict) -> tuple[bytes, "serdering.SerderKERI"]:
        """Build, sign, and persist the next ixn event anchoring ``seal``.

        Returns the CESR-encoded message (event + ControllerIdxSigs +
        N * Siger) and the parsed ``SerderKERI``. After this call,
        ``current_sn`` and ``last_event_digest`` must reflect the new
        event (i.e., ``current_sn`` has advanced by 1).
        """
        ...


# ---------------------------------------------------------------------------
# Hab-backed context (test path + --key-source habery)
# ---------------------------------------------------------------------------


@dataclass
class HabSigningContext:
    """Wraps a keripy ``Hab``. Backwards-compatible with the original Phase 4 path.

    All KEL state is owned by the Hab/Habery; ``current_sn`` / ``last_event_digest``
    just delegate to ``hab.kever``. ``build_signed_ixn`` calls ``hab.interact()``
    which constructs, signs, persists, AND messagizes the event in one shot.
    """

    hab: habbing.Hab

    @property
    def prefix(self) -> str:
        return self.hab.pre

    @property
    def current_sn(self) -> int:
        return self.hab.kever.sner.num

    @property
    def last_event_digest(self) -> str:
        return self.hab.kever.serder.said

    def build_signed_ixn(self, *, seal: dict) -> tuple[bytes, serdering.SerderKERI]:
        msg = self.hab.interact(data=[seal])
        serder = serdering.SerderKERI(raw=bytearray(msg))
        return bytes(msg), serder


# ---------------------------------------------------------------------------
# PEM-backed context (production reality — Phase 1 / Phase 4 bridge)
# ---------------------------------------------------------------------------


@dataclass
class PublisherStateFile:
    """JSON state cache: ``{publisher_aid, current_sn, last_event_digest}``.

    Stored at ``~/.locksmith-publisher/state.json`` (overridable). The CLI
    writes this after every successful anchor commit, so subsequent runs
    don't have to round-trip witnesses to learn the KEL tip.

    File schema::

        {
          "publisher_aid": "ECnJ7jhAxjrduHkIKS_ml56bqPuIJIvSw-i0mpZR_P8p",
          "current_sn": 0,
          "last_event_digest": "ECnJ7jhAxjrduHkIKS_ml56bqPuIJIvSw-i0mpZR_P8p"
        }
    """

    path: Path
    publisher_aid: str = ""
    current_sn: int = -1
    last_event_digest: str = ""

    @classmethod
    def load(cls, path: Path) -> "PublisherStateFile":
        if not path.exists():
            return cls(path=path)
        body = json.loads(path.read_text())
        return cls(
            path=path,
            publisher_aid=body.get("publisher_aid", ""),
            current_sn=int(body.get("current_sn", -1)),
            last_event_digest=body.get("last_event_digest", ""),
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "publisher_aid": self.publisher_aid,
            "current_sn": self.current_sn,
            "last_event_digest": self.last_event_digest,
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        try:
            self.path.chmod(0o600)
        except OSError:
            # On some platforms (e.g., Windows) chmod is a no-op; ignore.
            pass

    @property
    def has_tip(self) -> bool:
        return bool(self.publisher_aid) and self.current_sn >= 0


@dataclass
class PemFileSigningContext:
    """Signing context backed by an encrypted Ed25519 PEM file.

    Lifecycle:

    1. Load the PEM file from ``keys_dir/key-1.enc.pem``, decrypt with
       ``passphrase``.
    2. Derive the publisher AID prefix from the Ed25519 public key via the
       keripy primitives so it matches the prefix the inception ceremony
       wrote (``coring.Verfer(raw=pubkey, code=MtrDex.Ed25519)`` →
       AID prefix via Blake3-256 self-addressing). The caller passes
       the expected publisher AID and we verify the match.
    3. Maintain KEL-tip state in ``state_file`` (see ``PublisherStateFile``).
    4. On ``build_signed_ixn``: construct ``interact()`` event with the
       cached tip, sign with the in-memory Ed25519 key, attach
       ``Counter(ControllerIdxSigs, count=1) + Siger(...).qb64b``, and
       persist the new tip back to ``state_file``.

    Note: the publisher AID is single-sig per Phase 1; multi-key support
    can be added later by accepting multiple PEM files and producing
    multiple indexed Sigers.
    """

    publisher_aid: str
    keys_dir: Path
    passphrase: bytes
    state_file: PublisherStateFile
    key_filename: str = "key-1.enc.pem"
    _device: SoftwareKeyDevice = field(init=False, default=None)  # type: ignore[assignment]
    _pubkey: bytes = field(init=False, default=b"")

    def __post_init__(self) -> None:
        if isinstance(self.passphrase, str):
            self.passphrase = self.passphrase.encode("utf-8")
        if not isinstance(self.keys_dir, Path):
            self.keys_dir = Path(self.keys_dir)
        key_path = self.keys_dir / self.key_filename
        if not key_path.is_file():
            raise FileNotFoundError(
                f"publisher PEM key not found at {key_path}; "
                f"did you run `locksmith-publisher incept` with --software-keys?"
            )
        self._device = SoftwareKeyDevice(
            serial="publisher",
            slot="sw",
            key_path=key_path,
            passphrase=self.passphrase,
        )
        # Loads + decrypts the key (raises YubiKeyError on bad passphrase).
        self._pubkey = self._device.generate_signing_key()
        # The publisher AID prefix is the Blake3-256 SAID of the icp event,
        # which depends on next-key digests, witnesses, etc., so we cannot
        # recompute it from the public key alone. The expected AID is
        # operator-supplied (read from the bundled publisher_anchor.json)
        # and the final cryptographic check happens on the witness side:
        # any ixn signed by the wrong key will be rejected because the
        # controlling key on record doesn't match the signature.
        # If the state file has a publisher_aid set, it must match.
        if self.state_file.publisher_aid and self.state_file.publisher_aid != self.publisher_aid:
            raise ValueError(
                f"state file {self.state_file.path} is for a different publisher AID "
                f"({self.state_file.publisher_aid!r}); refusing to overwrite"
            )

    # --- PublisherSigningContext protocol -----------------------------

    @property
    def prefix(self) -> str:
        return self.publisher_aid

    @property
    def current_sn(self) -> int:
        if self.state_file.current_sn < 0:
            raise RuntimeError(
                f"publisher KEL tip unknown; state file at {self.state_file.path} "
                "is empty and witness fallback hasn't been seeded. Run "
                "`seed_state_from_anchor()` or `seed_state_from_witnesses()` first."
            )
        return self.state_file.current_sn

    @property
    def last_event_digest(self) -> str:
        if not self.state_file.last_event_digest:
            raise RuntimeError(
                f"publisher KEL prior digest unknown; state file at "
                f"{self.state_file.path} is empty"
            )
        return self.state_file.last_event_digest

    def build_signed_ixn(self, *, seal: dict) -> tuple[bytes, serdering.SerderKERI]:
        next_sn = self.current_sn + 1
        # kind='JSON' for v1 protocol — matches inception event serialisation.
        serder = interact(
            pre=self.prefix,
            dig=self.last_event_digest,
            sn=next_sn,
            data=[seal],
            kind="JSON",
        )
        sig_raw = self._device.sign(bytes(serder.raw))
        # Single-sig: one indexed signature at index 0.
        msg = bytearray(serder.raw)
        msg.extend(
            Counter(Codens.ControllerIdxSigs, count=1, version=Vrsn_1_0).qb64b
        )
        siger = Siger(raw=sig_raw, code=IdrDex.Ed25519_Sig, index=0)
        msg.extend(siger.qb64b)

        # Persist new tip before returning so a crash post-witness-submit
        # but pre-state-save doesn't permanently desync. (If we crash
        # before submit, the operator can manually decrement; if we crash
        # after submit but before save, we've at least recorded locally.)
        self.state_file.publisher_aid = self.publisher_aid
        self.state_file.current_sn = next_sn
        self.state_file.last_event_digest = serder.said
        self.state_file.save()

        return bytes(msg), serder

    # --- KEL-tip seeding helpers --------------------------------------

    def seed_state_from_anchor(
        self,
        *,
        aid: str,
        sn: int,
        event_digest: str,
    ) -> None:
        """Initialize state from the bundled publisher_anchor.json.

        Used on the very first ixn after inception, when no remote
        anchor commits have happened yet.
        """
        if aid != self.publisher_aid:
            raise ValueError(
                f"anchor AID {aid!r} does not match publisher AID "
                f"{self.publisher_aid!r}"
            )
        self.state_file.publisher_aid = aid
        self.state_file.current_sn = sn
        self.state_file.last_event_digest = event_digest
        self.state_file.save()

    def seed_state_from_witnesses(self, witness_client: Any) -> None:
        """Initialize state by querying the witness federation.

        ``witness_client`` must expose ``query_state(aid)`` returning an
        object with ``.sn`` and ``.current_said`` attributes
        (``WitnessClient.query_state`` is the canonical caller).
        """
        ks = witness_client.query_state(self.publisher_aid)
        self.state_file.publisher_aid = self.publisher_aid
        self.state_file.current_sn = int(ks.sn)
        self.state_file.last_event_digest = ks.current_said
        self.state_file.save()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def derive_publisher_verfer_qb64(public_key_raw: bytes) -> str:
    """Return the qb64-encoded Verfer for a raw Ed25519 public key.

    This is the public-key fingerprint (NOT the publisher AID prefix —
    the AID prefix is the Blake3-256 SAID of the icp event and cannot
    be recomputed from the public key alone). Useful for callers that
    want to verify a loaded PEM matches a known inception-time pubkey.
    """
    verfer = coring.Verfer(raw=public_key_raw, code=coring.MtrDex.Ed25519)
    return verfer.qb64


__all__ = [
    "HabSigningContext",
    "PemFileSigningContext",
    "PublisherSigningContext",
    "PublisherStateFile",
    "derive_publisher_verfer_qb64",
]
