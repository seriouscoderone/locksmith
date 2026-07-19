# -*- encoding: utf-8 -*-
"""
locksmith.core.apping module

This module contains main Locksmith Application class
"""
from pathlib import Path

from keri import help
from keri.app.keeping import Keeper
from keri.app.storing import Mailboxer
from keri.db.dbing import LMDBer

from locksmith.core import branding
from locksmith.core.configing import LocksmithConfig
from locksmith.core.instancing import InstanceCoordinator
from locksmith.core.vaulting import Vault
from locksmith.db.basing import LocksmithBaser
from locksmith.plugins.manager import PluginManager
from locksmith.plugins.updates import PluginUpdateChecker
from locksmith.update.appcast import parse_appcast, select_latest_for_platform
from locksmith.update.cli import _detect_platform, _load_anchor_and_appcast
from locksmith.update.errors import NetworkError
from locksmith.update.log import record_verification_result
from locksmith.update.verify import VerificationResult, verify_artifact

logger = help.ogler.getLogger(__name__)


# KERI on-disk store directory names, derived from the owning classes so they
# track upstream renames. Each vault gets a <store>/<base>/<name> dir per store.
_DB_DIR = Path(LMDBer.TailDirPath).name              # "db"   (KEL/history)
_KS_DIR = Path(Keeper.TailDirPath).name              # "ks"   (keystore)
_MBX_DIR = Path(Mailboxer.TailDirPath).name          # "mbx"  (mailbox)
_RT_DIR = Path(LocksmithBaser.TailDirPath).name      # "rt"   (Locksmith runtime db)


# Generous: the artifact (a DMG / installer) is tens of MB. The gate fetches
# it once to verify; Sparkle fetches it again to install.
_VERIFY_DOWNLOAD_TIMEOUT_SEC = 120


def _anchor_and_appcast_or_dark(platform: str):
    """Return the loaded ``(appcast_raw, aid, sn, said, toad, platform)`` tuple,
    or ``None`` when OFF (no enforceable publisher anchor injected yet).

    OFF means: the anchor file is missing (``FileNotFoundError``), OR it is
    present but half-filled — no pinned KEL ``sn``/``said`` to enforce against.
    A ``NetworkError`` from the appcast fetch propagates so the gate fails closed.
    """
    try:
        loaded = _load_anchor_and_appcast(platform)
    except FileNotFoundError:
        return None
    _appcast_raw, _aid, kel_sn, kel_said, _toad, _plat = loaded
    if kel_sn is None or kel_said is None:
        return None
    return loaded


def _run_verify_artifact(
    artifact_path: Path, loaded: tuple, platform: str
) -> VerificationResult:
    """Run ``verify_artifact`` with the anchor-mapped params from ``loaded``.

    Returns the ``VerificationResult`` (so the gate can hand the proof to the
    verification log). Raises the same ``UpdateError`` subclasses
    ``verify_artifact`` does on a real failure (the bridge turns those into a
    verify-fail).
    """
    appcast_raw, publisher_aid, kel_sn, kel_said, toad, _plat = loaded
    return verify_artifact(
        artifact_path=artifact_path,
        appcast_raw=appcast_raw,
        platform=platform,
        embedded_publisher_aid=publisher_aid,
        embedded_kel_sn=kel_sn,
        embedded_kel_said=kel_said,
        toad=toad,
        embedded_brand=branding.brand().id,
    )


def _download_to_temp(url: str) -> Path:
    """Stream-download ``url`` to a fresh temp file; return its path.

    Raises ``NetworkError`` on any transport failure (and removes the partial
    temp file). The caller owns deleting the returned file.
    """
    import os
    import shutil
    import tempfile
    import urllib.error
    import urllib.request

    from locksmith.update.verify import ssl_context

    fd, name = tempfile.mkstemp(suffix=".locksmith-update")
    path = Path(name)
    try:
        with urllib.request.urlopen(
            url, timeout=_VERIFY_DOWNLOAD_TIMEOUT_SEC, context=ssl_context()
        ) as resp, os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(resp, out)
    except BaseException as exc:
        try:
            path.unlink()
        except OSError:
            pass
        if isinstance(exc, (urllib.error.URLError, OSError, TimeoutError)):
            raise NetworkError(
                f"artifact download failed: {url}: {exc}",
                log_fields={"url": url, "reason": str(exc)},
            ) from exc
        raise
    return path


