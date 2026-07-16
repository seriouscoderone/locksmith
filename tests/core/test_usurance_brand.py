import json, tomllib, pathlib

def test_usurance_brand_toml_has_hoa_bootstrap():
    toml = tomllib.loads(pathlib.Path("brands/usurance/brand.toml").read_text())
    bs = toml["bootstrap"]
    assert bs["peel_core_pages"] is True
    assert bs["default_aid_alias"]
    assert bs["default_witnesses"] == []   # witnessless POC
