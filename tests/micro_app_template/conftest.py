"""Shared fixtures for micro-app-template tests."""
from __future__ import annotations

from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def minimal_valid_template() -> dict:
    """A minimal document that conforms to the meta-schema once it is built.

    Used as the smoke-test seed across validation tests.
    """
    return {
        "d": "#" * 44,
        "spec_version": "micro-app-template/0.1",
        "header": {
            "id": "minimal-test",
            "display_name": "Minimal Test Template",
            "description": "Smallest valid template used as a test fixture.",
            "version": "0.1",
            "expression_language": "UEL/1.0",
        },
        "role": {
            "id": "tester",
            "display_name": "Test Actor",
            "description": "A placeholder role used for fixtures.",
            "kind": "individual",
            "keri_infrastructure": {
                "witness_pool": False,
                "watcher_network": False,
                "mailbox": True,
                "acdc_registry": False,
            },
        },
        "credentials": {"imports": [], "exports": []},
        "commands": [],
        "aggregates": [],
        "reactions": [],
        "workflows": [],
        "projections": [],
        "rules": [],
    }