def _make_update_verifier_macos(on_verified=None):
    """Return the URL-based ``(enclosure_url, info) -> bool`` gate for Sparkle.

    Sparkle's only veto fires BEFORE download and never exposes the staged
    artifact (see ``sparkle_bridge``), so this closure fetches the artifact from
    the enclosure URL itself and runs the SAME ``verify_artifact`` pipeline on
    the bytes it fetched — giving byte-level KERI binding. DARK (no anchor)
    short-circuits to True WITHOUT downloading; a download failure while trust
    is active fails CLOSED.

    ``on_verified`` (optional) is called with the ``VerificationResult`` on an
    enforced PASS so the app can persist the proof for the Release Verification
    dialog.
    """

    def _verify(enclosure_url: str, info: dict) -> bool:
        platform = _detect_platform()
        loaded = _anchor_and_appcast_or_dark(platform)
        if loaded is None:
            logger.info(
                "[update] verify gate DARK: no publisher anchor injected "
                "(verification not yet active); allowing update"
            )
            return True
        try:
            staged = _download_to_temp(enclosure_url)
        except Exception as exc:  # noqa: BLE001 - transport failure -> fail closed
            logger.warning(
                "[update] verify download failed url=%s err=%s; blocking update",
                enclosure_url, exc,
            )
            return False
        try:
            result = _run_verify_artifact(staged, loaded, platform)
            if on_verified is not None and result.ok:
                on_verified(result)
            return bool(result.ok)
        finally:
            try:
                staged.unlink()
            except OSError:
                pass

    return _verify


def _make_update_verifier_windows(on_verified=None):
    """Return the no-arg ``() -> (ok, version)`` gate for WinSparkle.

    WinSparkle 0.8.3 hands its callbacks NOTHING (no staged path, URL, or
    version), so this closure derives the MSI URL from the appcast itself,
    self-downloads it, and runs ``verify_artifact`` against the KEL — the
    Windows analogue of ``_make_update_verifier_macos``. It MUST NOT raise (it
    runs in WinSparkle's ``can_shutdown`` C callback): any failure returns
    ``(False, version)`` so the gate cleanly blocks. DARK → ``(True, "")``.
    ``on_verified`` is called with the ``VerificationResult`` on an enforced
    PASS so the app can persist the proof for the Release Verification dialog.
    """

    def _verify() -> tuple[bool, str]:
        platform = "windows"
        loaded = _anchor_and_appcast_or_dark(platform)
        if loaded is None:
            logger.info(
                "[update] verify gate DARK: no publisher anchor injected "
                "(verification not yet active); allowing update"
            )
            return (True, "")
        try:
            rel = select_latest_for_platform(parse_appcast(loaded[0]), platform)
        except Exception as exc:  # noqa: BLE001 - bad appcast -> block
            logger.warning("[update] winsparkle appcast parse failed err=%s", exc)
            return (False, "unknown")
        version = rel.version
        try:
            staged = _download_to_temp(rel.artifact_url)
        except Exception as exc:  # noqa: BLE001 - transport failure -> block
            logger.warning(
                "[update] verify download failed url=%s err=%s; blocking update",
                rel.artifact_url, exc,
            )
            return (False, version)
        try:
            result = _run_verify_artifact(staged, loaded, platform)
            if on_verified is not None and result.ok:
                on_verified(result)
            return (bool(result.ok), version)
        except Exception as exc:  # noqa: BLE001 - verify failure -> block (never raise into C)
            logger.warning(
                "[update] winsparkle verify failed version=%s err=%s; blocking",
                version, exc,
            )
            return (False, version)
        finally:
            try:
                staged.unlink()
            except OSError:
                pass

    return _verify


def _vault_head_dirs():
    """KERI roots (…/keri, …/.keri) that currently exist, in keripy order.

    Mirrors keri LMDBer head/tail pairing: the system head uses the ``keri``
    parent, the home head uses ``.keri``. Single source of truth for both
    ``environments()`` and ``adopt_legacy_vaults`` so the two never drift.
    Evaluated per call (not at import) so tests can point it at a tmp dir.
    """
    roots = (
        Path(LMDBer.HeadDirPath) / Path(LocksmithBaser.TailDirPath).parent,
        Path(LMDBer.AltHeadDirPath) / Path(LocksmithBaser.AltTailDirPath).parent,
    )
    return [root for root in roots if root.is_dir()]


def _store_dir(root, store_name, base=""):
    """Path to a KERI store dir under one root: ``root/store_name/base``."""
    base_path = Path(base) if base else Path()
    return root / store_name / base_path


