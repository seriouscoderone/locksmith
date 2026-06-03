"""Build-time constants must be present and stringly-typed."""
import re

import locksmith.build_info as bi


def test_version_is_semver():
    assert isinstance(bi.LOCKSMITH_VERSION, str)
    # Allow 0.0.0 as the dev-tree default
    assert re.match(r"^\d+\.\d+\.\d+", bi.LOCKSMITH_VERSION), bi.LOCKSMITH_VERSION


def test_channel_is_stable_for_now():
    # Phase 2: single channel. Future phases may extend this.
    assert bi.LOCKSMITH_RELEASE_CHANNEL == "stable"
