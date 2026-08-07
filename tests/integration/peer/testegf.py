# -*- encoding: utf-8 -*-
"""Build a TEST EGF bundle whose trust root is a wallet the fixture owns.

A branded HOA trusts exactly one authority: the AID pinned in its EGF. The
shipped usurance bundle pins the real `usurance-admin`
(`EGjm-X1JMz-...`, in overlay.usurance.json and as the `issuer` of every role
credential), so a spawned test admin's grants can never satisfy a role gate.
That is Principle VIII working — authority comes from the ecosystem's
governance, not from whoever happens to be running.

So an end-to-end HOA test cannot reuse the shipped brand. It has to mint its
OWN ecosystem: same derivation, same corpus, a different trust root. This is
the fixture equivalent of `_build_test_admin` — extended from "an admin the
suite owns" to "an ecosystem the suite owns" — and it means the suite never
needs the real operator identity or its passcode.

Consequence the caller must respect: the admin wallet must be RUNNING and hold
an AID before this can be built, so a mixed fleet cannot be spawned in one go.
Admin first, derive, then the HOAs.
"""
from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

#: The shipped bundle we re-derive from — corpus and governance are reused
#: verbatim; only the trust root changes.
UGARD_EGF = Path.home() / "code" / "ugard" / "docs" / "usurance" / "egf"

TOKEN_PREFIX = "locksmith-peer-oobi:v1:"

#: The authority the shipped bundle is rooted at — the real operator identity,
#: which this fixture must never need.
REAL_ADMIN_AID = "EGjm-X1JMz-yKFeumEZ9meSVNvnV8VTXmjJMlyBVMMTO"

BUNDLES = ("cuo-declares-product-mandate", "actuary-attests-rate-program",
           "designer-assembles-product-bundle")


def oobi_cesr_from_token(token: str) -> bytes:
    """The raw CESR behind a `locksmith-peer-oobi:v1:` token.

    The token a wallet shows in Settings is base64 over exactly the bytes an
    `oobis/<aid>.cesr` holds — so the fixture can obtain the admin's OOBI from
    its own UI, with no keystore access and no passcode.
    """
    body = token.strip()
    if body.startswith(TOKEN_PREFIX):
        body = body[len(TOKEN_PREFIX):]
    body += "=" * (-len(body) % 4)
    return base64.urlsafe_b64decode(body.encode()) if "-" in body or "_" in body \
        else base64.b64decode(body.encode())


def build_test_brand(dest: Path, *, admin_aid: str, admin_oobi_token: str,
                     src_brand: Path) -> Path:
    """Write a brand.json + egf/ bundle rooted at `admin_aid`. Returns brand.json.

    Re-derives with ugard's own `derive_usurance_egf` rather than hand-editing
    the published document: the EGF's SAID commits to its contents, so swapping
    an AID by text would produce a bundle whose SAID no longer matches and
    which the HOA would reject.
    """
    import sys
    sys.path.insert(0, str(Path.home() / "code" / "ugard" / "scripts"))

    dest.mkdir(parents=True, exist_ok=True)
    egf_dir = dest / "egf"
    if egf_dir.exists():
        shutil.rmtree(egf_dir)
    shutil.copytree(UGARD_EGF, egf_dir)

    # 0. RE-ROOT THE CORPUS FIRST. The authority AID is not confined to the
    #    overlay: every micro-app template pins it as `commands[].authz.issuer`
    #    and `reactions[].authz.issuer` — the authorization gate itself. Leave
    #    those and the HOA still demands credentials from the real admin, so
    #    the test admin's grants authorize nothing.
    #
    #    Templates are content-addressed, so rewriting one changes its SAID;
    #    they must be re-SAIDed, and the EGF derived from the REWRITTEN copies
    #    so its micro_app refs point at the new SAIDs. Hence a private corpus
    #    rather than an edit in place.
    corpus = _reroot_corpus(dest / "corpus", admin_aid)

    # 1. Re-point the overlay's single irreducible fact.
    overlay_path = egf_dir / "overlay.usurance.json"
    overlay = json.loads(overlay_path.read_text())
    for auth in overlay.get("authorities", []):
        if auth.get("aid"):
            auth["aid"] = admin_aid
            for ep in auth.get("endpoints", []):
                if "oobi_ref" in ep:
                    ep["oobi_ref"] = admin_aid
    overlay_path.write_text(json.dumps(overlay, indent=2))

    # 2. The authority's OOBI, taken from the running wallet's own UI.
    oobis = egf_dir / "oobis"
    oobis.mkdir(exist_ok=True)
    for stale in oobis.glob("E*.cesr"):
        stale.unlink()
    (oobis / f"{admin_aid}.cesr").write_bytes(oobi_cesr_from_token(admin_oobi_token))

    # 3. Re-derive from the re-rooted corpus, and publish those templates.
    said = _rederive(egf_dir, corpus)
    _publish(egf_dir, corpus, said)

    # 4. A brand.json beside it, so egf_local_dir() finds the bundle.
    brand = json.loads(Path(src_brand).read_text())
    brand.setdefault("egf", {})["document_said"] = said
    brand["egf"]["source"] = "local"
    brand_path = dest / "brand.json"
    brand_path.write_text(json.dumps(brand, indent=2))
    return brand_path


