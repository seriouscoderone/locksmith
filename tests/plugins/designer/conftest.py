# -*- encoding: utf-8 -*-
"""Shared fixtures for Designer plugin tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.store import TemplateStore


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_dir():
    return FIXTURES


@pytest.fixture
def seeded_store(tmp_path):
    store = TemplateStore(root=tmp_path)
    for f in FIXTURES.glob("*.json"):
        doc = json.loads(f.read_text())
        store.save_registered(said=doc["d"], doc=doc, metadata={})
    return store