def _legacy_vault_names_in_root(root, base=""):
    """Names under one KERI root matching db ∩ ks ∩ mbx − rt (the vaults
    created + opened at least once by a wallet-like app, not yet adopted)."""
    db_home = _store_dir(root, _DB_DIR, base)
    if not db_home.is_dir():
        return set()
    names = set()
    for entry in db_home.iterdir():
        name = entry.name
        if not entry.is_dir():
            continue
        if not (_store_dir(root, _KS_DIR, base) / name).is_dir():
            continue
        if not (_store_dir(root, _MBX_DIR, base) / name).is_dir():
            continue
        if (_store_dir(root, _RT_DIR, base) / name).is_dir():
            continue  # already adopted
        names.add(name)
    return names


def find_legacy_vaults(base="", heads=None):
    """Sorted names of un-adopted legacy vaults across KERI roots.

    Pure query — no writes, no Qt, no ``self``. Host-agnostic so a future
    Universal CLI can reuse the same predicate. ``heads`` overrides the
    head-dir seam for testing.
    """
    roots = heads if heads is not None else _vault_head_dirs()
    found = set()
    for root in roots:
        found |= _legacy_vault_names_in_root(root, base)
    return sorted(found)


def adopt_legacy_vaults(base="", heads=None):
    """Backfill the missing rt/<base>/<name> dir for each legacy vault so it
    reappears in the drawer. Idempotent; adopts within each vault's own root;
    per-name failures are logged and skipped. Returns the adopted names.

    Host-agnostic (no Qt, no ``self``). The LMDB files inside rt/ are created
    later by the normal vault-open path — this only creates the directory,
    exactly like the manual `mkdir ~/.keri/rt/<name>` workaround.
    """
    roots = heads if heads is not None else _vault_head_dirs()
    adopted = []
    for root in roots:
        for name in sorted(_legacy_vault_names_in_root(root, base)):
            rt_dir = _store_dir(root, _RT_DIR, base) / name
            try:
                rt_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.warning("adopt_legacy_vaults: failed to adopt %r: %s",
                               name, exc)
                continue
            adopted.append(name)
            logger.info("adopt_legacy_vaults: adopted legacy vault %r -> %s",
                        name, rt_dir)
    if adopted:
        logger.info("adopt_legacy_vaults: adopted %d legacy vault(s): %s",
                    len(adopted), adopted)
    return adopted


