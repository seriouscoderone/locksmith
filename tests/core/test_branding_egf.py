from locksmith.core.branding import Brand, _from_dict


def test_defaults_are_inert():
    b = Brand()
    assert b.egf_document_said == "" and b.onboarding_enabled is False
    assert b.egf_accept_phases == ("production",)


def test_from_dict_reads_egf_and_onboarding():
    b = _from_dict({"id": "usurance",
                    "egf": {"source": "local", "document_said": "E" + "G" * 43,
                            "accept_phases": ["bootstrap", "production"]},
                    "onboarding": {"enabled": True}})
    assert b.egf_document_said == "E" + "G" * 43
    assert b.egf_accept_phases == ("bootstrap", "production")
    assert b.onboarding_enabled is True
