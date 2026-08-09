# -*- encoding: utf-8 -*-

"""
KERI
locksmith.core.basing package

"""

from dataclasses import dataclass

from keri.db import dbing, koming

from locksmith.peer.records import PeerHealth, PeerModeSettings, PeerRecord


@dataclass
class LandingPrefs:
    """Where this vault opens, and how often we have explained it.

    Per VAULT, not per app. A vault holds the credentials, so the role set is a
    property of the vault; and `QSettings` is brand-scoped, so putting it there
    would leak one person's landing choice onto another person's vault on a
    shared machine.

    `pinned_page_key` is a PAGE KEY, never a role name -- the framework does not
    know what a role is. It is applied only when that key is currently
    registered, so a pin naming a revoked surface degrades on its own. It is kept
    rather than cleared on revocation: revoke -> re-grant is a real arc, and
    silently forgetting the choice would make the re-grant a mystery.
    """

    pinned_page_key: str = ""
    notice_count: int = 0


@dataclass
class OTPSecret:
    vault: str
    secret: str

class OTPSecrets(dbing.LMDBer):

    TailDirPath = "keri/locksmith"
    AltTailDirPath = ".keri/locksmith"
    TempPrefix = "locksmith"

    def __init__(self, name="locksmithOtpSecrets", headDirPath=None, reopen=True, **kwa):
        self.otpSecrets = None

        super(OTPSecrets, self).__init__(name=name, headDirPath=headDirPath, reopen=reopen, **kwa)

    def reopen(self, **kwa):  # type: ignore[override]
        """
        Reopen database and initialize sub-dbs
        """
        super(OTPSecrets, self).reopen(**kwa)

        self.otpSecrets = koming.Komer(db=self, subkey='otpSecrets.', klas=OTPSecret)

        return self.env

@dataclass
class IdentifierMetaInfo:
    """
    Class to track identifier metadata
    """
    prefix: str
    auth_pending: bool

@dataclass
class MailboxListener:
    """
        Mailbox listener state
    """
    cid: str
    eid: str
    name: str

@dataclass
class BrowserPluginSettings:
    """
    Track browser plugin connection settings.

    Stores the Locksmith Identifier (HAD prefix) and Plugin Identifier
    for browser plugin integration.
    """
    locksmith_identifier: str
    locksmith_alias: str
    plugin_identifier: str | None = None

class LocksmithBaser(dbing.LMDBer):
    TailDirPath = "keri/rt"
    AltTailDirPath = ".keri/rt"
    TempPrefix = "rt"

    def __init__(self, name="locksmith", headDirPath=None, reopen=True, **kwa):
        """
        Initialize the LocksmithBaser database.

        Args:
            name: Database name (typically the vault name)
            headDirPath: Base directory path for the database
            reopen: Whether to reopen the database on init
            **kwa: Additional keyword arguments passed to LMDBer
        """

        # identifier metadata
        self.idm = None

        # mailbox listening storage
        self.mbx = None

        # Browser plugin settings
        self.pluginSettings = None

        # Peer-mode allowlist + listener settings
        self.peerAllowlist = None
        self.landing = None
        self.peerSettings = None
        self.peerHealth = None

        super(LocksmithBaser, self).__init__(name=name, headDirPath=headDirPath, reopen=reopen, **kwa)

    def reopen(self, **kwa):  # type: ignore[override]
        """
        Reopen database and initialize sub-dbs
        """
        super(LocksmithBaser, self).reopen(**kwa)

        # Identifier metadata storage
        self.idm = koming.Komer(db=self, subkey='.idm', klas=IdentifierMetaInfo)

        # Mailbox listening storage
        self.mbx = koming.Komer(db=self, subkey='mbx.', klas=MailboxListener)

        # Browser plugin settings storage
        self.pluginSettings = koming.Komer(
            db=self,
            subkey='pluginSettings.',
            klas=BrowserPluginSettings
        )

        # Peer-mode storage
        self.peerAllowlist = koming.Komer(
            db=self, subkey='peer.', klas=PeerRecord
        )
        self.landing = koming.Komer(
            db=self, subkey='landing.', klas=LandingPrefs
        )
        self.peerSettings = koming.Komer(
            db=self, subkey='peerSettings.', klas=PeerModeSettings
        )
        self.peerHealth = koming.Komer(
            db=self, subkey='peerHealth.', klas=PeerHealth
        )

        return self.env
