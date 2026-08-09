"""Activate the usurance brand for every test in this package.

These are the BRAND-BUNDLED role plugins ([plugins] bundled in
`brands/usurance/brand.toml`), and since 2026-08-08 one of their pages reads its
brand's EGF while it is being constructed: `CuoMandatePage` builds every control
from the `declare_product_mandate` payload schema and refuses to open at all if
it cannot find it (`schema_source`'s "fails LOUD" rule -- a form that fell back to
"no constraints" would accept anything and let the issuer reject it). So
`CuoPlugin.get_pages()` needs the brand that bundles the plugin to be active,
which is a true precondition rather than a test workaround.

Reuses `tests/plugins/cuo/conftest.py`'s bundle builder -- `src/locksmith/release/`
is gitignored, so a fresh clone has no usurance brand until `brand_apply` runs.
Resets the branding cache on BOTH sides: an activated brand that outlives its test
leaks into every later module in the session.
"""
import pytest

from tests.plugins.cuo.conftest import _release_dir


@pytest.fixture(autouse=True)
def usurance_brand(monkeypatch):
    from locksmith.core import branding

    brand_json = _release_dir() / "brand.json"
    assert brand_json.is_file(), (
        f"brand_apply did not produce {brand_json}; the brand-bundled role "
        f"plugins cannot build their pages without the usurance EGF bundle")

    monkeypatch.setenv(branding.BRAND_CONFIG_ENV_VAR, str(brand_json))
    branding._reset_cache_for_tests()
    branding.brand()                      # populates _brand_source_dir
    yield
    branding._reset_cache_for_tests()
