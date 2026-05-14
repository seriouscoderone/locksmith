from pathlib import Path

import pytest

from locksmith.plugins.designer import seed_fixtures
from locksmith.plugins.designer.store import TemplateStore


@pytest.fixture
def tmp_store(tmp_path) -> TemplateStore:
    return TemplateStore(root=tmp_path)


def test_no_seed_when_env_var_absent(tmp_store, monkeypatch):
    monkeypatch.delenv("LOCKSMITH_DESIGNER_SEED_FIXTURES", raising=False)
    seed_fixtures.maybe_seed(tmp_store)
    assert tmp_store.list_templates() == []


def test_seed_creates_two_registered_templates(tmp_store, monkeypatch):
    monkeypatch.setenv("LOCKSMITH_DESIGNER_SEED_FIXTURES", "1")
    seed_fixtures.maybe_seed(tmp_store)
    saids = {ref.said for ref in tmp_store.list_templates()
             if ref.kind == "registered"}
    assert any(s and s.startswith("EGCp") for s in saids)
    assert any(s and s.startswith("ECAR") for s in saids)


def test_seed_is_idempotent(tmp_store, monkeypatch):
    monkeypatch.setenv("LOCKSMITH_DESIGNER_SEED_FIXTURES", "1")
    seed_fixtures.maybe_seed(tmp_store)
    first = tmp_store.list_templates()
    seed_fixtures.maybe_seed(tmp_store)
    second = tmp_store.list_templates()
    assert len(first) == len(second) == 2
