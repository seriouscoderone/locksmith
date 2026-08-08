import json, pathlib, tomllib
from keri.core import coring

BUNDLE = pathlib.Path("brands/usurance/egf")


def _resaid(doc: dict, label: str) -> str:
    probe = dict(doc); probe[label] = ""
    _, sad = coring.Saider.saidify(sad=probe, label=label)
    return sad[label]


def test_every_file_resaids_to_its_filename():
    for p in BUNDLE.glob("E*.json"):
        doc = json.loads(p.read_text())
        label = "$id" if "$id" in doc else "d"
        assert doc[label] == p.stem and _resaid(doc, label) == p.stem, p.name


def _egf() -> dict:
    return next(json.loads(p.read_text()) for p in BUNDLE.glob("E*.json")
                if json.loads(p.read_text()).get("spec_version") == "egf-doc/0.1")


def test_egf_references_resolve_in_bundle_and_brand_pin_matches():
    egf = _egf()
    # accepted_schema_saids joined this set on 2026-08-08. Without it the guard
    # walked credentials[].schema_said | micro_apps[].said, and neither field names a
    # schema that no role credential is issued against -- so the three CREDENTIAL
    # schemas (product mandate, rate program attestation, product bundle) were only
    # ever in this directory because the plugin commits that needed them put them
    # here by hand, and ugard's canonical bundle shipped three of six for eleven
    # days. An accepted schema absent from the bundle means a validator trusting
    # this EGF cannot check the credential it is handed.
    refs = ({c["schema_said"] for c in egf["credentials"]}
            | {m["said"] for m in egf["micro_apps"]}
            | set(egf["accepted_schema_saids"]))
    on_disk = {p.stem for p in BUNDLE.glob("E*.json")}
    assert refs <= on_disk, refs - on_disk
    toml = tomllib.loads(pathlib.Path("brands/usurance/brand.toml").read_text())
    assert toml["egf"]["document_said"] == egf["d"]


def test_direct_endpoints_have_bundled_oobi_artifacts():
    egf = _egf()
    checked = 0
    for a in egf["authorities"]:
        for ep in a.get("endpoints", []):
            if ep.get("mode") == "direct":
                aid = ep.get("oobi_ref") or a["aid"]
                artifact = BUNDLE / "oobis" / f"{aid}.cesr"
                assert artifact.is_file() and artifact.stat().st_size > 0, aid
                checked += 1
    assert checked, "expected at least one direct-mode endpoint in the bundle"
