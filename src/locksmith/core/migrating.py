# -*- encoding: utf-8 -*-
"""
locksmith.core.migrating module

Migrate a vault's KERI DB schema to the running keripy version, backing up first.

TRANSITIONAL / UX (KERI v2 v1-hold, Stage 3b): Locksmith auto-updates, and old
released builds bundled ``keri==1.3.4``. A v2-based build (keripy ``2.0.0-dev6``)
opening a user's 1.3.4-schema vault hits keripy's schema guard —
``DatabaseError("Database migrations must be run. DB version 1.3.4; current
2.0.0-dev6")`` raised from ``Baser.reload()`` during ``Habery`` construction — a
hard brick with no data loss but no way in either.

``ensure_migrated`` runs BEFORE the ``Habery`` opens: it detects a stale schema,
backs the vault up, then runs keripy's own migrations (``BE KERI NATIVE`` — no
hand-rolled DB transforms). On failure it restores the backup and re-raises so the
caller can surface a clear error rather than bricking.

Note on the open idiom: ``Baser.reopen()`` creates every sub-DB and only THEN calls
``reload()``, which raises on a stale schema. So the DB is fully usable for
``.current`` / ``.migrate()`` after swallowing that one error — this is exactly the
idiom keripy's own ``kli migrate run`` uses.
"""
from __future__ import annotations

import tarfile
from pathlib import Path

from keri import help
from keri.db.basing import Baser
from keri.help import helping
from keri.kering import DatabaseError

logger = help.ogler.getLogger(__name__)

# Vault store subdirs under the keri head. "db" carries the schema version that
# triggers migration; the rest are captured in the backup so a restore is complete.
# The custom LocksmithBaser ("rt") and KFBaser ("kf") stores are schema-agnostic
# Komer/JSON and are not touched by keripy's migrations, but are backed up anyway.
_STORE_SUBDIRS = ("db", "ks", "cf", "reg", "rt", "kf")

_DB_MARKER = "/db/"


def _open_tolerant(name: str, base: str) -> Baser:
    """Open a Baser tolerating a stale-schema DB.

    ``reopen()`` builds all sub-DBs then ``reload()`` raises ``DatabaseError`` on a
    stale version; the DB is still fully open and usable for ``.current`` /
    ``.migrate()`` afterwards (keripy's own ``kli migrate run`` relies on this).
    """
    db = Baser(name=name, base=base, temp=False, reopen=False)
    try:
        db.reopen()
    except DatabaseError:
        pass
    return db


def _keri_head_and_vault_dirs(db_path: str, name: str) -> tuple[Path, list[Path]]:
    """Derive the keri head (…/keri) and the on-disk vault dirs from an opened
    Baser's ``.path`` (``{head}/db[/{base}]/{name}``)."""
    i = db_path.rfind(_DB_MARKER)
    head = Path(db_path[:i])                       # {…}/keri
    remainder = db_path[i + len(_DB_MARKER):]      # {base}/{name} or {name}
    base = remainder[: -len(name)].strip("/")      # {base} or ""
    dirs: list[Path] = []
    for sub in _STORE_SUBDIRS:
        d = (head / sub / base / name) if base else (head / sub / name)
        if d.exists():
            dirs.append(d)
    return head, dirs


def backup_vault(head: Path, vault_dirs: list[Path], *,
                 backup_root: Path | None = None, stamp: str | None = None) -> Path:
    """Tar the vault dirs (arcnames relative to the keri head) to a timestamped
    backup and return its path."""
    stamp = stamp or helping.nowIso8601().replace(":", "").replace(".", "")
    root = Path(backup_root) if backup_root else (Path.home() / ".locksmith" / "backups")
    root.mkdir(parents=True, exist_ok=True)
    tarpath = root / f"vault-v1-backup-{stamp}.tar.gz"
    with tarfile.open(tarpath, "w:gz") as tar:
        for d in vault_dirs:
            tar.add(d, arcname=str(d.relative_to(head)))
    return tarpath


def _restore(backup: Path, head: Path) -> None:
    """Extract a backup tar back over the vault dirs (arcnames are relative to head)."""
    with tarfile.open(backup, "r:gz") as tar:
        tar.extractall(head)


def ensure_migrated(name: str, base: str = "", *,
                    backup_root: Path | None = None, stamp: str | None = None) -> Path | None:
    """Migrate ``name``'s vault DB schema to the running keripy version if stale.

    Must be called BEFORE constructing the ``Habery`` (whose ``reopen`` would raise
    on a stale schema). Returns the backup path if it migrated, else ``None`` (already
    current). On migration failure the backup is restored and the error re-raised so
    the caller surfaces it — never a silent brick.
    """
    db = _open_tolerant(name, base)
    try:
        if db.current:
            return None
        head, vault_dirs = _keri_head_and_vault_dirs(db.path, name)
        stale_version = db.version
    finally:
        db.close()

    logger.info("vault.migrate.begin name=%s from_version=%s dirs=%d",
                name, stale_version, len(vault_dirs))
    backup = backup_vault(head, vault_dirs, backup_root=backup_root, stamp=stamp)
    logger.info("vault.migrate.backup name=%s path=%s", name, backup)

    db = _open_tolerant(name, base)
    closed = False
    try:
        db.migrate()
        if not db.current:
            raise DatabaseError(
                f"migration did not bring vault {name!r} current "
                f"(version {db.version}; expected current)")
        to_version = db.version
    except Exception as exc:  # noqa: BLE001 — restore then re-raise; never brick
        db.close()
        closed = True
        logger.error("vault.migrate.failed name=%s err=%s; restoring backup %s",
                     name, exc, backup)
        _restore(backup, head)
        raise
    finally:
        if not closed:
            db.close()

    logger.info("vault.migrate.done name=%s to_version=%s", name, to_version)
    return backup
