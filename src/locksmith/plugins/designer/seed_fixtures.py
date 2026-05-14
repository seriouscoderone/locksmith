# -*- encoding: utf-8 -*-
"""Dev-mode fixture seeding for the Designer plugin.

When `LOCKSMITH_DESIGNER_SEED_FIXTURES=1` and the store is missing one of
the bundled fixtures, copy that fixture into it as a registered template.
Idempotent. Off by default — production vaults stay empty.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from keri import help

from locksmith.plugins.designer.store import TemplateStore


logger = help.ogler.getLogger(__name__)


_FIXTURE_DIR = (
    Path(__file__).resolve().parents[4]
    / "tests" / "plugins" / "designer" / "fixtures"
)

_BUNDLED: list[str] = [
    "regulator-grants-carrier-license.json",
    "carrier-license-application.json",
]


def maybe_seed(store: TemplateStore) -> None:
    """Seed bundled fixtures into `store` if env var is set.

    Only registered (SAID-bearing) fixtures are seeded. Drafts and the
    broken-references fixture are intentionally skipped — they're test
    artifacts, not demo content.
    """
    if os.environ.get("LOCKSMITH_DESIGNER_SEED_FIXTURES") != "1":
        return
    existing_saids = {ref.said for ref in store.list_templates()
                      if ref.kind == "registered"}
    for filename in _BUNDLED:
        src = _FIXTURE_DIR / filename
        if not src.exists():
            logger.warning("Fixture not found, skipping: %s", src)
            continue
        try:
            doc = json.loads(src.read_text())
        except json.JSONDecodeError as e:
            logger.warning("Fixture %s is not valid JSON: %s", src, e)
            continue
        said = doc.get("d")
        if not said:
            logger.warning("Fixture %s missing 'd' (SAID), skipping", src)
            continue
        if said in existing_saids:
            continue
        metadata = {
            "imported_from": str(src),
            "schema_validated": True,
            "ecosystem_tags": _ecosystem_tags_for(filename),
        }
        store.save_registered(
            said=said, doc=doc, metadata=metadata, overwrite=False,
        )
        logger.info("Seeded designer fixture %s as registered SAID %s",
                    filename, said)


def _ecosystem_tags_for(filename: str) -> list[str]:
    if "regulator" in filename:
        return ["insurance", "compliance"]
    if "carrier-license-application" in filename:
        return ["insurance"]
    return []
