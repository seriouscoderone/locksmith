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


def test_egf_references_resolve_in_bundle_and_brand_pin_matches():
    egf = next(json.loads(p.read_text()) for p in BUNDLE.glob("E*.json")
               if json.loads(p.read_text()).get("spec_version") == "egf-doc/0.1")
    refs = {c["schema_said"] for c in egf["credentials"]} | {m["said"] for m in egf["micro_apps"]}
    on_disk = {p.stem for p in BUNDLE.glob("E*.json")}
    assert refs <= on_disk, refs - on_disk
    toml = tomllib.loads(pathlib.Path("brands/usurance/brand.toml").read_text())
    assert toml["egf"]["document_said"] == egf["d"]
