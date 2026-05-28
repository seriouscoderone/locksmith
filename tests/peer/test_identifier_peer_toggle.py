from locksmith.ui.vault.identifiers import identifier_sections


def test_oobi_dropdown_includes_peer_role():
    """The role_map at identifier_sections.py is the source of truth for
    which roles the dropdown surfaces."""
    role_map_source = identifier_sections.__file__
    with open(role_map_source) as f:
        src = f.read()
    assert '"Peer": "peer"' in src or "'Peer': 'peer'" in src, \
        "OOBI role dropdown must include a Peer entry"
