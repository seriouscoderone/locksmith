from locksmith.core.branding import Brand, _from_dict


def test_brand_defaults_are_non_hoa_safe():
    b = Brand()  # bare default (the reference Locksmith brand)
    assert b.peel_core_pages is False
    assert b.default_vault_name == ""
    assert b.default_witnesses == []
    assert b.default_toad == 0


def test_from_dict_reads_bootstrap_section():
    b = _from_dict({
        "id": "usurance",
        "bootstrap": {
            "peel_core_pages": True,
            "default_vault_name": "Carrier",
            "default_passcode": "",
            "default_aid_alias": "carrier",
            "default_witnesses": [],
            "default_toad": 0,
        },
    })
    assert b.peel_core_pages is True
    assert b.default_vault_name == "Carrier"
    assert b.default_aid_alias == "carrier"
