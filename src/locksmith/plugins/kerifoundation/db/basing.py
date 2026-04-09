# -*- encoding: utf-8 -*-
"""
locksmith.plugins.kerifoundation.db.basing module

LMDB storage for KERI Foundation plugin state — witness records,
witness batch groupings, and (future) watcher records.
"""
from dataclasses import dataclass, field

from keri.db import dbing, koming


@dataclass
class WitnessRecord:
    """Persisted state for a single registered KF witness."""
    eid: str = ""              # witness AID (prefix)
    url: str = ""              # base URL of witness server
    oobi: str = ""             # full OOBI URL
    totp_seed: str = ""        # decrypted base32 TOTP seed
    hab_pre: str = ""          # controller AID that registered
    registered_at: str = ""    # ISO8601 timestamp
    batch_mode: bool = False   # True if registered with a shared secret


@dataclass
class WitnessBatches:
    """Groups of witness EIDs that share a single TOTP secret."""
    batches: list = field(default_factory=list)  # list[list[str]]


@dataclass
class ProvisionedWitnessRecord:
    """Persisted state for a witness provisioned on a configured server."""

    boot_url: str = ""
    witness_url: str = ""
    eid: str = ""
    oobi: str = ""
    hab_pre: str = ""
    provisioned_at: str = ""


@dataclass
class WatcherRecord:
    """Stub for future watcher support."""
    eid: str = ""
    url: str = ""
    oobi: str = ""


class KFBaser(dbing.LMDBer):
    """LMDB database for KERI Foundation plugin."""

    TailDirPath = "keri/kf"
    AltTailDirPath = ".keri/kf"
    TempPrefix = "kf"

    def __init__(self, name="kerifoundation", headDirPath=None, reopen=True, **kwa):
        self.witnesses = None
        self.witBatches = None
        self.provisionedWitnesses = None
        self.watchers = None

        super(KFBaser, self).__init__(name=name, headDirPath=headDirPath, reopen=reopen, **kwa)

    def reopen(self, **kwa):
        super(KFBaser, self).reopen(**kwa)

        self.witnesses = koming.Komer(db=self, subkey='wit.', schema=WitnessRecord)
        self.witBatches = koming.Komer(db=self, subkey='witb.', schema=WitnessBatches)
        self.provisionedWitnesses = koming.Komer(
            db=self, subkey='pwit.', schema=ProvisionedWitnessRecord
        )
        self.watchers = koming.Komer(db=self, subkey='wat.', schema=WatcherRecord)

        return self.env
