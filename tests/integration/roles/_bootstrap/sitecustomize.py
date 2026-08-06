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

Five patches, all confined to THIS TEST PROCESS's copy of the code (never
touches a tracked file):

1. ``locksmith.core.branding.brand`` (and the `manager.py`-imported copy of
   it) — the documented monkeypatch seam (see ``activation_policy.HoaPeeled``
   's own docstring: "which also keeps `manager.brand` as the single
   monkeypatch point the existing HOA tests use") — augmented so
   ``bundled_plugins`` includes ``"cuo"``/``"actuary"``/``"product_designer"``
   and ``egf_document_said``/``egf_source``/``egf_accept_phases`` carry the
   REAL usurance values (see the Task 5 findings inline in `_patch()` for
   why `branding.brand()` does not already have either of these, and why
   `onboarding_enabled` is deliberately left at `_DEFAULT`'s `False` rather
   than also imported from the real brand.toml). Without the plugin-set fix,
   `NotBrandComposed` vetoes `cuo` as `"not_bundled"` and the plugin never
   loads at all, gate or no gate. Also points `_brand_source_dir` at a small
   scratch directory carrying both an `assets.rcc` (copied from the
   locally-staged, gitignored `src/locksmith/release/usurance/` —
   `register_brand_resources()` needs SOME assets.rcc to boot at all,
   branded or not) and a CURRENT `egf/` (copied from the checked-out SOURCE
   `brands/usurance/egf/`, which carries this task's newly-vendored
   `product_mandate`/`rate_program_attestation` schemas — the locally-staged
   copy predates them).

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

4. (Task 5) ``ActuaryPlugin.required_credential.issuer_aids`` — same trusted
   test-admin substitution as patch 2, for `actuary_role`. Also wraps
   ``ActuaryPlugin.on_vault_opened`` to pin `actuary_role`'s OWN gate schema
   (read from ``ACTUARY_TEST_ROLE_SCHEMA_PATH``), mirroring patch 2's
   `product_mandate`-labelled block exactly, just for the actuary's gate
   credential instead of the CUO's.

5. (Task 5) ``CuoMandatePage._show_declared`` — wrapped to ALSO write the
   just-declared mandate's real delivery artifact (registry TEL, credential
   TEL, and the credential's own raw ACDC + its SealSourceTriples anchoring
   proof — the exact recipe `keri.vdr.credentialing.sendCredential`/
   `sendArtifacts` streams over a postman) to a well-known path under HOME.
   Wallet A (the CUO) is a REAL driven GUI subprocess, not an in-process test
   party like `_build_test_admin`'s, so nothing in the pytest process can
   reach into it to pull these bytes out any other way — this hook runs
   INSIDE A's own process, where `vault.rgy.reger` is real and local, and
   writes what it finds there rather than fabricating it. The roles conftest
   reads the file this writes and pushes it over a real peer TCP connection
   into wallet B, where the (also real, patch-free) `Reactant`/`Verifier`
   pipeline lands and verifies it exactly as it would any other peer
   delivery — see `directing.py`'s `vry=self.verifier` fix, without which an
   ACDC message over this same transport is silently dropped.
