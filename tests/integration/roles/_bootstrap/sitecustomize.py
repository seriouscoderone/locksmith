# -*- encoding: utf-8 -*-
"""Test-only process bootstrap for the `roles/` UI suite.

Not shipped, not imported by any production code path — this directory is
added to a SPAWNED TEST WALLET's ``PYTHONPATH`` (by
``tests/integration/roles/conftest.py``, never by ``_start_wallet`` itself)
so Python's own site-init machinery imports it before ``locksmith.main``
runs a single line. That timing is the whole point: the patches below must
land before ``PluginManager.discover()`` and the ``cuo`` plugin's own module
body execute, and a wallet is a SEPARATE PROCESS — nothing in the pytest
process can reach into it after the fact.

Gated on ``CUO_TEST_ADMIN_AID`` being set (only the roles conftest sets it),
so this is an inert no-op for every other wallet — including wallet B in the
SAME `two_wallets` pair, and any locksmith process that happens to have this
directory on its path for an unrelated reason.

Three patches, all confined to THIS TEST PROCESS's copy of the code (never
touches a tracked file):

1. ``locksmith.plugins.manager.brand`` — the documented monkeypatch seam
   (see ``activation_policy.HoaPeeled``'s own docstring: "which also keeps
   `manager.brand` as the single monkeypatch point the existing HOA tests
   use") — augmented so ``bundled_plugins`` includes ``"cuo"``. Without
   this, `NotBrandComposed` vetoes the `cuo` candidate as `"not_bundled"`
   and the plugin never loads at all, gate or no gate. Also points
   `_brand_source_dir` at a small scratch directory carrying both an
   `assets.rcc` (copied from the locally-staged, gitignored
   `src/locksmith/release/usurance/` — `register_brand_resources()` needs
   SOME assets.rcc to boot at all, branded or not) and a CURRENT `egf/`
   (copied from the checked-out SOURCE `brands/usurance/egf/`, which
   carries this task's newly-vendored `product_mandate` schema — the
   locally-staged copy predates it).

2. ``CuoPlugin.required_credential.issuer_aids`` — overridden to trust a
   throwaway, deterministically-salted test-admin AID instead of the
   hardcoded production `usurance-admin` AID. This mirrors
   `tests/integration/test_multi_role_e2e.py`'s own explicit, documented
   pattern ("TEST ADMIN vs PRODUCTION ADMIN... override to the TEST admin
   for this in-process world") — the literal production AID belongs to a
   real, passcode-protected operator vault this test suite must never touch.
   Also wraps ``CuoPlugin.on_vault_opened`` to additionally pin the
   `product_mandate` gate schema into the freshly-opened vault's
   `hby.db.schema`, mirroring `_seed_role_schemas` in
   `test_multi_role_e2e.py`. Without this the credential a test admin
   grants lands in a missing-schema escrow, never `reger.saved` —
   `_held_credential_view`'s `chain_verified` would read False forever and
   the gate would never open, even though everything else about the grant
   was genuine.

3. ``QFileDialog.getSaveFileName`` — neutralized to a no-op. Measured root
   cause of a real hang: `AcceptCredentialDialog._admit_credential`
   (received/accept.py) always constructs `AcceptGrantDialog` with the
   default `save=True`, so a successful admit fires
   `_save_admit_to_file`, which calls the NATIVE
   `QFileDialog.getSaveFileName(...)`. Under `QT_QPA_PLATFORM=offscreen`
   that call has nothing to show and nothing that can dismiss it, and
   since it fires SYNCHRONOUSLY from within the SAME `admit_complete`
   signal emission that (via the earlier-connected `PluginManager`
   listener) ALSO drives the credential gate's own reveal, it freezes the
   vault's own Doist mid-tick: the gate reveal itself still completes (it
   runs first), but every doer scheduled afterward — including this
   suite's own `CuoMandatePage.submit()` -> `vault.extend([...])` — never
   gets ticked again. Patched to act as if the user cancelled the save (the
   credential landing this suite cares about happens BEFORE this dialog
   ever opens — only the optional "save the admit notice to a file"
   side-quest is skipped).
"""
from __future__ import annotations

import os


def _patch() -> None:
    admin_aid = os.environ.get("CUO_TEST_ADMIN_AID")
    if not admin_aid:
        return  # not a roles-suite wallet — do nothing

    import dataclasses
    import json
    import shutil
    import tempfile
    from pathlib import Path

    # -- 1. brand-compose "cuo" + a fresh-enough brand source dir ----------
    import locksmith.core.branding as branding
    import locksmith.plugins.manager as manager_module

    real_brand = branding.brand()
    if "cuo" not in real_brand.bundled_plugins:
        patched_brand = dataclasses.replace(
            real_brand, bundled_plugins=(*real_brand.bundled_plugins, "cuo"),
        )
    else:
        patched_brand = real_brand
    manager_module.brand = lambda: patched_brand

    repo_root = Path(__file__).resolve().parents[4]  # sitecustomize -> _bootstrap -> roles -> integration -> tests -> repo root
    staged_rcc = repo_root / "src" / "locksmith" / "release" / "usurance" / "assets.rcc"
    source_egf = repo_root / "brands" / "usurance" / "egf"
    scratch = Path(tempfile.mkdtemp(prefix="cuo_brand_source_"))
    if staged_rcc.is_file():
        shutil.copy(staged_rcc, scratch / "assets.rcc")
    if source_egf.is_dir():
        shutil.copytree(source_egf, scratch / "egf")
    branding._brand_source_dir = scratch

    # -- 2. the cuo plugin's trusted issuer + gate-schema seeding ----------
    import locksmith.plugins.cuo.plugin as cuo_plugin_module
    from locksmith.plugins.credential_gate import RequiredCredential

    cuo_plugin_module.CuoPlugin.required_credential = RequiredCredential(
        schema_said=cuo_plugin_module.CUO_ROLE_SCHEMA_SAID,
        issuer_aids=[admin_aid],
        required_state="active",
    )

    schema_path_str = os.environ.get("CUO_TEST_ROLE_SCHEMA_PATH")
    if schema_path_str:
        schema_path = Path(schema_path_str)
        _orig_on_vault_opened = cuo_plugin_module.CuoPlugin.on_vault_opened

        def _on_vault_opened_and_seed(self, vault):
            _orig_on_vault_opened(self, vault)
            from keri.core import scheming
            from keri.kering import Kinds

            sad = json.loads(schema_path.read_text())
            schemer = scheming.Schemer(sed=sad, kind=Kinds.json)
            vault.hby.db.schema.pin(keys=(schemer.said,), val=schemer)

        cuo_plugin_module.CuoPlugin.on_vault_opened = _on_vault_opened_and_seed

    # -- 3. neutralize the file-based Accept flow's post-success native
    # save dialog -----------------------------------------------------------
    from PySide6.QtWidgets import QFileDialog

    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))


try:
    _patch()
except Exception:  # noqa: BLE001 — must never crash the wallet's startup;
    # a missing patch surfaces plainly anyway as a permanently-unsatisfied
    # gate in the test itself, which is diagnosable — a crashed wallet at
    # startup is not.
    pass
