"""Tests for the _artifact_url helper and artifact_prefix config key."""
from locksmith_publisher import cli


def test_artifact_url_custom_prefix():
    """_artifact_url builds the correct URL with a custom brand prefix."""
    url = cli._artifact_url("https://cdn.example.com", "1.2.3", "Acme", "dmg")
    assert url == "https://cdn.example.com/releases/1.2.3/Acme-1.2.3.dmg"


def test_artifact_url_strips_trailing_slash_from_cdn():
    """_artifact_url strips a trailing slash from the CDN base."""
    url = cli._artifact_url("https://cdn.example.com/", "1.2.3", "Acme", "dmg")
    assert url == "https://cdn.example.com/releases/1.2.3/Acme-1.2.3.dmg"


def test_artifact_url_default_prefix_locksmith():
    """The default artifact_prefix is 'Locksmith' when absent from deploy_config."""
    assert cli._DEFAULT_ARTIFACT_PREFIX == "Locksmith"
    url = cli._artifact_url("https://cdn.example.com", "2.0.0", cli._DEFAULT_ARTIFACT_PREFIX, "msi")
    assert url == "https://cdn.example.com/releases/2.0.0/Locksmith-2.0.0.msi"


def test_artifact_url_msi_extension():
    """_artifact_url works for Windows .msi artifacts too."""
    url = cli._artifact_url("https://releases.example.com", "0.9.1", "MyApp", "msi")
    assert url == "https://releases.example.com/releases/0.9.1/MyApp-0.9.1.msi"