"""
from __future__ import annotations

import os

#: Cross-referenced literally (not imported) in
#: tests/integration/roles/conftest.py's `watch_cuo_mandate_via_peer` --
#: sitecustomize.py runs inside a SEPARATE wallet subprocess whose PYTHONPATH
#: does not carry the `tests` package, so the two copies of this name must be
#: kept in sync by hand rather than shared via import.
_MANDATE_EXPORT_FILENAME = "_test_mandate_export.cesr"


def _export_mandate_artifact(vault, said: str) -> None:
    """Write the real delivery artifact for the just-declared mandate credential
    `said` to `<HOME>/{_MANDATE_EXPORT_FILENAME}`. See patch 5's module-docstring
    entry for why this exists and what it mirrors."""
    from pathlib import Path

    from keri.core import Counter, Codens
    from keri.kering import Vrsn_1_0

    reger = vault.rgy.reger
    creder = reger.creds.get(keys=(said,))
    if creder is None:
        return  # nothing to export -- the caller's own log line covers this
    regk = creder.regid

    stream = bytearray()
    if regk is not None:
        for msg in reger.clonePreIter(pre=regk):        # the registry's own vcp (+ vrt)
            stream.extend(msg)
    for msg in reger.clonePreIter(pre=said):             # this credential's iss (+ rev)
        stream.extend(msg)

    # The credential's own raw ACDC + its anchoring proof -- see
    # keri.vdr.credentialing.sendCredential, which this mirrors exactly.
    _, prefixer, seqner, saider = reger.cloneCred(said)
    atc = bytearray(Counter(Codens.SealSourceTriples, count=1, version=Vrsn_1_0).qb64b)
    atc.extend(prefixer.qb64b)
    atc.extend(seqner.qb64b)
    atc.extend(saider.qb64b)
    stream.extend(bytes(creder.raw))
    stream.extend(atc)

    export_path = Path(os.environ["HOME"]) / _MANDATE_EXPORT_FILENAME
    export_path.write_bytes(bytes(stream))


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

    repo_root = Path(__file__).resolve().parents[4]  # sitecustomize -> _bootstrap -> roles -> integration -> tests -> repo root

    real_brand = branding.brand()
    # (Task 5 finding, part 1) `branding.brand()`, called this early (site-
    # init, before `locksmith.main` has done its own brand-config setup),
    # resolves to `_DEFAULT` -- `bundled_plugins == ()`, `egf_document_said ==
    # ""` -- because `load_brand()`'s packaged-`brand.json` path does not
    # exist on this dev checkout, and there is no env-injected one either.
    # `_DEFAULT` is also `onboarding_enabled=False`, and that field is
    # LOAD-BEARING for this suite: `open_test_vault_via_ui`
    # (tests/integration/peer/conftest.py, shared with every OTHER UI test)
    # drives the plain "Initialize New Vault" flow, not usurance's real HOA
    # first-run setup wizard -- so the fix below reads the checked-out SOURCE
    # `brand.toml` only far enough to recover the EGF fields `make_hoa_
    # resolver`/`verify_attestation` need, and otherwise keeps `_DEFAULT`'s
    # shape (onboarding OFF) rather than swapping in the real brand wholesale.
    import tomllib

    brand_toml_path = repo_root / "brands" / "usurance" / "brand.toml"
    egf_source = real_brand.egf_source
    egf_document_said = real_brand.egf_document_said
    egf_accept_phases = real_brand.egf_accept_phases
    if brand_toml_path.is_file():
        toml_doc = tomllib.loads(brand_toml_path.read_text())
        real_egf_fields = branding._from_dict(toml_doc)
        egf_source = real_egf_fields.egf_source
        egf_document_said = real_egf_fields.egf_document_said
        egf_accept_phases = real_egf_fields.egf_accept_phases

    # (Task 5 finding, part 2) Union "cuo" onto `bundled_plugins` -- without
    # it (measured, `real_brand` is the `_DEFAULT` fallback): `NotBrandComposed`
    # vetoes "cuo" as "not_bundled", the plugin never loads at all, gate or
    # no gate.
    needed = {"cuo", "actuary", "product_designer"}
    patched_brand = dataclasses.replace(
        real_brand,
        bundled_plugins=tuple(sorted(set(real_brand.bundled_plugins) | needed)),
        egf_source=egf_source,
        egf_document_said=egf_document_said,
        egf_accept_phases=egf_accept_phases,
    )

    # (Task 5 finding, part 3) `manager.py` does `from locksmith.core.branding
    # import brand`, a SEPARATE name binding from `branding.brand` itself --
    # patching only `manager_module.brand` (the original shape of this patch)
    # fixes what `PluginManager` sees but leaves every OTHER caller (e.g.
    # `ActuaryPage._egf_doc()`'s own `from locksmith.core.branding import
    # brand; brand()`, called fresh on every scan tick) reading the ORIGINAL
    # `@lru_cache(maxsize=1)`-memoized `_DEFAULT` forever -- `egf_document_
    # said=""`, so `make_hoa_resolver` returns None and `verify_attestation`
    # fails `schema_accepted` closed with "0 accepted" for every real schema,
    # silently. Patch the function `branding.brand` itself refers to, not
    # just the copy `manager` imported.
    branding.brand = lambda: patched_brand
    manager_module.brand = lambda: patched_brand
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

    # -- 4. (Task 5) the actuary plugin's trusted issuer + gate-schema seeding,
    # mirroring block 2 exactly for actuary_role instead of cuo_role -----------
    import locksmith.plugins.actuary.plugin as actuary_plugin_module

    actuary_plugin_module.ActuaryPlugin.required_credential = RequiredCredential(
        schema_said=actuary_plugin_module.ACTUARY_ROLE_SCHEMA_SAID,
        issuer_aids=[admin_aid],
        required_state="active",
    )

    actuary_schema_path_str = os.environ.get("ACTUARY_TEST_ROLE_SCHEMA_PATH")
    if actuary_schema_path_str:
        actuary_schema_path = Path(actuary_schema_path_str)
        _orig_actuary_on_vault_opened = actuary_plugin_module.ActuaryPlugin.on_vault_opened

        def _actuary_on_vault_opened_and_seed(self, vault):
            _orig_actuary_on_vault_opened(self, vault)
            from keri.core import scheming
            from keri.kering import Kinds

            sad = json.loads(actuary_schema_path.read_text())
            schemer = scheming.Schemer(sed=sad, kind=Kinds.json)
            vault.hby.db.schema.pin(keys=(schemer.said,), val=schemer)

        actuary_plugin_module.ActuaryPlugin.on_vault_opened = _actuary_on_vault_opened_and_seed

    # -- 5. (Task 5) export the just-declared mandate's real delivery artifact
    # from wallet A's own process -- see the module docstring's entry 5 ------
    import locksmith.plugins.cuo.page as cuo_page_module

    _orig_show_declared = cuo_page_module.CuoMandatePage._show_declared

    def _show_declared_and_export(self, said):
        _orig_show_declared(self, said)
        if said and self._app is not None and getattr(self._app, "vault", None) is not None:
            try:
                _export_mandate_artifact(self._app.vault, said)
            except Exception:  # noqa: BLE001 — must not crash the CUO's own submit
                # flow; the watcher-side conftest helper surfaces a clear,
                # diagnosable assertion if the export file never appears.
                import logging
                logging.getLogger(__name__).exception(
                    "roles_test.mandate_export_failed said=%s", said)

    cuo_page_module.CuoMandatePage._show_declared = _show_declared_and_export


try:
    _patch()
except Exception:  # noqa: BLE001 — must never crash the wallet's startup;
    # a missing patch surfaces plainly anyway as a permanently-unsatisfied
    # gate in the test itself, which is diagnosable — a crashed wallet at
    # startup is not.
    pass