def _reroot_corpus(dest: Path, admin_aid: str) -> Path:
    """Copy the three corpus templates, re-point their authz issuer, re-SAID.

    Returns the directory holding the rewritten bundles.
    """
    import json as _json
    import subprocess as _sp
    import sys as _sys

    src = Path.home() / "code" / "ugard" / "docs" / "micro-apps"
    saidify = Path.home() / "code" / "ugard" / "scripts" / "micro_app_saidify.py"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    for bundle in BUNDLES:
        shutil.copytree(src / bundle, dest / bundle)
        tpl = dest / bundle / "micro-app-template.json"
        text = tpl.read_text()
        # A literal swap is right here: the AID appears only as an issuer pin,
        # and the file is re-SAIDed immediately afterwards.
        tpl.write_text(text.replace(REAL_ADMIN_AID, admin_aid))
        r = _sp.run([_sys.executable, str(saidify), "--input", str(tpl),
                     "--in-place"], capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError(
                f"re-SAIDing {bundle} failed: {r.stderr or r.stdout}")
        assert REAL_ADMIN_AID not in tpl.read_text(), (
            f"{bundle} still pins the real admin after re-rooting")
    return dest


def _publish(egf_dir: Path, corpus: Path, said: str) -> None:
    """Replace the published templates with the RE-ROOTED ones.

    The bundle was copied from the shipped EGF, so it still carries the
    templates published against the real admin. Those are what the HOA reads to
    gate a command (`commands[].authz.issuer`), so leaving them means the
    ecosystem still demands the real operator's credentials no matter what the
    EGF document says. Templates are content-addressed, so the stale copies
    also have the wrong filenames — prune by SAID, then publish afresh.
    """
    import json as _json

    doc = _json.loads((egf_dir / f"{said}.json").read_text())
    wanted = {m["said"] for m in doc.get("micro_apps", [])}

    for prior in egf_dir.glob("E*.json"):
        if prior.stem in (said, *wanted):
            continue
        body = _json.loads(prior.read_text())
        if "header" in body and "role" in body:          # a micro-app template
            prior.unlink()

    for bundle in BUNDLES:
        tpl = corpus / bundle / "micro-app-template.json"
        body = _json.loads(tpl.read_text())
        if body["d"] in wanted:
            (egf_dir / f"{body['d']}.json").write_text(tpl.read_text())

    stale = [f.name for f in egf_dir.rglob("*.json")
             if REAL_ADMIN_AID in f.read_text()]
    assert not stale, f"bundle still pins the real admin: {stale}"


def _rederive(egf_dir: Path, corpus: Path) -> str:
    """Re-derive the EGF for `egf_dir`, returning its new SAID.

    Calls ugard's own pure functions (`derive_skeleton` / `build_egf`) rather
    than its `main()`, which hardcodes repo-relative paths. Mirrors main()'s
    steps exactly: same three corpus bundles, same overlay merge, same
    write-then-drop-the-stale-doc.
    """
    import json as _json

    import derive_usurance_egf as d

    templates = [_json.loads((corpus / b / "micro-app-template.json").read_text())
                 for b in BUNDLES]
    overlay = _json.loads((egf_dir / "overlay.usurance.json").read_text())

    doc = d.build_egf(d.derive_skeleton(templates), overlay)
    (egf_dir / f"{doc['d']}.json").write_text(
        _json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Drop any prior EGF doc, or the HOA sees two and resolves the wrong one.
    for prior in egf_dir.glob("E*.json"):
        if prior.stem == doc["d"]:
            continue
        if d._is_egf_doc(_json.loads(prior.read_text())):
            prior.unlink()
    return doc["d"]
