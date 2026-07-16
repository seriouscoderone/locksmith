# -*- encoding: utf-8 -*-
"""
locksmith.core.bootstrapping module

First-run bootstrap for brand-configured HOA builds: auto-create ONE default
vault + ONE witnessless default AID, so the HOA boots straight into an app
experience with no manual vault/identifier creation.

Brand-gated: only brands carrying a non-empty ``default_vault_name`` (the
``usurance`` HOA brand's ``[bootstrap]`` section, see ``core/branding.py``)
opt in. The reference Locksmith brand's ``default_vault_name`` is ``""`` and
is unaffected both by the internal guard here and by the call-site guard in
``ui/window.py``.

The call sequence mirrors, minus the dialogs, the manual UI paths:
  * ``CreateVaultDialog.create_vault`` (``ui/vaults/create.py``) for the
    claim -> open -> open_vault dance around a persistent, auto-opened
    vault (its ``open_hby`` reopen-after-create branch, ~:230-244).
  * ``CreateIdentifierDialog.create_identifier``
    (``ui/vault/identifiers/create.py``) for identifier creation: a
    'salty' key type identifier needs a fresh 21-char salt
    (``signing.Salter().qb64[2:23]``, ~:137), same as the manual dialog
    generates as its field default.

Note on ``open_hby`` (``core/habbing.py:100``): it already creates the vault
if it doesn't exist on disk (keripy's ``LMDBer.reopen`` creates-if-missing)
AND internally calls ``run_vault_controller`` before returning, so its return
value is already ``(vault, qtask)`` — ready to hand straight to
``app.open_vault``. There is no separate ``run_vault_controller`` call needed
here (an earlier investigation assumed one was; the code does not have it).
"""
from keri import help
from keri.core import signing

from locksmith.core.crypto import stretch_password_to_passcode
from locksmith.core.habbing import create_identifier, format_bran, open_hby

logger = help.ogler.getLogger(__name__)


def bootstrap_default_environment(app, brand_cfg) -> bool:
    """On first run only (no existing vaults), create one default vault and
    one witnessless default AID for a brand-gated HOA build.

    Returns:
        bool: True if it created (and opened) a vault this run. False as a
        no-op when a vault already exists, when the brand doesn't opt in
        (empty ``default_vault_name``), or when opening the freshly-created
        vault failed / lost the cross-instance claim race.

    Must be invoked AFTER plugin discovery + ``on_app_started`` (see the
    deferred ``QTimer.singleShot`` wiring in ``ui/window.py``), since opening
    the vault fires ``plugin_manager.on_vault_opened``, which plugins expect
    to receive only once they've been discovered and started.
    """
    if not brand_cfg.default_vault_name:
        return False  # non-HOA brand — never bootstraps

    if app.environments():
        return False  # not first run — a vault already exists on disk

    name = brand_cfg.default_vault_name
    config = app.config

    bran = ""
    if brand_cfg.default_passcode:
        bran = stretch_password_to_passcode(format_bran(brand_cfg.default_passcode))

    # Single-instance-per-vault claim, same as CreateVaultDialog's auto-open
    # path. On a genuine first run nothing else can own this brand-new vault
    # name, so this is expected to always succeed; guarded anyway for parity
    # with the manual path and to avoid a doomed double-open race.
    if not app.coordinator.claim(name):
        logger.error(
            "bootstrap.claim_denied name=%s; leaving default vault uncreated", name
        )
        return False

    try:
        vault, qtask = open_hby(
            name=name, base=config.base, bran=bran, app=app, salt=config.salt,
        )
    except Exception:  # noqa: BLE001 — never crash first boot; log and bail
        logger.exception("bootstrap.open_failed name=%s", name)
        app.coordinator.release(name)
        return False

    app.open_vault(name, vault, qtask)

    # Witnessless default AID: 'salty' key type needs its own random salt
    # (the manual dialog's field default is generated the same way).
    aid_salt = signing.Salter().qb64[2:23]
    result = create_identifier(
        app,
        alias=brand_cfg.default_aid_alias,
        key_type="salty",
        salt=aid_salt,
        toad=str(brand_cfg.default_toad),
        wits=list(brand_cfg.default_witnesses),
    )
    if isinstance(result, dict) and not result.get("success", True):
        logger.error(
            "bootstrap.identifier_failed alias=%s message=%s",
            brand_cfg.default_aid_alias, result.get("message"),
        )

    return True