class LocksmithApplication:
    """
    Main application class for Locksmith.

    Manages application state including vaults, haberies, and KERI operations.
    """

    def __init__(self, config: LocksmithConfig | None = None):
        """
        Initialize the Locksmith application.

        Args:
            config: LocksmithConfig instance (will create one if not provided)
        """
        # Configuration
        if config is None:
            config = LocksmithConfig.get_instance()
        self.config = config

        # Adopt vaults created before the rt/ repoint (dormant since) so they
        # reappear in the drawer. Runs before the onboarding gate, drawer, and
        # HOA bootstrap all read environments(). Never allowed to block launch.
        try:
            adopt_legacy_vaults(base=getattr(self.config, "base", "") or "")
        except Exception:  # noqa: BLE001 - launch must survive any fs anomaly
            logger.exception("adopt_legacy_vaults failed; continuing launch")

        # Cross-instance coordination (single-instance-per-vault). The
        # window sets `coordinator.raise_window` once it exists so an
        # incoming "raise" request can bring this window to the front.
        self.coordinator = InstanceCoordinator(
            base=getattr(self.config, "base", None)
        )

        # Application state
        self.name = None  # Current vault name
        self.hby = None  # Habery instance
        self.hab = None  # Current Hab (habitat/identifier)

        # Vault management
        self.vault: Vault | None = None  # Current Vault instance
        self.qtask = None  # QtTask running the vault
        self.rgy = None  # Regery instance

        # Set by the window (ui/window.py): called when a vault background doer crashes,
        # so the vault is torn down honestly instead of left live-but-dead. None until set.
        self.on_vault_crash = None

        # API client
        self._essr = None

        # Database
        self.db = None

        # Plugin manager
        self.plugin_manager = PluginManager(
            self, keri_base=Path(getattr(self.config, "base", None) or (Path.home() / ".keri")),
        )

        self.plugin_update_checker = PluginUpdateChecker(manager=self.plugin_manager)
        logger.info(
            "plugin_update_checker.constructed interval_hours=%d",
            self.plugin_update_checker.interval_seconds // 3600,
        )

        # App-update controller — Phase 5. Watches the appcast feed at
        # releases.keri.host, runs KERI verification on candidate
        # releases, hands off to Sparkle/WinSparkle for install. Lazy:
        # the controller is constructed but not started until the main
        # window calls `start_app_updates()` after first paint.
        self.update_controller = None  # type: ignore[assignment]
        self._init_update_controller()

    def _init_update_controller(self) -> None:
        """Construct the in-app updater controller + bridge adapter.

        Idempotent + safe to call without Qt running — uses PySide6
        QObject but won't trigger any UI.
        """
        try:
            from locksmith.update.controller import UpdateController
        except Exception as exc:  # noqa: BLE001 — defensive against import errors in tests
            logger.warning("update_controller.init_skipped reason=%s", exc)
            return

        # Native updater first, so the controller's on_check can drive it.
        self._native_updater = None
        self._native_updater_dll = None
        self._native_updater_callbacks = None
        self._native_updater_delegate = None
        # Strong ref to the ObjC delegate: SPUStandardUpdaterController holds
        # updaterDelegate __weak, so without this it deallocates and the KERI
        # verify veto never fires.
        self._native_updater_objc_delegate = None
        self._init_native_updater()

        self.update_controller = UpdateController(
            on_check=self.check_for_updates_with_ui,
        )

        logger.info(
            "update_controller.constructed native=%s",
            "yes" if (self._native_updater_dll is not None or self._native_updater is not None) else "no",
        )

    def _init_native_updater(self) -> None:
        """Wire Sparkle/WinSparkle so check_for_updates_with_ui() can
        pop the native update prompt. The verifier closure runs the real
        ``verify_artifact`` gate against the build-injected publisher trust
        anchor; until a real anchor exists it stays DARK (returns True,
        non-enforcing) — see ``_make_update_verifier_macos`` /
        ``_make_update_verifier_windows``."""
        import sys as _sys
        try:
            if _sys.platform == "win32":
                from locksmith.update.winsparkle_init import init_winsparkle
                # WinSparkle exposes NOTHING to its callbacks, so it uses the
                # no-arg self-download verifier (fetches appcast + MSI itself).
                dll, gate, cbs = init_winsparkle(
                    verifier=_make_update_verifier_windows(
                        on_verified=record_verification_result
                    ),
                    log_recorder=lambda **kw: logger.info("[update] log %s", kw),
                    on_failure=lambda v: (
                        self.update_controller.report_verification_failed(v)
                        if getattr(self, "update_controller", None) is not None
                        else logger.warning("[update] verify_failed (no controller) %s", v)
                    ),
                    on_shutdown_request=self._request_app_quit,
                )
                self._native_updater = gate
                self._native_updater_dll = dll
                self._native_updater_callbacks = cbs
            elif _sys.platform == "darwin":
                from locksmith.update.sparkle_init import init_sparkle
                # Sparkle never exposes the staged artifact + vetoes pre-download,
                # so it uses the URL-based verifier (self-download + verify).
                controller, py_delegate, objc_delegate = init_sparkle(
                    verifier=_make_update_verifier_macos(
                        on_verified=record_verification_result
                    ),
                    log_recorder=lambda **kw: logger.info("[update] log %s", kw),
                    on_failure=lambda v: (
                        self.update_controller.report_verification_failed(v)
                        if getattr(self, "update_controller", None) is not None
                        else logger.warning("[update] verify_failed (no controller) %s", v)
                    ),
                )
                self._native_updater = controller
                self._native_updater_delegate = py_delegate
                self._native_updater_objc_delegate = objc_delegate
        except Exception as exc:  # noqa: BLE001 — never let updater init crash the app
            logger.warning("native_updater.init_failed err=%s", exc)

    def _request_app_quit(self) -> None:
        """Gracefully quit the app for WinSparkle's installer (Windows).

        WinSparkle fires its shutdown-request OFF the main thread after launching
        the MSI installer; the app must exit so the installer can replace the
        running exe (otherwise it retries + flickers dialogs). Post the quit to
        the Qt main thread — calling quit() cross-thread directly is unsafe.
        """
        logger.info("[update] native_updater.quit_requested")
        try:
            from PySide6.QtCore import QCoreApplication, QMetaObject, Qt
            app = QCoreApplication.instance()
            if app is not None:
                QMetaObject.invokeMethod(
                    app, "quit", Qt.ConnectionType.QueuedConnection
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("[update] native_updater.quit_failed err=%s", exc)

    def check_for_updates_with_ui(self) -> None:
        """Trigger the native Sparkle/WinSparkle update prompt — fetches
        the appcast, shows 'vX.Y.Z is available' if newer, downloads,
        runs the KERI verifier gate, hands off to the OS installer.
        No-op when the native updater couldn't initialize (dev runs)."""
        dll = self._native_updater_dll
        if dll is not None:
            try:
                dll.win_sparkle_check_update_with_ui()
                logger.info("native_updater.check_update_with_ui_called")
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("native_updater.check_failed err=%s", exc)
        updater = self._native_updater
        if updater is not None and hasattr(updater, "checkForUpdates_"):
            try:
                updater.checkForUpdates_(None)
                logger.info("native_updater.checkForUpdates_called")
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("native_updater.check_failed err=%s", exc)
        logger.info("native_updater.unavailable (dev mode or init failed)")

    @property
    def protectedUrl(self) -> str:
        """Protected ESSR endpoint URL from config."""
        return self.config.protected_url

    @property
    def root(self) -> str:
        """API AID for ESSR encryption from config.
        
        Note: Despite the name 'root', this returns the API AID (delegated AID)
        which is the encryption target for ESSR. The loadbalancer can only sign
        as its delegated AID, not the parent root AID.
        """
        return self.config.api_aid

    @property
    def unprotectedUrl(self) -> str:
        """Unprotected API endpoint URL from config."""
        return self.config.unprotected_url

    def open_vault(self, name: str, vault, qtask):
        """
        Open a vault and store references.

        Args:
            name (str): Name of the vault
            vault: Vault instance
            qtask: QtTask instance running the vault
        """
        # Close existing vault if any
        self.close_vault()

        # Store new vault
        self.name = name
        self.vault = vault
        self.qtask = qtask
        self.hby = vault.hby
        self.rgy = vault.rgy

        # Give the vault a back-reference to the plugin manager
        vault.plugin_manager = self.plugin_manager

        # Notify plugins that vault is open
        self.plugin_manager.on_vault_opened(vault)

        # Resolve default OOBIs if they haven't been resolved yet
        self._resolve_default_oobis_if_needed()

    def close_vault(self):
        """Close the currently open vault."""
        if self.qtask is not None:
            logger.info(f"Closing vault: {self.name}")
            closing_name = self.name

            # Notify plugins before teardown
            if self.vault is not None:
                self.plugin_manager.on_vault_closed(self.vault)

            # Request shutdown
            self.qtask.shutdown()

            # Cleanup
            self.qtask.cleanup()

            # Close LMDB environments so vault can be reopened in this process
            if self.vault is not None and self.vault.db is not None:
                self.vault.db.close()
            if hasattr(self.vault, 'rep') and self.vault.rep is not None:
                if hasattr(self.vault.rep, 'mbx') and self.vault.rep.mbx is not None:
                    self.vault.rep.mbx.close()
            if hasattr(self.vault, 'notifier') and self.vault.notifier is not None:
                if hasattr(self.vault.notifier, 'noter') and self.vault.notifier.noter is not None:
                    self.vault.notifier.noter.close()
            if self.rgy is not None and hasattr(self.rgy, 'reger') and self.rgy.reger is not None:
                self.rgy.reger.close()
            if self.hby is not None:
                self.hby.close()

            # Clear references
            self.qtask = None
            self.vault = None
            self.hby = None
            self.rgy = None
            self.hab = None
            self.name = None

            if closing_name is not None:
                self.coordinator.release(closing_name)

            logger.info("Vault closed")

    def delete_vault(self, vault_name: str) -> bool:
        """
        Delete a vault and all its database files from disk.

        Uses KERI's built-in close(clear=True) method on each database instance
        to properly delete files. This is the correct KERI pattern since each 
        class knows its own path.

        Args:
            vault_name: Name of the vault to delete

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        # Verify this is the currently open vault
        if self.name != vault_name:
            logger.error(f"Cannot delete vault '{vault_name}' - it is not the currently open vault")
            return False

        if self.vault is None or self.hby is None:
            logger.error(f"Cannot delete vault '{vault_name}' - vault is not properly open")
            return False

        logger.info(f"Deleting vault '{vault_name}' using close(clear=True)")

        try:
            self.plugin_manager.prepare_vault_deletion(self.vault)
        except Exception:
            logger.exception(f"Aborting vault deletion for '{vault_name}' during plugin cleanup")
            return False

        # First, shutdown the QtTask to stop all doers
        if self.qtask is not None:
            self.qtask.shutdown()
            self.qtask.cleanup()
            self.qtask = None

        if self.vault is not None:
            self.plugin_manager.on_vault_closed(self.vault, clear=True)

        # Collect all database instances to close with clear=True
        # Order matters: close dependencies first
        databases_to_clear = []

        # LocksmithBaser (our custom db)
        if self.vault.db is not None:
            databases_to_clear.append(('LocksmithBaser', self.vault.db))

        # Mailboxer (from Respondant)
        if hasattr(self.vault, 'rep') and self.vault.rep is not None:
            if hasattr(self.vault.rep, 'mbx') and self.vault.rep.mbx is not None:
                databases_to_clear.append(('Mailboxer', self.vault.rep.mbx))

        # Noter (from Notifier)
        if hasattr(self.vault, 'notifier') and self.vault.notifier is not None:
            if hasattr(self.vault.notifier, 'noter') and self.vault.notifier.noter is not None:
                databases_to_clear.append(('Noter', self.vault.notifier.noter))

        # Reger (from Regery)
        if self.rgy is not None and hasattr(self.rgy, 'reger') and self.rgy.reger is not None:
            databases_to_clear.append(('Reger', self.rgy.reger))

        # Current keripy clears the Habery LMDB stores, but does not remove
        # the persistent Configer file. Delete it here as part of the vault.
        if self.hby is not None and getattr(self.hby, 'cf', None) is not None:
            databases_to_clear.append(('HaberyConfiger', self.hby.cf))

        # Habery databases (Baser, Keeper)
        if self.hby is not None:
            databases_to_clear.append(('Habery', self.hby))

        # Close each with clear=True to delete files
        deleted_count = 0
        error_count = 0

        for name, db in databases_to_clear:
            try:
                logger.info(f"Closing {name} with clear=True")
                db.close(clear=True)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to close/clear {name}: {e}")
                error_count += 1

        # Clear references
        self.vault = None
        self.hby = None
        self.rgy = None
        self.hab = None
        self.name = None

        # Release the cross-instance claim. Safe even if we never held it —
        # release() is a no-op for vaults this coordinator doesn't own.
        self.coordinator.release(vault_name)

        if error_count == 0:
            logger.info(f"Vault '{vault_name}' deleted successfully")
            return True
        else:
            logger.error(f"Vault '{vault_name}' deletion had {error_count} errors")
            return False

    @property
    def is_vault_open(self) -> bool:
        """
        Check if a vault is currently open.

        Returns:
            bool: True if a vault is open, False otherwise
        """
        return self.vault is not None and self.qtask is not None

    def _resolve_default_oobis_if_needed(self):
        """
        Check if default OOBIs need to be resolved and resolve them if necessary.

        This is called after opening a vault to ensure default OOBIs (root and API)
        are resolved on first open after vault creation.

        TODO(KERI Foundation): Populate root_aid, api_aid, root_oobi, api_oobi in configing.py.
        This will no-op until those values are set.
        """
        if self.hby is None:
            return

        from locksmith.core import remoting

        # Check if root OOBI needs resolution
        if hasattr(self.config, 'root_oobi') and self.config.root_oobi:
            if not self.hby.db.roobi.get(keys=(self.config.root_oobi,)):
                logger.info(f"Resolving default root OOBI: {self.config.root_oobi}")
                remoting.resolve_oobi_sync(
                    app=self,
                    pre=self.config.root_aid,
                    oobi=self.config.root_oobi,
                    alias="Root",
                )

        # Check if API OOBI needs resolution
        if hasattr(self.config, 'api_oobi') and self.config.api_oobi:
            if not self.hby.db.roobi.get(keys=(self.config.api_oobi,)):
                logger.info(f"Resolving default API OOBI: {self.config.api_oobi}")
                remoting.resolve_oobi_sync(
                    app=self,
                    pre=self.config.api_aid,
                    oobi=self.config.api_oobi,
                    alias="API",
                )

    def environments(self):
        """
        List Locksmith vault environments.

        Uses Locksmith's runtime database as the source of truth so generic KERI
        environments such as witnesses do not appear in the vault drawer.

        Legacy vaults created before the `rt/` repoint are backfilled at launch
        by `adopt_legacy_vaults`, so this pure read still surfaces them.

        Returns:
            list: List of vault names
        """
        base = getattr(self.config, "base", "") or ""
        for root in _vault_head_dirs():
            rt_home = _store_dir(root, _RT_DIR, base)
            if rt_home.is_dir():
                return sorted(
                    path.name for path in rt_home.iterdir() if path.is_dir()
                )
        return []
        
